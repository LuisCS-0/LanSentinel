"""
Avisos de alertas por canales externos (Telegram, ntfy, correo).

El notificador se suscribe al bus de eventos y, por cada alerta NUEVA con
severidad mayor o igual que NOTIFY_MIN_SEVERITY, envía un aviso a todos los
canales configurados. Las repeticiones agrupadas (alert.updated) no avisan
de nuevo: con la agrupación de alertas, un ataque continuado genera un solo
aviso.

Protección frente a avalanchas: como máximo NOTIFY_MAX_PER_HOUR avisos en
una ventana de una hora. Los que superan el límite no se envían; cuando
vuelve a haber hueco, el siguiente aviso va precedido de un resumen con
cuántos se omitieron.

Los envíos se hacen en esta tarea en segundo plano: un canal lento o caído
nunca retrasa la detección ni el registro de alertas.
"""

import asyncio
import time
from collections import deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.services.events.broker import event_broker
from app.services.notifications.channels import CHANNELS, Channel, Notification, NotificationError

log = structlog.get_logger(__name__)

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]
SEVERITY_LABEL = {
    "info": "⚪ Informativa",
    "low": "🔵 Baja",
    "medium": "🟡 Media",
    "high": "🟠 Alta",
    "critical": "🔴 Crítica",
}
_SOURCE_LABEL = {
    "suricata": "detección de intrusiones (Suricata)",
    "monitor": "monitor de dispositivos",
    "firewall": "cortafuegos",
    "system": "sistema",
}
_RATE_WINDOW_SECONDS = 3600


def severity_at_least(severity: str, minimum: str) -> bool:
    try:
        return SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index(minimum)
    except ValueError:
        return False


def panel_url(path: str) -> str | None:
    base = settings.PANEL_URL.strip().rstrip("/")
    return f"{base}{path}" if base else None


class Notifier:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._sent_at: deque[float] = deque()
        self._suppressed = 0
        # Estado por canal para el panel: último envío y último error
        self.last_sent_at: dict[str, str] = {}
        self.last_error: dict[str, str] = {}

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    def start(self) -> None:
        configured = [c.name for c in CHANNELS if c.is_configured()]
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="notifier")
        log.info("notifier.started", channels=configured, min_severity=settings.NOTIFY_MIN_SEVERITY)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        with event_broker.subscribe() as queue:
            while True:
                event = await queue.get()
                if event["type"] != "alert.created":
                    continue
                try:
                    await self.handle_alert(event["data"])
                except Exception as exc:
                    log.error("notifier.handle_error", error=str(exc), exc_info=True)

    # ── Lógica ──────────────────────────────────────────────────────────────

    def _channels(self) -> list[Channel]:
        return [c for c in CHANNELS if c.is_configured()]

    def _take_rate_slot(self) -> bool:
        """True si queda hueco en la ventana de una hora (y lo reserva)."""
        now = time.monotonic()
        while self._sent_at and now - self._sent_at[0] > _RATE_WINDOW_SECONDS:
            self._sent_at.popleft()
        if len(self._sent_at) >= settings.NOTIFY_MAX_PER_HOUR:
            return False
        self._sent_at.append(now)
        return True

    async def handle_alert(self, alert: dict) -> None:
        channels = self._channels()
        if not channels:
            return
        if not severity_at_least(alert.get("severity", "info"), settings.NOTIFY_MIN_SEVERITY):
            return

        if not self._take_rate_slot():
            self._suppressed += 1
            log.warning("notifier.rate_limited", suppressed=self._suppressed)
            return

        if self._suppressed:
            summary = Notification(
                title="Avisos omitidos",
                body=(
                    f"Se han omitido {self._suppressed} avisos en la última hora por "
                    f"superar el límite de {settings.NOTIFY_MAX_PER_HOUR}. Revisa el "
                    f"panel para ver todas las alertas."
                ),
                severity="medium",
                url=panel_url("/alerts"),
            )
            self._suppressed = 0
            await self._send_all(channels, summary)

        await self._send_all(channels, await self._build(alert))

    async def _build(self, alert: dict) -> Notification:
        severity = alert.get("severity", "info")
        lines = [alert.get("description") or "Sin descripción."]

        device = await self._device_label(alert.get("device_id"))
        if device:
            lines.append(f"Dispositivo: {device}")
        lines.append(f"Detectado por: {_SOURCE_LABEL.get(alert.get('source'), alert.get('source'))}")
        local_now = datetime.now(ZoneInfo(settings.TIMEZONE))
        lines.append(f"Hora: {local_now.strftime('%d/%m/%Y %H:%M:%S')}")

        return Notification(
            title=f"{SEVERITY_LABEL.get(severity, severity)}: {alert.get('title', 'Alerta')}",
            body="\n".join(lines),
            severity=severity,
            url=panel_url("/alerts"),
        )

    @staticmethod
    async def _device_label(device_id: str | None) -> str | None:
        if not device_id:
            return None
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Device).where(Device.id == device_id))
            device = result.scalar_one_or_none()
        if not device:
            return None
        name = device.hostname or device.vendor or device.mac
        return f"{name} ({device.ip or 'sin IP'}, {device.mac})"

    async def _send_all(self, channels: list[Channel], notification: Notification) -> None:
        await asyncio.gather(*(self._send(c, notification) for c in channels))

    async def _send(self, channel: Channel, notification: Notification) -> None:
        """Envía por un canal con un reintento; los fallos se registran, no se propagan."""
        for attempt in (1, 2):
            try:
                await channel.send(notification)
                self.last_sent_at[channel.name] = datetime.now(timezone.utc).isoformat()
                self.last_error.pop(channel.name, None)
                return
            except NotificationError as exc:
                self.last_error[channel.name] = str(exc)
                log.warning("notifier.send_failed", channel=channel.name, attempt=attempt, error=str(exc))
                if attempt == 1:
                    await asyncio.sleep(5)

    # ── API para el panel ───────────────────────────────────────────────────

    async def send_test(self, channel_name: str) -> None:
        """Envía un aviso de prueba por un canal. Lanza NotificationError si falla."""
        channel = next((c for c in CHANNELS if c.name == channel_name), None)
        if channel is None:
            raise NotificationError(f"Canal desconocido: {channel_name}")
        if not channel.is_configured():
            raise NotificationError(f"{channel.label} no está configurado en .env")
        notification = Notification(
            title="Aviso de prueba",
            body="Si recibes este mensaje, LanSentinel puede avisarte por este canal.",
            severity="info",
            url=panel_url("/"),
        )
        try:
            await channel.send(notification)
        except NotificationError as exc:
            self.last_error[channel.name] = str(exc)
            raise
        self.last_sent_at[channel.name] = datetime.now(timezone.utc).isoformat()
        self.last_error.pop(channel.name, None)

    def get_status(self) -> dict:
        return {
            "min_severity": settings.NOTIFY_MIN_SEVERITY,
            "max_per_hour": settings.NOTIFY_MAX_PER_HOUR,
            "panel_url": settings.PANEL_URL or None,
            "channels": [
                {
                    "name": c.name,
                    "label": c.label,
                    "configured": c.is_configured(),
                    "last_sent_at": self.last_sent_at.get(c.name),
                    "last_error": self.last_error.get(c.name),
                }
                for c in CHANNELS
            ],
        }


notifier = Notifier()
