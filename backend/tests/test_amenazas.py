"""Inteligencia de amenazas: listas de IPs, saneado, ipset, reglas y contadores."""

import ipaddress

from app.services.security import threat_lists as t

N = ipaddress.ip_network


def test_parse_sources():
    spec = "firehol_level1=https://a/x.netset, feodo=https://b/y.txt ,mal,ftp=ftp://c,Raro!=http://d"
    assert t.parse_sources(spec) == [
        ("firehol_level1", "https://a/x.netset"), ("feodo", "https://b/y.txt"), ("raro", "http://d"),
    ]


def test_parse_list_formatos():
    text = """\
# FireHOL: comentarios con almohadilla
1.2.3.0/24
5.6.7.8
; Spamhaus DROP
9.9.0.0/16 ; SBL123
2001:db8::/32
no-es-ip
45.10.20.30  # abuse.ch
"""
    assert t.parse_list(text) == [N("1.2.3.0/24"), N("5.6.7.8/32"), N("9.9.0.0/16"), N("45.10.20.30/32")]


def test_sanitize_quita_la_red_local_y_lo_protegido():
    nets = [
        N("192.168.0.0/16"), N("10.0.0.0/8"), N("0.0.0.0/8"), N("224.0.0.0/3"),   # "bogons" de FireHOL
        N("1.2.3.0/24"), N("1.2.3.128/25"),                                     # se unen
        N("8.8.8.0/24"),                                                        # protegida (p. ej. el DNS)
        N("0.0.0.0/1"),                                                         # contiene la LAN
        N("45.10.20.30/32"),
    ]
    kept, removed = t.sanitize(nets, [N("8.8.8.8/32")])
    assert kept == [N("1.2.3.0/24"), N("45.10.20.30/32")]
    assert removed == 6


def test_ipset_restore_script():
    script = t.ipset_restore_script("prueba", [N("1.2.3.0/24"), N("5.6.7.8/32")])
    lines = script.splitlines()
    assert lines[0].startswith("create prueba hash:net family inet") and "counters" in lines[0]
    assert lines[1:] == ["add prueba 1.2.3.0/24 -exist", "add prueba 5.6.7.8/32 -exist"]


def test_chain_rules_una_por_dispositivo():
    rules = t.chain_rules(["192.168.56.100", "192.168.56.20"])
    comments = [r[r.index("--comment") + 1] for r in rules]
    assert comments == [
        "lansentinel-threat:192.168.56.20", "lansentinel-threat:192.168.56.100",
        "lansentinel-threat:otros", "lansentinel-threat:entrante",
    ]
    assert rules[0][:2] == ["-s", "192.168.56.20"] and rules[0][-2:] == ["-j", "DROP"]
    assert "src" in rules[-1] and "dst" in rules[0]


SAVE = """\
*filter
:LANSENTINEL_THREAT - [0:0]
[7:420] -A LANSENTINEL_THREAT -s 192.168.56.20/32 -m set --match-set lansentinel-amenazas dst -m comment --comment lansentinel-threat:192.168.56.20 -j DROP
[0:0] -A LANSENTINEL_THREAT -m set --match-set lansentinel-amenazas dst -m comment --comment lansentinel-threat:otros -j DROP
[3:180] -A LANSENTINEL_THREAT -m set --match-set lansentinel-amenazas src -m comment --comment "lansentinel-threat:entrante" -j DROP
[99:9] -A LANSENTINEL_FWD -s 1.1.1.1/32 -m comment --comment lansentinel:5 -j DROP
COMMIT
"""


def test_parse_counters():
    assert t.parse_counters(SAVE) == {"192.168.56.20": 7, "otros": 0, "entrante": 3}


def test_parse_ipset_hits():
    output = """\
Name: lansentinel-amenazas
Type: hash:net
Header: family inet hashsize 1024 maxelem 262144 counters
Members:
1.2.3.0/24 packets 5 bytes 300
45.10.20.30 packets 0 bytes 0
"""
    assert t.parse_ipset_hits(output) == {"1.2.3.0/24": 5}


def test_reglas_cargadas_por_suricata():
    log = """\
Info: detect: 2 rule files processed. 47473 rules successfully loaded, 16 rules failed, 0 rules skipped
Notice: detect: rule reload starting
Info: detect: tenant id 0:  2 rule files processed. 47473 rules successfully loaded, 0 rules failed, 0 rules skipped
"""
    assert t.suricata_rules_loaded(log) == (47473, 0)
    assert t.suricata_rules_loaded("nada") is None
