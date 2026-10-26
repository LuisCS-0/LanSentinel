"""Cortafuegos: lectura de reglas, criterios de bloqueo, modo router y direcciones protegidas."""

import ipaddress

import pytest

from app.core.config import settings
from app.services.firewall import firewall_service as fs
from app.services.firewall import iptables_manager as ipt
from app.services.firewall import protection


# ── Lectura de `iptables -S` ─────────────────────────────────────────────────

IPTABLES_S = """\
-N LANSENTINEL_FWD
-P FORWARD DROP
-A LANSENTINEL_FWD -s 192.168.56.20/32 -m comment --comment lansentinel:1 -j DROP
-A LANSENTINEL_FWD -m mac --mac-source 08:00:27:4A:04:3A -m comment --comment lansentinel:12 -j DROP
-A LANSENTINEL_FWD -m comment --comment "texto con espacios" -j RETURN
"""


def test_parse_rule_specs_descarta_lo_que_no_son_reglas():
    specs = ipt.parse_rule_specs(IPTABLES_S)
    assert len(specs) == 3
    assert specs[0][:4] == ["-A", "LANSENTINEL_FWD", "-s", "192.168.56.20/32"]


def test_comment_of_completo_no_subcadena():
    specs = ipt.parse_rule_specs(IPTABLES_S)
    assert [ipt.comment_of(s) for s in specs] == ["lansentinel:1", "lansentinel:12", "texto con espacios"]
    # La regla 1 no se confunde con la 12
    assert [s for s in specs if ipt.comment_of(s) == "lansentinel:1"] == [specs[0]]
    assert ipt.comment_of(["-A", "X", "-j", "DROP"]) is None


def test_match_args_ip_por_familia_y_mac_en_ambas():
    mac = "08:00:27:4A:04:3A"
    assert ipt._match_args("192.168.56.20", mac, 4) == [["-s", "192.168.56.20"], ["-m", "mac", "--mac-source", mac]]
    # La IPv4 no va a ip6tables, la MAC sí: un bloqueado tampoco sale por IPv6
    assert ipt._match_args("192.168.56.20", mac, 6) == [["-m", "mac", "--mac-source", mac]]
    assert ipt._match_args("2001:db8::1", None, 6) == [["-s", "2001:db8::1"]]
    assert ipt._match_args(None, None, 4) == []
    assert ipt._ip_family("10.0.0.0/8") == 4 and ipt._ip_family("no-es-ip") is None


# ── Modo router ──────────────────────────────────────────────────────────────

def test_router_rules_ipv4():
    rules = ipt.router_rules("enp0s3", "enp0s8", 4)
    assert set(rules) == {("filter", ipt.CHAIN_WAN_IN), ("filter", ipt.CHAIN_ROUTE), ("nat", ipt.CHAIN_NAT)}
    wan_in = rules[("filter", ipt.CHAIN_WAN_IN)]
    # Desde la WAN: respuestas, ICMP y DHCP de cliente; lo demás se descarta, al final
    assert wan_in[-1][-2:] == ["-j", "DROP"] and all(r[:2] == ["-i", "enp0s3"] for r in wan_in)
    assert ["-i", "enp0s3", "-p", "udp", "--dport", "68", "-j", "RETURN"] in wan_in
    route = rules[("filter", ipt.CHAIN_ROUTE)]
    assert route[0][-2:] == ["-j", "DROP"] and "DNAT" in route[0]      # puertos publicados, cerrados a la WAN
    assert ["-i", "enp0s8", "-o", "enp0s3", "-j", "ACCEPT"] in route
    assert rules[("nat", ipt.CHAIN_NAT)] == [["-o", "enp0s3", "-j", "MASQUERADE"]]


def test_router_rules_ipv6_solo_cierra_la_wan():
    rules = ipt.router_rules("enp0s3", "enp0s8", 6)
    assert set(rules) == {("filter", ipt.CHAIN_WAN_IN)}
    flat = [x for r in rules[("filter", ipt.CHAIN_WAN_IN)] for x in r]
    assert "ipv6-icmp" in flat and "546" in flat and "icmp" not in flat


def test_router_problem(monkeypatch):
    monkeypatch.setattr(fs, "_interface_exists", lambda i: i in {"enp0s3", "enp0s8"})
    monkeypatch.setattr(settings, "MONITOR_INTERFACE", "enp0s8")
    monkeypatch.setattr(settings, "WAN_INTERFACE", "")
    assert "Falta WAN_INTERFACE" in fs.FirewallService.router_problem()
    monkeypatch.setattr(settings, "WAN_INTERFACE", "enp0s8")
    assert "misma interfaz" in fs.FirewallService.router_problem()
    monkeypatch.setattr(settings, "WAN_INTERFACE", "eth9")
    assert fs.FirewallService.router_problem() == "No existe la interfaz eth9"
    monkeypatch.setattr(settings, "WAN_INTERFACE", "enp0s3")
    assert fs.FirewallService.router_problem() is None


# ── Direcciones que nunca se bloquean ────────────────────────────────────────

@pytest.fixture
def red(monkeypatch):
    own = {ipaddress.ip_address(a) for a in ("192.168.56.10", "192.168.56.255", "fe80::a00:27ff:fea4:72d5")}
    monkeypatch.setattr(protection, "_local_addresses", lambda: own)
    monkeypatch.setattr(protection, "_gateway_addresses", lambda: {ipaddress.ip_address("10.0.2.2")})
    monkeypatch.setattr(settings, "FIREWALL_NEVER_BLOCK", ["192.168.56.200/30", "no-es-red"])


@pytest.mark.parametrize("ip, motivo", [
    ("no-es-ip", "no válida"),
    ("127.0.0.1", "loopback"),
    ("224.0.0.251", "multicast"),
    ("0.0.0.0", "sin asignar"),
    ("255.255.255.255", "broadcast"),
    ("192.168.56.10", "propio LanSentinel"),
    ("192.168.56.255", "propio LanSentinel"),          # broadcast de la interfaz
    ("fe80::a00:27ff:fea4:72d5%enp0s8", "propio LanSentinel"),
    ("10.0.2.2", "puerta de enlace"),
    ("192.168.56.201", "FIREWALL_NEVER_BLOCK"),
])
def test_protegidas(red, ip, motivo):
    assert motivo in protection.protected_reason(ip)


@pytest.mark.parametrize("ip", ["192.168.56.20", "8.8.8.8", "192.168.56.204", "2001:db8::1"])
def test_bloqueables(red, ip):
    assert protection.protected_reason(ip) is None


def test_is_own_address(red):
    assert protection.is_own_address("192.168.56.10")
    assert not protection.is_own_address("192.168.56.20") and not protection.is_own_address(None)
