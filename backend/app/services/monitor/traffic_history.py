"""
Histórico de tráfico por dispositivo.

El TrafficMeter mide en memoria; este servicio convierte esas medidas en un
histórico persistente en dos niveles:

  1. network_usage (bruto): cada TRAFFIC_HISTORY_INTERVAL_SECONDS (60 s) se
     recoge el tráfico acumulado por IP, se asocia al dispositivo que tiene
     esa IP y se guarda una fila por dispositivo. Se conserva
     TRAFFIC_RAW_RETENTION_DAYS días.

  2. network_usage_hourly (agregado): cada pocos minutos se recalculan las
     horas recientes sumando las filas en bruto. El recálculo es idempotente
     (INSERT ... ON CONFLICT DO UPDATE con la suma completa de la hora), así
     que repetirlo no duplica nada. Se conserva TRAFFIC_HOURLY_RETENTION_DAYS.

Las gráficas de días, semanas y meses consultan solo la tabla por horas, que
crece muy despacio (una fila por dispositivo y hora).

Al arrancar se recalculan las horas pendientes desde la última agregada, y al
parar se guarda el último tramo, para no perder datos entre reinicios.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, func, insert, select, text

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.models.traffic import NetworkUsage, NetworkUsageHourly
from app.services.monitor.traffic_meter import traffic_meter

log = structlog.get_logger(__name__)

_ROLLUP_EVERY_SECONDS = 300
_PURGE_EVERY_SECONDS = 3600

# Recalcula por horas las filas en bruto desde :since. Se suma la hora entera,
# así que :since debe caer en el inicio de una hora.
_ROLLUP_SQL = text("""
    INSERT INTO network_usage_hourly
        (device_id, hour, bytes_sent, bytes_recv, packets_sent, packets_recv)
    SELECT device_id, date_trunc('hour', recorded_at),
           SUM(bytes_sent), SUM(bytes_recv), SUM(packets_sent), SUM(packets_recv)
    FROM network_usage
    WHERE recorded_at >= :since
    GROUP BY device_id, date_trunc('hour', recorded_at)
    ON CONFLICT (device_id, hour) DO UPDATE SET
        bytes_sent   = EXCLUDED.bytes_sent,
        bytes_recv   = EXCLUDED.bytes_recv,
        packets_sent = EXCLUDED.packets_sent,
        packets_recv = EXCLUDED.packets_recv
""")


def _hour_start(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


class TrafficHistory:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_rollup = 0.0
        self._last_purge = 0.0
        self.last_flush_at: datetime | None = None

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        try:
            await self._catch_up()
        except Exception as exc:
            log.error("traffic_history.catch_up_error", error=str(exc))
        self._task = asyncio.create_task(self._loop(), name="traffic_history_loop")
        log.info("traffic_history.started", interval=settings.TRAFFIC_HISTORY_INTERVAL_SECONDS)

    async def stop(self):
        """Guarda el último tramo y lo agrega antes de parar."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            await self.flush()
            await self.rollup()
        except Exception as exc:
            log.error("traffic_history.stop_error", error=str(exc))
        log.info("traffic_history.stopped")

    async def _loop(self):
        while self._running:
            await asyncio.sleep(settings.TRAFFIC_HISTORY_INTERVAL_SECONDS)
            try:
                await self.flush()
                now = time.monotonic()
                if now - self._last_rollup >= _ROLLUP_EVERY_SECONDS:
                    await self.rollup()
                    self._last_rollup = now
                if now - self._last_purge >= _PURGE_EVERY_SECONDS:
                    await self.purge()
                    self._last_purge = now
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("traffic_history.loop_error", error=str(exc), exc_info=True)

    # ── Operaciones ─────────────────────────────────────────────────────────

    async def flush(self) -> int:
        """
        Guarda en network_usage el tráfico acumulado desde la última vez.
        Cada IP se asigna al dispositivo que la tiene (el visto más
        recientemente, si varios la comparten). Devuelve las filas insertadas.
        """
        pending = traffic_meter.drain_pending()
        if not pending:
            return 0

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Device.id, Device.ip)
                .where(Device.ip.in_(list(pending)))
                .order_by(Device.last_seen.desc())
            )
            device_by_ip: dict[str, object] = {}
            for device_id, ip in result.all():
                device_by_ip.setdefault(ip, device_id)

            rows = [
                {
                    "device_id": device_by_ip[ip],
                    "bytes_sent": c.tx_bytes,
                    "bytes_recv": c.rx_bytes,
                    "packets_sent": c.tx_packets,
                    "packets_recv": c.rx_packets,
                    "recorded_at": now,
                }
                for ip, c in pending.items()
                if ip in device_by_ip
            ]
            if rows:
                await db.execute(insert(NetworkUsage), rows)
                await db.commit()

        unknown = set(pending) - set(device_by_ip)
        if unknown:
            log.debug("traffic_history.unknown_ips", ips=sorted(unknown))
        self.last_flush_at = now
        return len(rows)

    async def rollup(self, since: datetime | None = None) -> None:
        """
        Recalcula network_usage_hourly desde `since` (por defecto, la hora
        anterior a la actual: así la hora que acaba de cerrarse queda completa).
        """
        if since is None:
            since = _hour_start(datetime.now(timezone.utc)) - timedelta(hours=1)
        async with AsyncSessionLocal() as db:
            await db.execute(_ROLLUP_SQL, {"since": _hour_start(since)})
            await db.commit()

    async def purge(self) -> None:
        """Borra los datos que superan su periodo de retención."""
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            raw = await db.execute(
                delete(NetworkUsage).where(
                    NetworkUsage.recorded_at < now - timedelta(days=settings.TRAFFIC_RAW_RETENTION_DAYS)
                )
            )
            hourly = await db.execute(
                delete(NetworkUsageHourly).where(
                    NetworkUsageHourly.hour < now - timedelta(days=settings.TRAFFIC_HOURLY_RETENTION_DAYS)
                )
            )
            await db.commit()
        if raw.rowcount or hourly.rowcount:
            log.info("traffic_history.purged", raw=raw.rowcount, hourly=hourly.rowcount)

    async def _catch_up(self) -> None:
        """
        Al arrancar, agrega las horas que quedaran pendientes (p. ej. si el
        backend se paró sin llegar a hacerlo): desde la última hora agregada
        o, si no hay ninguna, desde el inicio de los datos en bruto.
        """
        async with AsyncSessionLocal() as db:
            last_hour = (await db.execute(select(func.max(NetworkUsageHourly.hour)))).scalar()
            if last_hour is None:
                last_hour = (await db.execute(select(func.min(NetworkUsage.recorded_at)))).scalar()
        if last_hour is not None:
            await self.rollup(since=last_hour)
            log.info("traffic_history.caught_up", since=last_hour.isoformat())


traffic_history = TrafficHistory()
