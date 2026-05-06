"""
Módulo de descubrimiento de dispositivos mediante ARP.

Usa Scapy para enviar peticiones ARP al rango de la red y recolectar
las respuestas. Por cada dispositivo que responde, devuelve su MAC e IP.
Requiere privilegios de red (NET_RAW/NET_ADMIN o root).
"""

import asyncio
import socket
import struct
from dataclasses import dataclass, field
from datetime import datetime

import netifaces
import structlog

log = structlog.get_logger(__name__)


@dataclass
class DiscoveredDevice:
    mac: str
    ip: str
    hostname: str | None = None
    vendor: str | None = None
    discovered_at: datetime = field(default_factory=datetime.utcnow)


def _get_network_cidr(interface: str) -> str | None:
    """Obtiene el CIDR de la red a partir de la interfaz (ej. '192.168.1.0/24')."""
    try:
        addrs = netifaces.ifaddresses(interface)
        ipv4 = addrs.get(netifaces.AF_INET)
        if not ipv4:
            return None
        ip = ipv4[0]["addr"]
        netmask = ipv4[0]["netmask"]
        # Calcular dirección de red
        ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
        nm_int = struct.unpack("!I", socket.inet_aton(netmask))[0]
        net_int = ip_int & nm_int
        net_ip = socket.inet_ntoa(struct.pack("!I", net_int))
        # Calcular prefijo CIDR
        prefix = bin(nm_int).count("1")
        return f"{net_ip}/{prefix}"
    except Exception as exc:
        log.warning("arp_scanner.cidr_error", interface=interface, error=str(exc))
        return None


def _resolve_hostname(ip: str) -> str | None:
    """Resolución DNS inversa. No lanza excepción."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


def _mac_to_vendor_prefix(mac: str) -> str:
    """
    Retorna el prefijo OUI de la MAC (primeros 3 octetos).
    La resolución real del fabricante se hace en OUIResolver (ver oui_resolver.py).
    """
    return mac[:8].upper()


def _run_arp_scan(network_cidr: str) -> list[DiscoveredDevice]:
    """
    Ejecuta el ARP scan de forma síncrona (Scapy no es async).
    Se llama desde un executor para no bloquear el event loop.
    """
    try:
        # Import tardío: Scapy emite warnings al importarse si no hay raw socket
        from scapy.layers.l2 import ARP, Ether
        from scapy.sendrecv import srp

        log.info("arp_scanner.scan_start", network=network_cidr)

        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network_cidr)
        # timeout=2s, verbose=0 para no ensuciar los logs
        answered, _ = srp(packet, timeout=2, verbose=0)

        devices: list[DiscoveredDevice] = []
        for _, reply in answered:
            mac = reply[ARP].hwsrc.upper()
            ip = reply[ARP].psrc
            hostname = _resolve_hostname(ip)
            devices.append(DiscoveredDevice(mac=mac, ip=ip, hostname=hostname))

        log.info("arp_scanner.scan_done", found=len(devices))
        return devices

    except PermissionError:
        log.error(
            "arp_scanner.permission_denied",
            hint="El contenedor necesita CAP_NET_RAW. Comprueba docker-compose.yml",
        )
        return []
    except Exception as exc:
        log.error("arp_scanner.error", error=str(exc))
        return []


async def scan_network(interface: str, network_cidr: str | None = None) -> list[DiscoveredDevice]:
    """
    Versión async del ARP scan. Corre el scan en un ThreadPoolExecutor
    para no bloquear el event loop de FastAPI.

    Args:
        interface:    Interfaz de red (ej. 'eth0').
        network_cidr: Rango CIDR a escanear. Si None, lo infiere de la interfaz.

    Returns:
        Lista de dispositivos descubiertos.
    """
    cidr = network_cidr or _get_network_cidr(interface)
    if not cidr:
        log.error("arp_scanner.no_cidr", interface=interface)
        return []

    loop = asyncio.get_event_loop()
    devices = await loop.run_in_executor(None, _run_arp_scan, cidr)
    return devices
