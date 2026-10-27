"""
Los puertos en los que escucha el propio equipo de LanSentinel, leídos de
/proc/net (el backend usa la red del equipo, así que ve los mismos). Solo
el puerto, el protocolo y si escucha solo para el propio equipo o para
toda la red: nunca direcciones.
"""

from pathlib import Path

from app.services.ai_audit.snapshot import RawListener

_PROC = Path("/proc/net")
_TCP_LISTEN = "0A"
_UDP_UNCONNECTED = "07"
_WIDER = {"solo_el_equipo": 0, "una_direccion": 1, "toda_la_red": 2}


def _scope(hex_addr: str) -> str:
    if set(hex_addr) == {"0"}:
        return "toda_la_red"
    # IPv4 en orden de host (127.0.0.1 → 0100007F) o IPv6 (::1 → ...01000000)
    if len(hex_addr) == 8:
        return "solo_el_equipo" if hex_addr.endswith("7F") else "una_direccion"
    if hex_addr == "00000000000000000000000001000000":
        return "solo_el_equipo"
    if hex_addr.startswith("0000000000000000FFFF0000") and hex_addr.endswith("7F"):
        return "solo_el_equipo"                    # ::ffff:127.x
    return "una_direccion"


def parse_proc_net(text: str, protocol: str) -> list[RawListener]:
    """Las entradas en escucha de un fichero de /proc/net (tcp, tcp6, udp, udp6)."""
    wanted = _TCP_LISTEN if protocol == "tcp" else _UDP_UNCONNECTED
    result = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or parts[3] != wanted or ":" not in parts[1]:
            continue
        addr, port_hex = parts[1].rsplit(":", 1)
        port = int(port_hex, 16)
        if port:
            result.append(RawListener(protocol, port, _scope(addr)))
    return result


def merge(listeners: list[RawListener]) -> list[RawListener]:
    """Un puerto por protocolo, con su alcance más amplio (IPv4 e IPv6 juntos)."""
    best: dict[tuple[str, int], RawListener] = {}
    for x in listeners:
        key = (x.protocol, x.port)
        if key not in best or _WIDER[x.scope] > _WIDER[best[key].scope]:
            best[key] = x
    return list(best.values())


def read_listeners() -> list[RawListener] | None:
    found = []
    try:
        for name, protocol in (("tcp", "tcp"), ("tcp6", "tcp"), ("udp", "udp"), ("udp6", "udp")):
            path = _PROC / name
            if path.exists():
                found += parse_proc_net(path.read_text(), protocol)
    except OSError:
        return None
    # Los puertos UDP efímeros (respuestas de DNS, NTP...) no son servicios
    return merge([x for x in found if x.protocol == "tcp" or x.port < 32768])
