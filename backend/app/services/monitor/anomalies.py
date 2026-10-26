"""
Anomalías de tráfico: picos de consumo respecto a lo habitual de cada dispositivo.

Cada dispositivo tiene su patrón: una cámara sube poco y siempre parecido; un
portátil, de todo. Al terminar cada hora se compara lo que ha subido y bajado
cada dispositivo con sus horas de actividad de las últimas
ANOMALY_BASELINE_DAYS (network_usage_hourly). Es un pico si supera a la vez:

  - ANOMALY_FACTOR veces lo habitual (la mediana),
  - lo habitual más 6 desviaciones (robustas: MAD), para no saltar en
    dispositivos que ya varían mucho,
  - un mínimo absoluto (ANOMALY_UPLOAD_MIN_MB / ANOMALY_DOWNLOAD_MIN_MB), para
    no avisar de "subió 3 MB en vez de 200 kB".

La subida es lo que interesa: un dispositivo que de repente envía mucho más
de lo normal puede estar sacando datos o atacando a otros (botnet). La
descarga solo avisa con picos muy grandes y con severidad baja (suelen ser
actualizaciones o vídeo). Hacen falta ANOMALY_MIN_HISTORY_HOURS horas con
actividad antes de juzgar un dispositivo: un dispositivo nuevo aún no tiene
patrón.
"""

import asyncio
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import AlertSeverity, AlertSource
from app.models.device import Device
from app.models.traffic import NetworkUsageHourly
from app.services.alerts.alert_service import create_alert

log = structlog.get_logger(__name__)

MB = 1024 * 1024
DEVIATIONS = 6
_CHECK_EVERY_SECONDS = 300
# El agregado por horas se recalcula cada 5 minutos: se deja margen para que
# la hora terminada esté completa antes de juzgarla
_HOUR_SETTLE = timedelta(minutes=10)


@dataclass(frozen=True)
class Baseline:
    """Lo habitual de un dispositivo en una dirección, por hora con actividad."""
    samples: int
    median: float
    mad: float           # desviación absoluta mediana
    p95: float


# ── Funciones puras ──────────────────────────────────────────────────────────

def baseline(values: list[int], min_samples: int) -> Baseline | None:
    if len(values) < max(min_samples, 1):
        return None
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return Baseline(samples=len(values), median=median, mad=mad, p95=p95)


def threshold(b: Baseline, factor: float, min_bytes: int) -> float:
    """Bytes por hora a partir de los que es un pico."""
    sigma = 1.4826 * b.mad      # MAD → desviación típica equivalente
    return max(min_bytes, factor * b.median, b.median + DEVIATIONS * sigma)


def is_spike(value: int, b: Baseline | None, factor: float, min_bytes: int) -> bool:
    return b is not None and value > threshold(b, factor, min_bytes)


def human(n: float) -> str:
    for unit, size in (("GB", 1024 ** 3), ("MB", MB), ("kB", 1024)):
        if n >= size:
            return f"{n / size:.1f} {unit}".replace(".", ",")
    return f"{int(n)} B"


def describe(direction: str, value: int, b: Baseline, start_local: datetime) -> str:
    verb = "Ha subido" if direction == "upload" else "Ha descargado"
    end_local = start_local + timedelta(hours=1)
    text = (
        f"{verb} {human(value)} entre las {start_local:%H:%M} y las {end_local:%H:%M}, cuando lo "
        f"habitual son unos {human(b.median)} por hora (el 95 % de sus horas, menos de {human(b.p95)})."
    )
    if direction == "upload":
        text += (" Puede ser una copia de seguridad en la nube o una subida de fotos o vídeos; si no lo "
                 "esperas, puede ser un programa enviando datos o atacando a otros equipos.")
    else:
        text += " Suele ser una actualización o vídeo; revísalo si el dispositivo no debería hacerlo."
    return text


# ── Servicio ─────────────────────────────────────────────────────────────────

class AnomalyService:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._last_hour: datetime | None = None
        self.last_checked_at: datetime | None = None
        self.anomalies_found = 0

    def start(self) -> None:
        if settings.ANOMALY_DETECTION_ENABLED:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                now = datetime.now(timezone.utc)
                hour = (now - _HOUR_SETTLE).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
                if hour != self._last_hour:
                    await self.check_hour(hour)
                    self._last_hour = hour
            except Exception as exc:
                log.error("anomalies.check_failed", error=str(exc))
            await asyncio.sleep(_CHECK_EVERY_SECONDS)

    async def check_hour(self, hour: datetime) -> int:
        """Compara la hora `hour` (UTC, inicio) con lo habitual. Devuelve los picos encontrados."""
        since = hour - timedelta(days=settings.ANOMALY_BASELINE_DAYS)
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(NetworkUsageHourly).where(NetworkUsageHourly.hour >= since, NetworkUsageHourly.hour <= hour)
            )).scalars().all()
            devices = {d.id: d for d in (await db.execute(select(Device))).scalars().all()}

        history: dict[UUID, list[NetworkUsageHourly]] = {}
        current: dict[UUID, NetworkUsageHourly] = {}
        for r in rows:
            if r.hour == hour:
                current[r.device_id] = r
            elif r.bytes_sent or r.bytes_recv:
                history.setdefault(r.device_id, []).append(r)

        found = 0
        for device_id, row in current.items():
            past = history.get(device_id, [])
            checks = (
                ("upload", row.bytes_sent, [p.bytes_sent for p in past],
                 settings.ANOMALY_UPLOAD_MIN_MB * MB, AlertSeverity.medium),
                ("download", row.bytes_recv, [p.bytes_recv for p in past],
                 settings.ANOMALY_DOWNLOAD_MIN_MB * MB, AlertSeverity.low),
            )
            for direction, value, values, min_bytes, severity in checks:
                b = baseline(values, settings.ANOMALY_MIN_HISTORY_HOURS)
                if is_spike(value, b, settings.ANOMALY_FACTOR, min_bytes):
                    found += 1
                    await self._alert(devices.get(device_id), device_id, direction, value, b, hour, severity)
        self.last_checked_at = datetime.now(timezone.utc)
        self.anomalies_found += found
        return found

    async def _alert(self, device: Device | None, device_id: UUID, direction: str, value: int,
                     b: Baseline, hour: datetime, severity: AlertSeverity) -> None:
        name = (device.hostname or device.vendor or device.ip) if device else "Un dispositivo"
        what = "Subida" if direction == "upload" else "Descarga"
        local = hour.astimezone(ZoneInfo(settings.TIMEZONE))
        async with AsyncSessionLocal() as db:
            await create_alert(
                db,
                device_id=device_id,
                severity=severity,
                source=AlertSource.monitor,
                title=f"{what} inusual: {name}",
                description=describe(direction, value, b, local),
                raw_payload={
                    "direction": direction, "hour": hour.isoformat(), "bytes": value,
                    "median": b.median, "p95": b.p95, "samples": b.samples,
                },
                fingerprint=f"anomaly:{direction}:{device_id}",
            )
        log.warning("anomalies.spike", device=str(device_id), direction=direction, bytes=value, median=b.median)

    async def profile(self, device_id: UUID) -> dict:
        """Lo habitual de un dispositivo, para el panel."""
        since = datetime.now(timezone.utc) - timedelta(days=settings.ANOMALY_BASELINE_DAYS)
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(NetworkUsageHourly).where(
                    NetworkUsageHourly.device_id == device_id, NetworkUsageHourly.hour >= since,
                )
            )).scalars().all()
        active = [r for r in rows if r.bytes_sent or r.bytes_recv]

        def summary(values: list[int], min_mb: int) -> dict | None:
            b = baseline(values, 1)
            if b is None:
                return None
            return {"median": b.median, "p95": b.p95,
                    "threshold": threshold(b, settings.ANOMALY_FACTOR, min_mb * MB)}

        return {
            "enabled": settings.ANOMALY_DETECTION_ENABLED,
            "days": settings.ANOMALY_BASELINE_DAYS,
            "active_hours": len(active),
            "min_hours": settings.ANOMALY_MIN_HISTORY_HOURS,
            "upload": summary([r.bytes_sent for r in active], settings.ANOMALY_UPLOAD_MIN_MB),
            "download": summary([r.bytes_recv for r in active], settings.ANOMALY_DOWNLOAD_MIN_MB),
        }


anomaly_service = AnomalyService()
