"""
Conexiones abiertas de cada dispositivo, leídas de la tabla conntrack.

El kernel del equipo que hace de gateway lleva la cuenta de cada conexión que
lo atraviesa (para el NAT y para iptables). Esa tabla se lee con la
herramienta `conntrack` (por netlink: /proc/net/nf_conntrack no existe en
muchos kernels, como los de Ubuntu). Requiere NET_ADMIN, que el backend ya
tiene, y verla desde la red del equipo (network_mode: host).

Limitación: solo aparecen las conexiones que pasan por LanSentinel (las que
salen a Internet y las dirigidas al propio equipo). El tráfico entre dos
dispositivos de la LAN conectados al mismo switch no llega aquí. Por ahora
solo IPv4: los dispositivos se identifican por su IPv4.

Formato de una línea de `conntrack -L` (dos tuplas: original y respuesta):
  tcp 6 431999 ESTABLISHED src=A dst=B sport=1 dport=2 src=B dst=NAT
      sport=2 dport=1 [ASSURED] mark=0 use=1

Qué se considera "abierta". La tabla guarda más cosas que conexiones vivas:
  - Una consulta DNS o NTP es una pregunta y una respuesta, pero el kernel la
    recuerda ~30 s. Sin la marca [ASSURED] (tráfico sostenido en los dos
    sentidos) es un intercambio terminado, no una conexión: "done".
  - Una conexión TCP establecida se recuerda hasta 5 días sin tráfico. Si el
    equipo se apaga sin cerrarla queda ahí. Como el contador de la entrada se
    reinicia con cada paquete, timeout - expires_in es el tiempo sin tráfico:
    a partir de IDLE_AFTER se marca como "idle" (puede ser legítima, como una
    SSH en reposo, o un resto de una conexión ya muerta).
"""

import asyncio
import ipaddress
import subprocess
from dataclasses import dataclass

import structlog

from app.services.firewall.ipv6_lan import ipv6_lan
from app.services.monitor.neighbors import neighbors

log = structlog.get_logger(__name__)

# Estados TCP en los que la conexión ya se está cerrando o está cerrada
_CLOSING_STATES = {"FIN_WAIT", "CLOSE_WAIT", "LAST_ACK", "TIME_WAIT", "CLOSE"}

# Sin tráfico durante este tiempo, una conexión TCP establecida pasa a "idle"
IDLE_AFTER = 30 * 60

_TIMEOUTS_DIR = "/proc/sys/net/netfilter"


@dataclass(frozen=True)
class Timeouts:
    """Tiempos (s) que el kernel guarda cada tipo de entrada sin tráfico."""
    tcp_established: int = 432000
    # Con datos enviados aún sin confirmar (una transferencia en curso), el
    # kernel aplica este temporizador en lugar del de establecida
    tcp_unacknowledged: int = 300
    udp: int = 30
    udp_stream: int = 120


def read_timeouts() -> Timeouts:
    """Los del kernel (sysctl nf_conntrack_*); los predeterminados si no se pueden leer."""
    def read(name: str, default: int) -> int:
        try:
            with open(f"{_TIMEOUTS_DIR}/nf_conntrack_{name}") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return default
    d = Timeouts()
    return Timeouts(
        tcp_established=read("tcp_timeout_established", d.tcp_established),
        tcp_unacknowledged=read("tcp_timeout_unacknowledged", d.tcp_unacknowledged),
        udp=read("udp_timeout", d.udp),
        udp_stream=read("udp_timeout_stream", d.udp_stream),
    )

# Nombres de los servicios más habituales, para que la tabla del panel diga
# "HTTPS" en vez de solo 443
SERVICE_NAMES: dict[int, str] = {
    20: "FTP", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    67: "DHCP", 68: "DHCP", 80: "HTTP", 110: "POP3", 123: "NTP", 137: "NetBIOS",
    138: "NetBIOS", 139: "NetBIOS", 143: "IMAP", 161: "SNMP", 443: "HTTPS",
    445: "SMB", 465: "SMTPS", 587: "SMTP", 853: "DNS sobre TLS", 993: "IMAPS",
    995: "POP3S", 1194: "OpenVPN", 1883: "MQTT", 1900: "SSDP", 3074: "Xbox Live",
    3389: "RDP", 3478: "STUN", 5222: "XMPP", 5228: "Google Play", 5353: "mDNS",
    5900: "VNC", 8080: "HTTP", 8443: "HTTPS", 8883: "MQTT (TLS)", 51820: "WireGuard",
}


@dataclass
class ConntrackEntry:
    """Una conexión de la tabla conntrack, tal como la ve el kernel."""
    protocol: str
    state: str | None            # estado TCP; None en UDP/ICMP
    expires_in: int              # segundos hasta que el kernel la olvide
    orig_src: str
    orig_dst: str
    orig_sport: int | None
    orig_dport: int | None
    reply_src: str | None        # quien responde (distinto de orig_dst si hay DNAT)
    reply_sport: int | None
    replied: bool                # False si lleva la marca [UNREPLIED]
    assured: bool = False        # [ASSURED]: tráfico en los dos sentidos más de una vez


# ── Parseo (funciones puras) ─────────────────────────────────────────────────

def _port(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def parse_conntrack_line(line: str) -> ConntrackEntry | None:
    """Convierte una línea de `conntrack -L` en una entrada; None si no se entiende."""
    parts = line.split()
    if len(parts) < 4 or not parts[2].isdigit():
        return None
    protocol, expires_in = parts[0], int(parts[2])

    state = None
    tuples: list[dict[str, str]] = []
    replied = True
    assured = False
    for token in parts[3:]:
        if token == "[UNREPLIED]":
            replied = False
        elif token == "[ASSURED]":
            assured = True
        elif "=" in token:
            key, value = token.split("=", 1)
            # Cada "src=" abre una tupla: la primera es la original, la segunda la respuesta
            if key == "src":
                tuples.append({})
            if tuples:
                tuples[-1][key] = value
        elif not tuples and token.isupper():
            state = token

    if not tuples or "src" not in tuples[0] or "dst" not in tuples[0]:
        return None
    orig = tuples[0]
    reply = tuples[1] if len(tuples) > 1 else {}
    return ConntrackEntry(
        protocol=protocol,
        state=state,
        expires_in=expires_in,
        orig_src=orig["src"],
        orig_dst=orig["dst"],
        orig_sport=_port(orig.get("sport")),
        orig_dport=_port(orig.get("dport")),
        reply_src=reply.get("src"),
        reply_sport=_port(reply.get("sport")),
        replied=replied,
        assured=assured,
    )


def parse_conntrack(output: str) -> list[ConntrackEntry]:
    entries = []
    for line in output.splitlines():
        entry = parse_conntrack_line(line)
        if entry:
            entries.append(entry)
    return entries


def idle_seconds(entry: ConntrackEntry, t: Timeouts) -> int | None:
    """Segundos sin tráfico, cuando se pueden deducir del temporizador del kernel."""
    if entry.protocol == "tcp" and entry.state == "ESTABLISHED":
        # Temporizador por debajo del de datos sin confirmar: hay datos en
        # vuelo, así que la conexión está en uso ahora mismo (si no, una
        # descarga activa saldría con días "sin tráfico")
        if entry.expires_in <= t.tcp_unacknowledged:
            return 0
        total = t.tcp_established
    elif entry.protocol == "udp":
        total = t.udp_stream if entry.assured else t.udp
    else:
        return None
    return max(0, total - entry.expires_in)


def _status(entry: ConntrackEntry, idle: int | None) -> str:
    """
    open (en uso), idle (TCP establecida pero sin tráfico hace rato), pending
    (sin respuesta), done (intercambio suelto ya terminado, como una consulta
    DNS) o closing (TCP cerrándose).
    """
    if entry.state in _CLOSING_STATES:
        return "closing"
    if not entry.replied or entry.state in {"SYN_SENT", "SYN_RECV"}:
        return "pending"
    if entry.protocol == "tcp":
        return "idle" if idle is not None and idle >= IDLE_AFTER else "open"
    # UDP, ICMP...: solo es una conexión si hay tráfico sostenido
    return "open" if entry.assured else "done"


def _is_lan(ip: str) -> bool:
    """
    Dirección de la red de casa. En IPv4, cualquier privada. En IPv6 no basta
    con eso (una ULA puede estar al otro lado de la WAN y las de casa suelen
    ser públicas): de enlace local, del prefijo de la LAN o de un dispositivo
    de la tabla de vecinos.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 4:
        return addr.is_private
    if addr.is_link_local:
        return True
    plan = ipv6_lan.plan
    if plan and addr in ipaddress.ip_network(plan.prefix):
        return True
    return neighbors.mac_of(ip) is not None


_STATUS_ORDER = {"open": 0, "idle": 1, "pending": 2, "done": 3, "closing": 4}


def _view_from(e: ConntrackEntry, ip: str, t: Timeouts) -> dict | None:
    """
    La conexión vista desde el equipo con esa IP, o None si no participa:
      - saliente: la abre él (origen original = su IP)
      - entrante: la abre otro equipo hacia él, directamente o a través de
        una redirección de puertos (DNAT: quien responde es su IP)
    """
    if e.orig_src == ip:
        direction, local_port = "outgoing", e.orig_sport
        remote_ip, remote_port = e.orig_dst, e.orig_dport
        service_port = remote_port
    elif e.orig_dst == ip or e.reply_src == ip:
        direction = "incoming"
        local_port = e.reply_sport if e.reply_src == ip else e.orig_dport
        remote_ip, remote_port = e.orig_src, e.orig_sport
        service_port = local_port
    else:
        return None
    idle = idle_seconds(e, t)
    return {
        "protocol": e.protocol,
        "direction": direction,
        "local_port": local_port,
        "remote_ip": remote_ip,
        "remote_port": remote_port,
        "remote_is_lan": _is_lan(remote_ip),
        "service": SERVICE_NAMES.get(service_port) if service_port else None,
        "state": e.state,
        "status": _status(e, idle),
        "idle_seconds": idle,
        "expires_in": e.expires_in,
    }


def connections_for_ip(entries: list[ConntrackEntry], device_ip: str, t: Timeouts = Timeouts()) -> list[dict]:
    """Conexiones en las que participa la IP del dispositivo, las abiertas primero."""
    result = [view for e in entries if (view := _view_from(e, device_ip, t))]
    result.sort(key=lambda c: (_STATUS_ORDER[c["status"]], c["remote_ip"], c["remote_port"] or 0))
    return result


def connections_for_devices(
    entries: list[ConntrackEntry], devices_by_ip: dict[str, str], t: Timeouts = Timeouts(),
) -> list[dict]:
    """
    Conexiones de todos los dispositivos conocidos ({ip: device_id}), cada una
    con el device_id de su dispositivo. Una conexión entre dos dispositivos
    conocidos aparece dos veces, una vista desde cada uno.
    """
    result = []
    for e in entries:
        for ip in {e.orig_src, e.orig_dst, e.reply_src}:
            device_id = devices_by_ip.get(ip) if ip else None
            if device_id and (view := _view_from(e, ip, t)):
                result.append({"device_id": device_id, **view})
    result.sort(key=lambda c: (_STATUS_ORDER[c["status"]], c["device_id"], c["remote_ip"]))
    return result


# ── Lectura de la tabla ──────────────────────────────────────────────────────

def _run_conntrack(family: str = "ipv4") -> str | None:
    """Vuelca la tabla de una familia; None si conntrack no está disponible o falla."""
    try:
        proc = subprocess.run(
            ["conntrack", "-L", "-f", family], capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        log.warning("conntrack.not_found", hint="Instala el paquete conntrack en la imagen del backend")
        return None
    except subprocess.TimeoutExpired:
        log.error("conntrack.timeout")
        return None
    if proc.returncode != 0:
        # Sin NET_ADMIN, o sin el módulo nf_conntrack cargado
        log.warning("conntrack.failed", error=proc.stderr.strip())
        return None
    return proc.stdout


async def _read_table() -> list[ConntrackEntry] | None:
    """Tabla IPv4 y, si hay, IPv6 (la de IPv6 no es imprescindible)."""
    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(None, _run_conntrack, "ipv4")
    if output is None:
        return None
    entries = parse_conntrack(output)
    output6 = await loop.run_in_executor(None, _run_conntrack, "ipv6")
    if output6:
        entries += parse_conntrack(output6)
    return entries


async def device_connections(device_ip: str, ipv6: list[str] = ()) -> list[dict] | None:
    """Conexiones actuales del dispositivo (su IPv4 y sus IPv6); None si no se puede leer la tabla."""
    entries = await _read_table()
    if entries is None:
        return None
    t = read_timeouts()
    result = [c for ip in [device_ip, *ipv6] for c in connections_for_ip(entries, ip, t)]
    result.sort(key=lambda c: (_STATUS_ORDER[c["status"]], c["remote_ip"], c["remote_port"] or 0))
    return result


async def network_connections(devices_by_ip: dict[str, str]) -> list[dict] | None:
    """Conexiones actuales de todos los dispositivos; None si no se puede leer la tabla."""
    entries = await _read_table()
    return connections_for_devices(entries, devices_by_ip, read_timeouts()) if entries is not None else None
