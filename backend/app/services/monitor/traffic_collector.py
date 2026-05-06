"""
Recolector de métricas de tráfico por dispositivo.

Estrategia:
  - psutil.net_io_counters(pernic=True) nos da bytes globales por interfaz,
    pero NO por dispositivo. Para desglosar por dispositivo usamos
    psutil.net_connections() para mapear conexiones a IPs locales.

  - Para métricas por dispositivo de forma precisa se necesita pcap (Scapy).
    Implementamos ambas aproximaciones:

    1. RÁPIDA (psutil): tráfico global de la interfaz. Útil para el dashboard.
    2. PRECISA (Scapy sniffer): contabiliza bytes src/dst por IP en la LAN.
       Se activa si el sistema tiene CAP_NET_RAW.

  La clase TrafficCollector mantiene el estado entre muestras para calcular
  el delta (bytes en el intervalo, no el total acumulado).
"""

import asyncio
import time
from collections import defaultdict
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
class DeviceTrafficDelta:
    """Bytes enviados/recibidos por un dispositivo en el intervalo de muestreo."""
    ip: str
    bytes_sent: int       # bytes hacia el exterior
    bytes_recv: int       # bytes desde el exterior
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GlobalTrafficDelta:
    """Tráfico total de la interfaz en el intervalo."""
    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TrafficCollector:
    """
    Mantiene el estado de los contadores de red entre muestras.
    Instanciar una vez y llamar a sample() periódicamente.
    """

    def __init__(self, interface: str):
        self.interface = interface
        self._last_snapshot: InterfaceSnapshot | None = None
        self._last_per_ip: dict[str, int] = defaultdict(int)

    # ── Tráfico global de la interfaz ─────────────────────────────────────────

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
                return None  # Primera muestra: solo inicializamos

            elapsed = now_snap.timestamp - self._last_snapshot.timestamp
            if elapsed <= 0:
                return None

            delta = GlobalTrafficDelta(
                interface=self.interface,
                bytes_sent=max(0, now_snap.bytes_sent - self._last_snapshot.bytes_sent),
                bytes_recv=max(0, now_snap.bytes_recv - self._last_snapshot.bytes_recv),
                packets_sent=max(0, c.packets_sent - getattr(self._last_snapshot, "packets_sent", c.packets_sent)),
                packets_recv=max(0, c.packets_recv - getattr(self._last_snapshot, "packets_recv", c.packets_recv)),
            )

            self._last_snapshot = now_snap
            return delta

        except Exception as exc:
            log.error("traffic_collector.global_error", error=str(exc))
            return None

    # ── Tráfico por dispositivo (aproximación via conexiones activas) ──────────

    def sample_per_device(self) -> list[DeviceTrafficDelta]:
        """
        Aproximación rápida: agrupa conexiones TCP activas por IP de origen.
        No mide bytes reales por dispositivo (eso requiere pcap), pero permite
        identificar qué dispositivos tienen actividad en este momento.

        Para métricas de bytes exactas por dispositivo, ver _scapy_sniffer.py.
        """
        try:
            connections = psutil.net_connections(kind="inet")
            ip_activity: dict[str, int] = defaultdict(int)

            for conn in connections:
                if conn.laddr and conn.raddr:
                    # Contamos conexiones activas como proxy de actividad
                    ip_activity[conn.laddr.ip] += 1

            # Convertir a deltas (sin bytes reales: se necesita pcap para eso)
            deltas = [
                DeviceTrafficDelta(ip=ip, bytes_sent=0, bytes_recv=0)
                for ip in ip_activity
            ]
            return deltas

        except Exception as exc:
            log.error("traffic_collector.per_device_error", error=str(exc))
            return []

    # ── Estadísticas del sistema host ─────────────────────────────────────────

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


# ── Utilidad: lista de conexiones activas del sistema ─────────────────────────

def get_active_connections() -> list[dict]:
    """
    Devuelve las conexiones TCP/UDP activas del sistema, enriquecidas
    con el nombre del proceso cuando es posible.
    """
    results = []
    try:
        connections = psutil.net_connections(kind="inet")
        for conn in connections:
            if not conn.laddr:
                continue

            process_name = None
            try:
                if conn.pid:
                    process_name = psutil.Process(conn.pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            results.append({
                "src_ip":   conn.laddr.ip,
                "src_port": conn.laddr.port,
                "dst_ip":   conn.raddr.ip if conn.raddr else None,
                "dst_port": conn.raddr.port if conn.raddr else None,
                "protocol": "tcp" if conn.type.name == "SOCK_STREAM" else "udp",
                "state":    conn.status,
                "pid":      conn.pid,
                "process":  process_name,
            })
    except Exception as exc:
        log.error("get_active_connections.error", error=str(exc))

    return results
