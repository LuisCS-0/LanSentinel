"""
Política de bloqueo automático ante alertas críticas.

Esta política se invoca desde el threat_classifier cuando persiste una alerta
de Suricata con severidad CRITICAL. Si la opción está habilitada en settings,
extrae la IP origen y la bloquea inmediatamente mediante el firewall_service.

Diseño defensivo:
  - Si firewall_service no está corriendo, simplemente registra y continúa.
  - Nunca se bloquean las direcciones protegidas (protection.py): las del
    propio LanSentinel, su puerta de enlace, direcciones especiales y las
    indicadas en FIREWALL_NEVER_BLOCK. Bloquearlas dejaría el sistema sin red.
  - Tampoco se bloquean automáticamente los dispositivos marcados como de
    confianza: un falso positivo no debe cortar la red a un equipo conocido.
    El usuario puede bloquearlos a mano si lo considera necesario.
  - Se genera una alerta adicional informando del bloqueo automático,
    asociada al mismo dispositivo si está identificado.
"""

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus
from app.models.device import Device
from app.services.firewall.firewall_service import firewall_service
from app.services.firewall.protection import protected_reason

log = structlog.get_logger(__name__)


async def _is_trusted_ip(ip: str) -> bool:
    """True si la IP corresponde a algún dispositivo marcado como de confianza."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Device.id).where(Device.ip == ip, Device.is_trusted == True).limit(1)  # noqa: E712
        )
        return result.first() is not None


async def maybe_auto_block(alert: Alert, event: dict) -> None:
    """
    Punto de entrada llamado desde threat_classifier tras persistir una alerta.

    Se ejecuta solo si:
      - La política está habilitada en settings.
      - La severidad de la alerta es CRITICAL.
      - La IP origen es válida y no está protegida.
      - La IP origen no pertenece a un dispositivo de confianza.
      - El firewall_service está operativo.
    """
    if not settings.FIREWALL_AUTO_BLOCK_CRITICAL:
        return
    if alert.severity != AlertSeverity.critical:
        return

    src_ip = event.get("src_ip")
    if not src_ip:
        return

    reason_protected = protected_reason(src_ip)
    if reason_protected:
        log.info("auto_block.skipped_protected_ip", ip=src_ip, reason=reason_protected)
        return

    if await _is_trusted_ip(src_ip):
        log.info("auto_block.skipped_trusted_device", ip=src_ip)
        return

    if not firewall_service._running:
        log.warning("auto_block.firewall_not_running", ip=src_ip)
        return

    # Aplicar el bloqueo
    rule = await firewall_service.block_ip(
        ip=src_ip,
        reason=f"Bloqueo automático por alerta crítica: {alert.title}",
        device_id=alert.device_id,
        auto_generated=True,
    )

    if rule:
        log.info(
            "auto_block.applied",
            ip=src_ip, rule_id=rule.id, alert_id=alert.id,
        )
        await _notify_block(alert, src_ip, rule.id)


async def _notify_block(alert: Alert, ip: str, rule_id: int) -> None:
    """Registra una alerta informando del bloqueo automático aplicado."""
    async with AsyncSessionLocal() as db:
        db.add(Alert(
            device_id=alert.device_id,
            severity=AlertSeverity.high,
            source=AlertSource.firewall,
            status=AlertStatus.new,
            title=f"Bloqueo automático aplicado a {ip}",
            description=(
                f"LanSentinel ha bloqueado {ip} tras la alerta crítica "
                f"\"{alert.title}\". Si es un falso positivo, elimina la regla "
                f"desde la vista de cortafuegos y marca el dispositivo como de confianza."
            ),
            raw_payload={"ip": ip, "rule_id": rule_id, "alert_id": alert.id},
        ))
        await db.commit()
