"""
Creación centralizada de alertas.

Todos los módulos (monitor, Suricata, cortafuegos) registran sus alertas a
través de este servicio, de modo que el formato y las reglas comunes se
aplican en un único sitio.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus


async def create_alert(
    db: AsyncSession,
    *,
    severity: AlertSeverity,
    source: AlertSource,
    title: str,
    description: str | None = None,
    device_id: UUID | None = None,
    raw_payload: dict | None = None,
) -> Alert:
    """Persiste una alerta nueva y la devuelve ya con su id."""
    now = datetime.now(timezone.utc)
    alert = Alert(
        device_id=device_id,
        severity=severity,
        source=source,
        status=AlertStatus.new,
        title=title[:255],
        description=description,
        raw_payload=raw_payload,
        created_at=now,
        updated_at=now,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert
