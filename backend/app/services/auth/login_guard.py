"""
Protección del login frente a fuerza bruta.

Cuenta los intentos fallidos por (IP del cliente, usuario). Al llegar a
LOGIN_MAX_ATTEMPTS dentro de la ventana LOGIN_LOCKOUT_SECONDS, esa combinación
queda bloqueada hasta que pase la ventana. Se cuenta por pareja y no solo por
usuario para que un atacante no pueda dejar fuera al administrador legítimo
desde otra IP.

El estado vive en memoria: es suficiente para un único proceso del backend y
se reinicia con él.
"""

import ipaddress
import time

from fastapi import Request

from app.core.config import settings

# (ip, usuario) → marcas de tiempo de los fallos recientes
_failures: dict[tuple[str, str], list[float]] = {}


def client_ip(request: Request) -> str:
    """
    IP real del cliente. Detrás del nginx del frontend la conexión llega desde
    127.0.0.1, así que se usa X-Real-IP, pero solo si quien conecta es un
    proxy de confianza (si no, la cabecera podría falsificarse).
    """
    peer = request.client.host if request.client else "desconocida"
    forwarded = request.headers.get("x-real-ip")
    if forwarded and _is_trusted_proxy(peer):
        return forwarded.strip()
    return peer


def _is_trusted_proxy(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for net in settings.TRUSTED_PROXIES:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return True
        except ValueError:
            continue
    return False


def _recent(key: tuple[str, str], now: float) -> list[float]:
    window_start = now - settings.LOGIN_LOCKOUT_SECONDS
    recent = [t for t in _failures.get(key, []) if t >= window_start]
    if recent:
        _failures[key] = recent
    else:
        _failures.pop(key, None)
    return recent


def seconds_locked(ip: str, username: str) -> int:
    """Segundos que faltan para poder reintentar (0 si no está bloqueado)."""
    now = time.monotonic()
    recent = _recent((ip, username.lower()), now)
    if len(recent) < settings.LOGIN_MAX_ATTEMPTS:
        return 0
    return max(1, int(recent[0] + settings.LOGIN_LOCKOUT_SECONDS - now))


def register_failure(ip: str, username: str) -> int:
    """Registra un fallo y devuelve cuántos lleva esa pareja en la ventana."""
    now = time.monotonic()
    key = (ip, username.lower())
    recent = _recent(key, now)
    recent.append(now)
    _failures[key] = recent
    return len(recent)


def reset(ip: str, username: str) -> None:
    _failures.pop((ip, username.lower()), None)
