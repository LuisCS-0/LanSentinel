"""
Ajustes que se cambian desde el panel (services/panel_config). Solo para
administradores; los secretos nunca salen por aquí. Cambiar un secreto o a
dónde van los datos pide la contraseña del administrador, con el mismo
límite de intentos que el inicio de sesión.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.security import verify_password
from app.models.user import User
from app.services.auth import login_guard
from app.services.panel_config import ConfigError, needs_password, panel_config

router = APIRouter()


@router.get("")
async def get_config():
    return {"fields": panel_config.describe()}


class ConfigUpdate(BaseModel):
    # nombre → valor nuevo; null vuelve al de .env
    values: dict[str, object | None]
    password: str | None = None


@router.put("")
async def update_config(body: ConfigUpdate, request: Request, user: User = Depends(get_current_user)):
    try:
        changes = panel_config.validate(body.values)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if needs_password(changes):
        ip = login_guard.client_ip(request)
        wait = login_guard.seconds_locked(ip, user.username)
        if wait:
            raise HTTPException(status_code=429, detail=f"Demasiados intentos: espera {wait} s")
        if not body.password or not verify_password(body.password, user.password_hash):
            login_guard.register_failure(ip, user.username)
            raise HTTPException(status_code=403, detail="Contraseña incorrecta")
        login_guard.reset(ip, user.username)
    changed = await panel_config.update(changes)
    # En el registro de acciones, qué se cambió (los valores secretos ya van tapados)
    request.state.audit_target = ", ".join(changed)[:255] if changed else "sin cambios"
    return {"fields": panel_config.describe(), "changed": changed}
