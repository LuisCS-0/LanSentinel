"""Ajustes desde el panel: validación, secretos que nunca salen y vuelta a .env."""

import ipaddress

import pytest

from app.core.config import settings
from app.services.panel_config import (
    BY_NAME, FIELDS, ConfigError, PanelConfig, Snapshot, check_dhcp_range, coerce, decrypt, describe, encrypt,
    needs_password,
)


def test_cada_ajuste_existe_en_la_configuracion():
    for f in FIELDS:
        assert hasattr(settings, f.name), f.name
    # Lo que se fija al instalar no se toca desde el panel
    for name in ("SECRET_KEY", "DATABASE_URL", "MONITOR_INTERFACE", "WAN_INTERFACE", "ROUTER_MODE",
                 "FIREWALL_NEVER_BLOCK", "THREAT_LISTS", "OUI_DOWNLOAD_URL"):
        assert name not in BY_NAME


@pytest.mark.parametrize("name, value, expected", [
    ("AI_AUDIT_PROVIDER", "compatible", "compatible"),
    ("AI_AUDIT_TIMEOUT_SECONDS", "900", 900),
    ("AI_AUDIT_PRICE_INPUT", 2.5, 2.5),
    ("ANOMALY_DETECTION_ENABLED", False, False),
    ("AI_AUDIT_BASE_URL", " http://192.168.1.50:11434/v1 ", "http://192.168.1.50:11434/v1"),
    ("AI_AUDIT_BASE_URL", "", ""),
    ("SMTP_TO", "a@b.es, c@d.com", "a@b.es, c@d.com"),
    ("TIMEZONE", "America/Mexico_City", "America/Mexico_City"),
])
def test_valores_validos(name, value, expected):
    assert coerce(BY_NAME[name], value) == expected


@pytest.mark.parametrize("name, value, message", [
    ("AI_AUDIT_PROVIDER", "gemini", "opción desconocida"),
    ("AI_AUDIT_TIMEOUT_SECONDS", 5, "entre 30 y 7200"),
    ("AI_AUDIT_TIMEOUT_SECONDS", "mucho", "no es un número"),
    ("AI_AUDIT_TIMEOUT_SECONDS", 90.5, "entero"),
    ("ANOMALY_DETECTION_ENABLED", "sí", "sí o no"),
    ("AI_AUDIT_BASE_URL", "file:///etc/passwd", "http://"),
    ("SMTP_TO", "yo@", "correo no válida"),
    ("TIMEZONE", "Madrid", "zona horaria"),
    ("TELEGRAM_CHAT_ID", "123\nX-Header: 1", "no válido"),
])
def test_valores_que_no_valen(name, value, message):
    with pytest.raises(ConfigError, match=message):
        coerce(BY_NAME[name], value)


def test_los_secretos_nunca_salen():
    snap = Snapshot(panel={"AI_AUDIT_API_KEY": "sk-ant-secreta"}, env={"TELEGRAM_BOT_TOKEN": ""})
    fields = {f["name"]: f for f in describe(snap)}
    key = fields["AI_AUDIT_API_KEY"]
    assert key["value"] is None and key["is_set"] is True and key["source"] == "panel"
    assert fields["TELEGRAM_BOT_TOKEN"]["is_set"] is False
    assert "sk-ant-secreta" not in repr(describe(snap))


def test_de_donde_sale_cada_valor():
    snap = Snapshot(panel={"NOTIFY_MIN_SEVERITY": "critical"}, env={"PORT_SCAN_INTERVAL_HOURS": 12})
    fields = {f["name"]: f for f in describe(snap)}
    assert (fields["NOTIFY_MIN_SEVERITY"]["value"], fields["NOTIFY_MIN_SEVERITY"]["source"]) == ("critical", "panel")
    assert (fields["PORT_SCAN_INTERVAL_HOURS"]["value"], fields["PORT_SCAN_INTERVAL_HOURS"]["source"]) == (12, "env")
    assert fields["BACKUP_HOUR"]["source"] == "default"


def test_cifrado_de_secretos():
    token = encrypt("sk-ant-secreta", "clave-del-equipo")
    assert "sk-ant" not in token
    assert decrypt(token, "clave-del-equipo") == "sk-ant-secreta"
    with pytest.raises(Exception):
        decrypt(token, "otra-clave")


def test_que_cambios_piden_la_contrasena():
    # Secretos y destinos de los datos sí; un número o un interruptor de detección no
    assert needs_password({"AI_AUDIT_API_KEY": "x"})
    assert needs_password({"AI_AUDIT_BASE_URL": "http://otro"})
    assert needs_password({"SMTP_TO": "otro@correo.es"})
    assert needs_password({"AI_AUDIT_INCLUDE_DOMAINS": True})
    assert not needs_password({"NOTIFY_MIN_SEVERITY": "high", "BACKUP_HOUR": 4})
    assert not needs_password({"ANOMALY_DETECTION_ENABLED": False})


def test_aplicar_y_volver_a_env(monkeypatch):
    config = PanelConfig()
    monkeypatch.setattr(settings, "NOTIFY_MAX_PER_HOUR", config.env["NOTIFY_MAX_PER_HOUR"])
    original = settings.NOTIFY_MAX_PER_HOUR
    changes = config.validate({"NOTIFY_MAX_PER_HOUR": "50"})
    assert changes == {"NOTIFY_MAX_PER_HOUR": 50}
    config._apply("NOTIFY_MAX_PER_HOUR", 50)
    assert settings.NOTIFY_MAX_PER_HOUR == 50                  # los servicios lo ven al momento
    config._reset("NOTIFY_MAX_PER_HOUR")
    assert settings.NOTIFY_MAX_PER_HOUR == original
    assert config.validate({"NOTIFY_MAX_PER_HOUR": None}) == {"NOTIFY_MAX_PER_HOUR": None}
    with pytest.raises(ConfigError, match="No se puede cambiar SECRET_KEY"):
        config.validate({"SECRET_KEY": "x"})


# ── DHCP y DNS del modo router ───────────────────────────────────────────────

@pytest.mark.parametrize("name, value, expected", [
    ("DHCP_RANGE_START", " 192.168.50.20 ", "192.168.50.20"),
    ("DHCP_RANGE_END", "", ""),
    ("DHCP_LEASE_TIME", "7d", "7d"),
    ("DHCP_LEASE_TIME", "infinite", "infinite"),
    ("DNS_UPSTREAM", "1.1.1.1, 2606:4700:4700::1111 ,", "1.1.1.1,2606:4700:4700::1111"),
    ("LOCAL_DOMAIN", "Casa.LAN.", "casa.lan"),
])
def test_router_valores_validos(name, value, expected):
    assert coerce(BY_NAME[name], value) == expected


@pytest.mark.parametrize("name, value, message", [
    ("DHCP_RANGE_START", "192.168.50", "IPv4"),
    ("DHCP_LEASE_TIME", "12 horas", "infinite"),
    ("DNS_UPSTREAM", "", "separadas por comas"),
    ("DNS_UPSTREAM", "dns.google", "separadas por comas"),
    ("DNS_UPSTREAM", "127.0.0.1", "separadas por comas"),       # dnsmasq se preguntaría a sí mismo
    ("LOCAL_DOMAIN", "mi red", "letras, números"),
    ("LOCAL_DOMAIN", "-lan", "letras, números"),
])
def test_router_valores_que_no_valen(name, value, message):
    with pytest.raises(ConfigError, match=message):
        coerce(BY_NAME[name], value)


def test_rango_de_dhcp():
    lan = ipaddress.IPv4Interface("192.168.50.1/24")
    check_dhcp_range("", "", lan)                                  # .100-.199 por defecto
    check_dhcp_range("192.168.50.20", "192.168.50.60", lan)
    check_dhcp_range("10.0.0.5", "10.0.0.1", None)                 # sin IP en la LAN: no se puede saber
    with pytest.raises(ConfigError, match="red de la LAN"):
        check_dhcp_range("192.168.1.100", "", lan)
    with pytest.raises(ConfigError, match="ir antes"):
        check_dhcp_range("192.168.50.150", "192.168.50.120", lan)
    with pytest.raises(ConfigError, match="IP de LanSentinel"):
        check_dhcp_range("192.168.50.1", "192.168.50.50", lan)
    # Con la LAN más grande, el rango por defecto (.100-.199) sigue cabiendo
    check_dhcp_range("", "", ipaddress.IPv4Interface("10.20.0.1/16"))


def test_rango_con_los_valores_que_quedaran(monkeypatch):
    monkeypatch.setattr(settings, "DHCP_RANGE_START", "192.168.50.150")
    monkeypatch.setattr(settings, "DHCP_RANGE_END", "")
    config = PanelConfig()
    lan = ipaddress.IPv4Interface("192.168.50.1/24")
    # Solo cambia el final, pero queda antes del principio que ya había
    with pytest.raises(ConfigError, match="ir antes"):
        config.validate({"DHCP_RANGE_END": "192.168.50.120"}, lan)
    assert config.validate({"DHCP_RANGE_START": "192.168.50.100", "DHCP_RANGE_END": "192.168.50.120"}, lan)
    # Volver a .env es volver a la .150 de .env, que sigue sin caber antes de la .120
    assert config.effective("DHCP_RANGE_START", {"DHCP_RANGE_START": None}) == "192.168.50.150"
    with pytest.raises(ConfigError, match="ir antes"):
        config.validate({"DHCP_RANGE_START": None, "DHCP_RANGE_END": "192.168.50.120"}, lan)
