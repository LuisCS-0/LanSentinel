from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.monitor.monitor_service import monitor_service
from app.services.security.security_service import security_service
from app.services.firewall.firewall_service import firewall_service
from app.services.monitor.traffic_collector import TrafficCollector
from app.services.notifications.channels import NotificationError
from app.services.notifications.notifier import notifier
from app.services.events.broker import event_broker

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
        "security": security_service.get_status(),
        "firewall": firewall_service.get_status(),
    }


# ── Avisos ───────────────────────────────────────────────────────────────────

class TestNotificationRequest(BaseModel):
    channel: str


@router.get("/notifications")
async def notifications_status():
    """
    Configuración de avisos: severidad mínima, límite por hora y estado de
    cada canal (si está configurado, último envío y último error). Los
    secretos (tokens, contraseñas) nunca se devuelven.
    """
    status = notifier.get_status()
    status["live_clients"] = event_broker.subscriber_count
    return status


@router.post("/notifications/test")
async def notifications_test(payload: TestNotificationRequest):
    """Envía un aviso de prueba por el canal indicado (telegram, ntfy o email)."""
    try:
        await notifier.send_test(payload.channel)
    except NotificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"sent": True, "channel": payload.channel}
