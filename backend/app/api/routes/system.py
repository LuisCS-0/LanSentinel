from fastapi import APIRouter
from app.services.monitor.monitor_service import monitor_service
from app.services.monitor.traffic_collector import TrafficCollector

router = APIRouter()


@router.get("/info")
async def system_info():
    """Métricas del host: CPU, RAM, uptime."""
    collector = TrafficCollector(monitor_service._collector.interface)
    return collector.system_stats()


@router.get("/status")
async def service_status():
    """Estado de todos los servicios de LanSentinel."""
    return {
        "monitor":  monitor_service.get_status(),
        "suricata": {"running": False, "note": "Implementado en Fase 3"},
        "firewall": {"running": False, "note": "Implementado en Fase 4"},
    }
