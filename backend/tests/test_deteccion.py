"""Detección: Suricata (lectura de eve.json y clasificación), ARP spoofing y servicios inseguros."""

import json

from app.models.alert import AlertSeverity
from app.services.security import threat_classifier as tc
from app.services.security.arp_watch import Binding, LocalContext, evaluate, scan_conflicts
from app.services.security.insecure_services import assess, compare_scans
from app.services.security.suricata_reader import SuricataReader


# ── eve.json ─────────────────────────────────────────────────────────────────

def _event(n: int) -> str:
    return json.dumps({"event_type": "alert", "n": n}) + "\n"


async def test_lee_solo_lineas_completas(tmp_path):
    eve = tmp_path / "eve.json"
    eve.write_text(_event(1) + _event(2) + '{"event_type": "al')     # la última, a medio escribir
    reader = SuricataReader(str(eve), str(tmp_path / "offset"))
    lines, offset = await reader._read_new_lines(0)
    assert [json.loads(l)["n"] for l in lines] == [1, 2]
    assert offset == len((_event(1) + _event(2)).encode())
    # Cuando Suricata termina la línea, se lee desde donde se quedó
    with eve.open("a") as f:
        f.write('ert", "n": 3}\n')
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [3]


async def test_rotacion_vuelve_al_principio(tmp_path):
    eve = tmp_path / "eve.json"
    eve.write_text(_event(1) + _event(2) + _event(3))
    reader = SuricataReader(str(eve), str(tmp_path / "offset"))
    _, offset = await reader._read_new_lines(0)
    # Suricata rota: fichero nuevo (otro inodo) y más pequeño
    eve.unlink()
    eve.write_text(_event(4))
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [4]


async def test_rotacion_con_fichero_ya_mas_grande(tmp_path):
    eve = tmp_path / "eve.json"
    eve.write_text(_event(1))
    reader = SuricataReader(str(eve), str(tmp_path / "offset"))
    _, offset = await reader._read_new_lines(0)
    eve.unlink()
    eve.write_text(_event(5) + _event(6) + _event(7))       # ya supera el offset antiguo
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [5, 6, 7]


def test_offset_persistente(tmp_path):
    reader = SuricataReader(str(tmp_path / "eve.json"), str(tmp_path / "offset"))
    assert reader._load_offset() == 0
    reader._save_offset(1234)
    assert SuricataReader(str(tmp_path / "eve.json"), str(tmp_path / "offset"))._load_offset() == 1234


def test_clasificacion_de_suricata():
    assert [tc._map_severity(s) for s in (1, 2, 3, 4, None, 9)] == [
        AlertSeverity.critical, AlertSeverity.high, AlertSeverity.medium, AlertSeverity.low,
        AlertSeverity.info, AlertSeverity.info,
    ]
    event = {
        "src_ip": "192.168.56.20", "src_port": 4444, "dest_ip": "192.168.56.10", "dest_port": 22,
        "proto": "TCP", "alert": {"signature": "ET SCAN Nmap", "category": "Detection of a Network Scan"},
    }
    assert tc._build_title(event) == "ET SCAN Nmap"
    assert tc._build_description(event) == (
        "Origen: 192.168.56.20:4444 → Destino: 192.168.56.10:22. Protocolo: TCP. "
        "Categoría: Detection of a Network Scan"
    )
    assert len(tc._build_title({"alert": {"signature": "x" * 400}})) == 250
    assert tc._build_title({}) == "Alerta de Suricata"
    assert tc._build_description({}) == "Sin detalles adicionales."


# ── ARP spoofing ─────────────────────────────────────────────────────────────

CTX = LocalContext(own_ips={"192.168.56.10"}, own_macs={"08:00:27:A4:72:D5"}, gateway_ip="192.168.56.1")
A, B = "08:00:27:4A:04:3A", "DE:AD:BE:EF:00:01"


def _eval(bindings, ip, mac, now, baseline=None, trusted=frozenset()):
    return evaluate(bindings, ip, mac, now, CTX, baseline, set(trusted), window_seconds=600)


def test_otra_mac_reclama_la_ip_de_lansentinel():
    findings, _ = _eval({}, "192.168.56.10", B, 0)
    assert [(f.kind, f.severity) for f in findings] == [("own_ip", AlertSeverity.critical)]
    assert _eval({}, "192.168.56.10", "08:00:27:a4:72:d5", 0)[0] == []     # su propia MAC (en minúsculas)


def test_cambio_de_mac_del_gateway():
    findings, baseline = _eval({}, "192.168.56.1", A, 0)
    assert findings == [] and baseline == A                    # primera vez: referencia
    findings, baseline = _eval({}, "192.168.56.1", B, 1, baseline=A)
    assert findings[0].kind == "gateway_changed" and findings[0].previous_mac == A and baseline == A
    # Si la MAC nueva es de un dispositivo de confianza (router nuevo), se acepta
    findings, baseline = _eval({}, "192.168.56.1", B, 1, baseline=A, trusted={B})
    assert findings == [] and baseline == B


def test_vaiven_a_b_a_es_conflicto_pero_un_cambio_no():
    bindings: dict[str, Binding] = {}
    assert _eval(bindings, "192.168.56.20", A, 0)[0] == []
    assert _eval(bindings, "192.168.56.20", B, 10)[0] == []    # cambio único (DHCP, MAC aleatoria)
    findings, _ = _eval(bindings, "192.168.56.20", A, 20)       # vuelve: A → B → A
    assert [(f.kind, f.mac, f.previous_mac) for f in findings] == [("ip_conflict", A, B)]


def test_vaiven_fuera_de_la_ventana_no_alerta():
    bindings: dict[str, Binding] = {}
    _eval(bindings, "192.168.56.20", A, 0)
    _eval(bindings, "192.168.56.20", B, 10)
    assert _eval(bindings, "192.168.56.20", A, 10 + 601)[0] == []


def test_ignora_macs_y_ips_vacias():
    assert _eval({}, "0.0.0.0", B, 0)[0] == []
    assert _eval({}, "192.168.56.10", "ff:ff:ff:ff:ff:ff", 0)[0] == []


def test_conflicto_en_un_mismo_escaneo():
    entries = [("192.168.56.20", A), ("192.168.56.20", B.lower()), ("192.168.56.30", A), ("192.168.56.30", A.lower())]
    assert scan_conflicts(entries) == {"192.168.56.20": {A, B}}


# ── Servicios inseguros ──────────────────────────────────────────────────────

def test_assess_por_puerto_y_por_servicio():
    assert assess(23, None).severity == AlertSeverity.high
    assert assess(2222, "Telnet").severity == AlertSeverity.high     # telnet en otro puerto
    assert assess(443, "https") is None and assess(8022, None) is None


def test_primer_escaneo_solo_avisa_de_lo_inseguro():
    findings = compare_scans(None, [(22, "ssh"), (23, "telnet"), (80, "http")])
    assert [p for p, _, _ in findings.insecure] == [23]
    assert findings.new_ports == []                # en el primero todo es "nuevo": no se avisa


def test_escaneos_siguientes_avisan_de_puertos_nuevos():
    findings = compare_scans({22, 23}, [(22, "ssh"), (23, "telnet"), (80, "http"), (6379, "redis")])
    assert [p for p, _, _ in findings.insecure] == [6379]          # el 23 ya se conocía
    assert findings.new_ports == [(80, "http")]
