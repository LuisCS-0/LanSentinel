"""Auditoría con IA, fase 1: la instantánea que se enviaría, seudónimos y limpieza de datos."""

import json
import re
from datetime import datetime, timedelta, timezone

from app.services.ai_audit.snapshot import (
    Options, Pseudonymizer, RawAlert, RawData, RawDevice, RawPort, RawRule, RawUser, build_snapshot,
)

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
MAC_PORTATIL = "08:00:27:4A:04:3A"
MAC_CAMARA = "A4:CF:12:00:00:01"

PORTATIL = RawDevice(
    id="d-portatil", mac=MAC_PORTATIL, ip="192.168.56.20", hostname="portatil-luis", vendor="PCS Systemtechnik",
    device_type="ordenador", is_trusted=True, is_blocked=False,
    first_seen=NOW - timedelta(days=30), last_seen=NOW - timedelta(minutes=5),
    ipv6=["2a02:1234:5600:7:a00:27ff:fe4a:43a"],
)
CAMARA = RawDevice(
    id="d-camara", mac=MAC_CAMARA, ip="192.168.56.30", hostname="camara-salon", vendor="Espressif",
    device_type="cámara", is_trusted=False, is_blocked=False,
    first_seen=NOW - timedelta(days=2), last_seen=NOW - timedelta(hours=1),
)


def _raw(**overrides) -> RawData:
    base = dict(
        devices=[CAMARA, PORTATIL],
        ports=[RawPort("d-camara", 23, "tcp", "telnet", None), RawPort("d-camara", 80, "tcp", "http", "lighttpd 1.4")],
        alerts=[
            RawAlert("d-camara", "high", "suricata", "new", "Telnet desde 192.168.56.30 hacia 8.8.8.8",
                     f"Origen {MAC_CAMARA} (camara-salon)", 3, NOW - timedelta(hours=5), NOW - timedelta(hours=1)),
            RawAlert("d-camara", "high", "suricata", "acknowledged", "Telnet desde 192.168.56.30 hacia 8.8.8.8",
                     None, 2, NOW - timedelta(hours=30), NOW - timedelta(hours=20)),
            RawAlert("d-portatil", "medium", "monitor", "new", "Subida inusual: portatil-luis",
                     "Desde 2a02:1234:5600:7:a00:27ff:fe4a:43a y 10.0.2.15", 1, NOW - timedelta(hours=2), NOW - timedelta(hours=2)),
        ],
        rules=[RawRule(None, "185.15.58.224", "Bloqueo manual", False, NOW - timedelta(days=1)),
               RawRule("d-camara", "192.168.56.30", "Bloqueo automático de 192.168.56.30", True, NOW)],
        users=[RawUser("admin", True, NOW - timedelta(hours=1)), RawUser("viewer", True, None),
               RawUser("viewer", False, None)],
        usage_7d={"d-portatil": (150_000_000, 2_000_000_000)},
        domains={"d-portatil": [("www.wikipedia.org", 40), ("speed.cloudflare.com", 12)]},
        system={"modo_router": {"activo": True}},
        own_ips=["192.168.56.10"],
    )
    base.update(overrides)
    return RawData(**base)


def test_seudonimos_por_orden_de_aparicion():
    snap = build_snapshot(_raw(), Options(), NOW, "1.11.0")
    ids = {d["id"]: d["fabricante"] for d in snap.data["dispositivos"]}
    assert ids == {"disp-01": "PCS Systemtechnik", "disp-02": "Espressif"}      # el portátil llegó antes
    assert {m["id"]: m["nombre"] for m in snap.mapping} == {"disp-01": "portatil-luis", "disp-02": "camara-salon"}


def test_no_se_escapa_nada_de_la_lan():
    text = build_snapshot(_raw(), Options(), NOW, "1.11.0").to_json()
    assert not re.search(r"\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b", text)       # ninguna MAC
    for secret in ("192.168.56.20", "192.168.56.30", "192.168.56.10", "10.0.2.15",
                   "2a02:1234:5600:7:a00:27ff:fe4a:43a", "portatil-luis", "camara-salon", "wikipedia"):
        assert secret not in text, secret
    # Las IPs de Internet sí se quedan
    assert "8.8.8.8" in text and "185.15.58.224" in text


def test_limpieza_de_textos():
    p = Pseudonymizer([CAMARA, PORTATIL], ["192.168.56.10"], include_names=False)
    assert p.scrub("Telnet desde 192.168.56.30 a 192.168.56.10") == "Telnet desde disp-02 a lansentinel"
    assert p.scrub(f"MAC {MAC_CAMARA.lower()}") == "MAC [MAC]"
    assert p.scrub("Subida inusual: portatil-luis") == "Subida inusual: disp-01"
    assert p.scrub("Desde 10.0.2.15") == "Desde [IP privada]"
    assert p.scrub("Hacia 1.1.1.1") == "Hacia 1.1.1.1"


def test_alertas_agrupadas():
    alerts = build_snapshot(_raw(), Options(), NOW, "1.11.0").data["alertas"]
    telnet = alerts[0]
    assert telnet["titulo"] == "Telnet desde disp-02 hacia 8.8.8.8" and telnet["dispositivo"] == "disp-02"
    assert telnet["veces"] == 5 and telnet["estados"] == {"new": 1, "acknowledged": 1}
    assert (telnet["primera_hace_horas"], telnet["ultima_hace_horas"]) == (30.0, 1.0)
    assert telnet["descripcion"] == "Origen [MAC] (disp-02)"
    assert [a["gravedad"] for a in alerts] == ["high", "medium"]        # lo más grave primero


def test_puertos_con_su_riesgo_y_trafico():
    devices = {d["id"]: d for d in build_snapshot(_raw(), Options(), NOW, "1.11.0").data["dispositivos"]}
    telnet = next(p for p in devices["disp-02"]["puertos_abiertos"] if p["puerto"] == 23)
    assert telnet["riesgo"]["gravedad"] in {"high", "critical"}
    assert devices["disp-01"]["trafico_7_dias_mb"] == {"subida": 150.0, "bajada": 2000.0}
    assert devices["disp-01"]["direcciones_ipv6"] == 1
    assert devices["disp-01"]["dominios"] == {"distintos": 2}          # sin la lista


def test_nombres_y_dominios_solo_si_se_activan():
    snap = build_snapshot(_raw(), Options(include_names=True, include_domains=True), NOW, "1.11.0")
    portatil = snap.data["dispositivos"][0]
    assert portatil["nombre"] == "portatil-luis"
    assert portatil["dominios"]["principales"] == ["www.wikipedia.org", "speed.cloudflare.com"]
    assert "Subida inusual: portatil-luis" in snap.to_json()          # el nombre ya no se tapa
    assert snap.data["incluye"] == {"nombres_de_red": True, "dominios": True}


def test_bloqueos_y_usuarios():
    data = build_snapshot(_raw(), Options(), NOW, "1.11.0").data
    assert [b["objetivo"] for b in data["bloqueos_activos"]] == ["185.15.58.224", "disp-02"]
    assert data["bloqueos_activos"][1]["motivo"] == "Bloqueo automático de disp-02"
    assert data["sistema"]["usuarios"] == {
        "administradores_activos": 1, "solo_lectura_activos": 1, "desactivados": 1, "activos_sin_entrar_90_dias": 1,
    }
    assert data["sistema"]["modo_router"] == {"activo": True}


def test_json_compacto_y_estimacion():
    snap = build_snapshot(_raw(), Options(), NOW, "1.11.0")
    text = snap.to_json()
    assert json.loads(text) == json.loads(json.dumps(snap.data, default=str))
    assert text == json.dumps(snap.data, ensure_ascii=False, separators=(",", ":"), default=str)
    assert snap.approx_tokens() == round(len(text) / 3.5)
