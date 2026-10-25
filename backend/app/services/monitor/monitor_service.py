"""
Servicio de monitorización principal.

Bucle background que orquesta:
  1. Escaneo ARP periódico → descubre dispositivos → upsert en BD.
  2. Resolución de fabricante (OUI) para dispositivos nuevos.
  3. Snapshot de tráfico global cada intervalo.
  4. Detección de dispositivos nuevos → genera alerta + lanza port scan.
"""

import asyncio
from datetime import datetime, timezone

import structlog

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.services.monitor.arp_scanner import scan_network, DiscoveredDevice
from app.services.monitor.oui_resolver import resolve_vendors_batch
from app.services.monitor.traffic_collector import TrafficCollector
from app.services.monitor.device_repository import DeviceRepository
from app.services.monitor.traffic_meter import traffic_meter
from app.services.alerts.alert_service import create_alert
from app.services.firewall.firewall_service import firewall_service

log = structlog.get_logger(__name__)


def _one_entry_per_mac(
    discovered: list[DiscoveredDevice], known: dict,
) -> list[DiscoveredDevice]:
    """
    Una misma MAC puede responder por varias IPs en un escaneo (alias de red,
    proxy ARP del router...). Se conserva una sola entrada: la IP que ya tenía
    registrada si sigue entre las respuestas o, si no, la primera. Así la IP no
    alterna entre escaneos generando falsas alertas de cambio de IP.
    """
    by_mac: dict[str, list[DiscoveredDevice]] = {}
    for disc in discovered:
        by_mac.setdefault(disc.mac, []).append(disc)

    result = []
    for mac, entries in by_mac.items():
        stored = known.get(mac)
        chosen = next((d for d in entries if stored and d.ip == stored.ip), entries[0])
        if len(entries) > 1:
            log.info("monitor_service.mac_multiple_ips", mac=mac, ips=[d.ip for d in entries])
        result.append(chosen)
    return result


class MonitorService:

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._collector = TrafficCollector(settings.MONITOR_INTERFACE)
        # Evita que un escaneo manual se solape con el del bucle periódico
        # (ambos verían el mismo dispositivo como nuevo y duplicarían alertas)
        self._tick_lock = asyncio.Lock()

        self.last_scan_at: datetime | None = None
        self.devices_online: int = 0
        self.is_running: bool = False

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            log.warning("monitor_service.already_running")
            return
        self._running = True
        self.is_running = True
        self._task = asyncio.create_task(self._loop(), name="monitor_loop")
        log.info("monitor_service.started", interface=settings.MONITOR_INTERFACE)

    async def stop(self):
        self._running = False
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("monitor_service.stopped")

    # ── Bucle principal ───────────────────────────────────────────────────────

    async def _loop(self):
        log.info("monitor_service.loop_start")
        while self._running:
            try:
                async with self._tick_lock:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("monitor_service.tick_error", error=str(exc), exc_info=True)
            await asyncio.sleep(settings.MONITOR_INTERVAL_SECONDS)

    async def _tick(self):
        log.debug("monitor_service.tick")

        # 1. Escaneo ARP
        discovered = await scan_network(interface=settings.MONITOR_INTERFACE)
        self.last_scan_at = datetime.now(timezone.utc)

        if not discovered:
            self.devices_online = 0
            log.warning("monitor_service.no_devices_found")
            return

        async with AsyncSessionLocal() as db:
            repo = DeviceRepository(db)
            known = await repo.get_by_macs([d.mac for d in discovered])
            discovered = _one_entry_per_mac(discovered, known)
            self.devices_online = len(discovered)

            # 2. Resolver vendors (solo MACs nuevas o que aún no tienen vendor)
            macs_without_vendor = [
                d.mac for d in discovered
                if d.vendor is None and not (d.mac in known and known[d.mac].vendor)
            ]
            if macs_without_vendor:
                vendors = await resolve_vendors_batch(macs_without_vendor)
                for device in discovered:
                    device.vendor = vendors.get(device.mac)

            # 3. Upsert + detección de nuevos y de cambios de IP
            new_devices: list[DiscoveredDevice] = []
            ip_changes: list[tuple] = []

            for disc in discovered:
                existing = known.get(disc.mac)
                # Valores previos, antes de que el upsert los actualice
                old_ip = existing.ip if existing else None
                was_blocked = bool(existing and existing.is_blocked)

                await repo.upsert_device(disc)

                if disc.ip:
                    await traffic_meter.ensure_tracking(disc.ip)

                if existing is None:
                    new_devices.append(disc)
                    log.info(
                        "monitor_service.new_device",
                        mac=disc.mac, ip=disc.ip, vendor=disc.vendor,
                    )
                elif old_ip and disc.ip and old_ip != disc.ip:
                    ip_changes.append((existing, old_ip, disc.ip, was_blocked))
                    log.info(
                        "monitor_service.ip_changed",
                        mac=disc.mac, old_ip=old_ip, new_ip=disc.ip,
                    )

                # Un dispositivo bloqueado por MAC que aparece con otra IP:
                # se actualiza también la línea por IP de su regla
                if was_blocked:
                    await firewall_service.sync_device_ip(disc.mac, disc.ip)

            # 4. Alertas + escaneo automático de puertos
            if ip_changes:
                await self._alert_ip_changes(db, ip_changes)
            if new_devices:
                await self._alert_new_devices(db, new_devices)
                await self._auto_scan_new_devices(new_devices, db)

        # 5. Snapshot de tráfico global
        traffic_delta = self._collector.sample_global()
        if traffic_delta:
            log.debug(
                "monitor_service.traffic",
                bytes_sent=traffic_delta.bytes_sent,
                bytes_recv=traffic_delta.bytes_recv,
            )

    # ── Alertas y escaneo automático ──────────────────────────────────────────

    async def _alert_new_devices(self, db, new_devices: list[DiscoveredDevice]):
        """Genera una alerta por cada dispositivo nuevo detectado."""
        from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus

        repo = DeviceRepository(db)
        for disc in new_devices:
            device = await repo.get_by_mac(disc.mac)
            if not device:
                continue
            alert = Alert(
                device_id=device.id,
                severity=AlertSeverity.low,
                source=AlertSource.monitor,
                status=AlertStatus.new,
                title="Nuevo dispositivo detectado en la red",
                description=(
                    f"Dispositivo: {disc.hostname or disc.mac} ({disc.ip}). "
                    f"Fabricante: {disc.vendor or 'desconocido'}. "
                    f"Verifica si pertenece a tu red y márcalo como confiable."
                ),
                raw_payload={
                    "mac": disc.mac, "ip": disc.ip,
                    "hostname": disc.hostname, "vendor": disc.vendor,
                },
            )
            db.add(alert)
        await db.commit()

    async def _alert_ip_changes(self, db, changes: list[tuple]):
        """
        Genera una alerta por cada dispositivo conocido que ha cambiado de IP.
        Si el dispositivo estaba bloqueado se eleva la severidad: cambiar de IP
        es la forma más sencilla de intentar esquivar un bloqueo por IP.
        """
        from app.models.alert import AlertSeverity, AlertSource

        for device, old_ip, new_ip, was_blocked in changes:
            name = device.hostname or device.mac
            description = f"El dispositivo {name} ({device.mac}) ha pasado de {old_ip} a {new_ip}."
            if was_blocked:
                severity = AlertSeverity.medium
                description += (
                    " Está bloqueado: el bloqueo por MAC se mantiene y se ha"
                    " actualizado a la nueva IP. Un cambio de IP en un equipo"
                    " bloqueado puede ser un intento de esquivar el bloqueo."
                )
            elif device.is_trusted:
                severity = AlertSeverity.info
            else:
                severity = AlertSeverity.low

            await create_alert(
                db,
                device_id=device.id,
                severity=severity,
                source=AlertSource.monitor,
                title="Cambio de IP de un dispositivo",
                description=description,
                raw_payload={
                    "mac": device.mac, "old_ip": old_ip, "new_ip": new_ip,
                    "blocked": was_blocked,
                },
            )

    async def _auto_scan_new_devices(self, new_devices: list[DiscoveredDevice], db):
        """
        Lanza un escaneo de puertos en background para cada dispositivo nuevo.
        No espera a que termine — los resultados se persisten asincrónicamente.
        """
        # Import tardío para evitar dependencia circular monitor ↔ security
        from app.services.security.port_scanner import scan_and_persist
        from app.services.monitor.device_repository import DeviceRepository

        repo = DeviceRepository(db)
        for disc in new_devices:
            device = await repo.get_by_mac(disc.mac)
            if not device or not device.ip:
                continue

            # Lanzamos cada escaneo como tarea independiente para no bloquear
            # el ciclo de monitorización; cada una abre su propia sesión de BD.
            asyncio.create_task(
                self._run_background_scan(device.id, device.ip),
                name=f"port_scan_{device.mac}",
            )
            log.info(
                "monitor_service.auto_scan_triggered",
                mac=device.mac, ip=device.ip,
            )

    async def _run_background_scan(self, device_id, ip: str):
        """Wrapper que abre su propia sesión de BD para el escaneo en background."""
        from app.services.security.port_scanner import scan_and_persist
        try:
            async with AsyncSessionLocal() as db:
                await scan_and_persist(device_id=device_id, ip=ip, db=db)
        except Exception as exc:
            log.error("monitor_service.bg_scan_error", ip=ip, error=str(exc))

    # ── API pública ───────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "interface": settings.MONITOR_INTERFACE,
            "interval_seconds": settings.MONITOR_INTERVAL_SECONDS,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "devices_online": self.devices_online,
        }

    async def trigger_scan(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        if self._tick_lock.locked():
            return {"message": "Ya hay un escaneo en curso", "triggered_at": now}
        asyncio.create_task(self._manual_tick(), name="monitor_manual_scan")
        return {"message": "Escaneo iniciado", "triggered_at": now}

    async def _manual_tick(self):
        try:
            async with self._tick_lock:
                await self._tick()
        except Exception as exc:
            log.error("monitor_service.manual_tick_error", error=str(exc), exc_info=True)


monitor_service = MonitorService()
