"""
Clasificación de eventos de Suricata en alertas de LanSentinel.

Suricata genera distintos tipos de eventos en eve.json:
  - "alert"     → coincidencia con una regla de detección
  - "flow"      → resumen de un flujo de red completado
  - "dns", "tls", "http" → metadatos de protocolos
  - "stats"     → estadísticas internas

Solo los eventos de tipo "alert" se convierten en alertas de LanSentinel.
El resto se ignoran o se usan como contexto para enriquecer alertas existentes.

Mapeo de severidad:
  Suricata usa una escala 1-4 (1=más grave, 4=informativo).
  LanSentinel usa el ENUM (info, low, medium, high, critical).

  Suricata 1 → critical
  Suricata 2 → high
  Suricata 3 → medium
  Suricata 4 → low
"""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus
from app.models.device import Device

log = structlog.get_logger(__name__)


# Mapeo Suricata → LanSentinel severity
_SEVERITY_MAP = {
    1: AlertSeverity.critical,
    2: AlertSeverity.high,
    3: AlertSeverity.medium,
    4: AlertSeverity.low,
}


def _map_severity(suricata_severity: int | None) -> AlertSeverity:
    """Convierte la severidad de Suricata (1-4) a la de LanSentinel."""
    if suricata_severity is None:
        return AlertSeverity.info
    return _SEVERITY_MAP.get(suricata_severity, AlertSeverity.info)


def _build_title(event: dict) -> str:
    """Construye un título legible a partir del evento Suricata."""
    alert_data = event.get("alert", {})
    signature = alert_data.get("signature") or "Alerta de Suricata"
    # Truncamos por si la firma es muy larga
    if len(signature) > 250:
        signature = signature[:247] + "..."
    return signature


def _build_description(event: dict) -> str:
    """Descripción enriquecida con IPs, puertos y categoría."""
    alert_data = event.get("alert", {})
    parts = []

    src_ip = event.get("src_ip")
    src_port = event.get("src_port")
    dst_ip = event.get("dest_ip")
    dst_port = event.get("dest_port")
    proto = event.get("proto")
    category = alert_data.get("category")

    if src_ip:
        src = f"{src_ip}:{src_port}" if src_port else src_ip
        dst = f"{dst_ip}:{dst_port}" if dst_port else (dst_ip or "?")
        parts.append(f"Origen: {src} → Destino: {dst}")

    if proto:
        parts.append(f"Protocolo: {proto}")

    if category:
        parts.append(f"Categoría: {category}")

    return ". ".join(parts) if parts else "Sin detalles adicionales."


async def _find_device_by_ip(db: AsyncSession, ip: str | None) -> Device | None:
    """
    Busca el dispositivo asociado a una IP origen, si está registrado.

    Varias filas pueden compartir IP (el DHCP la reasigna y el equipo
    anterior conserva su última IP conocida), así que se elige el visto más
    recientemente, que es quien la tiene ahora.
    """
    if not ip:
        return None
    result = await db.execute(
        select(Device).where(Device.ip == ip).order_by(Device.last_seen.desc()).limit(1)
    )
    return result.scalars().first()


async def classify_and_persist(event: dict, db: AsyncSession) -> Alert | None:
    """
    Procesa un evento de Suricata y, si es de tipo 'alert', lo persiste como
    una alerta en la base de datos. Devuelve la alerta creada o None.
    """
    if event.get("event_type") != "alert":
        return None  # Solo procesamos eventos de tipo alert

    alert_data = event.get("alert", {})
    severity = _map_severity(alert_data.get("severity"))

    # Asociamos la alerta a un dispositivo si la IP origen es conocida.
    # Si no lo es, la alerta queda sin device_id (NULL).
    device = await _find_device_by_ip(db, event.get("src_ip"))

    alert = Alert(
        device_id=device.id if device else None,
        severity=severity,
        source=AlertSource.suricata,
        status=AlertStatus.new,
        title=_build_title(event),
        description=_build_description(event),
        raw_payload=event,  # Guardamos el evento completo en JSONB
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    log.info(
        "threat_classifier.alert_created",
        signature=alert_data.get("signature"),
        severity=severity.value,
        src_ip=event.get("src_ip"),
        device_id=str(device.id) if device else None,
    )

    # bloqueo automático ante severidad crítica.
    from app.services.firewall.auto_block import maybe_auto_block
    try:
        await maybe_auto_block(alert, event)
    except Exception as exc:
        log.error("threat_classifier.auto_block_error", error=str(exc))

    return alert
