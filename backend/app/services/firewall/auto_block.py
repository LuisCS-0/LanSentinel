"""
Política de bloqueo automático ante alertas críticas.

Esta política se invoca desde el threat_classifier cuando persiste una alerta
de Suricata con severidad CRITICAL. Si la opción está habilitada en settings,
extrae la IP origen y la bloquea inmediatamente mediante el firewall_service.

Diseño defensivo:
  - Si firewall_service no está corriendo, simplemente registra y continúa.
  - Si la IP origen es la propia LanSentinel u otra de la red local que
    no debería bloquearse (gateway, broadcast), se omite por seguridad para
    evitar dejar el sistema sin red.
  - Se genera una alerta adicional informando del bloqueo automático,
    asociada al mismo dispositivo si está identificado.
"""

import ipaddress

import structlog

from app.core.config import settings
from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus
from app.services.firewall.firewall_service import firewall_service

log = structlog.get_logger(__name__)


# IPs especiales que nunca se bloquean automáticamente para evitar que el sistema se desconecte a sí mismo o de la red.
# 
_NEVER_BLOCK_IPS = {
    "127.0.0.1",     # loopback
    "0.0.0.0",       # broadcast / sin asignar
}


def _is_safe_to_block(ip: str) -> bool:
    """
    Comprueba si una IP es segura de bloquear automáticamente.

    Reglas:
      - No bloquear loopback ni IPs no válidas.
      - No bloquear la propia interfaz monitorizada (la del backend).
      - No bloquear IPs multicast o de broadcast.
    """
    if ip in _NEVER_BLOCK_IPS:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        if addr.is_loopback or addr.is_multicast or addr.is_unspecified:
            return False
    except ValueError:
        return False
    return True


async def maybe_auto_block(alert: Alert, event: dict) -> None:
    """
    Punto de entrada llamado desde threat_classifier tras persistir una alerta.

    Se ejecuta solo si:
      - La política está habilitada en settings.
      - La severidad de la alerta es CRITICAL.
      - La IP origen es válida y segura de bloquear.
      - El firewall_service está operativo.
    """
    if not settings.FIREWALL_AUTO_BLOCK_CRITICAL:
        return
    if alert.severity != AlertSeverity.critical:
        return

    src_ip = event.get("src_ip")
    if not src_ip or not _is_safe_to_block(src_ip):
        log.debug("auto_block.skipped_unsafe_ip", ip=src_ip)
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
