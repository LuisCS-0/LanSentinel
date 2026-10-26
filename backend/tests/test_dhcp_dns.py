"""DHCP y DNS del modo router: plan, configuración de dnsmasq y concesiones."""

from app.core.config import settings
from app.services.firewall.dhcp_dns import LEASES_PATH, count_active_leases, make_plan, render_config


def test_plan_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "DHCP_RANGE_START", "")
    monkeypatch.setattr(settings, "DHCP_RANGE_END", "")
    monkeypatch.setattr(settings, "DNS_UPSTREAM", " 1.1.1.1 , ,9.9.9.9")
    plan = make_plan("enp0s8", "192.168.56.10")
    assert (plan.range_start, plan.range_end) == ("192.168.56.100", "192.168.56.199")
    assert plan.upstream == ["1.1.1.1", "9.9.9.9"]


def test_plan_con_rango_propio_y_sin_dns(monkeypatch):
    monkeypatch.setattr(settings, "DHCP_RANGE_START", "10.0.0.50")
    monkeypatch.setattr(settings, "DHCP_RANGE_END", "10.0.0.60")
    monkeypatch.setattr(settings, "DNS_UPSTREAM", "")
    plan = make_plan("eth1", "10.0.0.1")
    assert (plan.range_start, plan.range_end) == ("10.0.0.50", "10.0.0.60")
    assert plan.upstream == ["1.1.1.1", "9.9.9.9"]       # nunca sin DNS


def test_render_config(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_DOMAIN", "lan")
    monkeypatch.setattr(settings, "DHCP_RANGE_START", "")
    monkeypatch.setattr(settings, "DHCP_RANGE_END", "")
    lines = render_config(make_plan("enp0s8", "192.168.56.10")).splitlines()
    for expected in [
        "interface=enp0s8", "bind-interfaces", "no-resolv", "except-interface=lo",
        "dhcp-range=192.168.56.100,192.168.56.199,12h",
        "dhcp-option=option:router,192.168.56.10",
        "dhcp-option=option:dns-server,192.168.56.10",
        "host-record=lansentinel.lan,192.168.56.10",
        f"dhcp-leasefile={LEASES_PATH}",
    ]:
        assert expected in lines
    # Solo escucha en la LAN: nunca en todas las interfaces
    assert not any(line.startswith("interface=") and line != "interface=enp0s8" for line in lines)


def test_count_active_leases():
    leases = "\n".join([
        "2000 aa:aa:aa:aa:aa:01 192.168.56.100 pc *",          # vigente
        "500 aa:aa:aa:aa:aa:02 192.168.56.101 movil *",        # caducada
        "0 aa:aa:aa:aa:aa:03 192.168.56.102 fija *",           # sin caducidad
        "duid 00:01:00:01",                                     # cabecera de IPv6
        "",
    ])
    assert count_active_leases(leases, now=1000) == 2
    assert count_active_leases("", now=1000) == 0
