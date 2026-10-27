"""
IPv6 en la LAN en modo router (IPV6_LAN=true).

LanSentinel da a la LAN un prefijo /64, se pone la dirección ::1 de ese
prefijo en la interfaz LAN y dnsmasq lo anuncia (SLAAC y DNS por DHCPv6 sin
estado). El prefijo sale, por este orden, de:

  1. IPV6_PREFIX: un prefijo fijo que la operadora enruta hacia este equipo.
  2. DHCPv6-PD: dhcpcd, como proceso hijo (igual que dnsmasq), pide un
     prefijo delegado por la WAN y pone su ::1 en la LAN; aquí solo se mira
     qué dirección global aparece en la LAN.
  3. Si no hay ninguno de los dos (la operadora no delega prefijos o tarda),
     una ULA propia (fdXX:...) con NAT66 hacia la WAN, para que la LAN tenga
     IPv6 igualmente (IPV6_NAT_FALLBACK). Se genera una vez y se guarda.

En cuanto llega un prefijo delegado se deja la ULA y el NAT66; si se pierde,
se vuelve a ellos. Cada cambio avisa a firewall_service, que rehace las
reglas de ip6tables y relanza dnsmasq con el prefijo nuevo.

El reenvío IPv6 (net.ipv6.conf.all.forwarding) lo activa el instalador: un
contenedor no puede cambiarlo.
"""

import asyncio
import ipaddress
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

STATE_DIR = Path("/var/lib/lansentinel")
ULA_PATH = STATE_DIR / "ipv6_ula"
DHCPCD_CONF = STATE_DIR / "dhcpcd.conf"
DHCPCD_DB = STATE_DIR / "dhcpcd"          # DUID: la operadora reconoce al equipo y repite prefijo
WATCH_SECONDS = 10
DHCPCD_RETRY_SECONDS = 60     # si dhcpcd se cae, se relanza como mucho una vez por minuto


@dataclass(frozen=True)
class Ipv6Plan:
    """Lo que se sirve en la LAN."""
    prefix: str          # "2001:db8:1:2::/64"
    lan_address: str     # dirección de LanSentinel en la LAN ("...::1")
    source: str          # static | pd | ula
    nat: bool            # NAT66 hacia la WAN (solo con la ULA)


# ── Funciones puras ──────────────────────────────────────────────────────────

def normalize_prefix(text: str) -> ipaddress.IPv6Network:
    """El primer /64 de un prefijo IPv6 (/48, /56, /64...); ValueError si no vale."""
    net = ipaddress.ip_network(text.strip(), strict=False)
    if net.version != 6 or net.prefixlen > 64:
        raise ValueError(f"{text} no es un prefijo IPv6 de /64 o más corto")
    return net if net.prefixlen == 64 else next(net.subnets(new_prefix=64))


def router_address(prefix: ipaddress.IPv6Network) -> str:
    return str(prefix.network_address + 1)


def make_ula(seed: bytes) -> ipaddress.IPv6Network:
    """ULA (RFC 4193): fd + 40 bits aleatorios de identificador global, subred 0."""
    if len(seed) < 5:
        raise ValueError("Hacen falta 5 bytes aleatorios")
    raw = b"\xfd" + seed[:5] + b"\x00" * 10
    return ipaddress.IPv6Network((raw, 64))


def parse_global_addresses(output: str) -> list[tuple[str, int]]:
    """(dirección, longitud) de `ip -6 -o addr show dev X scope global`."""
    result = []
    for line in output.splitlines():
        parts = line.split()
        if "inet6" not in parts:
            continue
        try:
            iface = ipaddress.ip_interface(parts[parts.index("inet6") + 1])
        except (ValueError, IndexError):
            continue
        result.append((str(iface.ip), iface.network.prefixlen))
    return result


def pick_delegated(addresses: list[tuple[str, int]], own: str | None) -> Ipv6Plan | None:
    """La dirección /64 que dhcpcd ha puesto en la LAN con el prefijo delegado, si hay."""
    for address, length in addresses:
        addr = ipaddress.ip_address(address)
        if address == own or length != 64 or addr.is_private:
            continue
        prefix = ipaddress.ip_network(f"{address}/64", strict=False)
        return Ipv6Plan(prefix=str(prefix), lan_address=address, source="pd", nat=False)
    return None


def render_dhcpcd_conf(wan: str, lan: str) -> str:
    """
    dhcpcd solo para pedir un prefijo delegado por la WAN y ponerlo en la LAN.
    No configura nada más en la WAN (sus direcciones y rutas son cosa del
    sistema), ni toca IPv4 ni el DNS del equipo.
    """
    return "\n".join([
        "# Generado por LanSentinel: solo pide un prefijo delegado (DHCPv6-PD). No editar.",
        "ipv6only",
        "noipv6rs",           # los anuncios de la WAN los atiende el sistema
        "script /bin/true",   # sin scripts: nada de resolv.conf ni hostname
        "duid",
        f"allowinterfaces {wan}",
        f"interface {wan}",
        # Prefijo delegado → primer /64 en la LAN, con la dirección ::1
        f"  ia_pd 1 {lan}/0/64/1",
        "",
    ])


# ── Servicio ─────────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stdout if proc.returncode == 0 else proc.stderr).strip()


async def _run_async(cmd: list[str]) -> tuple[bool, str]:
    return await asyncio.get_running_loop().run_in_executor(None, _run, cmd)


class Ipv6LanService:

    def __init__(self):
        self.plan: Ipv6Plan | None = None
        self.error: str | None = None
        self._wan = self._lan = ""
        self._own: str | None = None            # dirección que ha puesto LanSentinel (fija o ULA)
        self._dhcpcd: asyncio.subprocess.Process | None = None
        self._watcher: asyncio.Task | None = None
        self._on_change: Callable[[], Awaitable[None]] | None = None
        self._dhcpcd_at = 0.0

    @property
    def enabled(self) -> bool:
        return settings.IPV6_LAN

    async def start(self, wan: str, lan: str, on_change: Callable[[], Awaitable[None]]) -> Ipv6Plan | None:
        """Prepara el prefijo de la LAN. Devuelve el plan con el que arrancar (o None)."""
        await self.stop()
        self._wan, self._lan, self._on_change = wan, lan, on_change
        self.error = None

        if settings.IPV6_PREFIX.strip():
            try:
                prefix = normalize_prefix(settings.IPV6_PREFIX)
            except ValueError as exc:
                self.error = str(exc)
                log.error("ipv6_lan.bad_prefix", error=self.error)
                return None
            self.plan = Ipv6Plan(str(prefix), router_address(prefix), "static", False)
            await self._assign(self.plan.lan_address)
            log.info("ipv6_lan.started", source="static", prefix=self.plan.prefix)
            return self.plan

        if settings.IPV6_PD:
            await self._spawn_dhcpcd()
        self.plan = await self._delegated() or await self._fallback()
        self._watcher = asyncio.create_task(self._watch())
        log.info("ipv6_lan.started", source=self.plan.source if self.plan else None,
                 prefix=self.plan.prefix if self.plan else None)
        return self.plan

    async def stop(self) -> None:
        if self._watcher:
            self._watcher.cancel()
            self._watcher = None
        await self._stop_dhcpcd()
        await self._unassign()
        self.plan = None

    # ── Prefijos ────────────────────────────────────────────────────────────

    async def _assign(self, address: str) -> None:
        ok, out = await _run_async(["ip", "-6", "addr", "replace", f"{address}/64", "dev", self._lan])
        if ok:
            self._own = address
        else:
            self.error = f"No se pudo poner {address} en {self._lan}: {out}"
            log.error("ipv6_lan.assign_failed", error=out)

    async def _unassign(self) -> None:
        if self._own and self._lan:
            await _run_async(["ip", "-6", "addr", "del", f"{self._own}/64", "dev", self._lan])
        self._own = None

    async def _delegated(self) -> Ipv6Plan | None:
        ok, out = await _run_async(["ip", "-6", "-o", "addr", "show", "dev", self._lan, "scope", "global"])
        return pick_delegated(parse_global_addresses(out), self._own) if ok else None

    async def _fallback(self) -> Ipv6Plan | None:
        if not settings.IPV6_NAT_FALLBACK:
            self.error = "La operadora no ha delegado ningún prefijo IPv6 (DHCPv6-PD)"
            return None
        prefix = _load_or_create_ula()
        plan = Ipv6Plan(str(prefix), router_address(prefix), "ula", True)
        await self._assign(plan.lan_address)
        return plan

    async def _watch(self) -> None:
        """Cambia a un prefijo delegado cuando llega, y vuelve a la ULA si se pierde."""
        while True:
            await asyncio.sleep(WATCH_SECONDS)
            try:
                dhcpcd_down = self._dhcpcd is None or self._dhcpcd.returncode is not None
                if settings.IPV6_PD and dhcpcd_down and time.monotonic() - self._dhcpcd_at > DHCPCD_RETRY_SECONDS:
                    await self._spawn_dhcpcd()
                delegated = await self._delegated()
                if delegated and delegated != self.plan:
                    if self._own:
                        await self._unassign()
                    self.plan = delegated
                    log.warning("ipv6_lan.prefix_delegated", prefix=delegated.prefix)
                elif not delegated and self.plan is not None and self.plan.source == "pd":
                    self.plan = await self._fallback()
                    log.warning("ipv6_lan.prefix_lost", fallback=self.plan.prefix if self.plan else None)
                else:
                    continue
                if self._on_change:
                    await self._on_change()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("ipv6_lan.watch_failed", error=str(exc))

    # ── dhcpcd ──────────────────────────────────────────────────────────────

    async def _spawn_dhcpcd(self) -> None:
        self._dhcpcd_at = time.monotonic()
        try:
            DHCPCD_DB.mkdir(parents=True, exist_ok=True)
            DHCPCD_CONF.write_text(render_dhcpcd_conf(self._wan, self._lan))
            self._dhcpcd = await asyncio.create_subprocess_exec(
                "dhcpcd", "--nobackground", "--config", str(DHCPCD_CONF), self._wan,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            asyncio.create_task(self._log_dhcpcd(self._dhcpcd))
            log.info("ipv6_lan.dhcpcd_started", wan=self._wan, lan=self._lan)
        except (OSError, FileNotFoundError) as exc:
            self._dhcpcd = None
            self.error = f"No se pudo lanzar dhcpcd: {exc}"
            log.error("ipv6_lan.dhcpcd_failed", error=str(exc))

    @staticmethod
    async def _log_dhcpcd(proc: asyncio.subprocess.Process) -> None:
        while line := await proc.stderr.readline():
            log.info("dhcpcd", line=line.decode(errors="replace").rstrip())

    async def _stop_dhcpcd(self) -> None:
        proc, self._dhcpcd = self._dhcpcd, None
        if proc and proc.returncode is None:
            proc.terminate()          # al salir, dhcpcd retira el prefijo delegado
            try:
                await asyncio.wait_for(proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    def status(self) -> dict:
        p = self.plan
        return {
            "enabled": self.enabled,
            "active": p is not None,
            "source": p.source if p else None,
            "prefix": p.prefix if p else None,
            "lan_address": p.lan_address if p else None,
            "nat": p.nat if p else False,
            "pd_client": self._dhcpcd is not None and self._dhcpcd.returncode is None,
            "error": self.error,
        }


def _load_or_create_ula() -> ipaddress.IPv6Network:
    """La ULA de esta instalación: se genera la primera vez y se guarda (estable)."""
    try:
        return normalize_prefix(ULA_PATH.read_text())
    except (OSError, ValueError):
        prefix = make_ula(os.urandom(5))
        try:
            ULA_PATH.parent.mkdir(parents=True, exist_ok=True)
            ULA_PATH.write_text(str(prefix) + "\n")
        except OSError as exc:
            log.warning("ipv6_lan.ula_not_saved", error=str(exc))
        return prefix


ipv6_lan = Ipv6LanService()
