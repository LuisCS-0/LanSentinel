"""Registro de acciones (solo administradores): lo más reciente primero, por páginas."""

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.auth.audit import audit_log

router = APIRouter()


class AuditEntryResponse(BaseModel):
    id: int
    created_at: datetime
    username: str | None
    ip: str | None
    method: str
    path: str
    action: str
    target: str | None
    status_code: int
    details: dict | None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditEntryResponse])
async def list_audit(
    limit: int = Query(50, ge=1, le=500),
    before_id: int | None = Query(None, description="Para la página siguiente: el id más bajo recibido"),
    username: str | None = None,
    only_failed: bool = False,
):
    return await audit_log.list(limit, before_id=before_id, username=username, only_failed=only_failed)
