"""
Direcciones de cada dispositivo de la LAN, según la tabla de vecinos del
kernel (`ip neigh`, ARP en IPv4 y descubrimiento de vecinos en IPv6).

Con IPv6 un equipo tiene varias direcciones globales y las de privacidad
cambian cada día, así que no sirven como identificador. LanSentinel sigue
usando la IPv4 de cada dispositivo como clave (conteo, histórico,
anomalías, dominios) y aquí se traduce cualquier dirección IPv6 de la LAN a
la IPv4 del mismo equipo, por su MAC.

Como LanSentinel es el router, el kernel resuelve la MAC de cada dirección
de la LAN que reenvía: en la tabla aparecen todas las que están en uso.
Las de enlace local (fe80::) no se reenvían y no se cuentan.
"""

import asyncio
import ipaddress
import subprocess
import time

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

REFRESH_SECONDS = 15
# Una dirección IPv6 que deja de aparecer se olvida pasado este tiempo
FORGET_AFTER_SECONDS = 24 * 3600

_IGNORED_STATES = {"FAILED", "INCOMPLETE"}


def parse_neighbors(output: str) -> list[tuple[str, str]]:
    """(ip, mac) de la salida de `ip neigh show dev X` (función pura)."""
    result = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3 or "lladdr" not in parts or parts[-1] in _IGNORED_STATES:
            continue
        try:
            ip = str(ipaddress.ip_address(parts[0]))
        except ValueError:
            continue
        mac = parts[parts.index("lladdr") + 1].upper()
        result.append((ip, mac))
    return result


def is_routable_v6(ip: str) -> bool:
    """IPv6 global o ULA (las de enlace local no atraviesan el router)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 6 and not (addr.is_link_local or addr.is_loopback or addr.is_multicast)


class NeighborTable:

    def __init__(self):
        self._v4_by_mac: dict[str, str] = {}
        self._v6: dict[str, dict[str, float]] = {}     # mac → {ipv6: última vez visto}
        self._mac_by_ip: dict[str, str] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception as exc:
                log.error("neighbors.refresh_failed", error=str(exc))
            await asyncio.sleep(REFRESH_SECONDS)

    async def refresh(self) -> None:
        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(None, _run_ip_neigh, settings.MONITOR_INTERFACE)
        if output is not None:
            self.update(parse_neighbors(output), time.time())

    def update(self, pairs: list[tuple[str, str]], now: float) -> None:
        """Incorpora una lectura de la tabla (separado para poder probarlo)."""
        for ip, mac in pairs:
            if ":" not in ip:
                self._v4_by_mac[mac] = ip
            elif is_routable_v6(ip):
                self._v6.setdefault(mac, {})[ip] = now
        for mac in list(self._v6):
            self._v6[mac] = {ip: seen for ip, seen in self._v6[mac].items() if now - seen < FORGET_AFTER_SECONDS}
            if not self._v6[mac]:
                del self._v6[mac]
        self._mac_by_ip = {ip: mac for mac, ip in self._v4_by_mac.items()}
        self._mac_by_ip.update({ip: mac for mac, addrs in self._v6.items() for ip in addrs})

    def set_ipv4(self, mac: str, ip: str) -> None:
        """El escaneo ARP también informa de la IPv4 de cada MAC."""
        self._v4_by_mac[mac.upper()] = ip
        self._mac_by_ip[ip] = mac.upper()

    def ipv6_of(self, mac: str) -> list[str]:
        return sorted(self._v6.get(mac.upper(), {}))

    def mac_of(self, ip: str) -> str | None:
        return self._mac_by_ip.get(ip)

    def device_ipv4(self, ip: str | None) -> str | None:
        """
        IPv4 del equipo que usa esta dirección: la misma si ya es IPv4, la del
        mismo MAC si es una IPv6 de la LAN; None si no se conoce.
        """
        if not ip:
            return None
        if ":" not in ip:
            return ip
        mac = self._mac_by_ip.get(ip)
        return self._v4_by_mac.get(mac) if mac else None

    def ipv6_by_ipv4(self) -> dict[str, list[str]]:
        """{IPv4 del dispositivo: sus IPv6}, para los que tienen alguna."""
        return {
            self._v4_by_mac[mac]: sorted(addrs)
            for mac, addrs in self._v6.items() if mac in self._v4_by_mac
        }


def _run_ip_neigh(interface: str) -> str | None:
    try:
        proc = subprocess.run(["ip", "neigh", "show", "dev", interface], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


neighbors = NeighborTable()
