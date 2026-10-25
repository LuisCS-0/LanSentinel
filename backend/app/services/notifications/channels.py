"""
Canales de aviso externos: Telegram, ntfy y correo electrónico.

Cada canal se activa solo si su configuración está completa en .env. send()
lanza NotificationError con un mensaje legible si el envío falla, para que
el botón "Enviar prueba" del panel pueda mostrar el motivo.
"""

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import settings

_HTTP_TIMEOUT = 10.0


class NotificationError(Exception):
    """Fallo al enviar un aviso; el mensaje explica el motivo."""


@dataclass
class Notification:
    title: str
    body: str
    severity: str          # info | low | medium | high | critical
    url: str | None = None


class Channel:
    name: str = ""
    label: str = ""

    def is_configured(self) -> bool:
        raise NotImplementedError

    async def send(self, notification: Notification) -> None:
        raise NotImplementedError


# ── Telegram ─────────────────────────────────────────────────────────────────

class TelegramChannel(Channel):
    """
    Bot de Telegram. Se crea con @BotFather (da el token); el chat_id es el
    del usuario o grupo al que el bot debe escribir (hay que haberle hablado
    antes al bot para que pueda hacerlo).
    """
    name = "telegram"
    label = "Telegram"

    def is_configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)

    async def send(self, notification: Notification) -> None:
        text = f"{notification.title}\n\n{notification.body}"
        if notification.url:
            text += f"\n\n{notification.url}"
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(url, json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": text[:4000],   # límite de Telegram: 4096 caracteres
                    "disable_web_page_preview": True,
                })
        except httpx.HTTPError as exc:
            raise NotificationError(f"No se pudo contactar con Telegram: {exc}") from exc
        if response.status_code != 200:
            # Telegram explica el error en "description" (token o chat_id incorrectos...)
            try:
                detail = response.json().get("description", response.text)
            except ValueError:
                detail = response.text
            raise NotificationError(f"Telegram respondió {response.status_code}: {detail}")


# ── ntfy ─────────────────────────────────────────────────────────────────────

_NTFY_PRIORITY = {"info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
_NTFY_TAGS = {
    "info": ["information_source"],
    "low": ["large_blue_circle"],
    "medium": ["warning"],
    "high": ["warning"],
    "critical": ["rotating_light"],
}


class NtfyChannel(Channel):
    """
    ntfy (https://ntfy.sh o un servidor propio): la app del móvil se suscribe
    a un tema y recibe notificaciones push. Cualquiera que conozca el nombre
    del tema puede leerlo, así que conviene un nombre largo y difícil de
    adivinar, o un servidor propio con token.
    """
    name = "ntfy"
    label = "ntfy"

    def is_configured(self) -> bool:
        return bool(settings.NTFY_SERVER and settings.NTFY_TOPIC)

    async def send(self, notification: Notification) -> None:
        # Publicación en JSON: permite títulos con tildes (en cabeceras HTTP no)
        payload = {
            "topic": settings.NTFY_TOPIC,
            "title": notification.title,
            "message": notification.body,
            "priority": _NTFY_PRIORITY.get(notification.severity, 3),
            "tags": _NTFY_TAGS.get(notification.severity, []),
        }
        if notification.url:
            payload["click"] = notification.url
        headers = {}
        if settings.NTFY_TOKEN:
            headers["Authorization"] = f"Bearer {settings.NTFY_TOKEN}"
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.post(settings.NTFY_SERVER.rstrip("/"), json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise NotificationError(f"No se pudo contactar con ntfy: {exc}") from exc
        if response.status_code >= 300:
            raise NotificationError(f"ntfy respondió {response.status_code}: {response.text[:200]}")


# ── Correo ───────────────────────────────────────────────────────────────────

class EmailChannel(Channel):
    name = "email"
    label = "Correo electrónico"

    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM and self._recipients())

    @staticmethod
    def _recipients() -> list[str]:
        return [r.strip() for r in settings.SMTP_TO.split(",") if r.strip()]

    async def send(self, notification: Notification) -> None:
        message = EmailMessage()
        message["Subject"] = f"[LanSentinel] {notification.title}"
        message["From"] = settings.SMTP_FROM
        message["To"] = ", ".join(self._recipients())
        body = notification.body
        if notification.url:
            body += f"\n\nAbrir el panel: {notification.url}"
        message.set_content(body)
        # smtplib es síncrono: se ejecuta en un hilo para no bloquear el backend
        await asyncio.get_running_loop().run_in_executor(None, self._send_sync, message)

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        security = settings.SMTP_SECURITY.lower()
        context = ssl.create_default_context()
        try:
            if security == "ssl":
                smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_HTTP_TIMEOUT, context=context)
            else:
                smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_HTTP_TIMEOUT)
            with smtp:
                if security == "starttls":
                    smtp.starttls(context=context)
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotificationError("El servidor de correo rechazó el usuario o la contraseña") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"Error al enviar el correo: {exc}") from exc


CHANNELS: list[Channel] = [TelegramChannel(), NtfyChannel(), EmailChannel()]
