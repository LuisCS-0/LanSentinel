"""
Servicio de seguridad — orquestador del módulo.

Arranca el SuricataReader como tarea background al iniciar FastAPI,
de la misma manera que MonitorService gestiona el bucle de monitorización.
Cada evento de Suricata se entrega al threat_classifier para su persistencia.
"""

import asyncio
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.security.suricata_reader import SuricataReader
from app.services.security.threat_classifier import classify_and_persist

log = structlog.get_logger(__name__)


class SecurityService:
    """Singleton que gestiona el ciclo de vida del lector de Suricata."""

    def __init__(self):
        self._reader = SuricataReader(eve_path=settings.SURICATA_LOG_PATH)
        self._task: asyncio.Task | None = None
        self._running: bool = False

        # Estado expuesto a la API
        self.events_processed: int = 0
        self.alerts_generated: int = 0
        self.last_event_at: datetime | None = None

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            log.warning("security_service.already_running")
            return
        self._running = True
        self._task = asyncio.create_task(
            self._reader.run(self._handle_event),
            name="suricata_reader_loop",
        )
        log.info("security_service.started", path=settings.SURICATA_LOG_PATH)

    async def stop(self):
        self._running = False
        self._reader.stop()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("security_service.stopped")

    # ── Handler de eventos ────────────────────────────────────────────────────

    async def _handle_event(self, event: dict):
        """Callback que recibe cada evento parseado del eve.json."""
        self.events_processed += 1
        self.last_event_at = datetime.now(timezone.utc)

        # Solo persistimos los eventos de tipo 'alert'.
        # Otros eventos (flow, dns, http) se descartan en esta versión.
        if event.get("event_type") != "alert":
            return

        try:
            async with AsyncSessionLocal() as db:
                alert = await classify_and_persist(event, db)
                if alert:
                    self.alerts_generated += 1
        except Exception as exc:
            log.error("security_service.handler_error", error=str(exc))

    # ── API pública ───────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running":          self._running,
            "eve_path":         settings.SURICATA_LOG_PATH,
            "events_processed": self.events_processed,
            "alerts_generated": self.alerts_generated,
            "last_event_at":    self.last_event_at.isoformat()
                                if self.last_event_at else None,
        }


# Singleton importable desde main.py
security_service = SecurityService()
