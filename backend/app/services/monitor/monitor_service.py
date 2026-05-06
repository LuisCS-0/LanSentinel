"""
Servicio de monitorización principal.

Corre como tarea en background (asyncio) y coordina:
  1. Escaneo ARP periódico → descubre dispositivos → upsert en BD.
  2. Resolución de fabricante (OUI) para dispositivos nuevos.
  3. Snapshot de tráfico global cada intervalo.
  4. Detección de dispositivos nuevos (no vistos antes) → genera alerta.

El ciclo de vida lo gestiona FastAPI a través del lifespan:
    startup  → await monitor_service.start()
    shutdown → await monitor_service.stop()
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

log = structlog.get_logger(__name__)


class MonitorService:
    """
    Servicio singleton de monitorización.
    Gestiona el bucle de fondo y expone el estado actual para la API.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._collector = TrafficCollector(settings.MONITOR_INTERFACE)

        # Estado compartido (leído por la API sin tocar la BD)
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
        """
        Bucle principal. Cada iteración:
          - Escanea la red (ARP).
          - Upsert de dispositivos en BD.
          - Resuelve vendors de dispositivos nuevos.
          - Toma snapshot de tráfico.
          - Duerme hasta el siguiente intervalo.
        """
        log.info("monitor_service.loop_start")
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                # El bucle no debe morir por un error transitorio
                log.error("monitor_service.tick_error", error=str(exc), exc_info=True)

            await asyncio.sleep(settings.MONITOR_INTERVAL_SECONDS)

    async def _tick(self):
        """Una iteración del bucle de monitorización."""
        log.debug("monitor_service.tick")

        # 1. Escaneo ARP
        discovered = await scan_network(
            interface=settings.MONITOR_INTERFACE,
        )
        self.devices_online = len(discovered)
        self.last_scan_at = datetime.now(timezone.utc)

        if not discovered:
            log.warning("monitor_service.no_devices_found")
            return

        # 2. Resolver vendors (solo MACs sin vendor conocido)
        macs_without_vendor = [d.mac for d in discovered if d.vendor is None]
        if macs_without_vendor:
            vendors = await resolve_vendors_batch(macs_without_vendor)
            for device in discovered:
                device.vendor = vendors.get(device.mac)

        # 3. Upsert de dispositivos y detección de nuevos
        async with AsyncSessionLocal() as db:
            repo = DeviceRepository(db)
            new_devices: list[DiscoveredDevice] = []

            for disc in discovered:
                existing = await repo.get_by_mac(disc.mac)
                is_new = existing is None

                await repo.upsert_device(disc)

                if is_new:
                    new_devices.append(disc)
                    log.info(
                        "monitor_service.new_device",
                        mac=disc.mac,
                        ip=disc.ip,
                        vendor=disc.vendor,
                    )

            # 4. Alertas por dispositivos nuevos
            if new_devices:
                await self._alert_new_devices(db, new_devices)

        # 5. Snapshot de tráfico global
        traffic_delta = self._collector.sample_global()
        if traffic_delta:
            log.debug(
                "monitor_service.traffic",
                bytes_sent=traffic_delta.bytes_sent,
                bytes_recv=traffic_delta.bytes_recv,
            )
            # Aquí se podría guardar el delta global en BD si se quiere histórico
            # Por ahora solo lo logueamos; la BD de tráfico por dispositivo
            # se implementa cuando tengamos pcap (Fase 2 del módulo).

    async def _alert_new_devices(self, db, new_devices: list[DiscoveredDevice]):
        """Genera una alerta por cada dispositivo nuevo detectado en la red."""
        # Import aquí para evitar circular imports
        from app.models.alert import Alert, AlertSeverity, AlertSource, AlertStatus
        from app.services.monitor.device_repository import DeviceRepository

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
                    f"Se ha detectado un nuevo dispositivo: "
                    f"{disc.hostname or disc.mac} ({disc.ip}). "
                    f"Fabricante: {disc.vendor or 'desconocido'}. "
                    f"Verifica si pertenece a tu red y márcalo como confiable."
                ),
                raw_payload={
                    "mac": disc.mac,
                    "ip": disc.ip,
                    "hostname": disc.hostname,
                    "vendor": disc.vendor,
                },
            )
            db.add(alert)

        await db.commit()

    # ── API pública (para el endpoint /system/status) ─────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "interface": settings.MONITOR_INTERFACE,
            "interval_seconds": settings.MONITOR_INTERVAL_SECONDS,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "devices_online": self.devices_online,
        }

    async def trigger_scan(self) -> dict:
        """
        Fuerza un escaneo inmediato fuera del ciclo periódico.
        Lo ejecuta en background para no bloquear la respuesta HTTP.
        """
        asyncio.create_task(self._tick())
        return {"message": "Escaneo iniciado", "triggered_at": datetime.now(timezone.utc).isoformat()}


# Instancia global (singleton) — importar desde aquí en el resto del proyecto
monitor_service = MonitorService()
