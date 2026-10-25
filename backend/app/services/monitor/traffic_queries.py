"""
Consultas sobre el histórico de tráfico (network_usage_hourly).

Rangos disponibles y tamaño de cada tramo de la gráfica:
  24h → por horas (24 tramos)      30d → por días (30 tramos)
  7d  → por horas (168 tramos)     1y  → por meses (12 tramos)

Los tramos se calculan en la zona horaria local (TIMEZONE), de modo que "un
día" va de 00:00 a 00:00 hora española y no UTC. Los tramos sin tráfico se
devuelven a cero para que la gráfica no tenga huecos.

Los datos salen de la tabla por horas, que se recalcula cada 5 minutos: la
hora en curso puede ir hasta 5 minutos por detrás del tráfico en vivo.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.device import Device
from app.models.traffic import NetworkUsageHourly

TrafficRange = Literal["24h", "7d", "30d", "1y"]
Unit = Literal["hour", "day", "month"]

# rango → (unidad del tramo, número de tramos)
RANGES: dict[str, tuple[Unit, int]] = {
    "24h": ("hour", 24),
    "7d": ("hour", 24 * 7),
    "30d": ("day", 30),
    "1y": ("month", 12),
}


@dataclass
class Bucket:
    start: datetime          # inicio del tramo, con zona horaria local
    bytes_sent: int = 0      # subida
    bytes_recv: int = 0      # descarga


# ── Tramos (funciones puras) ─────────────────────────────────────────────────

def _truncate(local: datetime, unit: Unit) -> datetime:
    if unit == "hour":
        return local.replace(minute=0, second=0, microsecond=0)
    if unit == "day":
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _step(local: datetime, unit: Unit, n: int) -> datetime:
    """Avanza (n > 0) o retrocede (n < 0) n tramos en hora local."""
    if unit == "hour":
        return local + timedelta(hours=n)
    if unit == "day":
        return local + timedelta(days=n)
    month_index = local.year * 12 + (local.month - 1) + n
    return local.replace(year=month_index // 12, month=month_index % 12 + 1)


def bucket_starts(range_key: str, now: datetime, tz: ZoneInfo) -> list[datetime]:
    """
    Inicios de los tramos del rango, en hora local sin zona (naive), del más
    antiguo al actual. El último tramo es el que contiene `now`.
    """
    unit, count = RANGES[range_key]
    current = _truncate(now.astimezone(tz).replace(tzinfo=None), unit)
    first = _step(current, unit, -(count - 1))
    return [_step(first, unit, i) for i in range(count)]


def fill_buckets(
    starts: list[datetime], rows: dict[datetime, tuple[int, int]], tz: ZoneInfo,
) -> list[Bucket]:
    """Une los tramos esperados con los que tienen datos; el resto, a cero."""
    buckets = []
    for start in starts:
        sent, recv = rows.get(start, (0, 0))
        buckets.append(Bucket(start=start.replace(tzinfo=tz), bytes_sent=sent, bytes_recv=recv))
    return buckets


def range_start_utc(range_key: str, now: datetime, tz: ZoneInfo) -> datetime:
    """Inicio del rango en UTC, para filtrar la tabla por horas."""
    first_local = bucket_starts(range_key, now, tz)[0]
    return first_local.replace(tzinfo=tz).astimezone(timezone.utc)


# ── Consultas ────────────────────────────────────────────────────────────────

async def usage_series(
    db: AsyncSession, range_key: str, device_id: UUID | None = None,
) -> tuple[Unit, list[Bucket]]:
    """Serie de consumo del rango: de toda la red o de un dispositivo."""
    tz = ZoneInfo(settings.TIMEZONE)
    unit, _ = RANGES[range_key]
    now = datetime.now(timezone.utc)
    starts = bucket_starts(range_key, now, tz)

    # date_trunc sobre la hora local (AT TIME ZONE) → inicio del tramo local
    sql = """
        SELECT date_trunc(:unit, hour AT TIME ZONE :tz) AS bucket,
               SUM(bytes_sent) AS sent, SUM(bytes_recv) AS recv
        FROM network_usage_hourly
        WHERE hour >= :since
    """
    params = {"unit": unit, "tz": settings.TIMEZONE, "since": range_start_utc(range_key, now, tz)}
    if device_id:
        sql += " AND device_id = :device_id"
        params["device_id"] = device_id
    sql += " GROUP BY bucket"

    result = await db.execute(text(sql), params)
    rows = {bucket: (int(sent or 0), int(recv or 0)) for bucket, sent, recv in result.all()}
    return unit, fill_buckets(starts, rows, tz)


async def device_totals(db: AsyncSession, range_key: str) -> list[dict]:
    """
    Consumo total de cada dispositivo en el rango, de mayor a menor. Incluye
    a cero los dispositivos vistos en el rango que no han generado tráfico
    medido, para que el ranking muestre también los que menos consumen.
    """
    tz = ZoneInfo(settings.TIMEZONE)
    since = range_start_utc(range_key, datetime.now(timezone.utc), tz)

    totals_q = await db.execute(
        select(
            NetworkUsageHourly.device_id,
            func.sum(NetworkUsageHourly.bytes_sent),
            func.sum(NetworkUsageHourly.bytes_recv),
        )
        .where(NetworkUsageHourly.hour >= since)
        .group_by(NetworkUsageHourly.device_id)
    )
    totals = {device_id: (int(sent or 0), int(recv or 0)) for device_id, sent, recv in totals_q.all()}

    devices_q = await db.execute(
        select(Device).where((Device.last_seen >= since) | (Device.id.in_(list(totals) or [None])))
    )
    result = []
    for device in devices_q.scalars().all():
        sent, recv = totals.get(device.id, (0, 0))
        result.append({
            "device_id": device.id,
            "mac": device.mac,
            "ip": device.ip,
            "hostname": device.hostname,
            "vendor": device.vendor,
            "bytes_sent": sent,
            "bytes_recv": recv,
            "total_bytes": sent + recv,
        })
    result.sort(key=lambda d: d["total_bytes"], reverse=True)
    return result
