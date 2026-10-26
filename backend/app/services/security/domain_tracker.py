"""
Dominios y huellas TLS por dispositivo, a partir de los eventos dns y tls de
Suricata.

Casi todo el tráfico va cifrado, pero dos cosas siguen viéndose:

  - las consultas DNS (qué nombre resuelve cada dispositivo y a qué IPs),
  - el SNI de cada conexión TLS (a qué servidor se conecta, en claro en el
    saludo) y las huellas del cliente (JA4 y JA3: identifican el programa,
    no el contenido).

Con eso se guarda qué dominios usa cada dispositivo (device_domains) y con
qué programas (device_tls_fingerprints), agregados con contadores, y se
mantiene en memoria qué nombre corresponde a cada IP remota, para que la
tabla de conexiones diga "www.wikipedia.org" y no solo 185.15.58.224.

Es el historial de navegación de cada equipo: solo lo ve el administrador,
se borra a los DOMAIN_HISTORY_DAYS días sin verse y se desactiva con
DOMAIN_TRACKING_ENABLED=false. No se ve lo que va por DNS cifrado (DoH/DoT):
de eso solo queda el SNI del servidor DNS.
"""

import asyncio
import ipaddress
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.models.domains import DeviceDomain, DeviceTlsFingerprint

log = structlog.get_logger(__name__)

FLUSH_EVERY_SECONDS = 60
PURGE_EVERY_SECONDS = 3600
NAME_TTL = timedelta(hours=6)
MAX_NAMES = 20000

_LABEL = re.compile(r"^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")


@dataclass
class Observation:
    """Lo que interesa de un evento de Suricata."""
    device_ip: str | None = None
    domains: list[str] = field(default_factory=list)
    via: str = "dns"                            # dns | tls
    ip_names: list[tuple[str, str]] = field(default_factory=list)   # (IP remota, nombre)
    fingerprint: str | None = None              # JA4 o, si no hay, JA3
    ja3: str | None = None


# ── Funciones puras ──────────────────────────────────────────────────────────

def normalize_domain(name: str | None) -> str | None:
    """Nombre en minúsculas y sin punto final; None si no es un dominio útil."""
    if not name:
        return None
    name = name.strip().rstrip(".").lower()
    if len(name) > 253 or "." not in name or name.endswith(".arpa"):
        return None
    if not all(_LABEL.match(label) for label in name.split(".")):
        return None
    return name


def _is_device_ip(ip: str | None) -> bool:
    try:
        return ip is not None and ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def observe_event(event: dict) -> Observation | None:
    """Extrae dominios, nombres de IPs y huellas de un evento dns o tls."""
    kind = event.get("event_type")
    if kind == "tls":
        tls = event.get("tls") or {}
        if not _is_device_ip(event.get("src_ip")):
            return None
        sni = normalize_domain(tls.get("sni"))
        ja3 = (tls.get("ja3") or {}).get("hash")
        obs = Observation(device_ip=event["src_ip"], via="tls", ja3=ja3, fingerprint=tls.get("ja4") or ja3)
        if sni:
            obs.domains.append(sni)
            if event.get("dest_ip"):
                obs.ip_names.append((event["dest_ip"], sni))
        return obs if (obs.domains or obs.fingerprint) else None

    if kind == "dns":
        dns = event.get("dns") or {}
        queries = [q for q in dns.get("queries") or [] if q.get("rrtype") != "PTR"]
        names = [n for n in (normalize_domain(q.get("rrname")) for q in queries) if n]
        if dns.get("type") in ("request", "query"):
            if not _is_device_ip(event.get("src_ip")) or not names:
                return None
            return Observation(device_ip=event["src_ip"], domains=names, via="dns")
        if dns.get("type") in ("response", "answer"):
            # La IP se asocia al nombre consultado, no al último de la cadena de
            # CNAME: "www.netflix.com" dice más que el nombre del CDN
            if not _is_device_ip(event.get("dest_ip")) or not names:
                return None
            ips = [a.get("rdata") for a in dns.get("answers") or [] if a.get("rrtype") in ("A", "AAAA")]
            pairs = [(ip, names[0]) for ip in ips if ip]
            return Observation(device_ip=event["dest_ip"], ip_names=pairs, via="dns") if pairs else None
    return None


def _chunks(rows: list[dict], size: int = 1000):
    """Trozos para no pasar del límite de parámetros de una sentencia."""
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


# ── Servicio ─────────────────────────────────────────────────────────────────

class DomainTracker:

    def __init__(self):
        self._names: OrderedDict[str, tuple[str, datetime]] = OrderedDict()
        self._domains: dict[tuple[str, str], list] = {}     # (ip, dominio) → [hits, dns, tls, primera, última]
        self._fps: dict[tuple[str, str], list] = {}         # (ip, huella) → [hits, ja3, sni, primera, última]
        self._task: asyncio.Task | None = None
        self.events_seen = 0

    @property
    def enabled(self) -> bool:
        return settings.DOMAIN_TRACKING_ENABLED

    def start(self) -> None:
        if self.enabled:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
            await self.flush()

    def observe(self, event: dict) -> None:
        if not self.enabled:
            return
        obs = observe_event(event)
        if obs is None:
            return
        self.events_seen += 1
        now = datetime.now(timezone.utc)
        for ip, name in obs.ip_names:
            self._names[ip] = (name, now)
            self._names.move_to_end(ip)
        while len(self._names) > MAX_NAMES:
            self._names.popitem(last=False)
        for domain in obs.domains:
            entry = self._domains.setdefault((obs.device_ip, domain), [0, False, False, now, now])
            entry[0] += 1
            entry[1] |= obs.via == "dns"
            entry[2] |= obs.via == "tls"
            entry[4] = now
        if obs.fingerprint:
            entry = self._fps.setdefault((obs.device_ip, obs.fingerprint), [0, obs.ja3, None, now, now])
            entry[0] += 1
            entry[2] = obs.domains[0] if obs.domains else entry[2]
            entry[4] = now

    def name_for(self, ip: str) -> str | None:
        """Último nombre visto para una IP remota (DNS o SNI), si es reciente."""
        hit = self._names.get(ip)
        if hit and datetime.now(timezone.utc) - hit[1] < NAME_TTL:
            return hit[0]
        return None

    def annotate(self, conns: list[dict] | None) -> list[dict] | None:
        """Añade a cada conexión el dominio de su IP remota (remote_name)."""
        for c in conns or []:
            c["remote_name"] = self.name_for(c["remote_ip"])
        return conns

    async def device_history(self, device_id, days: int, limit: int = 1000) -> dict:
        """Dominios y huellas de un dispositivo vistos en los últimos `days` días."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as db:
            domains = (await db.execute(
                select(DeviceDomain)
                .where(DeviceDomain.device_id == device_id, DeviceDomain.last_seen >= since)
                .order_by(DeviceDomain.last_seen.desc()).limit(limit)
            )).scalars().all()
            fps = (await db.execute(
                select(DeviceTlsFingerprint)
                .where(DeviceTlsFingerprint.device_id == device_id, DeviceTlsFingerprint.last_seen >= since)
                .order_by(DeviceTlsFingerprint.last_seen.desc())
            )).scalars().all()
        return {
            "enabled": self.enabled,
            "history_days": settings.DOMAIN_HISTORY_DAYS,
            "domains": [
                {"domain": d.domain, "hits": d.hits, "via_dns": d.via_dns, "via_tls": d.via_tls,
                 "first_seen": d.first_seen, "last_seen": d.last_seen}
                for d in domains
            ],
            "fingerprints": [
                {"fingerprint": f.fingerprint, "ja3": f.ja3, "last_sni": f.last_sni, "hits": f.hits,
                 "first_seen": f.first_seen, "last_seen": f.last_seen}
                for f in fps
            ],
        }

    async def _loop(self) -> None:
        last_purge = 0.0
        while True:
            await asyncio.sleep(FLUSH_EVERY_SECONDS)
            try:
                await self.flush()
                loop_time = asyncio.get_running_loop().time()
                if loop_time - last_purge > PURGE_EVERY_SECONDS:
                    await self.purge()
                    last_purge = loop_time
            except Exception as exc:
                log.error("domain_tracker.flush_failed", error=str(exc))

    async def flush(self) -> None:
        """Guarda lo acumulado (sumando a lo que ya hubiera) y empieza de cero."""
        domains, fps = self._domains, self._fps
        self._domains, self._fps = {}, {}
        if not domains and not fps:
            return
        async with AsyncSessionLocal() as db:
            ips = {ip for ip, _ in domains} | {ip for ip, _ in fps}
            rows = (await db.execute(select(Device.ip, Device.id).where(Device.ip.in_(ips)))).all()
            by_ip = {ip: device_id for ip, device_id in rows}
            domain_rows = [
                {"device_id": by_ip[ip], "domain": d, "hits": e[0], "via_dns": e[1], "via_tls": e[2],
                 "first_seen": e[3], "last_seen": e[4]}
                for (ip, d), e in domains.items() if ip in by_ip
            ]
            fp_rows = [
                {"device_id": by_ip[ip], "fingerprint": fp, "ja3": e[1], "last_sni": e[2], "hits": e[0],
                 "first_seen": e[3], "last_seen": e[4]}
                for (ip, fp), e in fps.items() if ip in by_ip
            ]
            for chunk in _chunks(domain_rows):
                stmt = insert(DeviceDomain).values(chunk)
                await db.execute(stmt.on_conflict_do_update(
                    index_elements=["device_id", "domain"],
                    set_={
                        "hits": DeviceDomain.hits + stmt.excluded.hits,
                        "via_dns": DeviceDomain.via_dns | stmt.excluded.via_dns,
                        "via_tls": DeviceDomain.via_tls | stmt.excluded.via_tls,
                        "last_seen": func.greatest(DeviceDomain.last_seen, stmt.excluded.last_seen),
                    },
                ))
            for chunk in _chunks(fp_rows):
                stmt = insert(DeviceTlsFingerprint).values(chunk)
                await db.execute(stmt.on_conflict_do_update(
                    index_elements=["device_id", "fingerprint"],
                    set_={
                        "hits": DeviceTlsFingerprint.hits + stmt.excluded.hits,
                        "ja3": func.coalesce(stmt.excluded.ja3, DeviceTlsFingerprint.ja3),
                        "last_sni": func.coalesce(stmt.excluded.last_sni, DeviceTlsFingerprint.last_sni),
                        "last_seen": func.greatest(DeviceTlsFingerprint.last_seen, stmt.excluded.last_seen),
                    },
                ))
            await db.commit()

    async def purge(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.DOMAIN_HISTORY_DAYS)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(DeviceDomain).where(DeviceDomain.last_seen < cutoff))
            await db.execute(delete(DeviceTlsFingerprint).where(DeviceTlsFingerprint.last_seen < cutoff))
            await db.commit()


domain_tracker = DomainTracker()
