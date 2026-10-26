"""
Router del cortafuegos: bloqueo manual de IPs y consulta de reglas activas.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.device import Device
from app.schemas.device import DeviceSummary
from app.schemas.firewall import (
    BlockIpRequest, FirewallRuleResponse, FirewallStatusResponse,
)
from app.services.firewall.rule_repository import FirewallRuleRepository
from app.services.firewall.firewall_service import firewall_service
from app.services.firewall.protection import ProtectedAddressError

router = APIRouter()


# ── Operaciones de bloqueo ───────────────────────────────────────────────────

@router.post("/block", response_model=FirewallRuleResponse, status_code=201)
async def block_ip(payload: BlockIpRequest):
    """
    Bloquea una dirección IP en el cortafuegos.
    Si ya existe una regla activa para la misma IP, devuelve la existente.
    Rechaza con 400 las IPs protegidas (el propio LanSentinel, su puerta de
    enlace, direcciones especiales o las de FIREWALL_NEVER_BLOCK).
    """
    try:
        rule = await firewall_service.block_ip(
            ip=payload.ip,
            reason=payload.reason or "Bloqueo manual",
            device_id=payload.device_id,
            auto_generated=False,
        )
    except ProtectedAddressError as exc:
        raise HTTPException(status_code=400, detail=f"No se puede bloquear {payload.ip}: {exc}")
    if not rule:
        raise HTTPException(
            status_code=500,
            detail="No se pudo aplicar la regla en iptables",
        )
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
async def unblock_rule(rule_id: int):
    """
    Elimina una regla del cortafuegos por su ID.
    Se quita tanto de iptables como se marca inactiva en BD.
    """
    correcto = await firewall_service.unblock_rule(rule_id)
    if not correcto:
        raise HTTPException(status_code=404, detail="Regla no encontrada o ya inactiva")
    return None


# ── Consulta ────────────────────────────────────────────────────────────────

@router.get("/rules", response_model=list[FirewallRuleResponse])
async def list_rules(
    only_active: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Lista las reglas del cortafuegos. Por defecto solo las activas."""
    repo = FirewallRuleRepository(db)
    if only_active:
        return await repo.get_all_active()
    return await repo.get_all()


@router.get("/status", response_model=FirewallStatusResponse)
async def firewall_status():
    """Estado del servicio de cortafuegos."""
    return firewall_service.get_status()


# ── Modo cuarentena ──────────────────────────────────────────────────────────

class QuarantineUpdate(BaseModel):
    enabled: bool


class QuarantineStatus(BaseModel):
    enabled: bool
    interface: str
    trusted_count: int
    # Dispositivos sin confianza vistos en las últimas 24 h: los que quedan
    # (o quedarían) sin Internet con el modo activo
    quarantined: list[DeviceSummary]


async def _quarantine_status(db: AsyncSession) -> QuarantineStatus:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    devices = (await db.execute(select(Device).order_by(Device.last_seen.desc()))).scalars().all()
    return QuarantineStatus(
        enabled=firewall_service.quarantine_enabled,
        interface=settings.MONITOR_INTERFACE,
        trusted_count=sum(1 for d in devices if d.is_trusted),
        quarantined=[d for d in devices if not d.is_trusted and d.last_seen >= since],
    )


@router.get("/quarantine", response_model=QuarantineStatus)
async def quarantine_status(db: AsyncSession = Depends(get_db)):
    """Estado del modo cuarentena y dispositivos afectados."""
    return await _quarantine_status(db)


@router.put("/quarantine", response_model=QuarantineStatus)
async def update_quarantine(payload: QuarantineUpdate, db: AsyncSession = Depends(get_db)):
    """
    Activa o desactiva el modo cuarentena: con él activo, solo los
    dispositivos de confianza pueden salir a Internet.
    """
    if not firewall_service._running:
        raise HTTPException(status_code=409, detail="El cortafuegos no está disponible (iptables)")
    ok = await firewall_service.set_quarantine(payload.enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudieron aplicar las reglas de cuarentena")
    return await _quarantine_status(db)


# ── Modo router ──────────────────────────────────────────────────────────────

class RouterUpdate(BaseModel):
    enabled: bool


class DhcpStatus(BaseModel):
    running: bool
    lan_ip: str | None
    range_start: str | None
    range_end: str | None
    active_leases: int
    error: str | None


class RouterStatus(BaseModel):
    enabled: bool                 # estado elegido (panel o .env)
    active: bool                  # reglas de NAT y reenvío aplicadas
    available: bool               # WAN configurada y válida
    problem: str | None           # por qué no se puede activar
    wan_interface: str | None
    lan_interface: str
    ip_forward: bool              # reenvío activado en el sistema
    dhcp_enabled: bool            # ROUTER_DHCP: LanSentinel da DHCP/DNS
    dhcp: DhcpStatus


async def _router_status() -> RouterStatus:
    return RouterStatus(enabled=await firewall_service.router_enabled(), **firewall_service.router_status())


@router.get("/router", response_model=RouterStatus)
async def router_status():
    """Estado del modo router (NAT, reenvío, WAN cerrada y DHCP/DNS)."""
    return await _router_status()


@router.put("/router", response_model=RouterStatus)
async def update_router(payload: RouterUpdate):
    """
    Enciende o apaga el modo router. Apagarlo deja sin Internet a los
    dispositivos que usan LanSentinel como puerta de enlace y detiene el
    DHCP/DNS.
    """
    if not firewall_service._running:
        raise HTTPException(status_code=409, detail="El cortafuegos no está disponible (iptables)")
    if payload.enabled and (problem := firewall_service.router_problem()):
        raise HTTPException(status_code=409, detail=problem)
    ok = await firewall_service.set_router(payload.enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudieron aplicar las reglas del modo router")
    return await _router_status()
