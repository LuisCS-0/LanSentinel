"""Autenticación: contraseñas, tokens de sesión, IP real tras el proxy y límite de intentos."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from starlette.requests import Request

from app.core import security
from app.core.config import settings
from app.services.auth import login_guard


# ── Contraseñas y tokens ─────────────────────────────────────────────────────

def test_hash_de_contrasena():
    h = security.hash_password("correcta horse")
    assert h.startswith("$argon2id$") and "correcta" not in h
    assert security.verify_password("correcta horse", h)
    assert not security.verify_password("otra", h)
    assert not security.verify_password("x", "no-es-un-hash")


def test_contrasenas_generadas():
    a, b = security.generate_password(), security.generate_password()
    assert a != b and len(a) >= 16


def test_token_ida_y_vuelta():
    changed = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    token, expires = security.create_access_token("admin", changed)
    payload = security.decode_access_token(token)
    assert payload["sub"] == "admin" and payload["pwd"] == security.password_stamp(changed)
    assert expires > datetime.now(timezone.utc)


def test_sello_de_contrasena_sin_zona_es_utc():
    naive = datetime(2026, 10, 25, 12, 0)
    assert security.password_stamp(naive) == security.password_stamp(naive.replace(tzinfo=timezone.utc))


def test_tokens_invalidos():
    assert security.decode_access_token("basura") is None
    # Firmado con otra clave
    forged = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1), "pwd": 1},
                        "otra-clave" * 8, algorithm="HS256")
    assert security.decode_access_token(forged) is None
    # Caducado
    old = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) - timedelta(seconds=1), "pwd": 1},
                     security.get_secret_key(), algorithm="HS256")
    assert security.decode_access_token(old) is None
    # Sin el sello de contraseña
    nopwd = jwt.encode({"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                       security.get_secret_key(), algorithm="HS256")
    assert security.decode_access_token(nopwd) is None


# ── IP real del cliente ──────────────────────────────────────────────────────

def _request(peer: str, real_ip: str | None = None) -> Request:
    headers = [(b"x-real-ip", real_ip.encode())] if real_ip else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_ip_real_solo_desde_nginx():
    # nginx (127.0.0.1) dice quién es el cliente
    assert login_guard.client_ip(_request("127.0.0.1", "192.168.56.20")) == "192.168.56.20"
    # Cualquier otro no puede falsificar la cabecera
    assert login_guard.client_ip(_request("192.168.56.30", "1.2.3.4")) == "192.168.56.30"
    assert login_guard.client_ip(_request("172.18.0.3", "1.2.3.4")) == "172.18.0.3"
    assert login_guard.client_ip(_request("127.0.0.1")) == "127.0.0.1"


# ── Límite de intentos ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def limpio():
    login_guard._failures.clear()
    yield
    login_guard._failures.clear()


def test_bloqueo_tras_varios_fallos(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_SECONDS", 300)
    for i in range(2):
        login_guard.register_failure("192.168.56.20", "admin")
    assert login_guard.seconds_locked("192.168.56.20", "admin") == 0
    assert login_guard.register_failure("192.168.56.20", "ADMIN") == 3      # sin distinguir mayúsculas
    assert 0 < login_guard.seconds_locked("192.168.56.20", "admin") <= 300
    # Solo esa pareja IP + usuario: otra IP sigue pudiendo entrar
    assert login_guard.seconds_locked("192.168.56.30", "admin") == 0
    login_guard.reset("192.168.56.20", "admin")
    assert login_guard.seconds_locked("192.168.56.20", "admin") == 0


def test_los_fallos_caducan(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_SECONDS", 300)
    clock = [1000.0]
    monkeypatch.setattr(login_guard.time, "monotonic", lambda: clock[0])
    login_guard.register_failure("10.0.0.5", "admin")
    clock[0] += 301                                   # el primero ya no cuenta
    assert login_guard.register_failure("10.0.0.5", "admin") == 1
    assert login_guard.seconds_locked("10.0.0.5", "admin") == 0


def test_dos_cambios_de_contrasena_en_el_mismo_segundo():
    # El sello va en segundos: el segundo cambio tiene que dar un sello nuevo
    first = datetime(2026, 10, 26, 21, 42, 19, 100000, tzinfo=timezone.utc)
    second = first + timedelta(milliseconds=500)
    changed = security.next_password_change(first, second)
    assert security.password_stamp(changed) == security.password_stamp(first) + 1
    # Si ya ha pasado al menos un segundo, se guarda la hora real
    later = first + timedelta(seconds=3)
    assert security.next_password_change(first, later) == later
    assert security.next_password_change(None, later) == later


# ── Contraseña inicial ───────────────────────────────────────────────────────

def test_contrasena_inicial_pendiente(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.services.auth import user_service

    fichero = tmp_path / "initial_admin_password"
    monkeypatch.setattr(settings, "INITIAL_PASSWORD_PATH", str(fichero))
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(user_service, "_initial_pending", {})
    sello = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def usuario(nombre, clave, cambio=sello):
        return SimpleNamespace(id=1, username=nombre, password_changed_at=cambio,
                               password_hash=security.hash_password(clave))

    # Sin fichero (ADMIN_PASSWORD en .env o ya cambiada): nada que pedir
    assert not user_service.initial_password_pending(usuario("admin", "inicial-123"))

    # Con el fichero y la misma contraseña: hay que cambiarla
    fichero.write_text("inicial-123\n")
    admin = usuario("Admin", "inicial-123", sello + timedelta(seconds=1))
    assert user_service.initial_password_pending(admin)
    # Otros usuarios nunca
    assert not user_service.initial_password_pending(usuario("ana", "inicial-123"))
    # Si el fichero desaparece, deja de pedirlo aunque la respuesta esté en caché
    fichero.unlink()
    assert not user_service.initial_password_pending(admin)
    fichero.write_text("inicial-123\n")

    # Cambiada con una versión que no borraba el fichero: se borra
    assert not user_service.initial_password_pending(usuario("admin", "otra-clave-9", sello + timedelta(seconds=2)))
    assert not fichero.exists()
