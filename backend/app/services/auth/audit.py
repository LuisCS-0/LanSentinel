"""
Registro de acciones: quién cambió qué, desde dónde y con qué resultado.

Un middleware ASGI mira cada petición a la API que cambia algo (todo lo que
no es GET, más las descargas de copias, que contienen secretos) y, cuando
termina, guarda una fila en audit_log con:

  - el usuario (lo deja get_current_user en request.state; en un login
    fallido, el nombre que se intentó),
  - la IP real del cliente (X-Real-IP del nginx, como el límite de login),
  - una descripción legible ("Bloquear dispositivo") y el objetivo
    ("portatil-luis (192.168.56.20)"),
  - el código de respuesta (403 si un usuario de solo lectura lo intentó),
  - el cuerpo de la petición, sin contraseñas, tokens ni secretos.

Las peticiones sin sesión (salvo el login) no se guardan: un 401 de algo que
ni siquiera ha iniciado sesión es ruido. Las filas se borran a los
AUDIT_LOG_DAYS días. Nada en la API permite borrarlas a mano.
"""

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.audit import AuditEntry
from app.models.device import Device
from app.models.firewall_rule import FirewallRule
from app.models.user import User
from app.services.auth.login_guard import client_ip

log = structlog.get_logger(__name__)

API_PREFIX = "/api/v1"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MAX_BODY = 4096                     # lo que se guarda del cuerpo, como mucho
PURGE_EVERY = timedelta(hours=24)
REDACTED = "***"

# Claves cuyo valor nunca se guarda (password, new_password, token, secret...)
_SECRET_KEY = re.compile(r"pass|token|secret|key|credential", re.IGNORECASE)

# (método, ruta sin el prefijo /api/v1) → descripción
ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/auth/login"): "Inicio de sesión",
    ("POST", "/auth/token"): "Inicio de sesión (token)",
    ("POST", "/auth/logout"): "Cierre de sesión",
    ("POST", "/auth/password"): "Cambiar su contraseña",
    ("PATCH", "/alerts/{alert_id}"): "Cambiar estado de alerta",
    ("POST", "/network/scan"): "Escanear la red",
    ("POST", "/system/notifications/test"): "Enviar aviso de prueba",
    ("POST", "/system/backups"): "Hacer copia de seguridad",
    ("GET", "/system/backups/{name}"): "Descargar copia de seguridad",
    ("POST", "/firewall/block"): "Bloquear IP",
    ("DELETE", "/firewall/rules/{rule_id}"): "Quitar regla del cortafuegos",
    ("PUT", "/firewall/quarantine"): "Cambiar modo cuarentena",
    ("PUT", "/firewall/router"): "Cambiar modo router",
    ("PATCH", "/devices/{device_id}"): "Editar dispositivo",
    ("POST", "/devices/{device_id}/trust"): "Marcar como de confianza",
    ("DELETE", "/devices/{device_id}/trust"): "Quitar de confianza",
    ("POST", "/devices/{device_id}/block"): "Bloquear dispositivo",
    ("DELETE", "/devices/{device_id}/block"): "Desbloquear dispositivo",
    ("POST", "/security/devices/{device_id}/scan"): "Escanear puertos",
    ("POST", "/security/threat-intel/update"): "Actualizar listas de amenazas",
    ("POST", "/users"): "Crear usuario",
    ("PATCH", "/users/{user_id}"): "Editar usuario",
    ("POST", "/users/{user_id}/password"): "Cambiar contraseña de otro usuario",
    ("DELETE", "/users/{user_id}"): "Borrar usuario",
    ("POST", "/ai-audit/run"): "Lanzar auditoría con IA",
    ("POST", "/ai-audit/check"): "Probar el proveedor de IA",
    ("PUT", "/ai-audit/reports/{audit_id}/findings/{index}"): "Marcar hallazgo de la auditoría con IA",
    ("PUT", "/ai-audit/reports/{audit_id}/actions/{index}"): "Marcar acción del plan de la auditoría con IA",
    ("DELETE", "/ai-audit/reports/{audit_id}"): "Borrar auditoría con IA",
    ("PUT", "/config"): "Cambiar ajustes",
}

# GET que también se registran: descargan secretos
AUDITED_GETS = {route for method, route in ACTIONS if method == "GET"}

# Rutas en las que no hay sesión todavía, pero se registran igual
LOGIN_ROUTES = {"/auth/login", "/auth/token"}


# ── Funciones puras ──────────────────────────────────────────────────────────

def should_audit(method: str, route: str | None) -> bool:
    """Si una petición (ruta ya resuelta, sin prefijo) se registra."""
    if route is None:
        return False
    if method in SAFE_METHODS:
        return method == "GET" and route in AUDITED_GETS
    return True


def describe(method: str, route: str) -> str:
    return ACTIONS.get((method, route), f"{method} {route}")


def sanitize(value):
    """Copia del cuerpo sin los valores de claves que parecen secretos."""
    if isinstance(value, dict):
        return {k: REDACTED if _SECRET_KEY.search(str(k)) else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def parse_body(raw: bytes, content_type: str) -> dict | list | None:
    """Cuerpo JSON o de formulario, ya sin secretos; None si no hay o no se entiende."""
    if not raw:
        return None
    if len(raw) > MAX_BODY:
        return {"_omitido": f"{len(raw)} bytes"}
    try:
        if "application/json" in content_type:
            return sanitize(json.loads(raw))
        if "application/x-www-form-urlencoded" in content_type:
            from urllib.parse import parse_qsl
            return sanitize(dict(parse_qsl(raw.decode(), keep_blank_values=True)))
    except (ValueError, UnicodeDecodeError):
        return {"_omitido": "no se pudo leer"}
    return None


def route_of(scope: Scope) -> str | None:
    """Plantilla de la ruta ("/devices/{device_id}/block"), sin el prefijo de la API."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if not path or not path.startswith(API_PREFIX):
        return None
    return path[len(API_PREFIX):].rstrip("/") or "/"


# ── Escritura y lectura ──────────────────────────────────────────────────────

class AuditLog:

    def __init__(self):
        self._last_purge: datetime | None = None

    async def record(self, *, username: str | None, ip: str | None, method: str, path: str,
                     route: str, status_code: int, path_params: dict, body,
                     target: str | None = None) -> None:
        details = {}
        if path_params:
            details["params"] = {k: str(v) for k, v in path_params.items()}
        if body is not None:
            details["body"] = body
        async with AsyncSessionLocal() as db:
            # Una ruta que borra algo deja el nombre en request.state.audit_target
            target = target or await self._target(db, path_params, body)
            db.add(AuditEntry(
                username=username, ip=ip, method=method, path=path[:255],
                action=describe(method, route)[:128], target=target[:255] if target else None,
                status_code=status_code, details=details or None,
            ))
            await db.commit()
        await self._maybe_purge()

    @staticmethod
    async def _target(db, params: dict, body) -> str | None:
        """Lo que se ha tocado, con nombre: así se entiende aunque luego cambie."""
        try:
            if "device_id" in params:
                device = await db.get(Device, uuid.UUID(str(params["device_id"])))
                if device:
                    name = device.hostname or device.vendor or device.mac
                    return f"{name} ({device.ip})" if device.ip else name
            if "user_id" in params:
                user = await db.get(User, int(params["user_id"]))
                return user.username if user else f"usuario {params['user_id']}"
            if "rule_id" in params:
                rule = await db.get(FirewallRule, int(params["rule_id"]))
                return f"regla {rule.id}: {rule.src_ip or rule.dst_ip or rule.name}" if rule else f"regla {params['rule_id']}"
            if "alert_id" in params:
                alert = await db.get(Alert, int(params["alert_id"]))
                return f"alerta {alert.id}: {alert.title}" if alert else f"alerta {params['alert_id']}"
            if "name" in params:
                return str(params["name"])
        except (ValueError, TypeError):
            return None
        if isinstance(body, dict):
            for key in ("ip", "username", "channel"):
                if body.get(key):
                    return str(body[key])
        return None

    async def _maybe_purge(self) -> None:
        now = datetime.now(timezone.utc)
        if self._last_purge and now - self._last_purge < PURGE_EVERY:
            return
        self._last_purge = now
        async with AsyncSessionLocal() as db:
            await db.execute(delete(AuditEntry).where(
                AuditEntry.created_at < now - timedelta(days=settings.AUDIT_LOG_DAYS)))
            await db.commit()

    async def list(self, limit: int, before_id: int | None = None, username: str | None = None,
                   only_failed: bool = False) -> list[AuditEntry]:
        query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
        if before_id:
            query = query.where(AuditEntry.id < before_id)
        if username:
            query = query.where(AuditEntry.username == username)
        if only_failed:
            query = query.where(AuditEntry.status_code >= 400)
        async with AsyncSessionLocal() as db:
            return list((await db.execute(query)).scalars().all())


audit_log = AuditLog()


# ── Middleware ───────────────────────────────────────────────────────────────

class AuditMiddleware:
    """Middleware ASGI puro: copia el cuerpo al vuelo y anota el código de respuesta."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return

        # get_current_user deja aquí el usuario (request.state usa este dict)
        scope.setdefault("state", {})
        body = bytearray()
        status = {"code": 500}

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request" and len(body) <= MAX_BODY:
                body.extend(message.get("body", b""))
            return message

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            await self._after(scope, bytes(body), status["code"])

    async def _after(self, scope: Scope, raw_body: bytes, status_code: int) -> None:
        method = scope["method"]
        route = route_of(scope)
        if not should_audit(method, route):
            return
        state = scope.get("state") or {}
        user = state.get("user")
        request = Request(scope)
        parsed = parse_body(raw_body, request.headers.get("content-type", ""))
        if user is not None:
            username = user.username
        elif route in LOGIN_ROUTES:
            username = (parsed or {}).get("username") if isinstance(parsed, dict) else None
        else:
            return
        try:
            await audit_log.record(
                username=username, ip=client_ip(request), method=method, path=scope["path"],
                route=route, status_code=status_code, path_params=scope.get("path_params") or {},
                body=parsed, target=state.get("audit_target"),
            )
        except Exception as exc:      # el registro nunca debe tumbar una petición
            log.error("audit.record_failed", error=str(exc), path=scope["path"])
