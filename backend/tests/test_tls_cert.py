"""HTTPS: CA propia con restricción de nombres y certificado del panel."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.x509.verification import PolicyBuilder, Store, VerificationError

from app.services import tls_cert as t

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ca():
    return t.make_ca("lansentinel-host1", t.permitted_dns("lansentinel-host1", "lan"), NOW)


def _verify(ca_cert, leaf, name: x509.GeneralName):
    verifier = PolicyBuilder().store(Store([ca_cert])).time(NOW + timedelta(hours=1)).build_server_verifier(name)
    return verifier.verify(leaf, [])


# ── Nombres ──────────────────────────────────────────────────────────────────

def test_permitted_dns():
    assert t.permitted_dns("lansentinel-host1", "lan") == ["lan", "lansentinel-host1", "localhost"]
    assert t.permitted_dns("mi_pc", "home.arpa") == ["home.arpa", "localhost"]      # "_" no es válido
    assert t.permitted_dns("pc", "") == ["pc", "localhost"]


def test_wanted_names_solo_lo_que_la_ca_puede_firmar():
    names = t.wanted_names("lansentinel-host1", "lan", ["192.168.56.10", "10.0.2.15", "8.8.8.8"],
                           ["lan", "lansentinel-host1", "localhost"])
    assert names.dns == ("lansentinel.lan", "lansentinel-host1", "lansentinel-host1.lan", "localhost")
    assert names.ips == ("10.0.2.15", "127.0.0.1", "192.168.56.10")        # la pública, fuera
    # Si el equipo cambia de nombre, el nuevo no está entre los permitidos de la CA
    renamed = t.wanted_names("otro", "lan", [], ["lan", "lansentinel-host1", "localhost"])
    assert "otro" not in renamed.dns and "otro.lan" in renamed.dns


@pytest.mark.parametrize("ip, ok", [
    ("192.168.1.1", True), ("10.1.2.3", True), ("172.20.0.1", True), ("100.64.0.1", True),
    ("127.0.0.1", True), ("8.8.8.8", False), ("172.32.0.1", False),
])
def test_ips_permitidas(ip, ok):
    assert t.is_permitted_ip(ip) is ok


# ── Certificados ─────────────────────────────────────────────────────────────

def test_certificado_del_panel_valida_con_la_ca(ca):
    ca_cert, ca_key = ca
    names = t.Names(dns=("lansentinel.lan", "localhost"), ips=("127.0.0.1", "192.168.56.10"))
    leaf, _ = t.make_server_cert(names, ca_cert, ca_key, NOW)
    assert t.signed_by(leaf, ca_cert)
    _verify(ca_cert, leaf, x509.DNSName("lansentinel.lan"))
    import ipaddress
    _verify(ca_cert, leaf, x509.IPAddress(ipaddress.ip_address("192.168.56.10")))
    assert t.cert_names(leaf) == names
    assert leaf.not_valid_after_utc - NOW == timedelta(days=t.SERVER_DAYS)


def test_la_ca_no_sirve_para_webs_de_internet(ca):
    ca_cert, ca_key = ca
    evil, _ = t.make_server_cert(t.Names(dns=("www.google.com",), ips=()), ca_cert, ca_key, NOW)
    with pytest.raises(VerificationError):
        _verify(ca_cert, evil, x509.DNSName("www.google.com"))
    import ipaddress
    evil_ip, _ = t.make_server_cert(t.Names(dns=(), ips=("8.8.8.8",)), ca_cert, ca_key, NOW)
    with pytest.raises(VerificationError):
        _verify(ca_cert, evil_ip, x509.IPAddress(ipaddress.ip_address("8.8.8.8")))


def test_nombre_que_no_esta_en_el_certificado(ca):
    ca_cert, ca_key = ca
    leaf, _ = t.make_server_cert(t.Names(dns=("lansentinel.lan",), ips=()), ca_cert, ca_key, NOW)
    with pytest.raises(VerificationError):
        _verify(ca_cert, leaf, x509.DNSName("otro.lan"))


def test_certificado_de_otra_ca(ca):
    other_ca, other_key = t.make_ca("otro", ["lan"], NOW)
    leaf, _ = t.make_server_cert(t.Names(dns=("panel.lan",), ips=()), other_ca, other_key, NOW)
    assert not t.signed_by(leaf, ca[0])


def test_cuando_renovar(ca):
    ca_cert, ca_key = ca
    names = t.Names(dns=("lansentinel.lan",), ips=("192.168.56.10",))
    leaf, _ = t.make_server_cert(names, ca_cert, ca_key, NOW)
    assert not t.needs_renewal(leaf, names, NOW)
    assert t.needs_renewal(leaf, t.Names(dns=names.dns, ips=("192.168.1.50",)), NOW)      # cambió la IP
    assert t.needs_renewal(leaf, names, NOW + timedelta(days=t.SERVER_DAYS - 29))        # menos de un mes
    assert not t.needs_renewal(leaf, names, NOW + timedelta(days=t.SERVER_DAYS - 31))


# ── Servicio completo con ficheros ───────────────────────────────────────────

@pytest.fixture
def tls_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(t, "TLS_DIR", tmp_path)
    monkeypatch.setattr(t, "CA_CERT", tmp_path / "ca.crt")
    monkeypatch.setattr(t, "CA_KEY", tmp_path / "ca.key")
    monkeypatch.setattr(t, "SERVER_CERT", tmp_path / "server.crt")
    monkeypatch.setattr(t, "SERVER_KEY", tmp_path / "server.key")
    monkeypatch.setattr(t.socket, "gethostname", lambda: "lansentinel-host1")
    ips = ["192.168.56.10"]
    monkeypatch.setattr(t, "local_ipv4", lambda: list(ips))
    return tmp_path, ips


def test_ensure_crea_y_reutiliza(tls_dir):
    d, ips = tls_dir
    service = t.TlsService()
    service.ensure()
    status = service.status()
    assert status["issuer"] == "lansentinel" and "192.168.56.10" in status["ip_addresses"]
    assert oct((d / "ca.key").stat().st_mode & 0o777) == "0o600"
    assert oct((d / "server.key").stat().st_mode & 0o777) == "0o600"
    ca_before, server_before = (d / "ca.crt").read_bytes(), (d / "server.crt").read_bytes()

    service.ensure()                                      # nada cambia: no se rehace
    assert (d / "server.crt").read_bytes() == server_before

    ips[:] = ["192.168.1.50"]                             # cambia la IP: nuevo certificado, misma CA
    service.ensure()
    assert (d / "server.crt").read_bytes() != server_before
    assert (d / "ca.crt").read_bytes() == ca_before
    assert "192.168.1.50" in service.status()["ip_addresses"]


def test_ensure_respeta_un_certificado_propio(tls_dir):
    d, _ = tls_dir
    service = t.TlsService()
    service.ensure()
    from cryptography.hazmat.primitives import serialization
    other_ca, other_key = t.make_ca("otro", ["lan"], datetime.now(timezone.utc))
    own, own_key = t.make_server_cert(t.Names(dns=("panel.lan",), ips=()), other_ca, other_key, datetime.now(timezone.utc))
    (d / "server.crt").write_bytes(own.public_bytes(serialization.Encoding.PEM))
    service.ensure()
    assert (d / "server.crt").read_bytes() == own.public_bytes(serialization.Encoding.PEM)
    assert service.status()["issuer"] == "custom" and service.status()["ca_fingerprint"] is None
