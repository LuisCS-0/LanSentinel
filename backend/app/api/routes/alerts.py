from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.alert import Alert, AlertSeverity, AlertStatus

router = APIRouter()


class AlertUpdate(BaseModel):
    """Payload para actualizar el estado de una alerta."""
    status: Literal["new", "acknowledged", "resolved", "ignored"]
    acknowledged_by: str | None = None


@router.get("/")
async def list_alerts(
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """
    Lista alertas con filtros opcionales por estado y severidad, ordenadas por
    su última ocurrencia: una alerta agrupada que se repite vuelve arriba.
    """
    stmt = select(Alert).order_by(Alert.last_seen_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/summary")
async def alert_summary(db: AsyncSession = Depends(get_db)):
    """Resumen de alertas por severidad para el dashboard."""
    counts = {}
    for sev in AlertSeverity:
        q = await db.execute(
            select(func.count()).select_from(Alert)
            .where(Alert.severity == sev)
            .where(Alert.status == AlertStatus.new)
        )
        counts[sev.value] = q.scalar()
    total_new = await db.execute(
        select(func.count()).select_from(Alert).where(Alert.status == AlertStatus.new)
    )
    return {"by_severity": counts, "total_new": total_new.scalar()}


@router.get("/{alert_id}")
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Detalle de una alerta."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    return alert


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Actualiza el estado de una alerta.

    Estados:
      - 'new':           sin revisar
      - 'acknowledged':  en seguimiento
      - 'resolved':      resuelta (incidente cerrado correctamente)
      - 'ignored':       descartada
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    try:
        new_status = AlertStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Estado inválido: {payload.status}")

    alert.status = new_status
    alert.updated_at = datetime.now(timezone.utc)

    # Si pasa a acknowledged, registrar quién y cuándo
    if new_status == AlertStatus.acknowledged:
        alert.acknowledged_by = payload.acknowledged_by or "usuario"
        alert.acknowledged_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(alert)
    return alert
