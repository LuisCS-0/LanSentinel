"""
Comprobaciones antes de encender el modo router desde el panel.

El instalador ya las hace con --router, pero el modo también se puede
encender desde el panel en un equipo instalado sin él. Encenderlo con la red
mal preparada puede dejar sin conexión a toda la casa: la LAN con una IP que
cambia (la puerta de enlace de todos los equipos se movería), la salida a
Internet por la interfaz equivocada o, lo más habitual, dos servidores DHCP
en la misma red (el del router de la operadora y el de LanSentinel), que
reparten direcciones distintas y cada equipo acaba con la de uno u otro.

Cada comprobación dice qué falla y cómo arreglarlo. Las que fallan impiden
encenderlo; la de DHCP, si no se ha podido hacer, solo avisa.

La de DHCP pide una dirección (DHCPDISCOVER) por la LAN y escucha las
ofertas durante unos segundos, sin aceptar ninguna: el servidor que responda
no llega a asignar nada. Las ofertas del propio LanSentinel (dnsmasq, si el
modo ya está encendido) no cuentan.
"""

import asyncio
import ipaddress
import random
import threading
from dataclasses import asdict, dataclass

import netifaces
import structlog

from app.core.config import settings
from app.services.firewall.firewall_service import ip_forward_enabled

log = structlog.get_logger(__name__)

# Muchos servidores DHCP (dnsmasq, routers) hacen ping a la dirección antes
# de ofrecerla y tardan unos 3 s en responder la primera vez: se espera hasta
# 6 s y se repite la petición a los 2 s, como un cliente DHCP
PROBE_SECONDS = 6
RETRY_SECONDS = 2
COMMAND_TIMEOUT = 5


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    label: str
    detail: str
    fix: str | None = None
    blocking: bool = True         # si falla, no deja encender el modo router

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Address:
    interface: ipaddress.IPv4Interface
    dynamic: bool                 # asignada por DHCP (caduca)


@dataclass(frozen=True)
class DhcpOffer:
    server: str
    mac: str
    offered: str


@dataclass
class Facts:
    """Lo que se ha visto en el equipo; evaluate() decide con esto."""
    problem: str | None           # WAN_INTERFACE/MONITOR_INTERFACE mal (router_problem)
    wan: str
    lan: str
    lan_addresses: list[Address]
    wan_addresses: list[Address]
    default_routes: list[str]     # interfaces de las rutas por defecto
    ip_forward: bool
    dhcp_wanted: bool             # ROUTER_DHCP: LanSentinel dará DHCP
    dhcp_offers: list[DhcpOffer] | None = None
    dhcp_error: str | None = None


# ── Lectura de la salida de ip (funciones puras) ─────────────────────────────

def parse_addresses(output: str) -> list[Address]:
    """
    Direcciones de `ip -4 -o addr show dev X`. Las que da un servidor DHCP
    llevan "dynamic" (y un valid_lft que no es forever).
    """
    found = []
    for line in output.splitlines():
        words = line.split()
        if "inet" not in words:
            continue
        try:
            iface = ipaddress.IPv4Interface(words[words.index("inet") + 1])
        except (IndexError, ValueError):
            continue
        found.append(Address(iface, "dynamic" in words))
    return found


def parse_default_routes(output: str) -> list[str]:
    """Interfaces de las rutas por defecto de `ip -4 route show default`."""
    devs = []
    for line in output.splitlines():
        words = line.split()
        if words[:1] == ["default"] and "dev" in words and words.index("dev") + 1 < len(words):
            devs.append(words[words.index("dev") + 1])
    return devs


def offers_from_packets(packets, own_ips: set[str]) -> list[DhcpOffer]:
    """Ofertas DHCP de otros servidores (una por servidor), sin las propias."""
    from scapy.layers.dhcp import BOOTP, DHCP
    from scapy.layers.inet import IP
    from scapy.layers.l2 import Ether

    offers: dict[str, DhcpOffer] = {}
    for p in packets:
        if BOOTP not in p:
            continue
        options = p[DHCP].options if DHCP in p else []
        server = next((o[1] for o in options if isinstance(o, tuple) and o[0] == "server_id"), None)
        server = server or (p[IP].src if IP in p else "?")
        if server in own_ips or (IP in p and p[IP].src in own_ips):
            continue
        mac = p[Ether].src.upper() if Ether in p else "?"
        offers.setdefault(server, DhcpOffer(server, mac, p[BOOTP].yiaddr))
    return list(offers.values())


# ── Evaluación (función pura) ────────────────────────────────────────────────

def _static_ip_fix(lan: str) -> str:
    return (
        f"Pon una IP fija en {lan} desde el sistema (no se cambia desde aquí para no cortar la "
        f"conexión). Por ejemplo, con netplan, en /etc/netplan/60-lansentinel.yaml pon para {lan} "
        "«dhcp4: false» y «addresses: [192.168.50.1/24]», y aplícala con 'sudo netplan try' "
        "(se deshace sola si pierdes la conexión)."
    )


def evaluate(f: Facts) -> list[Check]:
    if f.problem:
        return [Check(
            "interfaces", False, "Interfaces WAN y LAN", f.problem,
            "Conecta la segunda tarjeta de red y vuelve a ejecutar sudo scripts/instalar.sh: "
            "detecta cuál va al router de la operadora (WAN) y cuál a la red de casa (LAN).",
        )]
    checks = [Check("interfaces", True, "Interfaces WAN y LAN", f"WAN {f.wan} · LAN {f.lan}")]

    # La LAN es la puerta de enlace de toda la red: su IP no puede cambiar
    lan = f.lan_addresses[0] if f.lan_addresses else None
    if lan is None:
        checks.append(Check("lan_ip", False, "IP fija en la LAN", f"{f.lan} no tiene dirección IPv4",
                            _static_ip_fix(f.lan)))
    elif lan.dynamic:
        checks.append(Check("lan_ip", False, "IP fija en la LAN",
                            f"{f.lan} tiene {lan.interface}, pero la da un servidor DHCP y puede cambiar",
                            _static_ip_fix(f.lan)))
    else:
        checks.append(Check("lan_ip", True, "IP fija en la LAN", f"{f.lan} tiene {lan.interface} (fija)"))

    # La WAN necesita dirección y estar en otra red que la LAN
    wan = f.wan_addresses[0] if f.wan_addresses else None
    if wan is None:
        checks.append(Check("wan_ip", False, "Dirección en la WAN", f"{f.wan} no tiene dirección IPv4",
                            f"Conecta {f.wan} al router de la operadora: debe recibir una IP por DHCP "
                            "(o tener una fija en su red)."))
    elif lan and lan.interface.network.overlaps(wan.interface.network):
        checks.append(Check("wan_ip", False, "Dirección en la WAN",
                            f"La LAN ({lan.interface.network}) y la WAN ({wan.interface.network}) "
                            "están en la misma red: no se puede enrutar entre ellas",
                            "Usa en la LAN una red distinta de la del router de la operadora, "
                            "por ejemplo 192.168.50.1/24."))
    else:
        checks.append(Check("wan_ip", True, "Dirección en la WAN", f"{f.wan} tiene {wan.interface}"))

    # La salida a Internet tiene que ir por la WAN
    if not f.default_routes:
        checks.append(Check("default_route", False, "Salida a Internet por la WAN",
                            "El equipo no tiene ruta por defecto (no sale a Internet)",
                            f"Conecta {f.wan} al router de la operadora y comprueba que recibe "
                            "IP y puerta de enlace por DHCP."))
    elif f.wan not in f.default_routes:
        checks.append(Check("default_route", False, "Salida a Internet por la WAN",
                            f"La ruta por defecto va por {', '.join(f.default_routes)}, no por {f.wan}",
                            f"Quita la puerta de enlace de {f.lan} en la configuración de red del "
                            f"sistema (gateway4 o routes en netplan): la salida debe ir por {f.wan}."))
    else:
        checks.append(Check("default_route", True, "Salida a Internet por la WAN",
                            f"La ruta por defecto va por {f.wan}"))

    if f.ip_forward:
        checks.append(Check("ip_forward", True, "Reenvío de paquetes", "net.ipv4.ip_forward=1"))
    else:
        checks.append(Check("ip_forward", False, "Reenvío de paquetes",
                            "El sistema no reenvía paquetes entre interfaces (net.ipv4.ip_forward=0)",
                            "Vuelve a ejecutar sudo scripts/instalar.sh (lo deja activado de forma "
                            "permanente) o, para probar, sudo sysctl -w net.ipv4.ip_forward=1."))

    # Dos servidores DHCP en la misma red rompen la red de casa
    if f.dhcp_wanted:
        if f.dhcp_error:
            checks.append(Check("dhcp", False, "Ningún otro servidor DHCP en la LAN",
                                f"No se ha podido comprobar: {f.dhcp_error}",
                                "Asegúrate de que el router de la operadora no da DHCP en la LAN.",
                                blocking=False))
        elif f.dhcp_offers:
            servers = ", ".join(f"{o.server} ({o.mac})" for o in f.dhcp_offers)
            checks.append(Check("dhcp", False, "Ningún otro servidor DHCP en la LAN",
                                f"Ya reparte direcciones en {f.lan}: {servers}",
                                "Desactiva el DHCP de ese equipo (en el router de la operadora suele "
                                "estar en LAN o DHCP; o ponlo en modo bridge). Si prefieres que lo siga "
                                "dando él, desactiva el DHCP de LanSentinel (ROUTER_DHCP=false)."))
        else:
            checks.append(Check("dhcp", True, "Ningún otro servidor DHCP en la LAN",
                                f"Nadie más ha respondido en {f.lan}"))
    return checks


def failures(checks: list[Check]) -> list[Check]:
    """Las que impiden encender el modo router."""
    return [c for c in checks if not c.ok and c.blocking]


# ── Recogida de datos del equipo ─────────────────────────────────────────────

async def _ip(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), COMMAND_TIMEOUT)
        return out.decode(errors="replace")
    except (OSError, asyncio.TimeoutError) as exc:
        log.error("router_checks.ip_failed", args=args, error=str(exc))
        return ""


def _own_ipv4() -> set[str]:
    own = set()
    for name in netifaces.interfaces():
        own.update(a["addr"] for a in netifaces.ifaddresses(name).get(netifaces.AF_INET, []))
    return own


def probe_dhcp(interface: str, timeout: float = PROBE_SECONDS) -> list:
    """
    Envía un DHCPDISCOVER por la interfaz y devuelve las respuestas (síncrono,
    Scapy no es async). Pide la respuesta en difusión (flag broadcast): así
    llega aunque la dirección ofrecida no sea la del equipo. Termina con la
    primera oferta o al agotar el tiempo.
    """
    # Import tardío: Scapy tarda en cargar y avisa si no hay raw sockets
    from scapy.arch import get_if_hwaddr
    from scapy.layers.dhcp import BOOTP, DHCP
    from scapy.layers.inet import IP, UDP
    from scapy.layers.l2 import Ether
    from scapy.sendrecv import AsyncSniffer, sendp
    from scapy.utils import mac2str

    mac = get_if_hwaddr(interface)
    xid = random.getrandbits(32)
    started = threading.Event()

    def is_answer(p) -> bool:
        return BOOTP in p and p[BOOTP].op == 2 and p[BOOTP].xid == xid

    sniffer = AsyncSniffer(
        iface=interface, filter="udp and dst port 68", timeout=timeout,
        lfilter=is_answer, stop_filter=is_answer, started_callback=started.set,
    )
    sniffer.start()
    started.wait(2)
    discover = (
        Ether(src=mac, dst="ff:ff:ff:ff:ff:ff")
        / IP(src="0.0.0.0", dst="255.255.255.255")
        / UDP(sport=68, dport=67)
        / BOOTP(chaddr=mac2str(mac), xid=xid, flags=0x8000)
        / DHCP(options=[("message-type", "discover"), "end"])
    )
    sendp(discover, iface=interface, verbose=0)
    sniffer.join(RETRY_SECONDS)
    if sniffer.running:
        sendp(discover, iface=interface, verbose=0)
        sniffer.join()
    return list(sniffer.results or [])


async def run(problem: str | None) -> list[Check]:
    """Hace todas las comprobaciones (la de DHCP tarda unos segundos)."""
    wan, lan = settings.WAN_INTERFACE.strip(), settings.MONITOR_INTERFACE
    facts = Facts(problem=problem, wan=wan, lan=lan, lan_addresses=[], wan_addresses=[],
                  default_routes=[], ip_forward=ip_forward_enabled(), dhcp_wanted=settings.ROUTER_DHCP)
    if problem:
        return evaluate(facts)
    lan_out, wan_out, routes = await asyncio.gather(
        _ip("-4", "-o", "addr", "show", "dev", lan),
        _ip("-4", "-o", "addr", "show", "dev", wan),
        _ip("-4", "route", "show", "default"),
    )
    facts.lan_addresses = parse_addresses(lan_out)
    facts.wan_addresses = parse_addresses(wan_out)
    facts.default_routes = parse_default_routes(routes)
    if settings.ROUTER_DHCP:
        try:
            packets = await asyncio.get_running_loop().run_in_executor(None, probe_dhcp, lan)
            facts.dhcp_offers = offers_from_packets(packets, _own_ipv4())
        except PermissionError:
            facts.dhcp_error = "faltan permisos para enviar paquetes (CAP_NET_RAW)"
        except Exception as exc:
            facts.dhcp_error = str(exc) or type(exc).__name__
    checks = evaluate(facts)
    log.info("router_checks.done", failed=[c.id for c in checks if not c.ok])
    return checks
