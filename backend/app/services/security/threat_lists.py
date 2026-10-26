"""
Listas de IPs maliciosas (inteligencia de amenazas).

Descarga listas públicas de redes peligrosas (por defecto FireHOL nivel 1 y
los servidores de control de botnets de abuse.ch), las carga en un ipset y el
cortafuegos corta el tráfico con ellas en la cadena LANSENTINEL_THREAT
(enlazada al principio de FORWARD e INPUT):

  - de cada dispositivo conocido hacia la lista: una regla por dispositivo,
    para saber quién lo intentó (sus contadores);
  - del resto de equipos hacia la lista, y de la lista hacia la red.

Si un dispositivo intenta conectar con una IP de la lista, casi siempre es
malware o un programa no deseado llamando a casa: se crea una alerta alta con
el dispositivo y las redes contactadas. Lo que llega de fuera desde la lista
solo se cuenta (escaneos de Internet: ruido).

Seguridad de la red local: algunas listas incluyen rangos reservados (FireHOL
nivel 1 trae 192.168.0.0/16 y 10.0.0.0/8 como "bogons"). Bloquearlos dejaría
la LAN sin red, así que se quita cualquier red que se solape con rangos
privados o especiales, con las IPs del propio equipo y su puerta de enlace, o
con FIREWALL_NEVER_BLOCK.

Además de las listas descargadas, se carga /var/lib/lansentinel/amenazas/
propia.txt si existe (una IP o red por línea), para bloquear a mano.

Las listas se guardan en disco: tras un reinicio se cargan al momento, sin
esperar a la red. Solo IPv4 por ahora.
"""

import asyncio
import ipaddress
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import structlog
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.alert import AlertSeverity, AlertSource
from app.models.device import Device
from app.services.alerts.alert_service import create_alert
from app.services.firewall import iptables_manager
from app.services.firewall import protection

log = structlog.get_logger(__name__)

LISTS_DIR = Path("/var/lib/lansentinel/amenazas")
OWN_LIST = LISTS_DIR / "propia.txt"
IPSET_NAME = "lansentinel-amenazas"
CHAIN = "LANSENTINEL_THREAT"
COMMENT_PREFIX = "lansentinel-threat:"
MAX_ELEMENTS = 262144
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
CHECK_EVERY_SECONDS = 60
SURICATA_STATUS = Path("/var/lib/suricata/lansentinel-estado.json")
SURICATA_LOG = Path("/var/log/suricata/suricata.log")

Net = ipaddress.IPv4Network

# Rangos que nunca son "de Internet": privados, reservados, documentación,
# multicast... Una lista que los incluya los pierde
SPECIAL_NETWORKS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/3",
)]


# ── Funciones puras ──────────────────────────────────────────────────────────

def parse_sources(spec: str) -> list[tuple[str, str]]:
    """'nombre=url,nombre=url' → [(nombre, url)]; ignora lo mal formado."""
    sources = []
    for item in spec.split(","):
        name, sep, url = item.strip().partition("=")
        name = re.sub(r"[^a-z0-9_-]", "", name.strip().lower())
        if sep and name and url.strip().startswith(("http://", "https://")):
            sources.append((name, url.strip()))
    return sources


def parse_list(text: str) -> list[Net]:
    """
    Redes IPv4 de una lista: una IP o red por línea; lo que va tras '#' o ';'
    es comentario (formatos de FireHOL, abuse.ch y Spamhaus).
    """
    nets = []
    for line in text.splitlines():
        token = re.split(r"[#;\s]", line.strip(), maxsplit=1)[0]
        if not token:
            continue
        try:
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        if net.version == 4:
            nets.append(net)
    return nets


def sanitize(nets: list[Net], protected: list[Net]) -> tuple[list[Net], int]:
    """
    Quita las redes que se solapan con rangos especiales o protegidos y une
    las que se pueden juntar. Devuelve (redes, cuántas se quitaron).
    """
    forbidden = SPECIAL_NETWORKS + protected
    kept = [n for n in nets if not any(n.overlaps(f) for f in forbidden)]
    return list(ipaddress.collapse_addresses(kept)), len(nets) - len(kept)


def ipset_restore_script(name: str, nets: list[Net]) -> str:
    """Entrada de `ipset restore` que crea el conjunto y lo llena."""
    lines = [f"create {name} hash:net family inet maxelem {MAX_ELEMENTS} counters -exist"]
    lines += [f"add {name} {n} -exist" for n in nets]
    return "\n".join(lines) + "\n"


def chain_rules(device_ips: list[str]) -> list[list[str]]:
    """Reglas de LANSENTINEL_THREAT: una por dispositivo para saber quién lo intentó."""
    match_dst = ["-m", "set", "--match-set", IPSET_NAME, "dst"]
    rules = [
        ["-s", ip] + match_dst + ["-m", "comment", "--comment", f"{COMMENT_PREFIX}{ip}", "-j", "DROP"]
        for ip in sorted(device_ips, key=ipaddress.ip_address)
    ]
    rules.append(match_dst + ["-m", "comment", "--comment", f"{COMMENT_PREFIX}otros", "-j", "DROP"])
    rules.append(["-m", "set", "--match-set", IPSET_NAME, "src",
                  "-m", "comment", "--comment", f"{COMMENT_PREFIX}entrante", "-j", "DROP"])
    return rules


_SAVE_LINE = re.compile(r"^\[(\d+):(\d+)\] -A (\S+) .*--comment \"?([^\" ]+)\"?")


def parse_counters(save_output: str, chain: str = CHAIN) -> dict[str, int]:
    """Paquetes por regla (por su comentario) de `iptables-save -c`."""
    counters: dict[str, int] = {}
    for line in save_output.splitlines():
        m = _SAVE_LINE.match(line.strip())
        if m and m[3] == chain and m[4].startswith(COMMENT_PREFIX):
            key = m[4][len(COMMENT_PREFIX):]
            counters[key] = counters.get(key, 0) + int(m[1])
    return counters


def parse_ipset_hits(output: str) -> dict[str, int]:
    """Redes del ipset con paquetes (`ipset list` con contadores)."""
    hits = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1] == "packets" and parts[2].isdigit() and int(parts[2]) > 0:
            hits[parts[0]] = int(parts[2])
    return hits


_LOADED = re.compile(r"(\d+) rules successfully loaded, (\d+) rules failed")


def suricata_rules_loaded(log_text: str) -> tuple[int, int] | None:
    """(cargadas, fallidas) de la última carga de reglas que registra Suricata."""
    matches = _LOADED.findall(log_text)
    return (int(matches[-1][0]), int(matches[-1][1])) if matches else None


# ── Sistema ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60)


def _protected_networks() -> list[Net]:
    nets = []
    for addr in protection._local_addresses() | protection._gateway_addresses():
        if addr.version == 4:
            nets.append(ipaddress.ip_network(addr))
    for entry in settings.FIREWALL_NEVER_BLOCK:
        try:
            net = ipaddress.ip_network(entry, strict=False)
            if net.version == 4:
                nets.append(net)
        except ValueError:
            pass
    return nets


def _load_ipset(nets: list[Net]) -> str | None:
    """Carga las redes de forma atómica (conjunto temporal + swap). Error o None."""
    tmp = f"{IPSET_NAME}-nuevo"
    _run(["ipset", "destroy", tmp])
    created = _run(["ipset", "restore"], ipset_restore_script(tmp, nets))
    if created.returncode != 0:
        return f"ipset: {created.stderr.strip()[-200:]}"
    _run(["ipset", "create", IPSET_NAME, "hash:net", "family", "inet",
          "maxelem", str(MAX_ELEMENTS), "counters", "-exist"])
    swapped = _run(["ipset", "swap", tmp, IPSET_NAME])
    _run(["ipset", "destroy", tmp])
    return None if swapped.returncode == 0 else f"ipset swap: {swapped.stderr.strip()[-200:]}"


@dataclass
class ListStatus:
    name: str
    url: str | None
    entries: int = 0
    updated_at: str | None = None
    error: str | None = None
    nets: list[Net] = field(default_factory=list, repr=False)


class ThreatListService:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self.lists: dict[str, ListStatus] = {}
        self.total = 0
        self.removed_unsafe = 0
        self.applied_at: str | None = None
        self.error: str | None = None
        self._last_download = 0.0
        self._device_ips: list[str] | None = None
        self._counters: dict[str, int] = {}
        self._hits: dict[str, int] = {}
        self._update_now = asyncio.Event()

    # ── Arranque ──
    async def start(self) -> None:
        if not settings.THREAT_LISTS_ENABLED:
            await asyncio.to_thread(_run, ["iptables", "-F", CHAIN])
            log.info("threat_lists.disabled")
            return
        LISTS_DIR.mkdir(parents=True, exist_ok=True)
        # Lo descargado en otra ocasión se aplica ya; la descarga, después
        for name, url in parse_sources(settings.THREAT_LISTS):
            self.lists[name] = ListStatus(name, url)
            cached = LISTS_DIR / f"{name}.txt"
            if cached.exists():
                self._read_cached(self.lists[name], cached)
                self._last_download = max(self._last_download, cached.stat().st_mtime)
        await self._apply()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def request_update(self) -> None:
        self._update_now.set()

    @staticmethod
    def _read_cached(status: ListStatus, path: Path) -> None:
        status.nets = parse_list(path.read_text(errors="replace"))
        status.entries = len(status.nets)
        status.updated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    # ── Descarga ──
    async def _download_all(self) -> None:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True,
                                     headers={"User-Agent": "LanSentinel"}) as client:
            for name, status in self.lists.items():
                if status.url is None:
                    continue
                try:
                    data = bytearray()
                    async with client.stream("GET", status.url) as resp:
                        resp.raise_for_status()
                        async for chunk in resp.aiter_bytes():
                            data += chunk
                            if len(data) > MAX_DOWNLOAD_BYTES:
                                raise ValueError("la lista es demasiado grande")
                    text = data.decode(errors="replace")
                    nets = parse_list(text)
                    if not nets:
                        raise ValueError("la lista no contiene redes IPv4")
                    path = LISTS_DIR / f"{name}.txt"
                    path.with_suffix(".tmp").write_text(text)
                    path.with_suffix(".tmp").replace(path)
                    self._read_cached(status, path)
                    status.error = None
                except Exception as exc:     # se sigue con la copia anterior
                    status.error = f"No se pudo descargar: {exc}"
                    log.warning("threat_lists.download_failed", list=name, error=str(exc))
        self._last_download = time.time()

    # ── Aplicar ──
    async def _apply(self) -> None:
        own = ListStatus("propia", None)
        if OWN_LIST.exists():
            self._read_cached(own, OWN_LIST)
            self.lists["propia"] = own
        else:
            self.lists.pop("propia", None)
        all_nets = [n for status in self.lists.values() for n in status.nets]
        nets, removed = await asyncio.to_thread(sanitize, all_nets, _protected_networks())
        error = await asyncio.to_thread(_load_ipset, nets)
        if error:
            self.error = error
            log.error("threat_lists.ipset_failed", error=error)
            return
        self.total, self.removed_unsafe = sum(n.num_addresses for n in nets), removed
        self.applied_at = datetime.now(timezone.utc).isoformat()
        self.error = None
        self._hits = {}
        self._device_ips = None       # rehacer la cadena (y sus contadores)
        log.info("threat_lists.applied", networks=len(nets), addresses=self.total, removed_unsafe=removed)

    async def _sync_chain(self, device_ips: list[str]) -> None:
        if device_ips == self._device_ips:
            return
        for parent in ("FORWARD", "INPUT"):
            await iptables_manager._ensure_jump(parent, CHAIN, 4)
        await asyncio.to_thread(_run, ["iptables", "-F", CHAIN])
        for rule in chain_rules(device_ips):
            result = await asyncio.to_thread(_run, ["iptables", "-A", CHAIN] + rule)
            if result.returncode != 0:
                self.error = f"iptables: {result.stderr.strip()[-200:]}"
                log.error("threat_lists.rule_failed", rule=rule, error=result.stderr)
        self._device_ips = device_ips
        self._counters = {}

    # ── Bucle ──
    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                log.error("threat_lists.tick_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._update_now.wait(), timeout=CHECK_EVERY_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        due = time.time() - self._last_download > settings.THREAT_LISTS_UPDATE_HOURS * 3600
        if self._update_now.is_set() or due:
            self._update_now.clear()
            await self._download_all()
            await self._apply()
        async with AsyncSessionLocal() as db:
            devices = (await db.execute(select(Device).where(Device.ip.is_not(None)))).scalars().all()
        by_ip = {d.ip: d for d in devices if d.ip and ipaddress.ip_address(d.ip).version == 4}
        await self._sync_chain(sorted(by_ip))
        await self._check_counters(by_ip)

    async def _check_counters(self, by_ip: dict[str, Device]) -> None:
        saved = await asyncio.to_thread(_run, ["iptables-save", "-c", "-t", "filter"])
        current = parse_counters(saved.stdout)
        attempts = {}
        for key, packets in current.items():
            previous = self._counters.get(key, 0)
            delta = packets - previous if packets >= previous else packets
            if delta > 0 and key in by_ip:
                attempts[key] = delta
        self._counters = current
        if not attempts:
            return
        listed = await asyncio.to_thread(_run, ["ipset", "list", IPSET_NAME])
        hits = parse_ipset_hits(listed.stdout)
        new_hits = {net: n - self._hits.get(net, 0) for net, n in hits.items() if n > self._hits.get(net, 0)}
        self._hits = hits
        for ip, packets in attempts.items():
            await self._alert(by_ip[ip], packets, new_hits)

    def _lists_containing(self, net_text: str) -> list[str]:
        net = ipaddress.ip_network(net_text, strict=False)
        return [s.name for s in self.lists.values() if any(net.overlaps(n) for n in s.nets)]

    async def _alert(self, device: Device, packets: int, new_hits: dict[str, int]) -> None:
        name = device.hostname or device.vendor or device.ip
        top = sorted(new_hits.items(), key=lambda kv: kv[1], reverse=True)[:5]
        detail = "; ".join(f"{net} ({', '.join(self._lists_containing(net)) or '?'})" for net, _ in top)
        async with AsyncSessionLocal() as db:
            await create_alert(
                db,
                device_id=device.id,
                severity=AlertSeverity.high,
                source=AlertSource.firewall,
                title=f"{name} intentó conectar con IPs de listas de amenazas",
                description=(
                    f"El cortafuegos ha bloqueado {packets} paquetes de {device.ip} hacia redes "
                    f"conocidas por malware o botnets{': ' + detail if detail else ''}. Suele indicar "
                    "un programa malicioso en el dispositivo: revísalo o ponlo en cuarentena."
                ),
                raw_payload={"ip": device.ip, "packets": packets, "networks": dict(top)},
                fingerprint=f"threat_list:{device.ip}",
            )
        log.warning("threat_lists.device_blocked", ip=device.ip, packets=packets, networks=dict(top))

    # ── Estado ──
    def status(self) -> dict:
        outgoing = sum(v for k, v in self._counters.items() if k != "entrante")
        suricata: dict = {}
        try:
            suricata = json.loads(SURICATA_STATUS.read_text())
        except (OSError, ValueError):
            pass
        try:
            with SURICATA_LOG.open("rb") as f:
                f.seek(max(0, SURICATA_LOG.stat().st_size - 512 * 1024))
                loaded = suricata_rules_loaded(f.read().decode(errors="replace"))
        except OSError:
            loaded = None
        return {
            "enabled": settings.THREAT_LISTS_ENABLED,
            "lists": [
                {"name": s.name, "url": s.url, "entries": s.entries, "updated_at": s.updated_at, "error": s.error}
                for s in self.lists.values()
            ],
            "addresses": self.total,
            "removed_unsafe": self.removed_unsafe,
            "applied_at": self.applied_at,
            "update_hours": settings.THREAT_LISTS_UPDATE_HOURS,
            "blocked_outgoing": outgoing,
            "blocked_incoming": self._counters.get("entrante", 0),
            "error": self.error,
            "suricata": {
                "rules": suricata.get("rules"),
                "last_success_at": suricata.get("last_success_at"),
                "error": suricata.get("error"),
                "loaded": loaded[0] if loaded else None,
                "failed": loaded[1] if loaded else None,
            },
        }


threat_lists = ThreatListService()
