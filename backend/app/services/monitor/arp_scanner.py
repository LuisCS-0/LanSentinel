"""Módulo de descubrimiento de dispositivos con ARP."""

import asyncio
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import netifaces
import structlog

log = structlog.get_logger(__name__)

# Datos de un dispositivo descubierto en la red
@dataclass
class DiscoveredDevice:
    mac: str
    ip: str
    hostname: str | None = None
    vendor: str | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _get_network_cidr(interface: str) -> str | None:
    """Obtiene el CIDR de la red a partir de la interfaz (ej. '192.168.1.0/24')."""
    try:
        # Obtiene la IP y máscara de la interfaz indicada
        addrs = netifaces.ifaddresses(interface)
        ipv4 = addrs.get(netifaces.AF_INET)
        if not ipv4:
            return None
        ip = ipv4[0]["addr"]
        netmask = ipv4[0]["netmask"]
        # Paso de IP y máscara a enteros para calcular la dirección de red
        ip_int = struct.unpack("!I", socket.inet_aton(ip))[0]
        nm_int = struct.unpack("!I", socket.inet_aton(netmask))[0]
        # AND para calcular la dirección de red
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


# DNS inversa: una IP sin nombre tarda en contestar (~0,7 s). De una en una,
# con 200 dispositivos el escaneo ARP pasaba de 2 s a un minuto y el ciclo de
# vigilancia de 30 s a 90. Ahora se preguntan a la vez y se recuerdan: los
# nombres cambian muy poco (una hora) y los "sin nombre" se reintentan antes.
NAME_TTL_SECONDS = 3600
NO_NAME_TTL_SECONDS = 600
_NAME_CACHE_MAX = 4096
_NAME_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="dns-inversa")
_name_cache: dict[str, tuple[float, str | None]] = {}     # ip → (caduca, nombre)


def resolve_hostnames(ips: list[str]) -> dict[str, str | None]:
    """Nombres de varias IPs: de la caché o preguntando a la vez las que falten."""
    now = time.monotonic()
    names: dict[str, str | None] = {}
    missing = []
    for ip in dict.fromkeys(ips):
        cached = _name_cache.get(ip)
        if cached and cached[0] > now:
            names[ip] = cached[1]
        else:
            missing.append(ip)
    if missing:
        if len(_name_cache) + len(missing) > _NAME_CACHE_MAX:
            _name_cache.clear()
        for ip, name in zip(missing, _NAME_POOL.map(_resolve_hostname, missing)):
            names[ip] = name
            _name_cache[ip] = (now + (NAME_TTL_SECONDS if name else NO_NAME_TTL_SECONDS), name)
    return names


def _mac_to_vendor_prefix(mac: str) -> str:
    """Devuelve el prefijo OUI de la MAC (primeros 3 octetos)."""
    return mac[:8].upper()


def _run_arp_scan(network_cidr: str, interface: str) -> list[DiscoveredDevice]:
    """Ejecuta el ARP scan de forma síncrona (ya que Scapy no es async)."""
    try:
        # Import tardío: Scapy emite warnings al importarse si no hay raw socket
        from scapy.layers.l2 import ARP, Ether
        from scapy.sendrecv import srp

        log.info("arp_scanner.scan_start", network=network_cidr)
        # Construcción del paquete ARP, MAC broadcast
        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=network_cidr)
        # timeout=2s, verbose=0 para no ensuciar los logs
        answered, _ = srp(packet, timeout=2, verbose=0, iface=interface)

        # Se guardan los dispositivos descubiertos en una lista de DiscoveredDevice
        replies = [(reply[ARP].hwsrc.upper(), reply[ARP].psrc) for _, reply in answered]
        names = resolve_hostnames([ip for _, ip in replies])
        devices = [DiscoveredDevice(mac=mac, ip=ip, hostname=names.get(ip)) for mac, ip in replies]

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
    """Versión async del ARP scan. Corre el scan en un ThreadPoolExecutor"""
    cidr = network_cidr or _get_network_cidr(interface)
    if not cidr:
        log.error("arp_scanner.no_cidr", interface=interface)
        return []

    loop = asyncio.get_event_loop()
    devices = await loop.run_in_executor(None, _run_arp_scan, cidr, interface)
    return devices
