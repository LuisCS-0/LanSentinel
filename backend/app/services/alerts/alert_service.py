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
from app.services.events.broker import event_broker

log = structlog.get_logger(__name__)

_OPEN_STATUSES = (AlertStatus.new, AlertStatus.acknowledged)


def alert_event_payload(alert: Alert) -> dict:
    """Datos de una alerta que viajan en los eventos en tiempo real."""
    return {
        "id": alert.id,
        "severity": alert.severity.value,
        "source": alert.source.value,
        "status": alert.status.value,
        "title": alert.title,
        "description": alert.description,
        "device_id": str(alert.device_id) if alert.device_id else None,
        "occurrences": alert.occurrences,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
    }


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


def without_nul(value):
    """
    El valor sin el carácter NUL (\\u0000), que PostgreSQL no admite ni en
    text ni en jsonb: la alerta entera se perdía. Suricata lo deja en el
    payload de paquetes binarios (exploits, sondas de nmap), justo las
    alertas que más importan. Se cambia por el texto "\\x00" para que se vea
    que estaba (función pura, recorre dicts y listas).
    """
    if isinstance(value, str):
        return value.replace("\x00", "\\x00") if "\x00" in value else value
    if isinstance(value, dict):
        return {without_nul(k): without_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [without_nul(v) for v in value]
    return value


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
    title, description, raw_payload = without_nul(title), without_nul(description), without_nul(raw_payload)
    fingerprint = without_nul(fingerprint)

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
            event_broker.publish("alert.updated", alert_event_payload(duplicate))
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

    # Panel en tiempo real y canales externos (Telegram, ntfy, correo)
    event_broker.publish("alert.created", alert_event_payload(alert))
    return alert
