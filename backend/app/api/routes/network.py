from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.network import (
    GlobalStatsResponse, NetworkConnectionsResponse, ScanTriggerResponse,
    UsageSeriesResponse, TopDevicesResponse,
)
from app.services.monitor import connections
from app.services.monitor.neighbors import neighbors
from app.services.monitor.anomalies import anomaly_service
from app.services.security.domain_tracker import domain_tracker
from app.services.monitor.device_repository import DeviceRepository
from app.services.monitor.traffic_queries import TrafficRange, device_totals, usage_series
from app.services.monitor.monitor_service import monitor_service
from app.services.monitor.traffic_collector import TrafficCollector
from app.services.monitor.traffic_meter import traffic_meter

router = APIRouter()


@router.get("/stats", response_model=GlobalStatsResponse)
async def network_stats():
    """
    Estado global de la red: dispositivos online, tráfico de interfaz,
    estado del servicio de monitorización y métricas del sistema host.
    """
    collector = TrafficCollector(monitor_service._collector.interface)
    system = collector.system_stats()
    status = monitor_service.get_status()
    return {
        "interface":       status["interface"],
        "devices_online":  status["devices_online"],
        "monitor_running": status["running"],
        "last_scan_at":    status["last_scan_at"],
        "system":          system,
    }


@router.post("/scan", response_model=ScanTriggerResponse)
async def trigger_scan():
    """Fuerza un escaneo ARP inmediato fuera del ciclo periódico."""
    return await monitor_service.trigger_scan()


@router.get("/connections", response_model=NetworkConnectionsResponse)
async def all_connections(db: AsyncSession = Depends(get_db)):
    """
    Conexiones abiertas de todos los dispositivos conocidos, según la tabla
    conntrack del gateway (solo las que pasan por LanSentinel). Cada una lleva
    el device_id del dispositivo desde el que se ve.
    """
    devices = await DeviceRepository(db).get_all()
    by_ip = {d.ip: d.id for d in devices if d.ip}
    # Sus direcciones IPv6, según la tabla de vecinos
    by_ip.update({addr: d.id for d in devices for addr in neighbors.ipv6_of(d.mac)})
    conns = await connections.network_connections(by_ip)
    if conns is None:
        return NetworkConnectionsResponse(available=False, connections=[])
    kept, omitted = connections.most_relevant(conns)
    return NetworkConnectionsResponse(available=True, connections=domain_tracker.annotate(kept), omitted=omitted)


@router.get("/traffic/history")
async def network_traffic_history():
    """
    Histórico del tráfico total agregado de la red (todos los dispositivos).
    Devuelve hasta 120 muestras (últimos ~10 minutos con muestreo cada 5s).
    """
    return {
        "samples": traffic_meter.get_total_history(),
    }


@router.get("/traffic/usage", response_model=UsageSeriesResponse)
async def network_traffic_usage(range_: TrafficRange = Query("24h", alias="range"), db: AsyncSession = Depends(get_db)):
    """
    Consumo histórico de toda la red (suma de los dispositivos medidos) por
    tramos: 24h y 7d por horas, 30d por días, 1y por meses.
    """
    unit, buckets = await usage_series(db, range_)
    return UsageSeriesResponse(
        range=range_, unit=unit, buckets=buckets,
        total_sent=sum(b.bytes_sent for b in buckets),
        total_recv=sum(b.bytes_recv for b in buckets),
    )


@router.get("/traffic/top", response_model=TopDevicesResponse)
async def network_traffic_top(range_: TrafficRange = Query("24h", alias="range"), db: AsyncSession = Depends(get_db)):
    """Consumo total de cada dispositivo en el rango, de mayor a menor."""
    return TopDevicesResponse(range=range_, devices=await device_totals(db, range_))


@router.get("/devices/{device_id}/usage-profile")
async def device_usage_profile(device_id: UUID):
    """Consumo habitual por hora de un dispositivo y a partir de cuánto se avisa."""
    return await anomaly_service.profile(device_id)
