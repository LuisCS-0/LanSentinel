"""
Escaneo periódico de puertos de todos los dispositivos.

Cada pocos minutos busca los dispositivos que:
  - se han visto en las últimas PORT_SCAN_ACTIVE_HOURS horas (están en la red),
  - tienen IP y no están bloqueados (el cortafuegos descarta sus respuestas,
    el escaneo fallaría),
  - no tienen un escaneo completo en las últimas PORT_SCAN_INTERVAL_HOURS.
y los escanea de uno en uno, para no saturar la red ni el propio equipo. El
resultado pasa por la misma comparación que cualquier escaneo completo
(servicios inseguros y puertos nuevos).

PORT_SCAN_INTERVAL_HOURS=0 desactiva el escaneo periódico.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.services.security.port_scanner import scan_and_persist

log = structlog.get_logger(__name__)

_CHECK_EVERY_SECONDS = 600
# Espera inicial: deja que el monitor descubra la red antes del primer escaneo
_STARTUP_DELAY_SECONDS = 300


class ScanScheduler:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self.scanning_ip: str | None = None
        self.last_run_at: datetime | None = None
        self.scans_done = 0

    def start(self) -> None:
        if settings.PORT_SCAN_INTERVAL_HOURS <= 0:
            log.info("scan_scheduler.disabled")
            return
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="scan_scheduler")
            log.info("scan_scheduler.started", interval_hours=settings.PORT_SCAN_INTERVAL_HOURS)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
        while True:
            try:
                await self.run_due_scans()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("scan_scheduler.error", error=str(exc), exc_info=True)
            await asyncio.sleep(_CHECK_EVERY_SECONDS)

    async def due_devices(self) -> list[tuple]:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Device.id, Device.ip)
                .where(
                    Device.ip.is_not(None),
                    Device.is_blocked == False,  # noqa: E712
                    Device.last_seen >= now - timedelta(hours=settings.PORT_SCAN_ACTIVE_HOURS),
                    or_(
                        Device.last_port_scan_at.is_(None),
                        Device.last_port_scan_at < now - timedelta(hours=settings.PORT_SCAN_INTERVAL_HOURS),
                    ),
                )
                # Primero los que nunca se han escaneado
                .order_by(Device.last_port_scan_at.asc().nulls_first())
            )
            return list(result.all())

    async def run_due_scans(self) -> int:
        """Escanea, de uno en uno, los dispositivos a los que les toca."""
        devices = await self.due_devices()
        if not devices:
            return 0
        log.info("scan_scheduler.run", devices=len(devices))
        done = 0
        for device_id, ip in devices:
            self.scanning_ip = ip
            try:
                async with AsyncSessionLocal() as db:
                    result = await scan_and_persist(device_id=device_id, ip=ip, db=db)
                if result.ok:
                    done += 1
            except Exception as exc:
                log.error("scan_scheduler.scan_error", ip=ip, error=str(exc))
            finally:
                self.scanning_ip = None
        self.scans_done += done
        self.last_run_at = datetime.now(timezone.utc)
        return done

    def get_status(self) -> dict:
        return {
            "enabled": settings.PORT_SCAN_INTERVAL_HOURS > 0,
            "interval_hours": settings.PORT_SCAN_INTERVAL_HOURS,
            "scanning_ip": self.scanning_ip,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "scans_done": self.scans_done,
        }


scan_scheduler = ScanScheduler()
