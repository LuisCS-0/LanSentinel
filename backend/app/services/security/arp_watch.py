"""
Detección de ARP spoofing y conflictos de IP.

El ARP spoofing es la base de los ataques MITM en una LAN: el atacante envía
respuestas ARP falsas ("la IP X está en mi MAC") para que el tráfico de otros
pase por él. LanSentinel lo vigila de dos formas:

  1. Pasiva: escucha con scapy todos los paquetes ARP de la interfaz LAN
     (como arpwatch). Cada paquete revela una asociación IP → MAC de quien lo
     envía. Cuando LanSentinel es el gateway, un atacante que quiera
     interceptar las respuestas tiene que envenenar la caché de LanSentinel,
     así que sus paquetes llegan aquí.
  2. Activa: en cada escaneo ARP del monitor se comprueba si una misma IP
     responde desde varias MAC.

Reglas (evaluate):
  - CRÍTICA: otra MAC reclama una IP del propio LanSentinel.
  - CRÍTICA: cambia la MAC de la puerta de enlace de la interfaz (el router,
    cuando LanSentinel no es el gateway). La primera MAC vista se guarda como
    referencia en ARP_BASELINE_PATH. Si la MAC nueva es de un dispositivo de
    confianza se acepta como nueva referencia (p. ej. al cambiar de router).
  - ALTA: una IP alterna entre dos MAC (A → B → A) en menos de
    ARP_CONFLICT_WINDOW_SECONDS, o responde desde dos MAC en el mismo
    escaneo. Es lo que provoca un spoofing: el equipo legítimo sigue
    respondiendo mientras el atacante envenena. Un cambio único (DHCP que
    reasigna la IP, un móvil que rota su MAC aleatoria) no la dispara.

Solo se alerta; no se bloquea automáticamente: un falso positivo (cambio de
router) dejaría la red sin salida. Las repeticiones se agrupan por IP.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

import netifaces
import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import AlertSeverity, AlertSource
from app.models.device import Device
from app.services.alerts.alert_service import create_alert

log = structlog.get_logger(__name__)

_IGNORED_MACS = {"00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"}


@dataclass
class Binding:
    mac: str
    last_seen: float
    previous_mac: str | None = None     # MAC anterior, si la IP cambió de dueño
    changed_at: float = 0.0


@dataclass
class Finding:
    kind: str              # own_ip | gateway_changed | ip_conflict
    severity: AlertSeverity
    ip: str
    mac: str               # MAC que reclama la IP ahora
    previous_mac: str | None


@dataclass
class LocalContext:
    """Lo que hay que proteger en la interfaz monitorizada."""
    own_ips: set[str]
    own_macs: set[str]
    gateway_ip: str | None


# ── Reglas (función pura) ────────────────────────────────────────────────────

def evaluate(
    bindings: dict[str, Binding],
    ip: str,
    mac: str,
    now: float,
    ctx: LocalContext,
    gateway_baseline: str | None,
    trusted_macs: set[str],
    window_seconds: float,
) -> tuple[list[Finding], str | None]:
    """
    Evalúa una asociación IP → MAC observada. Actualiza `bindings` y devuelve
    los hallazgos y la referencia de MAC del gateway (nueva si cambia).
    """
    mac = mac.upper()
    findings: list[Finding] = []
    if not ip or ip == "0.0.0.0" or mac in _IGNORED_MACS:
        return findings, gateway_baseline

    if ip in ctx.own_ips and mac not in ctx.own_macs:
        findings.append(Finding("own_ip", AlertSeverity.critical, ip, mac, None))

    if ctx.gateway_ip and ip == ctx.gateway_ip:
        if gateway_baseline is None:
            gateway_baseline = mac
        elif mac != gateway_baseline:
            if mac in trusted_macs:
                log.info("arp_watch.gateway_mac_accepted", ip=ip, old=gateway_baseline, new=mac)
                gateway_baseline = mac
            else:
                findings.append(Finding("gateway_changed", AlertSeverity.critical, ip, mac, gateway_baseline))

    current = bindings.get(ip)
    if current is None:
        bindings[ip] = Binding(mac=mac, last_seen=now)
    elif current.mac == mac:
        current.last_seen = now
    else:
        # La IP cambia de MAC. Si vuelve a la MAC que la tenía justo antes
        # (vaivén A → B → A) dentro de la ventana, dos equipos se la disputan
        flip_flop = current.previous_mac == mac and now - current.changed_at < window_seconds
        if flip_flop and not findings:   # si no, ya lo cubre una regla más grave
            findings.append(Finding("ip_conflict", AlertSeverity.high, ip, mac, current.mac))
        bindings[ip] = Binding(mac=mac, last_seen=now, previous_mac=current.mac, changed_at=now)
    return findings, gateway_baseline


def scan_conflicts(entries: list[tuple[str, str]]) -> dict[str, set[str]]:
    """IPs que en un mismo escaneo han respondido desde más de una MAC."""
    by_ip: dict[str, set[str]] = {}
    for ip, mac in entries:
        by_ip.setdefault(ip, set()).add(mac.upper())
    return {ip: macs for ip, macs in by_ip.items() if len(macs) > 1}


# ── Servicio ─────────────────────────────────────────────────────────────────

def _local_context(interface: str) -> LocalContext:
    own_ips: set[str] = set()
    own_macs: set[str] = set()
    gateway_ip = None
    try:
        addrs = netifaces.ifaddresses(interface)
        own_ips = {a["addr"] for a in addrs.get(netifaces.AF_INET, []) if a.get("addr")}
        own_macs = {a["addr"].upper() for a in addrs.get(netifaces.AF_LINK, []) if a.get("addr")}
        # Puerta de enlace en esta misma interfaz (si LanSentinel es el gateway
        # de la LAN, no la hay: su salida está en otra interfaz)
        for gw_ip, gw_iface, *_ in netifaces.gateways().get(netifaces.AF_INET, []):
            if gw_iface == interface:
                gateway_ip = gw_ip
                break
    except Exception as exc:
        log.warning("arp_watch.context_error", interface=interface, error=str(exc))
    return LocalContext(own_ips=own_ips, own_macs=own_macs, gateway_ip=gateway_ip)


class ArpWatch:

    def __init__(self):
        self._bindings: dict[str, Binding] = {}
        self._gateway_baseline: str | None = None
        self._ctx = LocalContext(set(), set(), None)
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sniffer = None
        self._task: asyncio.Task | None = None
        self.packets_seen = 0
        self.running = False

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    async def start(self) -> None:
        if not settings.ARP_SPOOF_DETECTION or self.running:
            return
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=1000)
        self._ctx = _local_context(settings.MONITOR_INTERFACE)
        self._gateway_baseline = self._load_baseline()
        self._task = asyncio.create_task(self._consume(), name="arp_watch")
        try:
            self._start_sniffer()
            self.running = True
            log.info(
                "arp_watch.started", interface=settings.MONITOR_INTERFACE,
                own_ips=sorted(self._ctx.own_ips), gateway=self._ctx.gateway_ip,
            )
        except Exception as exc:
            # Sin captura (p. ej. falta CAP_NET_RAW) queda la comprobación activa
            log.warning("arp_watch.sniffer_unavailable", error=str(exc))

    async def stop(self) -> None:
        if self._sniffer is not None:
            sniffer, self._sniffer = self._sniffer, None
            try:
                await asyncio.get_running_loop().run_in_executor(None, sniffer.stop)
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.running = False

    def _start_sniffer(self) -> None:
        # Import tardío: Scapy tarda en cargar y avisa si no hay raw sockets
        from scapy.layers.l2 import ARP
        from scapy.sendrecv import AsyncSniffer

        def on_packet(packet) -> None:
            # Hilo del sniffer → cola del event loop
            arp = packet[ARP]
            self._loop.call_soon_threadsafe(self._enqueue, arp.psrc, arp.hwsrc)

        self._sniffer = AsyncSniffer(
            iface=settings.MONITOR_INTERFACE, filter="arp", store=False, prn=on_packet,
        )
        self._sniffer.start()

    def _enqueue(self, ip: str, mac: str) -> None:
        try:
            self._queue.put_nowait((ip, mac))
        except asyncio.QueueFull:
            pass

    async def _consume(self) -> None:
        while True:
            ip, mac = await self._queue.get()
            self.packets_seen += 1
            try:
                await self.observe(ip, mac)
            except Exception as exc:
                log.error("arp_watch.observe_error", error=str(exc))

    # ── Observaciones ───────────────────────────────────────────────────────

    async def observe(self, ip: str, mac: str) -> None:
        trusted = await self._trusted_macs() if self._needs_trusted(ip, mac) else set()
        findings, baseline = evaluate(
            self._bindings, ip, mac, time.monotonic(), self._ctx,
            self._gateway_baseline, trusted, settings.ARP_CONFLICT_WINDOW_SECONDS,
        )
        if baseline != self._gateway_baseline:
            self._gateway_baseline = baseline
            self._save_baseline(baseline)
        for finding in findings:
            await self._alert(finding)

    async def check_scan(self, entries: list[tuple[str, str]]) -> None:
        """
        Resultados de un escaneo ARP (IP, MAC), antes de deduplicar: varias
        MAC respondiendo por la misma IP en el mismo escaneo es un conflicto.
        """
        if not settings.ARP_SPOOF_DETECTION:
            return
        conflicts = scan_conflicts(entries)
        for ip, macs in conflicts.items():
            others = sorted(macs)
            await self._alert(Finding("ip_conflict", AlertSeverity.high, ip, others[-1], others[0]), extra_macs=others)
        for ip, mac in entries:
            if ip in conflicts:
                continue   # ya alertado; no evaluar el vaivén otra vez
            await self.observe(ip, mac)

    def _needs_trusted(self, ip: str, mac: str) -> bool:
        """Solo se consulta la BD cuando cambia la MAC del gateway."""
        return (
            self._ctx.gateway_ip == ip
            and self._gateway_baseline is not None
            and mac.upper() != self._gateway_baseline
        )

    @staticmethod
    async def _trusted_macs() -> set[str]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Device.mac).where(Device.is_trusted == True))  # noqa: E712
            return {m.upper() for m in result.scalars().all()}

    async def _alert(self, finding: Finding, extra_macs: list[str] | None = None) -> None:
        async with AsyncSessionLocal() as db:
            device = (await db.execute(select(Device).where(Device.mac == finding.mac))).scalar_one_or_none()
            name = (device.hostname or device.vendor) if device else None
            who = f"{finding.mac}" + (f" ({name})" if name else "")

            if finding.kind == "own_ip":
                title = f"Otro equipo reclama la IP de LanSentinel ({finding.ip})"
                description = (
                    f"El equipo {who} anuncia que la IP {finding.ip} de LanSentinel es suya. "
                    f"Es un ataque de suplantación (ARP spoofing) para interceptar el tráfico "
                    f"de la red, o un equipo mal configurado con una IP duplicada."
                )
            elif finding.kind == "gateway_changed":
                title = f"Ha cambiado la MAC de la puerta de enlace ({finding.ip})"
                description = (
                    f"La puerta de enlace {finding.ip} respondía desde {finding.previous_mac} y "
                    f"ahora lo hace {who}. Puede ser un ataque MITM (ARP spoofing). Si has "
                    f"cambiado de router, marca el nuevo dispositivo como de confianza y "
                    f"resuelve esta alerta."
                )
            else:
                macs = ", ".join(extra_macs or [finding.previous_mac or "?", finding.mac])
                title = f"Conflicto de IP: varias MAC reclaman {finding.ip}"
                description = (
                    f"La IP {finding.ip} ha sido reclamada por varias MAC en poco tiempo ({macs}). "
                    f"Puede ser un ataque de suplantación (ARP spoofing) o dos equipos con la "
                    f"misma IP configurada."
                )

            await create_alert(
                db,
                device_id=device.id if device else None,
                severity=finding.severity,
                source=AlertSource.monitor,
                title=title,
                description=description,
                raw_payload={
                    "kind": finding.kind, "ip": finding.ip, "mac": finding.mac,
                    "previous_mac": finding.previous_mac, "macs": extra_macs,
                },
                fingerprint=f"arp:{finding.kind}:{finding.ip}",
            )
        log.warning("arp_watch.finding", kind=finding.kind, ip=finding.ip, mac=finding.mac)

    # ── Referencia del gateway ──────────────────────────────────────────────

    @staticmethod
    def _load_baseline() -> str | None:
        try:
            return json.loads(Path(settings.ARP_BASELINE_PATH).read_text()).get("gateway_mac")
        except (OSError, ValueError):
            return None

    def _save_baseline(self, mac: str | None) -> None:
        try:
            path = Path(settings.ARP_BASELINE_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"gateway_ip": self._ctx.gateway_ip, "gateway_mac": mac}))
        except OSError as exc:
            log.warning("arp_watch.baseline_save_error", error=str(exc))

    def get_status(self) -> dict:
        return {
            "enabled": settings.ARP_SPOOF_DETECTION,
            "running": self.running,
            "packets_seen": self.packets_seen,
            "gateway_ip": self._ctx.gateway_ip,
            "gateway_mac": self._gateway_baseline,
        }


arp_watch = ArpWatch()
