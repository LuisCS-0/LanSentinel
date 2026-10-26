"""Dominios y huellas TLS: lectura de los eventos dns y tls de Suricata (copiados del laboratorio)."""

import pytest

from app.core.config import settings
from app.services.security.domain_tracker import DomainTracker, normalize_domain, observe_event

DNS_REQUEST = {
    "event_type": "dns", "src_ip": "192.168.56.20", "dest_ip": "1.1.1.1",
    "dns": {"version": 3, "type": "request", "queries": [{"rrname": "example.org", "rrtype": "A"}]},
}
DNS_RESPONSE = {
    "event_type": "dns", "src_ip": "1.1.1.1", "dest_ip": "192.168.56.20",
    "dns": {
        "version": 3, "type": "response",
        "queries": [{"rrname": "www.netflix.com", "rrtype": "A"}],
        "answers": [
            {"rrname": "www.netflix.com", "rrtype": "CNAME", "rdata": "www.dradis.netflix.com"},
            {"rrname": "www.dradis.netflix.com", "rrtype": "A", "rdata": "54.155.178.5"},
            {"rrname": "www.dradis.netflix.com", "rrtype": "A", "rdata": "3.251.50.149"},
        ],
    },
}
TLS = {
    "event_type": "tls", "src_ip": "192.168.56.20", "dest_ip": "185.15.58.224",
    "tls": {
        "sni": "www.wikipedia.org", "version": "TLS 1.3",
        "ja3": {"hash": "32e4b8812cda0c0d50783b438492a769"},
        "ja4": "t13d3013h2_1d37bd780c83_8537cf56674e",
    },
}


@pytest.mark.parametrize("name, expected", [
    ("Example.ORG.", "example.org"),
    ("www.wikipedia.org", "www.wikipedia.org"),
    ("_dmarc.example.com", "_dmarc.example.com"),
    ("localhost", None),                          # sin punto: no es un dominio útil
    ("20.56.168.192.in-addr.arpa", None),         # búsqueda inversa
    ("mal formado.com", None),
    ("", None), (None, None),
    ("a" * 64 + ".com", None),                    # etiqueta de más de 63
])
def test_normalize_domain(name, expected):
    assert normalize_domain(name) == expected


def test_consulta_dns():
    obs = observe_event(DNS_REQUEST)
    assert (obs.device_ip, obs.domains, obs.via) == ("192.168.56.20", ["example.org"], "dns")


def test_respuesta_dns_asocia_las_ips_al_nombre_consultado():
    obs = observe_event(DNS_RESPONSE)
    assert obs.device_ip == "192.168.56.20"
    assert obs.ip_names == [("54.155.178.5", "www.netflix.com"), ("3.251.50.149", "www.netflix.com")]
    assert obs.domains == []                       # la consulta ya se contó


def test_tls_sni_y_huellas():
    obs = observe_event(TLS)
    assert obs.domains == ["www.wikipedia.org"] and obs.via == "tls"
    assert obs.ip_names == [("185.15.58.224", "www.wikipedia.org")]
    assert obs.fingerprint == "t13d3013h2_1d37bd780c83_8537cf56674e"
    assert obs.ja3 == "32e4b8812cda0c0d50783b438492a769"


def test_tls_sin_ja4_usa_ja3_y_sin_sni_vale_la_huella():
    event = {**TLS, "tls": {"ja3": {"hash": "abc"}}}
    obs = observe_event(event)
    assert obs.fingerprint == "abc" and obs.domains == [] and obs.ip_names == []


def test_se_ignora_lo_que_no_es_de_un_dispositivo():
    # Consulta del propio servidor DNS hacia fuera (origen público), PTR, otros eventos
    assert observe_event({**DNS_REQUEST, "src_ip": "10.0.2.15x"}) is None
    assert observe_event({**DNS_REQUEST, "src_ip": "8.8.8.8"}) is None
    ptr = {**DNS_REQUEST, "dns": {"type": "request", "queries": [{"rrname": "1.0.0.10.in-addr.arpa", "rrtype": "PTR"}]}}
    assert observe_event(ptr) is None
    assert observe_event({"event_type": "flow", "src_ip": "192.168.56.20"}) is None
    assert observe_event({"event_type": "tls", "src_ip": "192.168.56.20", "tls": {}}) is None


def test_tracker_acumula_y_pone_nombre_a_las_conexiones(monkeypatch):
    monkeypatch.setattr(settings, "DOMAIN_TRACKING_ENABLED", True)
    t = DomainTracker()
    for _ in range(3):
        t.observe(TLS)
    t.observe(DNS_REQUEST)
    t.observe(DNS_RESPONSE)
    assert t._domains[("192.168.56.20", "www.wikipedia.org")][:3] == [3, False, True]
    assert t._domains[("192.168.56.20", "example.org")][:3] == [1, True, False]
    assert t._fps[("192.168.56.20", "t13d3013h2_1d37bd780c83_8537cf56674e")][0] == 3
    conns = [{"remote_ip": "185.15.58.224"}, {"remote_ip": "54.155.178.5"}, {"remote_ip": "9.9.9.9"}]
    assert [c["remote_name"] for c in t.annotate(conns)] == ["www.wikipedia.org", "www.netflix.com", None]


def test_tracker_desactivado_no_guarda_nada(monkeypatch):
    monkeypatch.setattr(settings, "DOMAIN_TRACKING_ENABLED", False)
    t = DomainTracker()
    t.observe(TLS)
    assert t._domains == {} and t.name_for("185.15.58.224") is None
