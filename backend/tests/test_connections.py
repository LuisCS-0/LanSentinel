"""Conexiones: parseo de `conntrack -L` y clasificación open/idle/pending/done/closing."""

from app.services.monitor.connections import (
    IDLE_AFTER, Timeouts, connections_for_devices, connections_for_ip, idle_seconds,
    parse_conntrack, parse_conntrack_line,
)

T = Timeouts(tcp_established=432000, tcp_unacknowledged=300, udp=30, udp_stream=120)

TCP_OPEN = (
    "tcp      6 431990 ESTABLISHED src=192.168.56.20 dst=142.250.0.1 sport=40000 dport=443 "
    "src=142.250.0.1 dst=10.0.2.15 sport=443 dport=40000 [ASSURED] mark=0 use=1"
)
TCP_IDLE = (
    "tcp      6 400000 ESTABLISHED src=192.168.56.20 dst=1.2.3.4 sport=40001 dport=22 "
    "src=1.2.3.4 dst=10.0.2.15 sport=22 dport=40001 [ASSURED] mark=0 use=1"
)
DNS_DONE = (
    "udp      17 25 src=192.168.56.20 dst=192.168.56.10 sport=50000 dport=53 "
    "src=192.168.56.10 dst=192.168.56.20 sport=53 dport=50000 mark=0 use=1"
)
SYN_PENDING = (
    "tcp      6 100 SYN_SENT src=192.168.56.20 dst=8.8.8.8 sport=40002 dport=80 [UNREPLIED] "
    "src=8.8.8.8 dst=10.0.2.15 sport=80 dport=40002 mark=0 use=1"
)
CLOSING = (
    "tcp      6 100 TIME_WAIT src=192.168.56.20 dst=8.8.4.4 sport=40003 dport=8443 "
    "src=8.8.4.4 dst=10.0.2.15 sport=8443 dport=40003 [ASSURED] mark=0 use=1"
)
# El panel visto desde la .20: entra por DNAT al contenedor
DNAT_IN = (
    "tcp      6 431999 ESTABLISHED src=192.168.56.1 dst=192.168.56.10 sport=55000 dport=3000 "
    "src=172.18.0.3 dst=192.168.56.1 sport=80 dport=55000 [ASSURED] mark=0 use=1"
)


def test_parse_line_tcp():
    e = parse_conntrack_line(TCP_OPEN)
    assert e is not None
    assert (e.protocol, e.state, e.expires_in) == ("tcp", "ESTABLISHED", 431990)
    assert (e.orig_src, e.orig_dst, e.orig_sport, e.orig_dport) == ("192.168.56.20", "142.250.0.1", 40000, 443)
    assert e.reply_src == "142.250.0.1" and e.reply_sport == 443
    assert e.replied and e.assured


def test_parse_line_udp_sin_estado_y_unreplied():
    e = parse_conntrack_line(DNS_DONE)
    assert e.state is None and not e.assured
    assert not parse_conntrack_line(SYN_PENDING).replied


def test_parse_ignora_lineas_raras():
    assert parse_conntrack_line("") is None
    assert parse_conntrack_line("conntrack v1.4.8 (conntrack-tools): 3 flow entries have been shown.") is None
    assert len(parse_conntrack("\n".join([TCP_OPEN, "basura", DNS_DONE]))) == 2


def test_idle_seconds():
    assert idle_seconds(parse_conntrack_line(TCP_OPEN), T) == 10
    assert idle_seconds(parse_conntrack_line(TCP_IDLE), T) == 32000
    assert idle_seconds(parse_conntrack_line(DNS_DONE), T) == 5
    assert idle_seconds(parse_conntrack_line(CLOSING), T) is None


def test_estados_vistos_desde_el_dispositivo():
    entries = parse_conntrack("\n".join([TCP_OPEN, TCP_IDLE, DNS_DONE, SYN_PENDING, CLOSING]))
    by_port = {c["remote_port"]: c for c in connections_for_ip(entries, "192.168.56.20", T)}
    assert by_port[443]["status"] == "open"
    assert by_port[8443]["status"] == "closing"
    assert by_port[22]["status"] == "idle" and 32000 >= IDLE_AFTER
    assert by_port[53]["status"] == "done"
    assert by_port[80]["status"] == "pending"
    statuses = [c["status"] for c in connections_for_ip(entries, "192.168.56.20", T)]
    assert statuses == sorted(statuses, key=["open", "idle", "pending", "done", "closing"].index)


def test_servicio_y_direccion():
    c = connections_for_ip([parse_conntrack_line(TCP_OPEN)], "192.168.56.20", T)[0]
    assert c["direction"] == "outgoing" and c["service"] == "HTTPS" and not c["remote_is_lan"]
    c = connections_for_ip([parse_conntrack_line(DNS_DONE)], "192.168.56.20", T)[0]
    assert c["service"] == "DNS" and c["remote_is_lan"]


def test_entrante_por_dnat():
    e = parse_conntrack_line(DNAT_IN)
    c = connections_for_ip([e], "172.18.0.3", T)[0]
    assert c["direction"] == "incoming" and c["local_port"] == 80 and c["remote_ip"] == "192.168.56.1"


def test_conexion_entre_dos_dispositivos_aparece_dos_veces():
    e = parse_conntrack_line(DNS_DONE)
    result = connections_for_devices([e], {"192.168.56.20": "a", "192.168.56.10": "b"}, T)
    assert sorted((c["device_id"], c["direction"]) for c in result) == [("a", "outgoing"), ("b", "incoming")]


def test_ip_ajena_no_aparece():
    assert connections_for_ip([parse_conntrack_line(TCP_OPEN)], "192.168.56.99", T) == []


def test_transferencia_en_curso_no_es_idle():
    # Descarga activa: el kernel usa el temporizador de datos sin confirmar (300 s)
    line = ("tcp      6 299 ESTABLISHED src=192.168.56.20 dst=162.159.140.220 sport=60182 dport=443 "
            "src=162.159.140.220 dst=10.0.2.15 sport=443 dport=60182 [ASSURED] mark=0 use=1")
    e = parse_conntrack_line(line)
    assert idle_seconds(e, T) == 0
    assert connections_for_ip([e], "192.168.56.20", T)[0]["status"] == "open"


def test_solo_las_conexiones_mas_relevantes():
    """Con 13.000 entradas en conntrack, la página recibía 5 MB cada pocos segundos."""
    from app.services.monitor.connections import most_relevant

    conns = ([{"status": "done", "idle_seconds": i} for i in range(50)]
             + [{"status": "idle", "idle_seconds": 3000}, {"status": "open", "idle_seconds": 20},
                {"status": "open", "idle_seconds": 1}, {"status": "pending", "idle_seconds": None}])
    kept, omitted = most_relevant(conns, limit=5)
    assert omitted == 49
    assert [(c["status"], c["idle_seconds"]) for c in kept] == [
        ("open", 1), ("open", 20), ("pending", None), ("idle", 3000), ("done", 0)]
    assert most_relevant(conns[:3], limit=5) == (conns[:3], 0)
