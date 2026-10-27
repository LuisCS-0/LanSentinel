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
MAX_DESCRIPTION = 240
TOP_DOMAINS = 15

_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
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


@dataclass
class Options:
    include_names: bool = False
    include_domains: bool = False
    alert_days: int = 30


@dataclass
class Snapshot:
    data: dict
    mapping: list[dict]          # seudónimo → dispositivo (no se envía)

    def to_json(self) -> str:
        """Lo que se envía: JSON compacto."""
        return json.dumps(self.data, ensure_ascii=False, separators=(",", ":"), default=str)

    def approx_tokens(self) -> int:
        # Aproximación: unos 3,5 caracteres por token en JSON con texto en español
        return round(len(self.to_json()) / 3.5)


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
        # Las IPv6 se buscan como texto: de la más larga a la más corta, para
        # no sustituir un prefijo de otra
        self._v6 = sorted((ip for ip in self.by_ip if ":" in ip), key=len, reverse=True)
        self._names = sorted(self.names, key=len, reverse=True)

    def alias(self, device_id: str | None) -> str | None:
        return self.by_id.get(device_id) if device_id else None

    def scrub(self, text: str | None) -> str | None:
        if not text:
            return text
        text = _MAC.sub("[MAC]", text)
        for ip in self._v6:
            text = text.replace(ip, self.by_ip[ip])
        text = _IPV4.sub(self._replace_v4, text)
        for name in self._names:
            text = re.sub(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", self.names[name], text)
        return text

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

    ports_by_device: dict[str, list[dict]] = {}
    for port in sorted(raw.ports, key=lambda x: (x.protocol, x.port)):
        risk = assess(port.port, port.service)
        entry = {"puerto": port.port, "protocolo": port.protocol, "servicio": port.service}
        if port.version:
            entry["version"] = port.version[:80]
        if risk:
            entry["riesgo"] = {"gravedad": risk.severity.value, "motivo": risk.reason}
        ports_by_device.setdefault(port.device_id, []).append(entry)

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
            "puertos_abiertos": ports_by_device.get(d.id, []),
        }
        if options.include_names and d.hostname:
            entry["nombre"] = d.hostname
        sent, recv = raw.usage_7d.get(d.id, (0, 0))
        entry["trafico_7_dias_mb"] = {"subida": _mb(sent), "bajada": _mb(recv)}
        domains = raw.domains.get(d.id, [])
        entry["dominios"] = {"distintos": len(domains)}
        if options.include_domains:
            entry["dominios"]["principales"] = [name for name, _ in domains[:TOP_DOMAINS]]
        devices.append(entry)

    return Snapshot(
        data={
            "generado": now.isoformat(timespec="minutes"),
            "lansentinel": version,
            "ventana_alertas_dias": options.alert_days,
            "incluye": {"nombres_de_red": options.include_names, "dominios": options.include_domains},
            "sistema": _system(raw, now),
            "dispositivos": devices,
            "alertas": _alert_groups(raw.alerts, p, now),
            "bloqueos_activos": [
                {
                    "objetivo": p.alias(r.device_id) or (p.scrub(r.ip) if r.ip else None),
                    "motivo": p.scrub(r.reason),
                    "automatico": r.auto_generated,
                    "desde_hace_dias": _days(now, r.created_at),
                }
                for r in raw.rules
            ],
        },
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
