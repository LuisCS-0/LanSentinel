"""
Recolector de métricas de tráfico por dispositivo.

Estrategia usada:
  - psutil.net_io_counters(pernic=True) nos da bytes globales por interfaz,
    pero NO por dispositivo: eso lo mide traffic_meter (cadena
    LANSENTINEL_ACCT) y las conexiones de cada uno, connections.py
    (tabla conntrack).

  La clase TrafficCollector mantiene el estado entre muestras para calcular
  el delta (bytes en el intervalo, no el total acumulado).
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psutil
import structlog

log = structlog.get_logger(__name__)


@dataclass
class InterfaceSnapshot:
    """Snapshot puntual del contador de bytes de una interfaz."""
    bytes_sent: int
    bytes_recv: int
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class GlobalTrafficDelta:
    """Tráfico total de la interfaz en el intervalo."""
    interface: str
    bytes_sent: int
    bytes_recv: int
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TrafficCollector:
    """
    Mantiene el estado de los contadores de red entre muestras.
    Instanciar una vez y llamar a sample() periódicamente.
    """

    def __init__(self, interface: str):
        self.interface = interface
        self._last_snapshot: InterfaceSnapshot | None = None
    # Tráfico global de la interfaz

    def sample_global(self) -> GlobalTrafficDelta | None:
        """
        Toma un snapshot de la interfaz y calcula el delta desde la última muestra.
        Primera llamada retorna None (no hay delta aún).
        """
        try:
            counters = psutil.net_io_counters(pernic=True)
            if self.interface not in counters:
                log.warning("traffic_collector.interface_not_found", iface=self.interface)
                return None

            c = counters[self.interface]
            now_snap = InterfaceSnapshot(
                bytes_sent=c.bytes_sent,
                bytes_recv=c.bytes_recv,
            )

            if self._last_snapshot is None:
                self._last_snapshot = now_snap
                return None  # Primera muestra, solo inicializamos

            elapsed = now_snap.timestamp - self._last_snapshot.timestamp
            if elapsed <= 0:
                return None

            delta = GlobalTrafficDelta(
                interface=self.interface,
                # Evitamos valores negativos si el contador se reinicia con max.
                bytes_sent=max(0, now_snap.bytes_sent - self._last_snapshot.bytes_sent),
                bytes_recv=max(0, now_snap.bytes_recv - self._last_snapshot.bytes_recv),
            )

            self._last_snapshot = now_snap
            return delta

        except Exception as exc:
            log.error("traffic_collector.global_error", error=str(exc))
            return None

    # Estadísticas del sistema host

    @staticmethod
    def system_stats() -> dict:
        """CPU, RAM y uptime del host donde corre LanSentinel."""
        try:
            mem = psutil.virtual_memory()
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "memory_total_mb": mem.total // (1024 * 1024),
                "memory_used_mb": mem.used // (1024 * 1024),
                "memory_percent": mem.percent,
                "uptime_seconds": int(time.time() - psutil.boot_time()),
            }
        except Exception as exc:
            log.error("traffic_collector.system_stats_error", error=str(exc))
            return {}
