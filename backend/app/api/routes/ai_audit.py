"""
Auditoría con IA (solo administradores): la vista previa de lo que se
enviaría, el proveedor configurado, lanzar una auditoría y consultar los
informes. La clave del proveedor nunca sale por aquí.
"""

from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_audit import collect
from app.services.ai_audit.providers import (
    ProviderError, configuration_problem, get_provider, model_name, provider_name, wants_compact,
)
from app.services.ai_audit.providers.openai_provider import is_local_url
from app.services.ai_audit.report import EstadoHallazgo, pending_findings
from app.services.ai_audit.service import AuditBusy, ai_audit_service

router = APIRouter()


@router.get("/preview")
async def preview():
    snapshot = await collect.build()
    text = snapshot.to_json()
    return {
        "snapshot": snapshot.data,
        "characters": len(text),
        "approx_tokens": snapshot.approx_tokens(),
        "mapping": snapshot.mapping,
    }


@router.get("/status")
async def status():
    problem = configuration_problem()
    base_url = settings.AI_AUDIT_BASE_URL.strip()
    compatible = provider_name() == "compatible" and bool(base_url)
    return {
        "configured": problem is None,
        "problem": problem,
        "provider": provider_name() or None,
        "model": model_name() or None,
        "local": compatible and is_local_url(base_url),
        # Solo el equipo, por si la dirección lleva usuario y contraseña
        "endpoint": urlparse(base_url).hostname if compatible else None,
        "compact": wants_compact(),
        "running": ai_audit_service.running,
    }


@router.post("/check")
async def check():
    """Comprueba la conexión con el proveedor (sin gastar tokens cuando se puede)."""
    try:
        return {"ok": True, "detail": await get_provider().check()}
    except ProviderError as exc:
        return {"ok": False, "detail": str(exc)}


@router.post("/run", status_code=202)
async def run(request: Request):
    """Lanza una auditoría en segundo plano; su estado se consulta en /reports/{id}."""
    user = getattr(request.state, "user", None)
    try:
        audit_id = await ai_audit_service.run(user.username if user else None)
    except AuditBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": audit_id}


class AuditSummary(BaseModel):
    id: int
    created_at: datetime
    finished_at: datetime | None
    status: str
    provider: str
    model: str
    local: bool
    requested_by: str | None
    cost_usd: float | None
    score: int | None
    findings: dict[str, int]
    pending: int                  # hallazgos sin aplicar ni descartar
    error: str | None


def _summary(row) -> AuditSummary:
    findings: dict[str, int] = {}
    for h in (row.report or {}).get("hallazgos", []):
        findings[h["gravedad"]] = findings.get(h["gravedad"], 0) + 1
    return AuditSummary(
        id=row.id, created_at=row.created_at, finished_at=row.finished_at, status=row.status,
        provider=row.provider, model=row.model, local=row.local, requested_by=row.requested_by,
        cost_usd=row.cost_usd, score=(row.report or {}).get("puntuacion"), findings=findings,
        pending=pending_findings(row.report, row.finding_states), error=row.error,
    )


@router.get("/reports", response_model=list[AuditSummary])
async def reports(limit: int = Query(20, ge=1, le=100)):
    return [_summary(r) for r in await ai_audit_service.list(limit)]


@router.get("/reports/{audit_id}")
async def report(audit_id: int):
    row = await ai_audit_service.get(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="No existe esa auditoría")
    return {
        **_summary(row).model_dump(),
        "report": row.report,
        "discarded": row.discarded or [],
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "snapshot": row.snapshot,
        "mapping": row.mapping or [],
        "finding_states": row.finding_states or {},
        "action_states": row.action_states or {},
    }


class FindingStateIn(BaseModel):
    estado: EstadoHallazgo


@router.put("/reports/{audit_id}/findings/{index}")
async def set_finding_state(audit_id: int, index: int, body: FindingStateIn, request: Request):
    """Aplicado, descartado o de vuelta a pendiente. Las acciones en sí van por sus rutas de siempre."""
    user = getattr(request.state, "user", None)
    try:
        row = await ai_audit_service.set_finding_state(audit_id, index, body.estado, user.username if user else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="No existe esa auditoría")
    request.state.audit_target = f"auditoría {audit_id}, hallazgo {index + 1}: {body.estado}"
    return {"finding_states": row.finding_states or {}, "pending": pending_findings(row.report, row.finding_states)}


@router.put("/reports/{audit_id}/actions/{index}")
async def set_action_state(audit_id: int, index: int, body: FindingStateIn, request: Request):
    """
    Lo que se hizo con una acción del plan. La acción en sí la aplica el
    panel por su ruta de siempre (bloquear, escanear...); esto solo lo anota.
    """
    user = getattr(request.state, "user", None)
    try:
        row = await ai_audit_service.set_action_state(audit_id, index, body.estado, user.username if user else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="No existe esa auditoría")
    request.state.audit_target = f"auditoría {audit_id}, acción {index + 1}: {body.estado}"
    return {"action_states": row.action_states or {}}


@router.delete("/reports/{audit_id}", status_code=204)
async def delete_report(audit_id: int, request: Request):
    try:
        deleted = await ai_audit_service.delete(audit_id)
    except AuditBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="No existe esa auditoría")
    request.state.audit_target = f"auditoría {audit_id}"
