"""
Router del cortafuegos: bloqueo manual de IPs y consulta de reglas activas.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
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
