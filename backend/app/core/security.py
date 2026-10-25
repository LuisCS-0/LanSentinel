"""
Utilidades de seguridad: hash de contraseñas y tokens de sesión.

  - Contraseñas: Argon2id (argon2-cffi), el algoritmo recomendado por OWASP.
  - Sesión: JWT firmado con HS256 y SECRET_KEY. El token lleva el usuario
    (sub), la caducidad (exp) y el momento del último cambio de contraseña
    (pwd); si la contraseña cambia, los tokens anteriores dejan de valer.

La SECRET_KEY no puede quedarse en un valor por defecto conocido: cualquiera
podría firmar tokens válidos. Si no se define una propia (o es demasiado
corta) se genera una aleatoria y se guarda en SECRET_KEY_PATH, que está en un
volumen persistente, para que las sesiones sobrevivan a los reinicios.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
import structlog
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

log = structlog.get_logger(__name__)

_ALGORITHM = "HS256"
_MIN_SECRET_LENGTH = 32
_hasher = PasswordHasher()

# Valores de ejemplo que han estado en el repositorio (.env.example,
# docker-compose.yml, config.py). Son públicos: nunca valen como clave.
_PLACEHOLDER_SECRETS = {
    "cambia_esto_en_produccion_genera_con_openssl_rand_hex_32",
    "changeme_in_production",
    "lansentinelSK",
}


# ── Contraseñas ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_password() -> str:
    """Contraseña aleatoria legible para el administrador inicial."""
    return secrets.token_urlsafe(18)


# ── Clave de firma ───────────────────────────────────────────────────────────

@lru_cache
def get_secret_key() -> str:
    configured = settings.SECRET_KEY.strip()
    # Si se ignora la de .env hay que decirlo claro: el operador podría creer
    # que su clave está en uso
    ignored_hint = (
        f"Se ignora la SECRET_KEY de .env y se usa la de {settings.SECRET_KEY_PATH}. "
        "Déjala vacía o pon una propia con: openssl rand -hex 32"
    )
    if configured in _PLACEHOLDER_SECRETS:
        log.warning("security.secret_key_placeholder_ignored", hint=ignored_hint)
    elif len(configured) >= _MIN_SECRET_LENGTH:
        return configured
    elif configured:
        log.warning("security.secret_key_too_short", min_length=_MIN_SECRET_LENGTH, hint=ignored_hint)

    path = Path(settings.SECRET_KEY_PATH)
    try:
        if path.exists():
            stored = path.read_text().strip()
            if len(stored) >= _MIN_SECRET_LENGTH:
                return stored
        key = secrets.token_hex(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key)
        os.chmod(path, 0o600)
        log.info("security.secret_key_generated", path=str(path))
        return key
    except OSError as exc:
        # Sin volumen persistente (p. ej. ejecutando fuera de Docker): la clave
        # vive en memoria y las sesiones se pierden al reiniciar
        log.warning("security.secret_key_ephemeral", error=str(exc))
        return secrets.token_hex(32)


# ── Tokens ───────────────────────────────────────────────────────────────────

def password_stamp(password_changed_at: datetime) -> int:
    """
    Sello (segundos UTC) del último cambio de contraseña que se guarda en el
    token. Una fecha sin zona horaria se interpreta como UTC, para que el
    valor no dependa de la zona horaria del equipo.
    """
    if password_changed_at.tzinfo is None:
        password_changed_at = password_changed_at.replace(tzinfo=timezone.utc)
    return int(password_changed_at.timestamp())


def create_access_token(username: str, password_changed_at: datetime) -> tuple[str, datetime]:
    """Devuelve el token y su fecha de caducidad."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "exp": expires_at,
        "pwd": password_stamp(password_changed_at),
    }
    return jwt.encode(payload, get_secret_key(), algorithm=_ALGORITHM), expires_at


def decode_access_token(token: str) -> dict | None:
    """Payload del token si la firma y la caducidad son válidas; None si no."""
    try:
        return jwt.decode(
            token, get_secret_key(), algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "pwd"]},
        )
    except jwt.PyJWTError:
        return None
