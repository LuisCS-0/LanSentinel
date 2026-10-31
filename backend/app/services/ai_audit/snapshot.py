"""
Instantánea de la red para la auditoría con IA: lo que se enviaría al
modelo. Lógica pura (sin BD ni red), para poder probarla y para que la vista
previa del panel enseñe exactamente lo mismo que saldrá.

Privacidad, por defecto:
  - cada dispositivo es "disp-NN" (por orden de aparición en la red); de la
    MAC solo queda el fabricante;
  - los nombres de red y el historial de dominios no salen salvo que se
    activen (AI_AUDIT_INCLUDE_NAMES, AI_AUDIT_INCLUDE_DOMAINS);
  - los textos libres (títulos y descripciones de alertas, motivos de
    bloqueo) se limpian: IPs de la LAN → su seudónimo, MACs → "[MAC]",
    nombres de red → seudónimo, cualquier otra IP privada → "[IP privada]".
    Las IPs públicas (de Internet) se mantienen: son las de los atacantes o
    los destinos, y son las que interesan.

La equivalencia seudónimo → dispositivo se queda en el equipo: sirve para
leer la vista previa y, más adelante, para enlazar los hallazgos.
"""

import ipaddress
import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.services.security.insecure_services import assess

MAX_ALERT_GROUPS = 150
MAX_REMOVED_RULES = 30
MAX_LISTED = 8
MAX_DESCRIPTION = 240
TOP_DOMAINS = 15

_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
# Palabras que pueden ser un nombre de red: "equipo-1", "movil.lan"... Un
# nombre solo cuenta entero (sin letras, dígitos ni guiones pegados), pero
# puede ir seguido de un punto ("equipo-1.lan" o el final de una frase)
_NAME_TOKEN = re.compile(r"(?<![\w.-])[\w-]+(?:\.[\w-]+)*")
_PLAIN_NAME = re.compile(r"[\w-]+(?:\.[\w-]+)*")
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# ── Datos de entrada (los rellena collect.py) ────────────────────────────────

@dataclass
class RawDevice:
    id: str
    mac: str
    ip: str | None
    hostname: str | None
    vendor: str | None
    device_type: str | None
    is_trusted: bool
    is_blocked: bool
    first_seen: datetime
    last_seen: datetime
    ipv6: list[str] = field(default_factory=list)
    last_port_scan_at: datetime | None = None     # None: nunca se han escaneado sus puertos


@dataclass
class RawPort:
    device_id: str
    port: int
    protocol: str
    service: str | None
    version: str | None


@dataclass
class RawAlert:
    device_id: str | None
    severity: str
    source: str
    status: str
    title: str
    description: str | None
    occurrences: int
    created_at: datetime
    last_seen_at: datetime


@dataclass
class RawRule:
    device_id: str | None
    ip: str | None
    reason: str | None
    auto_generated: bool
    created_at: datetime
    removed_at: datetime | None = None


@dataclass
class RawConnection:
    """Una conexión vista desde el dispositivo (services/monitor/connections)."""
    device_id: str
    direction: str                # outgoing | incoming
    protocol: str
    remote_ip: str
    remote_port: int | None
    local_port: int | None
    status: str                   # open | idle | done


@dataclass
class RawLogin:
    ip: str | None
    ok: bool
    at: datetime


@dataclass
class RawListener:
    """Un puerto en el que escucha el propio equipo de LanSentinel."""
    protocol: str
    port: int
    scope: str                    # solo_el_equipo | toda_la_red | una_direccion


@dataclass
class RawUser:
    role: str
    is_active: bool
    last_login_at: datetime | None


@dataclass
class RawData:
    devices: list[RawDevice]
    ports: list[RawPort]
    alerts: list[RawAlert]
    rules: list[RawRule]
    users: list[RawUser]
    usage_7d: dict[str, tuple[int, int]]          # device_id → (subida, bajada) en bytes
    domains: dict[str, list[tuple[str, int]]]      # device_id → [(dominio, veces)] por veces
    system: dict                                   # estado ya resumido (ver collect.py)
    own_ips: list[str] = field(default_factory=list)   # las del propio LanSentinel
    connections: list[RawConnection] | None = None     # None: no se pudo leer conntrack
    tls: dict[str, list[tuple[str, int]]] = field(default_factory=dict)   # device_id → [(JA4, veces)]
    night_share: dict[str, float] = field(default_factory=dict)  # device_id → % del tráfico de 0 a 6 h
    logins: list[RawLogin] = field(default_factory=list)          # intentos de entrar al panel
    listeners: list[RawListener] | None = None                    # None: no se pudo leer
    removed_rules: list[RawRule] = field(default_factory=list)    # bloqueos retirados en la ventana


@dataclass
class Options:
    include_names: bool = False
    include_domains: bool = False
    alert_days: int = 30
    compact_tokens: int = 0       # > 0: modo compacto, que quepa en esos tokens


@dataclass
class Snapshot:
    data: dict
    mapping: list[dict]          # seudónimo → dispositivo (no se envía)

    def to_json(self) -> str:
        """Lo que se envía: JSON compacto."""
        return _dumps(self.data)

    def approx_tokens(self) -> int:
        return approx_tokens(self.to_json())


def _dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def approx_tokens(text: str) -> int:
    # Aproximación: unos 3,5 caracteres por token en JSON con texto en español
    return round(len(text) / 3.5)


# ── Seudónimos y limpieza de textos ──────────────────────────────────────────

class Pseudonymizer:
    """Asigna disp-01, disp-02... y limpia los textos libres."""

    def __init__(self, devices: list[RawDevice], own_ips: list[str], include_names: bool):
        ordered = sorted(devices, key=lambda d: (d.first_seen, d.mac))
        width = max(2, len(str(len(ordered))))
        self.by_id = {d.id: f"disp-{i:0{width}d}" for i, d in enumerate(ordered, start=1)}
        self.by_ip: dict[str, str] = {}
        self.names: dict[str, str] = {}
        for d in ordered:
            alias = self.by_id[d.id]
            for ip in [d.ip, *d.ipv6]:
                if ip:
                    self.by_ip[ip] = alias
            if d.hostname and not include_names and len(d.hostname) >= 3:
                self.names[d.hostname] = alias
        for ip in own_ips:
            self.by_ip.setdefault(ip, "lansentinel")
        # Todo se busca de una pasada por texto, no una búsqueda por
        # dispositivo: con miles de dispositivos y de alertas, eso eran
        # decenas de millones de búsquedas (minutos con el backend parado).
        # Las IPv6, con una sola expresión de la más larga a la más corta,
        # para no sustituir un prefijo de otra.
        v6 = sorted((ip for ip in self.by_ip if ":" in ip), key=len, reverse=True)
        self._v6 = re.compile("|".join(map(re.escape, v6))) if v6 else None
        # Los nombres normales se buscan por palabra en un diccionario; los
        # raros (con espacios, apóstrofos...), uno a uno como antes
        self._odd_names = sorted((n for n in self.names if not _PLAIN_NAME.fullmatch(n)), key=len, reverse=True)

    def alias(self, device_id: str | None) -> str | None:
        return self.by_id.get(device_id) if device_id else None

    def address(self, ip: str) -> str:
        """Una dirección suelta (IPv4 o IPv6): su seudónimo, "lansentinel", "[IP privada]" o, si es de Internet, ella misma."""
        if ip in self.by_ip:
            return self.by_ip[ip]
        return ip if _is_public(ip) else "[IP privada]"

    def scrub(self, text: str | None) -> str | None:
        if not text:
            return text
        text = _MAC.sub("[MAC]", text)
        if self._v6:
            text = self._v6.sub(lambda m: self.by_ip[m.group(0)], text)
        text = _IPV4.sub(self._replace_v4, text)
        if self.names:
            text = _NAME_TOKEN.sub(self._replace_name, text)
        for name in self._odd_names:
            text = re.sub(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", self.names[name], text)
        return text

    def _replace_name(self, match: re.Match) -> str:
        """La palabra entera o su parte antes de un punto, si es un nombre ("equipo-1.lan")."""
        word = match.group(0)
        cut = len(word)
        while cut > 0:
            alias = self.names.get(word[:cut])
            if alias:
                return alias + word[cut:]
            cut = word.rfind(".", 0, cut)
        return word

    def _replace_v4(self, match: re.Match) -> str:
        ip = match.group(0)
        if ip in self.by_ip:
            return self.by_ip[ip]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return ip
        return "[IP privada]" if addr.is_private else ip


def _hours(now: datetime, then: datetime | None) -> float | None:
    return round((now - then).total_seconds() / 3600, 1) if then else None


def _days(now: datetime, then: datetime | None) -> float | None:
    return round((now - then).total_seconds() / 86400, 1) if then else None


def _mb(value: int) -> float:
    return round(value / 1_000_000, 1)


# ── Construcción ─────────────────────────────────────────────────────────────

def build_snapshot(raw: RawData, options: Options, now: datetime, version: str) -> Snapshot:
    p = Pseudonymizer(raw.devices, raw.own_ips, options.include_names)
    own = set(raw.own_ips)

    ports_by_device: dict[str, list[dict]] = {}
    for port in sorted(raw.ports, key=lambda x: (x.protocol, x.port)):
        risk = assess(port.port, port.service)
        entry = {"puerto": port.port, "protocolo": port.protocol, "servicio": port.service}
        if port.version:
            entry["version"] = port.version[:80]
        if risk:
            entry["riesgo"] = {"gravedad": risk.severity.value, "motivo": risk.reason}
        ports_by_device.setdefault(port.device_id, []).append(entry)

    conns_by_device: dict[str, list[RawConnection]] = {}
    for c in raw.connections or []:
        conns_by_device.setdefault(c.device_id, []).append(c)

    devices = []
    for d in sorted(raw.devices, key=lambda x: p.by_id[x.id]):
        entry = {
            "id": p.by_id[d.id],
            "fabricante": d.vendor or "desconocido",
            "tipo": d.device_type,
            "de_confianza": d.is_trusted,
            "bloqueado": d.is_blocked,
            "visto_hace_horas": _hours(now, d.last_seen),
            "en_la_red_desde_dias": _days(now, d.first_seen),
            "direcciones_ipv6": len(d.ipv6),
            # Sin escanear no es lo mismo que sin puertos abiertos
            "puertos_escaneados_hace_horas": _hours(now, d.last_port_scan_at),
            "puertos_abiertos": ports_by_device.get(d.id, []),
        }
        if options.include_names and d.hostname:
            entry["nombre"] = d.hostname
        sent, recv = raw.usage_7d.get(d.id, (0, 0))
        entry["trafico_7_dias_mb"] = {"subida": _mb(sent), "bajada": _mb(recv)}
        if d.id in raw.night_share:
            entry["trafico_7_dias_mb"]["de_0_a_6_h_pct"] = raw.night_share[d.id]
        if raw.connections is not None:
            entry["conexiones_ahora"] = _connections(
                conns_by_device.get(d.id, []), p, own=own,
            )
        fingerprints = raw.tls.get(d.id, [])
        if fingerprints:
            entry["huellas_tls_ja4"] = {"distintas": len(fingerprints), "principales": [f for f, _ in fingerprints[:3]]}
        domains = raw.domains.get(d.id, [])
        entry["dominios"] = {"distintos": len(domains)}
        if options.include_domains:
            entry["dominios"]["principales"] = [name for name, _ in domains[:TOP_DOMAINS]]
        devices.append(entry)

    data = {
        "generado": now.isoformat(timespec="minutes"),
        "lansentinel": version,
        "ventana_alertas_dias": options.alert_days,
        "incluye": {"nombres_de_red": options.include_names, "dominios": options.include_domains},
        "sistema": _system(raw, now),
        "dispositivos": devices,
        "alertas": _alert_groups(raw.alerts, p, now),
        "bloqueos_activos": [
            {
                "objetivo": p.alias(r.device_id) or (p.address(r.ip) if r.ip else None),
                "motivo": p.scrub(r.reason),
                "automatico": r.auto_generated,
                "desde_hace_dias": _days(now, r.created_at),
            }
            for r in raw.rules
        ],
        "bloqueos_retirados": [
            {
                "objetivo": p.alias(r.device_id) or (p.address(r.ip) if r.ip else None),
                "motivo": p.scrub(r.reason),
                "automatico": r.auto_generated,
                "duro_horas": _hours(r.removed_at, r.created_at) if r.removed_at else None,
                "retirado_hace_dias": _days(now, r.removed_at),
            }
            for r in raw.removed_rules[:MAX_REMOVED_RULES]
        ],
    }
    data["sistema"]["acceso_al_panel"] = _logins(raw.logins, p, now)
    if raw.listeners is not None:
        data["sistema"]["servicios_del_equipo"] = sorted(
            ({"puerto": x.port, "protocolo": x.protocol, "escucha_en": x.scope} for x in raw.listeners),
            key=lambda x: (x["protocolo"], x["puerto"]),
        )
    if options.compact_tokens > 0:
        data = compact(data, options.compact_tokens)
    return Snapshot(
        data=data,
        mapping=[
            {"id": p.by_id[d.id], "device_id": d.id, "nombre": d.hostname or d.vendor, "ip": d.ip, "mac": d.mac}
            for d in sorted(raw.devices, key=lambda x: p.by_id[x.id])
        ],
    )


def _alert_groups(alerts: list[RawAlert], p: Pseudonymizer, now: datetime) -> list[dict]:
    """Alertas agrupadas por título, gravedad, origen y dispositivo, con totales."""
    groups: dict[tuple, dict] = {}
    for a in alerts:
        title = p.scrub(a.title)
        key = (title, a.severity, a.source, p.alias(a.device_id))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "titulo": title,
                "gravedad": a.severity,
                "origen": a.source,
                "dispositivo": p.alias(a.device_id),
                "veces": 0,
                "estados": {},
                "primera_hace_horas": _hours(now, a.created_at),
                "ultima_hace_horas": _hours(now, a.last_seen_at),
                "descripcion": (p.scrub(a.description) or "")[:MAX_DESCRIPTION] or None,
            }
        g["veces"] += a.occurrences
        g["estados"][a.status] = g["estados"].get(a.status, 0) + 1
        g["primera_hace_horas"] = max(g["primera_hace_horas"], _hours(now, a.created_at))
        g["ultima_hace_horas"] = min(g["ultima_hace_horas"], _hours(now, a.last_seen_at))
    ordered = sorted(groups.values(), key=lambda g: (_SEVERITY_ORDER.get(g["gravedad"], 9), g["ultima_hace_horas"]))
    return ordered[:MAX_ALERT_GROUPS]


def _connections(conns: list[RawConnection], p: Pseudonymizer, own: set[str]) -> dict:
    """
    Resumen de las conexiones de un dispositivo: cuántas, con cuántos
    destinos de Internet, a qué puertos, si alguien de fuera entra (puerto
    redirigido) y con qué equipos de casa habla (movimiento lateral).
    """
    live = [c for c in conns if c.status != "done"]
    external = [c for c in live if _is_public(c.remote_ip)]
    lan_peers = sorted({
        p.address(c.remote_ip) for c in live
        if not _is_public(c.remote_ip) and c.remote_ip not in own
    })
    ports: dict[str, int] = {}
    for c in external:
        if c.direction == "outgoing" and c.remote_port:
            key = f"{c.remote_port}/{c.protocol}"
            ports[key] = ports.get(key, 0) + 1
    destinations: dict[str, int] = {}
    for c in external:
        if c.direction == "outgoing":
            destinations[c.remote_ip] = destinations.get(c.remote_ip, 0) + 1
    return {
        "abiertas": sum(c.status == "open" for c in live),
        "destinos_de_internet": len({c.remote_ip for c in external}),
        "puertos_de_destino": [k for k, _ in sorted(ports.items(), key=lambda x: -x[1])[:MAX_LISTED]],
        "principales_destinos": [ip for ip, _ in sorted(destinations.items(), key=lambda x: -x[1])[:5]],
        "entrantes_desde_internet": sum(c.direction == "incoming" for c in external),
        "con_equipos_de_casa": lan_peers[:MAX_LISTED],
    }


def _logins(logins: list[RawLogin], p: Pseudonymizer, now: datetime) -> dict:
    """Intentos de entrar al panel en la ventana: fallidos, desde dónde y el último."""
    failed = [x for x in logins if not x.ok]
    origins: dict[str, int] = {}
    for x in failed:
        origin = p.address(x.ip) if x.ip else "desconocido"
        origins[origin] = origins.get(origin, 0) + 1
    return {
        "correctos": sum(x.ok for x in logins),
        "fallidos": len(failed),
        "origenes_fallidos": [
            {"origen": o, "veces": n} for o, n in sorted(origins.items(), key=lambda x: -x[1])[:5]
        ],
        "ultimo_fallido_hace_horas": _hours(now, max(x.at for x in failed)) if failed else None,
    }


def _is_public(ip: str) -> bool:
    """De Internet: global y no multidifusión (224.0.0.251 de mDNS cuenta como global)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_global and not addr.is_multicast


def _system(raw: RawData, now: datetime) -> dict:
    """El estado de LanSentinel ya viene resumido; aquí solo se añaden los usuarios."""
    active = [u for u in raw.users if u.is_active]
    stale = [u for u in active if u.last_login_at is None or _days(now, u.last_login_at) > 90]
    return {
        **raw.system,
        "usuarios": {
            "administradores_activos": sum(u.role == "admin" for u in active),
            "solo_lectura_activos": sum(u.role == "viewer" for u in active),
            "desactivados": sum(not u.is_active for u in raw.users),
            "activos_sin_entrar_90_dias": len(stale),
        },
    }


# ── Modo compacto ────────────────────────────────────────────────────────────

_PENDING = ("new",)


def compact(data: dict, max_tokens: int) -> dict:
    """
    Instantánea reducida para modelos con poco contexto (los locales). Lo
    mismo con menos texto: puertos como "23/tcp telnet !alta", alertas sin
    descripción, números redondos. Si aun así no cabe en max_tokens, se
    quitan primero las alertas menos graves y más antiguas y después los
    dispositivos sin puertos ni alertas que más tiempo llevan sin verse.
    Lo quitado se cuenta en "omitido", para que el modelo lo sepa.
    """
    devices = [_compact_device(d) for d in data["dispositivos"]]
    alerts = [
        {
            "titulo": a["titulo"][:120], "gravedad": a["gravedad"], "origen": a["origen"],
            "dispositivo": a["dispositivo"], "veces": a["veces"],
            "pendientes": sum(n for s, n in a["estados"].items() if s in _PENDING),
            "ultima_hace_h": round(a["ultima_hace_horas"] or 0),
        }
        for a in data["alertas"]
    ]
    blocks = [
        {"objetivo": b["objetivo"], "automatico": b["automatico"], "motivo": (b["motivo"] or "")[:80] or None}
        for b in data["bloqueos_activos"]
    ]
    removed = [
        {"objetivo": b["objetivo"], "automatico": b["automatico"], "hace_dias": round(b["retirado_hace_dias"] or 0)}
        for b in data.get("bloqueos_retirados", [])[:10]
    ]
    out = {
        "generado": data["generado"], "lansentinel": data["lansentinel"], "compacta": True,
        "ventana_alertas_dias": data["ventana_alertas_dias"], "incluye": data["incluye"],
        "sistema": data["sistema"], "dispositivos": devices, "alertas": alerts, "bloqueos_activos": blocks,
        "bloqueos_retirados": removed,
        "omitido": {"alertas": 0, "dispositivos": 0},
    }

    def fits() -> bool:
        return approx_tokens(_dumps(out)) <= max_tokens

    # Volver a serializar todo tras cada elemento quitado era cuadrático (con
    # miles de dispositivos, segundos): se resta lo que ocupa cada uno (su
    # texto y la coma) y al final se comprueba de verdad
    size = len(_dumps(out))
    limit = max_tokens * 3.5

    def drop(item: dict) -> None:
        nonlocal size
        size -= len(_dumps(item)) + 1

    # Alertas: ya van de más a menos grave y de más a menos reciente
    while alerts and size > limit:
        drop(alerts.pop())
        out["omitido"]["alertas"] += 1
    if size > limit:
        cited = {a["dispositivo"] for a in alerts} | {b["objetivo"] for b in blocks}
        spare = sorted(
            (d for d in devices if not d.get("puertos") and d["id"] not in cited),
            key=lambda d: d.get("visto_hace_h") or 0, reverse=True,
        )
        gone: set[str] = set()
        for d in spare:
            if size <= limit:
                break
            gone.add(d["id"])
            drop(d)
            out["omitido"]["dispositivos"] += 1
        devices[:] = [d for d in devices if d["id"] not in gone]

    # Por si la cuenta se ha quedado corta por unos caracteres
    while alerts and not fits():
        alerts.pop()
        out["omitido"]["alertas"] += 1
    if not fits():
        cited = {a["dispositivo"] for a in alerts} | {b["objetivo"] for b in blocks}
        for d in [d for d in devices if not d.get("puertos") and d["id"] not in cited][::-1]:
            if fits():
                break
            devices.remove(d)
            out["omitido"]["dispositivos"] += 1
    return out


def _compact_device(d: dict) -> dict:
    entry = {"id": d["id"], "fabricante": d["fabricante"]}
    for key in ("nombre", "tipo"):
        if d.get(key):
            entry[key] = d[key]
    if d["de_confianza"]:
        entry["de_confianza"] = True
    if d["bloqueado"]:
        entry["bloqueado"] = True
    entry["visto_hace_h"] = round(d["visto_hace_horas"] or 0)
    entry["en_la_red_dias"] = round(d["en_la_red_desde_dias"] or 0)
    scanned = d.get("puertos_escaneados_hace_horas")
    entry["escaneado_hace_h"] = round(scanned) if scanned is not None else None
    ports = []
    for p in d["puertos_abiertos"]:
        text = f"{p['puerto']}/{p['protocolo']} {p['servicio'] or '?'}"
        if p.get("riesgo"):
            text += f" !{p['riesgo']['gravedad']}"
        ports.append(text)
    if ports:
        entry["puertos"] = ports
    traffic = d["trafico_7_dias_mb"]
    entry["mb_7d"] = [round(traffic["subida"]), round(traffic["bajada"])]
    if traffic.get("de_0_a_6_h_pct"):
        entry["noche_pct"] = round(traffic["de_0_a_6_h_pct"])
    conns = d.get("conexiones_ahora")
    if conns and (conns["abiertas"] or conns["destinos_de_internet"]):
        entry["conex"] = {
            "abiertas": conns["abiertas"], "internet": conns["destinos_de_internet"],
            "puertos": conns["puertos_de_destino"][:4],
        }
        if conns["entrantes_desde_internet"]:
            entry["conex"]["entrantes"] = conns["entrantes_desde_internet"]
        if conns["con_equipos_de_casa"]:
            entry["conex"]["lan"] = conns["con_equipos_de_casa"][:4]
    if d["dominios"].get("principales"):
        entry["dominios"] = d["dominios"]["principales"][:5]
    return entry


def night_shares(rows: list[tuple[str, datetime, int]], tz, min_bytes: int = 1_000_000) -> dict[str, float]:
    """
    Porcentaje del tráfico de cada dispositivo entre las 0 y las 6 (hora
    local) a partir de sus filas horarias (device_id, hora, bytes). Los que
    apenas han tenido tráfico no salen: el porcentaje no diría nada.
    """
    total: dict[str, int] = {}
    night: dict[str, int] = {}
    for device_id, hour, value in rows:
        total[device_id] = total.get(device_id, 0) + value
        if hour.astimezone(tz).hour < 6:
            night[device_id] = night.get(device_id, 0) + value
    return {d: round(100 * night.get(d, 0) / v, 1) for d, v in total.items() if v >= min_bytes}


_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?![\w:])")


def public_ips(data: dict) -> set[str]:
    """Las IPs de Internet que aparecen en la instantánea: las únicas que el plan puede bloquear."""
    text = _dumps(data)
    return {ip for ip in _IPV4.findall(text) + _IPV6.findall(text) if _is_public(ip)}
