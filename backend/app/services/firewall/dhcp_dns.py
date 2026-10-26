"""
DHCP y DNS de la LAN en modo router (dnsmasq).

dnsmasq corre como un proceso hijo del backend, que lo arranca y lo para al
activar o desactivar el modo router desde el panel. Así un solo interruptor
gobierna NAT, reenvío y DHCP/DNS, sin dar al backend acceso a Docker (el
socket de Docker equivaldría a control total del equipo).

El backend usa la red del equipo (network_mode: host) y tiene NET_ADMIN y
NET_RAW, que es lo que dnsmasq necesita para servir DHCP en la interfaz LAN.
Solo escucha en la LAN: no responde en la WAN ni choca con el resolvedor del
sistema (systemd-resolved escucha en 127.0.0.53).

Si dnsmasq se cae mientras el modo está activo, se vuelve a lanzar.
"""

import asyncio
import ipaddress
import time
from dataclasses import dataclass
from pathlib import Path

import netifaces
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

CONF_PATH = Path("/var/lib/lansentinel/dnsmasq.conf")
LEASES_PATH = Path("/var/lib/lansentinel/dnsmasq.leases")
RESTART_DELAY_SECONDS = 5


@dataclass(frozen=True)
class DhcpPlan:
    """Lo que se va a servir: IP de LanSentinel en la LAN y rango de DHCP."""
    interface: str
    lan_ip: str
    range_start: str
    range_end: str
    lease_time: str
    upstream: list[str]
    domain: str


def lan_ipv4(interface: str) -> str | None:
    addrs = netifaces.ifaddresses(interface).get(netifaces.AF_INET, []) if interface in netifaces.interfaces() else []
    return addrs[0]["addr"] if addrs else None


def make_plan(interface: str, lan_ip: str) -> DhcpPlan:
    """Rango por defecto: .100-.199 de la red de la LAN (función pura)."""
    prefix = lan_ip.rsplit(".", 1)[0]
    upstream = [s.strip() for s in settings.DNS_UPSTREAM.split(",") if s.strip()]
    return DhcpPlan(
        interface=interface,
        lan_ip=lan_ip,
        range_start=settings.DHCP_RANGE_START or f"{prefix}.100",
        range_end=settings.DHCP_RANGE_END or f"{prefix}.199",
        lease_time=settings.DHCP_LEASE_TIME,
        upstream=upstream or ["1.1.1.1", "9.9.9.9"],
        domain=settings.LOCAL_DOMAIN,
    )


def render_config(plan: DhcpPlan) -> str:
    """Fichero de configuración de dnsmasq para el plan (función pura)."""
    lines = [
        "# Generado por LanSentinel al activar el modo router: no editar a mano",
        "keep-in-foreground",
        "log-facility=-",
        "user=root",
        f"interface={plan.interface}",
        "except-interface=lo",
        "bind-interfaces",
        # DNS: reenvía a los servidores indicados, no a los del sistema
        "no-resolv",
        *[f"server={s}" for s in plan.upstream],
        "domain-needed",
        "bogus-priv",
        "cache-size=1000",
        f"domain={plan.domain}",
        f"local=/{plan.domain}/",
        "expand-hosts",
        # DHCP: LanSentinel es la puerta de enlace y el DNS de la red
        f"dhcp-range={plan.range_start},{plan.range_end},{plan.lease_time}",
        f"dhcp-option=option:router,{plan.lan_ip}",
        f"dhcp-option=option:dns-server,{plan.lan_ip}",
        "dhcp-authoritative",
        f"dhcp-leasefile={LEASES_PATH}",
    ]
    return "\n".join(lines) + "\n"


def count_active_leases(text: str, now: float) -> int:
    """Concesiones vigentes en el fichero de dnsmasq: 'expira mac ip nombre id' (función pura)."""
    count = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and (int(parts[0]) == 0 or int(parts[0]) > now):
            count += 1
    return count


class DhcpDnsService:
    def __init__(self):
        self._proc: asyncio.subprocess.Process | None = None
        self._watcher: asyncio.Task | None = None
        self._wanted = False
        self.plan: DhcpPlan | None = None
        self.last_error: str | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, interface: str) -> bool:
        """Arranca dnsmasq en la interfaz LAN (si ya corre, lo reinicia con la configuración actual)."""
        await self.stop()
        lan_ip = lan_ipv4(interface)
        if not lan_ip:
            self.last_error = f"La interfaz {interface} no tiene IPv4"
            log.error("dhcp_dns.no_lan_ip", interface=interface)
            return False
        try:
            ipaddress.ip_address(lan_ip)
            self.plan = make_plan(interface, lan_ip)
            CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONF_PATH.write_text(render_config(self.plan))
        except (OSError, ValueError) as exc:
            self.last_error = f"No se pudo preparar la configuración: {exc}"
            log.error("dhcp_dns.config_failed", error=str(exc))
            return False
        self._wanted = True
        ok = await self._spawn()
        if ok:
            self._watcher = asyncio.create_task(self._watch())
        else:
            self._wanted = False
        return ok

    async def _spawn(self) -> bool:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "dnsmasq", f"--conf-file={CONF_PATH}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            self.last_error = "dnsmasq no está instalado en la imagen del backend"
            log.error("dhcp_dns.not_installed")
            return False
        # Si la configuración es inválida o el puerto 53 está ocupado, sale enseguida
        await asyncio.sleep(1)
        if self._proc.returncode is not None:
            output = (await self._proc.stdout.read()).decode(errors="replace").strip()
            self.last_error = output.splitlines()[-1] if output else f"dnsmasq terminó con código {self._proc.returncode}"
            log.error("dhcp_dns.start_failed", error=self.last_error)
            return False
        self.last_error = None
        p = self.plan
        log.info("dhcp_dns.started", interface=p.interface, lan_ip=p.lan_ip, range=f"{p.range_start}-{p.range_end}")
        return True

    async def _watch(self) -> None:
        """Pasa la salida de dnsmasq al log y lo relanza si se cae."""
        while self._wanted:
            proc = self._proc
            if proc is None:
                return
            while line := await proc.stdout.readline():
                log.debug("dnsmasq", line=line.decode(errors="replace").rstrip())
            await proc.wait()
            if not self._wanted:
                return
            log.warning("dhcp_dns.exited", code=proc.returncode, hint="Se vuelve a lanzar")
            await asyncio.sleep(RESTART_DELAY_SECONDS)
            if self._wanted and not await self._spawn():
                await asyncio.sleep(RESTART_DELAY_SECONDS * 6)

    async def stop(self) -> None:
        self._wanted = False
        if self._watcher:
            self._watcher.cancel()
            self._watcher = None
        if self.running:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
            log.info("dhcp_dns.stopped")
        self._proc = None

    def status(self) -> dict:
        try:
            leases = count_active_leases(LEASES_PATH.read_text(), time.time()) if self.running else 0
        except OSError:
            leases = 0
        p = self.plan
        return {
            "running": self.running,
            "lan_ip": p.lan_ip if p else None,
            "range_start": p.range_start if p else None,
            "range_end": p.range_end if p else None,
            "active_leases": leases,
            "error": self.last_error,
        }


dhcp_dns = DhcpDnsService()
