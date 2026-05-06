from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.db.session import get_db
from app.models.alert import Alert, AlertStatus, AlertSeverity
from datetime import datetime, timezone

router = APIRouter()


@router.get("/")
async def list_alerts(
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Lista alertas con filtros opcionales por estado y severidad."""
    stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
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
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    return alert


@router.patch("/{alert_id}/ack")
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Marca la alerta como gestionada."""
    await db.execute(
        update(Alert).where(Alert.id == alert_id).values(
            status=AlertStatus.acknowledged,
            acknowledged_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return {"alert_id": alert_id, "status": "acknowledged"}


@router.patch("/{alert_id}/ignore")
async def ignore_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(Alert).where(Alert.id == alert_id).values(
            status=AlertStatus.ignored,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return {"alert_id": alert_id, "status": "ignored"}
