"""
Recogida de los datos de la instantánea (snapshot.py): la BD y el estado de
los servicios, resumido. De cada servicio solo se toma lo que sirve para
auditar (activado, cuándo fue la última vez, si hay error); nada de rutas,
URLs, claves ni direcciones.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select

from app.core.config import VERSION, settings
from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.device import Device
from app.models.audit import AuditEntry
from app.models.domains import DeviceDomain, DeviceTlsFingerprint
from app.models.firewall_rule import FirewallRule
from app.models.network_usage import PortScan
from app.models.traffic import NetworkUsageHourly
from app.models.user import User
from app.services.ai_audit.providers import wants_compact
from app.services.ai_audit.host import read_listeners
from app.services.ai_audit.snapshot import (
    Options, RawAlert, RawConnection, RawData, RawDevice, RawLogin, RawPort, RawRule, RawUser, Snapshot,
    build_snapshot, night_shares,
)
from app.services.auth.audit import ACTIONS
from app.services.monitor import connections as conntrack
from app.services.backup.backup_service import backup_service
from app.services.firewall import iptables_manager
from app.services.firewall.firewall_service import firewall_service
from app.services.firewall.protection import _local_addresses
from app.services.monitor.neighbors import neighbors
from app.services.notifications.notifier import notifier
from app.services.security.security_service import security_service
from app.services.security.threat_lists import threat_lists
from app.services.tls_cert import tls_service

log = structlog.get_logger(__name__)
LOGIN_ACTIONS = [ACTIONS[("POST", "/auth/login")], ACTIONS[("POST", "/auth/token")]]


def options_from_settings() -> Options:
    return Options(
        include_names=settings.AI_AUDIT_INCLUDE_NAMES,
        include_domains=settings.AI_AUDIT_INCLUDE_DOMAINS,
        alert_days=settings.AI_AUDIT_ALERT_DAYS,
        compact_tokens=max(500, settings.AI_AUDIT_SNAPSHOT_TOKENS) if wants_compact() else 0,
    )


async def build(options: Options | None = None) -> Snapshot:
    options = options or options_from_settings()
    now = datetime.now(timezone.utc)
    raw = await collect(options, now)
    # En un hilo: con muchos dispositivos y alertas es trabajo de CPU, y en el
    # bucle de eventos pararía todo el backend (API, vigilancia, cortafuegos)
    return await asyncio.to_thread(build_snapshot, raw, options, now, VERSION)


async def collect(options: Options, now: datetime) -> RawData:
    since_alerts = now - timedelta(days=options.alert_days)
    since_usage = now - timedelta(days=7)
    async with AsyncSessionLocal() as db:
        devices = (await db.execute(select(Device))).scalars().all()

        # Último escaneo completo de cada dispositivo: los puertos de esa pasada
        ports = []
        for d in devices:
            if d.last_port_scan_at is None:
                continue
            rows = (await db.execute(
                select(PortScan).where(
                    PortScan.device_id == d.id, PortScan.state == "open",
                    PortScan.scanned_at >= d.last_port_scan_at - timedelta(minutes=10),
                )
            )).scalars().all()
            seen = set()
            for r in rows:
                if (r.port, r.protocol) not in seen:
                    seen.add((r.port, r.protocol))
                    ports.append(RawPort(str(d.id), r.port, r.protocol, r.service, r.version))

        alerts = (await db.execute(
            select(Alert).where(Alert.last_seen_at >= since_alerts)
        )).scalars().all()
        rules = (await db.execute(
            select(FirewallRule).where(FirewallRule.is_active.is_(True))
        )).scalars().all()
        users = (await db.execute(select(User))).scalars().all()
        usage = (await db.execute(
            select(NetworkUsageHourly.device_id,
                   func.sum(NetworkUsageHourly.bytes_sent), func.sum(NetworkUsageHourly.bytes_recv))
            .where(NetworkUsageHourly.hour >= since_usage)
            .group_by(NetworkUsageHourly.device_id)
        )).all()
        domain_rows = (await db.execute(
            select(DeviceDomain.device_id, DeviceDomain.domain, DeviceDomain.hits)
            .where(DeviceDomain.last_seen >= now - timedelta(days=30))
            .order_by(DeviceDomain.hits.desc())
        )).all()
        tls_rows = (await db.execute(
            select(DeviceTlsFingerprint.device_id, DeviceTlsFingerprint.fingerprint, DeviceTlsFingerprint.hits)
            .where(DeviceTlsFingerprint.last_seen >= now - timedelta(days=30))
            .order_by(DeviceTlsFingerprint.hits.desc())
        )).all()
        hourly = (await db.execute(
            select(NetworkUsageHourly.device_id, NetworkUsageHourly.hour,
                   NetworkUsageHourly.bytes_sent + NetworkUsageHourly.bytes_recv)
            .where(NetworkUsageHourly.hour >= since_usage)
        )).all()
        logins = (await db.execute(
            select(AuditEntry.ip, AuditEntry.status_code, AuditEntry.created_at)
            .where(AuditEntry.action.in_(LOGIN_ACTIONS), AuditEntry.created_at >= since_alerts)
        )).all()
        removed = (await db.execute(
            select(FirewallRule).where(FirewallRule.is_active.is_(False), FirewallRule.updated_at >= since_alerts)
            .order_by(FirewallRule.updated_at.desc())
        )).scalars().all()

    domains: dict[str, list[tuple[str, int]]] = {}
    for device_id, domain, hits in domain_rows:
        domains.setdefault(str(device_id), []).append((domain, hits))
    tls: dict[str, list[tuple[str, int]]] = {}
    for device_id, fingerprint, hits in tls_rows:
        tls.setdefault(str(device_id), []).append((fingerprint, hits))
    try:
        tz = ZoneInfo(settings.TIMEZONE)
    except Exception:
        tz = timezone.utc

    # Conexiones de ahora mismo; si conntrack no se puede leer, la auditoría sigue sin ellas
    by_ip = {}
    for d in devices:
        for ip in [d.ip, *neighbors.ipv6_of(d.mac)]:
            if ip:
                by_ip[ip] = str(d.id)
    try:
        live = await conntrack.network_connections(by_ip)
    except Exception as exc:
        log.warning("ai_audit.connections_failed", error=str(exc))
        live = None

    return RawData(
        devices=[
            RawDevice(
                id=str(d.id), mac=d.mac, ip=d.ip, hostname=d.hostname, vendor=d.vendor,
                device_type=d.device_type, is_trusted=d.is_trusted, is_blocked=d.is_blocked,
                first_seen=d.first_seen, last_seen=d.last_seen, ipv6=neighbors.ipv6_of(d.mac),
                last_port_scan_at=d.last_port_scan_at,
            )
            for d in devices
        ],
        ports=ports,
        alerts=[
            RawAlert(
                device_id=str(a.device_id) if a.device_id else None,
                severity=a.severity.value, source=a.source.value, status=a.status.value,
                title=a.title, description=a.description, occurrences=a.occurrences or 1,
                created_at=a.created_at, last_seen_at=a.last_seen_at,
            )
            for a in alerts
        ],
        rules=[
            RawRule(
                device_id=str(r.device_id) if r.device_id else None, ip=r.src_ip or r.dst_ip,
                reason=r.description or r.name, auto_generated=r.auto_generated, created_at=r.created_at,
            )
            for r in rules
        ],
        users=[RawUser(u.role, u.is_active, u.last_login_at) for u in users],
        usage_7d={str(device_id): (int(sent or 0), int(recv or 0)) for device_id, sent, recv in usage},
        domains=domains,
        system=system_summary(now),
        own_ips=[str(ip) for ip in _local_addresses()],
        connections=None if live is None else [
            RawConnection(
                device_id=c["device_id"], direction=c["direction"], protocol=c["protocol"],
                remote_ip=c["remote_ip"], remote_port=c["remote_port"], local_port=c["local_port"],
                status=c["status"],
            )
            for c in live
        ],
        tls=tls,
        night_share=night_shares([(str(d), h, int(b or 0)) for d, h, b in hourly], tz),
        logins=[RawLogin(ip, status == 200, at) for ip, status, at in logins],
        listeners=read_listeners(),
        removed_rules=[
            RawRule(
                device_id=str(r.device_id) if r.device_id else None, ip=r.src_ip or r.dst_ip,
                reason=r.description or r.name, auto_generated=r.auto_generated,
                created_at=r.created_at, removed_at=r.updated_at,
            )
            for r in removed
        ],
    )


def _hours_since(value, now: datetime) -> float | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round((now - value).total_seconds() / 3600, 1)


def system_summary(now: datetime) -> dict:
    """Estado de LanSentinel, resumido y sin datos que identifiquen la red."""
    router = firewall_service.router_status()
    ipv6 = router.get("ipv6") or {}
    intel = threat_lists.status()
    suricata = intel.get("suricata") or {}
    lists_updated = [s["updated_at"] for s in intel.get("lists", []) if s.get("updated_at")]
    tls = tls_service.status()
    backups = backup_service.status()
    security = security_service.get_status()
    notify = notifier.get_status()
    return {
        "modo_router": {
            "activo": router["active"],
            "dhcp_dns": router["dhcp_enabled"] and router["dhcp"]["running"],
            "reenvio_ipv4": router["ip_forward"],
            "ipv6_lan": {
                "activo": bool(ipv6.get("active")),
                "origen_prefijo": ipv6.get("source"),       # static | pd | ula
                "nat66": bool(ipv6.get("nat")),
            },
        },
        "cortafuegos": {
            "operativo": firewall_service.get_status()["running"],
            "ipv6": iptables_manager.ipv6_enabled(),
            "modo_cuarentena": firewall_service.quarantine_enabled,
            "bloqueo_automatico_alertas_criticas": settings.FIREWALL_AUTO_BLOCK_CRITICAL,
        },
        "deteccion": {
            "suricata_en_marcha": security["running"],
            "eventos_procesados": security["events_processed"],
            "reglas_cargadas": suricata.get("loaded"),
            "reglas_fallidas": suricata.get("failed"),
            "reglas_actualizadas_hace_horas": _hours_since(suricata.get("last_success_at"), now),
            "listas_de_amenazas": {
                "activas": intel["enabled"],
                "redes": intel["addresses"],
                "actualizadas_hace_horas": _hours_since(max(lists_updated), now) if lists_updated else None,
                "con_error": bool(intel.get("error")) or any(s.get("error") for s in intel.get("lists", [])),
            },
            "escaneo_de_puertos_cada_horas": settings.PORT_SCAN_INTERVAL_HOURS,
            "picos_de_consumo": settings.ANOMALY_DETECTION_ENABLED,
            "dominios_por_dispositivo": settings.DOMAIN_TRACKING_ENABLED,
        },
        "https": {
            "certificado": tls["issuer"],                   # lansentinel | custom | None
            "caduca_en_dias": round(-_hours_since(tls["valid_until"], now) / 24) if tls["valid_until"] else None,
        },
        "copias_de_seguridad": {
            "automaticas": backups["enabled"],
            "ultima_correcta_hace_horas": _hours_since(backups["last_success_at"], now),
            "con_error": bool(backups["last_error"]),
            "guardadas": len(backups["backups"]),
            "en_otro_disco": bool(settings.BACKUP_PATH),
        },
        "avisos": {
            "canales_configurados": [c["name"] for c in notify["channels"] if c["configured"]],
            "gravedad_minima": notify["min_severity"],
        },
    }
