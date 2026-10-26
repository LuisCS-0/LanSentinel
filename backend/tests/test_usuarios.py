"""Usuarios con roles y registro de acciones: permisos, protección del último admin y middleware."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.routing import APIRoute

from app.api.deps import can_write, get_current_user, require_admin, require_write
from app.models.user import ROLE_ADMIN, ROLE_VIEWER
from app.services.auth import audit
from app.services.auth.audit import (
    ACTIONS, AuditMiddleware, describe, parse_body, sanitize, should_audit,
)
from app.services.auth.user_service import leaves_without_admin


def _user(id, role=ROLE_ADMIN, active=True, username=None):
    return SimpleNamespace(id=id, role=role, is_active=active, username=username or f"u{id}")


# ── Permisos ─────────────────────────────────────────────────────────────────

def test_solo_lectura_puede_leer_pero_no_cambiar():
    viewer, admin = _user(1, ROLE_VIEWER), _user(2)
    assert can_write(viewer, "GET") and can_write(viewer, "HEAD")
    assert not any(can_write(viewer, m) for m in ("POST", "PUT", "PATCH", "DELETE"))
    assert all(can_write(admin, m) for m in ("GET", "POST", "PUT", "PATCH", "DELETE"))


# ── Siempre un administrador activo ──────────────────────────────────────────

def test_no_se_queda_sin_administrador():
    users = [_user(1), _user(2, ROLE_VIEWER)]
    assert leaves_without_admin(users, 1, role=ROLE_VIEWER)
    assert leaves_without_admin(users, 1, is_active=False)
    assert leaves_without_admin(users, 1, deleting=True)
    assert not leaves_without_admin(users, 2, deleting=True)
    assert not leaves_without_admin(users, 2, role=ROLE_ADMIN)


def test_con_dos_administradores_se_puede_quitar_uno():
    users = [_user(1), _user(2), _user(3, ROLE_VIEWER)]
    assert not leaves_without_admin(users, 1, role=ROLE_VIEWER)
    assert not leaves_without_admin(users, 1, deleting=True)


def test_un_admin_desactivado_no_cuenta():
    users = [_user(1), _user(2, active=False)]
    assert leaves_without_admin(users, 1, deleting=True)
    # Reactivarlo sí deja uno
    assert not leaves_without_admin(users, 2, is_active=True)


# ── Qué se registra y cómo ───────────────────────────────────────────────────

def test_que_peticiones_se_registran():
    assert should_audit("POST", "/devices/{device_id}/block")
    assert should_audit("DELETE", "/firewall/rules/{rule_id}")
    assert should_audit("GET", "/system/backups/{name}")       # descarga secretos
    assert not should_audit("GET", "/devices")
    assert not should_audit("POST", None)                       # ruta que no existe


def test_descripciones():
    assert describe("PUT", "/firewall/router") == "Cambiar modo router"
    assert describe("POST", "/algo/nuevo") == "POST /algo/nuevo"


def test_los_secretos_no_se_guardan():
    body = {"username": "ana", "password": "x", "new_password": "y", "current_password": "z",
            "role": "viewer", "nested": [{"api_key": "k", "ip": "1.2.3.4"}], "TOKEN": "t"}
    clean = sanitize(body)
    assert clean["username"] == "ana" and clean["role"] == "viewer"
    assert clean["password"] == clean["new_password"] == clean["current_password"] == "***"
    assert clean["nested"] == [{"api_key": "***", "ip": "1.2.3.4"}] and clean["TOKEN"] == "***"


def test_parse_body():
    assert parse_body(b'{"ip": "1.2.3.4", "reason": "x"}', "application/json") == {"ip": "1.2.3.4", "reason": "x"}
    assert parse_body(b"username=ana&password=secreta", "application/x-www-form-urlencoded") == \
        {"username": "ana", "password": "***"}
    assert parse_body(b"", "application/json") is None
    assert parse_body(b"{roto", "application/json") == {"_omitido": "no se pudo leer"}
    assert parse_body(b"x" * 5000, "application/json") == {"_omitido": "5000 bytes"}


def test_toda_ruta_que_cambia_algo_tiene_descripcion():
    import app.main as main
    missing = []
    for route in main.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1"):
            continue
        for method in route.methods - {"GET", "HEAD", "OPTIONS"}:
            key = (method, route.path[len("/api/v1"):].rstrip("/") or "/")
            if key not in ACTIONS:
                missing.append(key)
    assert missing == []


# ── Middleware y permisos con una API de prueba ──────────────────────────────

@pytest.fixture
def api(monkeypatch):
    """API mínima con el middleware real; el registro se guarda en una lista."""
    records = []

    async def fake_record(**kwargs):
        records.append(kwargs)

    monkeypatch.setattr(audit.audit_log, "record", fake_record)
    app = FastAPI()
    app.add_middleware(AuditMiddleware)
    current = {"user": _user(1, ROLE_VIEWER, username="ana")}

    async def fake_user(request: Request):
        request.state.user = current["user"]
        return current["user"]

    app.dependency_overrides[get_current_user] = fake_user

    @app.get("/api/v1/devices/{device_id}", dependencies=[Depends(require_write)])
    async def read(device_id: str):
        return {"ok": True}

    @app.post("/api/v1/devices/{device_id}/block", dependencies=[Depends(require_write)])
    async def block(device_id: str, payload: dict):
        return {"ok": True}

    @app.get("/api/v1/system/backups/{name}", dependencies=[Depends(require_admin)])
    async def download(name: str):
        return {"ok": True}

    @app.post("/api/v1/auth/login")
    async def login(payload: dict):
        return {"ok": False}

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    return client, records, current


async def test_solo_lectura_recibe_403_y_queda_registrado(api):
    client, records, _ = api
    assert (await client.get("/api/v1/devices/abc")).status_code == 200
    r = await client.post("/api/v1/devices/abc/block", json={"reason": "prueba"})
    assert r.status_code == 403 and "solo lectura" in r.json()["detail"]
    assert (await client.get("/api/v1/system/backups/copia.tar.gz")).status_code == 403
    assert [(x["username"], x["route"], x["status_code"]) for x in records] == [
        ("ana", "/devices/{device_id}/block", 403),
        ("ana", "/system/backups/{name}", 403),
    ]
    assert records[0]["path_params"] == {"device_id": "abc"}


async def test_admin_cambia_y_se_guarda_el_cuerpo(api):
    client, records, current = api
    current["user"] = _user(2, username="luis")
    r = await client.post("/api/v1/devices/abc/block", json={"reason": "prueba", "password": "no"})
    assert r.status_code == 200
    assert records[0]["status_code"] == 200 and records[0]["username"] == "luis"
    assert records[0]["body"] == {"reason": "prueba", "password": "***"}


async def test_login_se_registra_con_el_nombre_intentado(api):
    client, records, _ = api
    await client.post("/api/v1/auth/login", json={"username": "intruso", "password": "123"})
    assert records[0]["username"] == "intruso" and records[0]["body"]["password"] == "***"
