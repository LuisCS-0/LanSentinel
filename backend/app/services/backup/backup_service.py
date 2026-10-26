"""
Copias de seguridad automáticas.

Cada 10 minutos comprueba si toca copia (archive.is_due): la inicial en
cuanto el backend lleva un rato en marcha y no hay ninguna, y luego una al
día a partir de BACKUP_HOUR (si el equipo estaba apagado a esa hora, se
hace al volver). Tras un fallo espera una hora antes de reintentar.

Avisa con una alerta si una copia falla y si la última correcta tiene más
de dos días (p. ej. el disco de las copias se ha llenado o desconectado).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import AlertSeverity, AlertSource
from app.services.alerts.alert_service import create_alert
from app.services.backup import archive
from app.services.backup.archive import BackupError, BackupFile

log = structlog.get_logger(__name__)

_CHECK_EVERY_SECONDS = 600
# Espera inicial: que el arranque (migraciones, primer escaneo) no coincida con la copia
_STARTUP_DELAY_SECONDS = 300
_RETRY_AFTER = timedelta(hours=1)
STALE_AFTER = timedelta(days=2)


class BackupService:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._retry_at: datetime | None = None
        self._stale_alerted_for: str | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def run(self, motivo: str) -> BackupFile:
        """Hace una copia ya (en un hilo: pg_dump y el comprimido bloquean)."""
        backup = await asyncio.to_thread(archive.create_backup, motivo)
        log.info("backup.created", name=backup.name, size=backup.size, motivo=motivo)
        return backup

    async def _loop(self) -> None:
        await asyncio.sleep(_STARTUP_DELAY_SECONDS)
        while True:
            try:
                await self._tick()
            except Exception as exc:
                log.error("backup.tick_failed", error=str(exc))
            await asyncio.sleep(_CHECK_EVERY_SECONDS)

    async def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        backups = archive.list_backups()
        motivo = archive.is_due(now.astimezone(ZoneInfo(settings.TIMEZONE)), settings.BACKUP_HOUR, backups)
        if motivo and not (self._retry_at and now < self._retry_at):
            try:
                await self.run(motivo)
                self._retry_at = None
            except archive.BackupBusy:
                pass
            except BackupError as exc:
                self._retry_at = now + _RETRY_AFTER
                log.error("backup.failed", error=str(exc))
                await self._alert(
                    AlertSeverity.high, "Ha fallado la copia de seguridad",
                    f"{exc}. Se volverá a intentar en una hora.", "backup_failed",
                )
        if settings.BACKUP_HOUR >= 0:
            await self._check_stale(now)

    async def _check_stale(self, now: datetime) -> None:
        last = archive.read_status().get("last_success_at")
        if not last:
            return
        if now - datetime.fromisoformat(last) > STALE_AFTER and self._stale_alerted_for != last:
            self._stale_alerted_for = last
            await self._alert(
                AlertSeverity.medium, "No hay copias de seguridad recientes",
                "La última copia correcta tiene más de dos días. Revisa en Ajustes → Copias de seguridad "
                "por qué fallan (espacio en disco, disco de las copias desconectado...).",
                "backup_stale",
            )

    async def _alert(self, severity: AlertSeverity, title: str, description: str, fingerprint: str) -> None:
        async with AsyncSessionLocal() as db:
            await create_alert(
                db, severity=severity, source=AlertSource.system,
                title=title, description=description, fingerprint=fingerprint,
            )

    def status(self) -> dict:
        backups = archive.list_backups()
        st = archive.read_status()
        now_local = datetime.now(ZoneInfo(settings.TIMEZONE))
        next_at = None
        if settings.BACKUP_HOUR >= 0:
            if archive.is_due(now_local, settings.BACKUP_HOUR, backups):
                next_at = now_local     # en la próxima comprobación (como mucho 10 min)
            else:
                next_at = now_local.replace(hour=settings.BACKUP_HOUR, minute=0, second=0, microsecond=0)
                if next_at <= now_local:
                    next_at += timedelta(days=1)
            next_at = next_at.astimezone(timezone.utc)
        return {
            "enabled": settings.BACKUP_HOUR >= 0,
            "hour": settings.BACKUP_HOUR,
            "keep_daily": settings.BACKUP_KEEP_DAILY,
            "keep_weekly": settings.BACKUP_KEEP_WEEKLY,
            "location": settings.BACKUP_PATH or str(archive.BACKUP_DIR),
            "running": archive.is_running(),
            "next_at": next_at,
            "last_success_at": st.get("last_success_at"),
            "last_error": st.get("last_error"),
            "last_error_at": st.get("last_error_at"),
            "backups": [
                {"name": b.name, "created_at": b.created_at, "motivo": b.motivo, "size": b.size}
                for b in backups
            ],
        }


backup_service = BackupService()
