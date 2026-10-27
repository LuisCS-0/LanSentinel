"""Ajustes desde el panel: validación, secretos que nunca salen y vuelta a .env."""

import pytest

from app.core.config import settings
from app.services.panel_config import (
    BY_NAME, FIELDS, ConfigError, PanelConfig, Snapshot, coerce, decrypt, describe, encrypt, needs_password,
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
