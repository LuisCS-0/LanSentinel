from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.network import GlobalStatsResponse, ActiveConnectionResponse, ScanTriggerResponse
from app.services.monitor.monitor_service import monitor_service
from app.services.monitor.traffic_collector import TrafficCollector, get_active_connections

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


@router.get("/connections", response_model=list[ActiveConnectionResponse])
async def all_connections():
    """Lista todas las conexiones activas del sistema (vía psutil)."""
    return get_active_connections()
