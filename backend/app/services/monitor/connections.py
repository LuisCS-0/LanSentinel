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
"""

import asyncio
import ipaddress
import subprocess
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

# Estados TCP en los que la conexión ya se está cerrando o está cerrada
_CLOSING_STATES = {"FIN_WAIT", "CLOSE_WAIT", "LAST_ACK", "TIME_WAIT", "CLOSE"}

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
    for token in parts[3:]:
        if token == "[UNREPLIED]":
            replied = False
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
    )


def parse_conntrack(output: str) -> list[ConntrackEntry]:
    entries = []
    for line in output.splitlines():
        entry = parse_conntrack_line(line)
        if entry:
            entries.append(entry)
    return entries


def _status(entry: ConntrackEntry) -> str:
    """open (en uso), pending (aún sin respuesta) o closing (cerrándose)."""
    if entry.state in _CLOSING_STATES:
        return "closing"
    if not entry.replied or entry.state in {"SYN_SENT", "SYN_RECV"}:
        return "pending"
    return "open"


def _is_lan(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def connections_for_ip(entries: list[ConntrackEntry], device_ip: str) -> list[dict]:
    """
    Conexiones en las que participa la IP del dispositivo, vistas desde él:
      - salientes: las abre el dispositivo (origen original = su IP)
      - entrantes: las abre otro equipo hacia él, directamente o a través
        de una redirección de puertos (DNAT: quien responde es su IP)
    Ordenadas con las abiertas primero.
    """
    result = []
    for e in entries:
        if e.orig_src == device_ip:
            direction, local_port = "outgoing", e.orig_sport
            remote_ip, remote_port = e.orig_dst, e.orig_dport
            service_port = remote_port
        elif e.orig_dst == device_ip or e.reply_src == device_ip:
            direction = "incoming"
            local_port = e.reply_sport if e.reply_src == device_ip else e.orig_dport
            remote_ip, remote_port = e.orig_src, e.orig_sport
            service_port = local_port
        else:
            continue
        result.append({
            "protocol": e.protocol,
            "direction": direction,
            "local_port": local_port,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "remote_is_lan": _is_lan(remote_ip),
            "service": SERVICE_NAMES.get(service_port) if service_port else None,
            "state": e.state,
            "status": _status(e),
            "expires_in": e.expires_in,
        })

    order = {"open": 0, "pending": 1, "closing": 2}
    result.sort(key=lambda c: (order[c["status"]], c["remote_ip"], c["remote_port"] or 0))
    return result


# ── Lectura de la tabla ──────────────────────────────────────────────────────

def _run_conntrack() -> str | None:
    """Vuelca la tabla IPv4; None si conntrack no está disponible o falla."""
    try:
        proc = subprocess.run(
            ["conntrack", "-L", "-f", "ipv4"], capture_output=True, text=True, timeout=10,
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


async def device_connections(device_ip: str) -> list[dict] | None:
    """Conexiones actuales del dispositivo; None si no se puede leer la tabla."""
    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(None, _run_conntrack)
    if output is None:
        return None
    return connections_for_ip(parse_conntrack(output), device_ip)
