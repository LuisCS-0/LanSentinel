"""
Direcciones que LanSentinel nunca debe bloquear.

Bloquear por error la IP del propio gateway, la del router de salida o una
dirección especial dejaría a LanSentinel aislado de la red y obligaría a
recuperarlo desde la consola. La comprobación se aplica tanto al bloqueo
automático como al manual.

Como el backend corre con network_mode: host, netifaces ve las interfaces
y rutas reales del equipo que hace de gateway.
"""

import ipaddress

import netifaces
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class ProtectedAddressError(Exception):
    """Se intenta bloquear una dirección protegida. El mensaje explica el motivo."""


def _parse(ip: str) -> IpAddress | None:
    # netifaces añade "%iface" a las IPv6 de enlace local
    try:
        return ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return None


def _local_addresses() -> set[IpAddress]:
    """IPs y direcciones de broadcast de todas las interfaces del equipo."""
    found: set[IpAddress] = set()
    try:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            for family in (netifaces.AF_INET, netifaces.AF_INET6):
                for entry in addrs.get(family, []):
                    for key in ("addr", "broadcast"):
                        addr = _parse(entry.get(key) or "")
                        if addr:
                            found.add(addr)
    except Exception as exc:
        log.warning("protection.local_addresses_error", error=str(exc))
    return found


def _gateway_addresses() -> set[IpAddress]:
    """Puertas de enlace conocidas por el equipo (normalmente, el router del ISP)."""
    found: set[IpAddress] = set()
    try:
        for family in (netifaces.AF_INET, netifaces.AF_INET6):
            for entry in netifaces.gateways().get(family, []):
                addr = _parse(entry[0])
                if addr:
                    found.add(addr)
    except Exception as exc:
        log.warning("protection.gateways_error", error=str(exc))
    return found


def protected_reason(ip: str) -> str | None:
    """
    Devuelve el motivo por el que una IP no debe bloquearse, o None si se
    puede bloquear sin riesgo para el propio sistema.
    """
    addr = _parse(ip)
    if addr is None:
        return "Dirección IP no válida"
    if addr.is_loopback:
        return "Es una dirección de loopback"
    if addr.is_multicast:
        return "Es una dirección multicast"
    if addr.is_unspecified:
        return "Es una dirección sin asignar"
    if addr == ipaddress.IPv4Address("255.255.255.255"):
        return "Es la dirección de broadcast"
    if addr in _local_addresses():
        return "Es una dirección del propio LanSentinel"
    if addr in _gateway_addresses():
        return "Es la puerta de enlace de LanSentinel (router de salida)"
    for net in settings.FIREWALL_NEVER_BLOCK:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return f"Está en la lista FIREWALL_NEVER_BLOCK ({net})"
        except ValueError:
            log.warning("protection.invalid_never_block_entry", entry=net)
    return None


def is_own_address(ip: str | None) -> bool:
    """True si la IP pertenece a alguna interfaz del propio LanSentinel."""
    addr = _parse(ip or "")
    return addr is not None and addr in _local_addresses()
