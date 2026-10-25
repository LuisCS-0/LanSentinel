"""
Creación centralizada de alertas.

Todos los módulos (monitor, Suricata, cortafuegos) registran sus alertas a
través de este servicio, de modo que el formato y las reglas comunes se
aplican en un único sitio.

Agrupación de alertas repetidas:
  Un escaneo de puertos o un ataque de fuerza bruta disparan la misma firma
  decenas de veces por minuto. Si cada evento creara una fila, la tabla se
  llenaría y la vista de alertas sería ilegible. Por eso cada alerta puede
  llevar una huella (fingerprint), p. ej. "suricata:<sid>:<ip origen>":
    - Si ya existe una alerta abierta (new o acknowledged) con la misma huella
      vista dentro de la ventana ALERT_DEDUP_WINDOW_SECONDS, se incrementa su
      contador (occurrences) y se actualiza last_seen_at.
    - Si no, se crea una alerta nueva.
  La ventana es deslizante: mientras el ataque continúe, sigue agrupándose
  en la misma alerta. Una vez resuelta o ignorada, la siguiente ocurrencia
  abre una alerta nueva.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus

log = structlog.get_logger(__name__)

_OPEN_STATUSES = (AlertStatus.new, AlertStatus.acknowledged)


async def _find_open_duplicate(db: AsyncSession, fingerprint: str, now: datetime) -> Alert | None:
    window_start = now - timedelta(seconds=settings.ALERT_DEDUP_WINDOW_SECONDS)
    result = await db.execute(
        select(Alert)
        .where(
            Alert.fingerprint == fingerprint,
            Alert.status.in_(_OPEN_STATUSES),
            Alert.last_seen_at >= window_start,
        )
        .order_by(Alert.last_seen_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def create_alert(
    db: AsyncSession,
    *,
    severity: AlertSeverity,
    source: AlertSource,
    title: str,
    description: str | None = None,
    device_id: UUID | None = None,
    raw_payload: dict | None = None,
    fingerprint: str | None = None,
) -> Alert:
    """
    Persiste una alerta y la devuelve ya con su id. Si se indica fingerprint
    y hay una alerta abierta reciente con la misma huella, se agrupa en ella
    (occurrences > 1) en lugar de crear otra.
    """
    now = datetime.now(timezone.utc)

    if fingerprint and settings.ALERT_DEDUP_WINDOW_SECONDS > 0:
        duplicate = await _find_open_duplicate(db, fingerprint, now)
        if duplicate:
            duplicate.occurrences += 1
            duplicate.last_seen_at = now
            duplicate.updated_at = now
            await db.commit()
            await db.refresh(duplicate)
            log.debug(
                "alert_service.aggregated",
                alert_id=duplicate.id, fingerprint=fingerprint,
                occurrences=duplicate.occurrences,
            )
            return duplicate

    alert = Alert(
        device_id=device_id,
        severity=severity,
        source=source,
        status=AlertStatus.new,
        title=title[:255],
        description=description,
        raw_payload=raw_payload,
        fingerprint=fingerprint,
        occurrences=1,
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert
