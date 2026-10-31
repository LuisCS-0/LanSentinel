"""Detección: Suricata (lectura de eve.json y clasificación), ARP spoofing y servicios inseguros."""

import json

from app.models.alert import AlertSeverity
from app.services.firewall.auto_block import lan_block_allowed
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
    # Suricata rota: fichero nuevo (otro inodo) y más pequeño. Se renombra como
    # hace logrotate: si se borrase, el sistema podría reutilizar el inodo
    eve.rename(tmp_path / "eve.json.1")
    eve.write_text(_event(4))
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [4]


async def test_rotacion_con_fichero_ya_mas_grande(tmp_path):
    eve = tmp_path / "eve.json"
    eve.write_text(_event(1))
    reader = SuricataReader(str(eve), str(tmp_path / "offset"))
    _, offset = await reader._read_new_lines(0)
    eve.rename(tmp_path / "eve.json.1")
    eve.write_text(_event(5) + _event(6) + _event(7))       # ya supera el offset antiguo
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [5, 6, 7]


async def test_rotacion_no_pierde_lo_escrito_justo_antes(tmp_path):
    # Suricata escribe 2 y 3 después de la última lectura y antes de rotar:
    # el lector los recupera del .1 antes de seguir con el nuevo
    eve = tmp_path / "eve.json"
    eve.write_text(_event(1))
    reader = SuricataReader(str(eve), str(tmp_path / "offset"))
    _, offset = await reader._read_new_lines(0)
    with eve.open("a") as f:
        f.write(_event(2) + _event(3))
    eve.rename(tmp_path / "eve.json.1")
    lines, offset = await reader._read_new_lines(offset)
    assert lines == []                                      # aún no hay eve.json nuevo
    eve.write_text(_event(4))
    lines, _ = await reader._read_new_lines(offset)
    assert [json.loads(l)["n"] for l in lines] == [2, 3, 4]


async def test_rotacion_con_el_backend_parado(tmp_path):
    eve, offset_file = tmp_path / "eve.json", tmp_path / "offset"
    eve.write_text(_event(1))
    reader = SuricataReader(str(eve), str(offset_file))
    _, offset = await reader._read_new_lines(0)
    reader._save_offset(offset)
    with eve.open("a") as f:
        f.write(_event(2))
    eve.rename(tmp_path / "eve.json.1")
    eve.write_text(_event(5) + _event(6) + _event(7))      # más grande que el offset
    again = SuricataReader(str(eve), str(offset_file))
    lines, _ = await again._read_new_lines(again._load_offset())
    assert [json.loads(l)["n"] for l in lines] == [2, 5, 6, 7]


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


# ── Bloqueo automático ───────────────────────────────────────────────────────

def test_bloqueo_automatico_de_la_lan_solo_con_reglas_propias():
    assert lan_block_allowed("192.168.56.20", 1000010)          # fuerza bruta SSH (propia)
    assert not lan_block_allowed("192.168.56.20", 2012278)      # regla de Emerging Threats
    assert not lan_block_allowed("192.168.56.20", None)
    assert lan_block_allowed("45.10.20.30", 2012278)            # externa: con cualquier regla
    assert not lan_block_allowed("no-es-ip", 1000010)


# ── Escaneo de puertos y base de datos ───────────────────────────────────────

async def test_el_escaneo_no_ocupa_la_bd_mientras_espera_a_nmap(monkeypatch):
    """Con muchos dispositivos nuevos, una conexión ocupada por escaneo agotaba el pool."""
    from types import SimpleNamespace

    from app.services.security import port_scanner as ps

    device = SimpleNamespace(id="d1", last_port_scan_at=None, hostname="camara", vendor=None, mac="AA")

    class Sesion:
        en_transaccion = False

        async def execute(self, _query):
            self.en_transaccion = True
            return SimpleNamespace(scalar_one_or_none=lambda: device)

        async def commit(self):
            self.en_transaccion = False

        def add(self, _row):
            self.en_transaccion = True

    db = Sesion()
    durante_nmap = []

    async def nmap_falso(ip, ports=ps.DEFAULT_SCAN_PORTS):
        durante_nmap.append(db.en_transaccion)
        return ps.ScanResult(ip=ip, ports=[ps.ScannedPort(80, "tcp", "open", "http")])

    async def sin_alertas(*_args, **_kwargs):
        pass

    monkeypatch.setattr(ps, "scan_device", nmap_falso)
    monkeypatch.setattr(ps, "report_findings", sin_alertas)
    result = await ps.scan_and_persist("d1", "192.168.1.5", db)
    assert result.ok and durante_nmap == [False]
    assert device.last_port_scan_at == result.scanned_at and not db.en_transaccion


def test_alertas_sin_caracter_nul():
    """PostgreSQL no admite \\u0000 en text ni jsonb: la alerta de Suricata se perdía entera."""
    from app.services.alerts.alert_service import without_nul

    evento = {"alert": {"signature": "SURICATA HTTP request missing protocol"},
              "http": {"url": "/\x00\x00admin", "cab\x00ecera": ["a\x00b", 3]}, "flow_id": 655059798211457}
    limpio = without_nul(evento)
    assert "\x00" not in json.dumps(limpio, ensure_ascii=False)
    assert limpio["http"] == {"url": "/\\x00\\x00admin", "cab\\x00ecera": ["a\\x00b", 3]}
    assert limpio["flow_id"] == 655059798211457 and without_nul(None) is None
    assert without_nul("título normal") == "título normal"


async def test_nmap_no_ocupa_la_cola_de_hilos_comun(monkeypatch):
    """Muchos escaneos pendientes dejaban sin hilos al escaneo ARP, iptables y conntrack."""
    import asyncio
    import time

    from app.services.security import port_scanner as ps

    def nmap_lento(ip, ports=ps.DEFAULT_SCAN_PORTS):
        time.sleep(0.3)
        return ps.ScanResult(ip=ip)

    monkeypatch.setattr(ps, "_run_nmap_scan", nmap_lento)
    loop = asyncio.get_running_loop()
    escaneos = [asyncio.create_task(ps.scan_device(f"10.0.0.{i}")) for i in range(12)]
    await asyncio.sleep(0.05)
    t = time.perf_counter()
    assert await loop.run_in_executor(None, lambda: "arp") == "arp"
    assert time.perf_counter() - t < 0.2                 # no espera a que acaben los escaneos
    assert len(await asyncio.gather(*escaneos)) == 12


def test_nombres_de_la_red_a_la_vez_y_recordados(monkeypatch):
    """De uno en uno, 200 dispositivos sin nombre alargaban el escaneo ARP a un minuto."""
    import time

    from app.services.monitor import arp_scanner as arp

    preguntas = []

    def dns_lento(ip):
        preguntas.append(ip)
        time.sleep(0.2)
        return f"equipo-{ip.rsplit('.', 1)[1]}" if ip.endswith("0") else None

    monkeypatch.setattr(arp, "_resolve_hostname", dns_lento)
    monkeypatch.setattr(arp, "_name_cache", {})
    ips = [f"192.168.1.{i}" for i in range(1, 49)]
    t = time.perf_counter()
    nombres = arp.resolve_hostnames(ips)
    assert time.perf_counter() - t < 1.5                 # de uno en uno serían 9,6 s
    assert nombres["192.168.1.10"] == "equipo-10" and nombres["192.168.1.11"] is None
    assert arp.resolve_hostnames(ips) == nombres and len(preguntas) == 48   # la segunda vez, de la caché
