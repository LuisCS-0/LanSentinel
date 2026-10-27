"""IPv6 en la LAN: prefijos, dhcpcd, reglas del router, dnsmasq, vecinos, conteo y conexiones."""

import ipaddress

import pytest

from app.services.firewall import iptables_manager as ipt
from app.services.firewall import ipv6_lan as v6
from app.services.firewall import auto_block
from app.services.firewall.auto_block import lan_block_allowed
from app.services.firewall.dhcp_dns import make_plan, render_config
from app.services.monitor import connections
from app.services.monitor.neighbors import FORGET_AFTER_SECONDS, NeighborTable, parse_neighbors
from app.services.monitor.traffic_meter import ipv6_rules, parse_counters6

MAC = "08:00:27:4A:04:3A"


# ── Prefijos ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    ("2a02:1234:5600::/56", "2a02:1234:5600::/64"),
    ("2a02:1234:5600:7::/64", "2a02:1234:5600:7::/64"),
    ("2a02:1234:5600:7::1/64", "2a02:1234:5600:7::/64"),      # con la dirección del router
])
def test_normalize_prefix(text, expected):
    assert str(v6.normalize_prefix(text)) == expected


@pytest.mark.parametrize("text", ["2a02:1234::/80", "192.168.1.0/24", "basura"])
def test_normalize_prefix_invalido(text):
    with pytest.raises(ValueError):
        v6.normalize_prefix(text)


def test_ula():
    prefix = v6.make_ula(bytes([0x12, 0x34, 0x56, 0x78, 0x9a]))
    assert str(prefix) == "fd12:3456:789a::/64"
    assert v6.router_address(prefix) == "fd12:3456:789a::1"
    assert prefix.is_private


IP_ADDR = """\
3: enp0s8    inet6 2a02:1234:5600:7::1/64 scope global dynamic noprefixroute \\       valid_lft 86000sec preferred_lft 14000sec
3: enp0s8    inet6 fd12:3456:789a::1/64 scope global \\       valid_lft forever preferred_lft forever
"""


def test_prefijo_delegado_por_dhcpcd():
    addresses = v6.parse_global_addresses(IP_ADDR)
    assert addresses == [("2a02:1234:5600:7::1", 64), ("fd12:3456:789a::1", 64)]
    plan = v6.pick_delegated(addresses, own="fd12:3456:789a::1")
    assert plan == v6.Ipv6Plan("2a02:1234:5600:7::/64", "2a02:1234:5600:7::1", "pd", False)
    # La ULA propia (o cualquier dirección privada) no es un prefijo delegado
    assert v6.pick_delegated([("fd12:3456:789a::1", 64)], own=None) is None


def test_dhcpcd_solo_pide_prefijo():
    conf = v6.render_dhcpcd_conf("enp0s3", "enp0s8")
    lines = [line.strip() for line in conf.splitlines()]
    assert "ipv6only" in lines and "noipv6rs" in lines
    assert "allowinterfaces enp0s3" in lines and "ia_pd 1 enp0s8/0/64/1" in lines
    assert not any(line.startswith("ia_na") for line in lines)     # ninguna dirección en la WAN


# ── Cortafuegos del router ───────────────────────────────────────────────────

def test_router_ipv6_cierra_la_entrada_desde_internet():
    rules = ipt.router_rules("enp0s3", "enp0s8", 6, ipv6_forward=True)
    route = rules[("filter", ipt.CHAIN_ROUTE)]
    assert ["-i", "enp0s8", "-o", "enp0s3", "-j", "ACCEPT"] in route
    assert "RELATED,ESTABLISHED" in route[0] and route[0][-1] == "ACCEPT"
    # Lo último: nada nuevo de la WAN llega a la LAN (FORWARD de ip6tables suele ser ACCEPT)
    assert route[-1][:4] == ["-i", "enp0s3", "-o", "enp0s8"] and route[-1][-1] == "DROP"
    assert ("nat", ipt.CHAIN_NAT) not in rules


def test_router_ipv6_nat66_con_la_ula():
    rules = ipt.router_rules("enp0s3", "enp0s8", 6, ipv6_forward=True, nat66_source="fd12:3456:789a::/64")
    assert rules[("nat", ipt.CHAIN_NAT)] == [["-s", "fd12:3456:789a::/64", "-o", "enp0s3", "-j", "MASQUERADE"]]


def test_router_ipv4_no_cambia_con_ipv6():
    assert ipt.router_rules("enp0s3", "enp0s8", 4, ipv6_forward=True) == ipt.router_rules("enp0s3", "enp0s8", 4)


# ── dnsmasq ──────────────────────────────────────────────────────────────────

def test_dnsmasq_anuncia_ipv6():
    conf = render_config(make_plan("enp0s8", "192.168.56.10", "fd12:3456:789a::1"))
    assert "enable-ra" in conf
    assert "dhcp-range=::,constructor:enp0s8,ra-stateless,ra-names,64,12h" in conf
    assert "dhcp-option=option6:dns-server,[::]" in conf
    assert "host-record=lansentinel.lan,192.168.56.10,fd12:3456:789a::1" in conf


def test_dnsmasq_sin_ipv6():
    conf = render_config(make_plan("enp0s8", "192.168.56.10"))
    assert "enable-ra" not in conf and "host-record=lansentinel.lan,192.168.56.10\n" in conf


# ── Vecinos ──────────────────────────────────────────────────────────────────

NEIGH = f"""\
192.168.56.20 lladdr {MAC.lower()} STALE
fd12:3456:789a::5 lladdr {MAC.lower()} REACHABLE
2a02:1234:5600:7:a00:27ff:fe4a:43a lladdr {MAC.lower()} STALE
fe80::a00:27ff:fe4a:43a lladdr {MAC.lower()} STALE
192.168.56.99  FAILED
fd12:3456:789a::77 INCOMPLETE
"""


def test_parse_vecinos():
    pairs = parse_neighbors(NEIGH)
    assert ("192.168.56.20", MAC) in pairs and len(pairs) == 4


def test_ipv6_de_cada_dispositivo():
    t = NeighborTable()
    t.update(parse_neighbors(NEIGH), now=1000.0)
    assert t.ipv6_of(MAC) == ["2a02:1234:5600:7:a00:27ff:fe4a:43a", "fd12:3456:789a::5"]     # sin fe80
    assert t.device_ipv4("fd12:3456:789a::5") == "192.168.56.20"
    assert t.device_ipv4("192.168.56.20") == "192.168.56.20"
    assert t.device_ipv4("2001:db8::1") is None
    # Una dirección que deja de verse se olvida al cabo de un día
    t.update([("192.168.56.20", MAC)], now=1000.0 + FORGET_AFTER_SECONDS + 1)
    assert t.ipv6_of(MAC) == []


# ── Conteo ───────────────────────────────────────────────────────────────────

def test_reglas_de_conteo_ipv6():
    rules = ipv6_rules("192.168.56.20", MAC, ["fd12:3456:789a::5"], "enp0s8")
    assert rules[f"192.168.56.20:tx:{MAC}"][:5] == ["-i", "enp0s8", "-m", "mac", "--mac-source"]
    assert rules["192.168.56.20:rx:fd12:3456:789a::5"][:2] == ["-d", "fd12:3456:789a::5"]


IP6TABLES_L = """\
Chain LANSENTINEL_ACCT (1 references)
    pkts      bytes target     prot opt in     out     source               destination
      10     1500            all      enp0s8 *       ::/0                 ::/0                 MAC 08:00:27:4A:04:3A /* lansentinel-traffic6:192.168.56.20:tx */
      20    30000            all      *      *       ::/0                 fd12:3456:789a::5    /* lansentinel-traffic6:192.168.56.20:rx */
       5      700            all      *      *       ::/0                 2a02:1234:5600:7::9  /* lansentinel-traffic6:192.168.56.20:rx */
"""


def test_contadores_ipv6_se_suman_a_la_ipv4():
    c = parse_counters6(IP6TABLES_L)["192.168.56.20"]
    assert (c.tx_bytes, c.rx_bytes, c.tx_packets, c.rx_packets) == (1500, 30700, 10, 25)


# ── Conexiones y bloqueo automático ──────────────────────────────────────────

CONNTRACK6 = (
    "tcp      6 431999 ESTABLISHED src=fd12:3456:789a::5 dst=2606:4700:4700::1111 sport=40000 dport=443 "
    "src=2606:4700:4700::1111 dst=2a02:1234:5600:7::1 sport=443 dport=40000 [ASSURED] mark=0 use=1"
)


def test_conexion_ipv6(monkeypatch):
    t = NeighborTable()
    t.update(parse_neighbors(NEIGH), now=1000.0)
    monkeypatch.setattr(connections, "neighbors", t)
    entry = connections.parse_conntrack_line(CONNTRACK6)
    c = connections.connections_for_ip([entry], "fd12:3456:789a::5")[0]
    assert c["remote_ip"] == "2606:4700:4700::1111" and c["direction"] == "outgoing"
    assert c["service"] == "HTTPS" and not c["remote_is_lan"]


def test_ipv6_de_la_lan_cuenta_como_lan(monkeypatch):
    t = NeighborTable()
    t.update(parse_neighbors(NEIGH), now=1000.0)
    monkeypatch.setattr(connections, "neighbors", t)
    assert connections._is_lan("2a02:1234:5600:7:a00:27ff:fe4a:43a")      # pública, pero de un equipo de casa
    assert connections._is_lan("fe80::1") and not connections._is_lan("2606:4700:4700::1111")
    # Una ULA al otro lado de la WAN (el router de la operadora) no es de casa
    assert not connections._is_lan("fd17:625c:f037:2::2")
    plan = v6.Ipv6Plan("2a02:1234:5600:7::/64", "2a02:1234:5600:7::1", "pd", False)
    monkeypatch.setattr(v6.ipv6_lan, "plan", plan)
    assert connections._is_lan("2a02:1234:5600:7::abcd")                   # del prefijo de la LAN


def test_bloqueo_automatico_trata_la_ipv6_de_casa_como_lan(monkeypatch):
    t = NeighborTable()
    t.update(parse_neighbors(NEIGH), now=1000.0)
    monkeypatch.setattr(auto_block, "neighbors", t)
    # Una regla de Emerging Threats desde la IPv6 pública de un equipo de casa: no se bloquea
    assert not lan_block_allowed("2a02:1234:5600:7:a00:27ff:fe4a:43a", 2012278)
    assert lan_block_allowed("2a02:1234:5600:7:a00:27ff:fe4a:43a", 1000010)
    assert lan_block_allowed("2606:4700:4700::1111", 2012278)             # de Internet


def test_ipaddress_ula_es_privada():
    # La lógica de LAN se apoya en esto: las ULA cuentan como privadas
    assert ipaddress.ip_address("fd12:3456:789a::5").is_private
