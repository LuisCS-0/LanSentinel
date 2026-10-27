"""Comprobaciones antes de encender el modo router desde el panel."""

import ipaddress

from app.services.firewall import router_checks as rc

ADDR_LAN_FIJA = (
    "3: enp0s8    inet 192.168.50.1/24 brd 192.168.50.255 scope global enp0s8\\"
    "       valid_lft forever preferred_lft forever\n"
)
ADDR_DINAMICA = (
    "2: enp0s3    inet 10.0.2.15/24 metric 100 brd 10.0.2.255 scope global dynamic enp0s3\\"
    "       valid_lft 85918sec preferred_lft 85918sec\n"
)
RUTAS = "default via 10.0.2.2 dev enp0s3 proto dhcp src 10.0.2.15 metric 100\n"


def _addr(cidr: str, dynamic: bool = False) -> rc.Address:
    return rc.Address(ipaddress.IPv4Interface(cidr), dynamic)


def _facts(**kw) -> rc.Facts:
    base = dict(
        problem=None, wan="enp0s3", lan="enp0s8",
        lan_addresses=[_addr("192.168.50.1/24")], wan_addresses=[_addr("10.0.2.15/24", True)],
        default_routes=["enp0s3"], ip_forward=True, dhcp_wanted=True, dhcp_offers=[],
    )
    return rc.Facts(**(base | kw))


def _by_id(checks: list[rc.Check]) -> dict[str, rc.Check]:
    return {c.id: c for c in checks}


# ── Lectura de la salida de ip ───────────────────────────────────────────────

def test_parse_addresses_distingue_fija_y_dinamica():
    assert rc.parse_addresses(ADDR_LAN_FIJA) == [_addr("192.168.50.1/24")]
    assert rc.parse_addresses(ADDR_DINAMICA) == [_addr("10.0.2.15/24", True)]
    assert rc.parse_addresses("") == []


def test_parse_default_routes():
    assert rc.parse_default_routes(RUTAS) == ["enp0s3"]
    dos = RUTAS + "default via 192.168.50.254 dev enp0s8 metric 200\n"
    assert rc.parse_default_routes(dos) == ["enp0s3", "enp0s8"]
    assert rc.parse_default_routes("") == []


# ── Evaluación ───────────────────────────────────────────────────────────────

def test_todo_correcto():
    checks = rc.evaluate(_facts())
    assert [c.id for c in checks] == ["interfaces", "lan_ip", "wan_ip", "default_route", "ip_forward", "dhcp"]
    assert all(c.ok for c in checks) and rc.failures(checks) == []


def test_interfaces_mal_no_sigue_comprobando():
    checks = rc.evaluate(_facts(problem="Falta WAN_INTERFACE en .env"))
    assert len(checks) == 1 and not checks[0].ok and "instalar.sh" in checks[0].fix


def test_lan_sin_ip_o_con_ip_de_dhcp():
    sin_ip = _by_id(rc.evaluate(_facts(lan_addresses=[])))["lan_ip"]
    assert not sin_ip.ok and "no tiene dirección" in sin_ip.detail and "netplan" in sin_ip.fix
    dinamica = _by_id(rc.evaluate(_facts(lan_addresses=[_addr("192.168.1.40/24", True)])))["lan_ip"]
    assert not dinamica.ok and "puede cambiar" in dinamica.detail


def test_lan_y_wan_en_la_misma_red():
    checks = _by_id(rc.evaluate(_facts(wan_addresses=[_addr("192.168.50.7/24", True)])))
    assert not checks["wan_ip"].ok and "misma red" in checks["wan_ip"].detail


def test_salida_por_la_lan_o_sin_salida():
    por_lan = _by_id(rc.evaluate(_facts(default_routes=["enp0s8"])))["default_route"]
    assert not por_lan.ok and "enp0s8" in por_lan.detail
    sin_ruta = _by_id(rc.evaluate(_facts(default_routes=[])))["default_route"]
    assert not sin_ruta.ok and "no tiene ruta" in sin_ruta.detail


def test_sin_reenvio():
    check = _by_id(rc.evaluate(_facts(ip_forward=False)))["ip_forward"]
    assert not check.ok and "sysctl" in check.fix


def test_otro_servidor_dhcp_impide_encenderlo():
    oferta = rc.DhcpOffer("192.168.50.254", "AA:BB:CC:00:11:22", "192.168.50.120")
    checks = rc.evaluate(_facts(dhcp_offers=[oferta]))
    dhcp = _by_id(checks)["dhcp"]
    assert not dhcp.ok and dhcp.blocking and "192.168.50.254" in dhcp.detail
    assert rc.failures(checks) == [dhcp]


def test_dhcp_sin_comprobar_solo_avisa():
    checks = rc.evaluate(_facts(dhcp_offers=None, dhcp_error="faltan permisos"))
    dhcp = _by_id(checks)["dhcp"]
    assert not dhcp.ok and not dhcp.blocking and rc.failures(checks) == []


def test_sin_dhcp_de_lansentinel_no_se_busca_otro():
    assert "dhcp" not in _by_id(rc.evaluate(_facts(dhcp_wanted=False)))


# ── Ofertas recibidas ────────────────────────────────────────────────────────

def _oferta(server: str, src: str, mac: str, ofrecida: str):
    from scapy.layers.dhcp import BOOTP, DHCP
    from scapy.layers.inet import IP, UDP
    from scapy.layers.l2 import Ether

    return (
        Ether(src=mac, dst="ff:ff:ff:ff:ff:ff") / IP(src=src, dst="255.255.255.255")
        / UDP(sport=67, dport=68) / BOOTP(op=2, yiaddr=ofrecida, xid=7)
        / DHCP(options=[("message-type", "offer"), ("server_id", server), "end"])
    )


def test_ofertas_sin_las_propias_y_una_por_servidor():
    paquetes = [
        _oferta("192.168.50.1", "192.168.50.1", "08:00:27:00:00:01", "192.168.50.150"),     # dnsmasq propio
        _oferta("192.168.50.254", "192.168.50.254", "aa:bb:cc:00:11:22", "192.168.50.120"),
        _oferta("192.168.50.254", "192.168.50.254", "aa:bb:cc:00:11:22", "192.168.50.121"),  # repetida
    ]
    ofertas = rc.offers_from_packets(paquetes, {"192.168.50.1", "10.0.2.15"})
    assert ofertas == [rc.DhcpOffer("192.168.50.254", "AA:BB:CC:00:11:22", "192.168.50.120")]
