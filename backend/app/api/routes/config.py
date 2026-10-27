"""
Ajustes que se cambian desde el panel (services/panel_config). Solo para
administradores; los secretos nunca salen por aquí. Cambiar un secreto o a
dónde van los datos pide la contraseña del administrador, con el mismo
límite de intentos que el inicio de sesión.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import verify_password
from app.models.user import User
from app.services.auth import login_guard
from app.services.firewall import router_checks
from app.services.firewall.dhcp_dns import lan_ipv4_interface
from app.services.firewall.firewall_service import firewall_service
from app.services.panel_config import BY_NAME, ConfigError, needs_password, panel_config

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
        changes = panel_config.validate(body.values, lan_ipv4_interface(settings.MONITOR_INTERFACE))
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
    # Dar DHCP con el modo router en marcha: como al encenderlo, que no haya
    # otro servidor DHCP en la LAN
    if firewall_service.router_active and not settings.ROUTER_DHCP and panel_config.effective("ROUTER_DHCP", changes):
        failed = [c for c in router_checks.failures(await router_checks.run(None, dhcp=True)) if c.id == "dhcp"]
        if failed:
            raise HTTPException(
                status_code=409,
                detail=f"{failed[0].detail}: desactiva primero el DHCP de ese equipo (en el router de la "
                       "operadora suele estar en LAN o DHCP) o ponlo en modo bridge.",
            )
    changed = await panel_config.update(changes)
    # DHCP y DNS: dnsmasq se relanza con los valores nuevos (o se para)
    if any(BY_NAME[n].group == "router" for n in changed):
        await firewall_service.apply_dhcp()
    # En el registro de acciones, qué se cambió (los valores secretos ya van tapados)
    request.state.audit_target = ", ".join(changed)[:255] if changed else "sin cambios"
    return {"fields": panel_config.describe(), "changed": changed}
