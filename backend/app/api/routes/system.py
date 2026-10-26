from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.api.deps import require_admin
from app.services.monitor.monitor_service import monitor_service
from app.services.security.security_service import security_service
from app.services.firewall.firewall_service import firewall_service
from app.services.monitor.traffic_collector import TrafficCollector
from app.services.notifications.channels import NotificationError
from app.services.notifications.notifier import notifier
from app.services.events.broker import event_broker
from app.services.security.arp_watch import arp_watch
from app.services.security.scan_scheduler import scan_scheduler
from app.services.tls_cert import tls_service
from app.services.backup import archive
from app.services.backup.backup_service import backup_service

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
        "arp_watch": arp_watch.get_status(),
        "port_scans": scan_scheduler.get_status(),
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


# ── HTTPS ────────────────────────────────────────────────────────────────────

@router.get("/tls")
async def tls_status():
    """Certificado con el que se sirve el panel y CA de LanSentinel."""
    return tls_service.status()


@router.get("/tls/ca.crt")
async def tls_ca_certificate():
    """CA de LanSentinel, para importarla en los dispositivos (no es secreta)."""
    pem = tls_service.ca_pem()
    if pem is None:
        raise HTTPException(status_code=404, detail="Todavía no se ha generado la CA")
    return Response(
        content=pem,
        media_type="application/x-x509-ca-cert",
        headers={"Content-Disposition": 'attachment; filename="lansentinel-ca.crt"'},
    )


# ── Copias de seguridad ──────────────────────────────────────────────────────

@router.get("/backups")
async def backups_status():
    """Copias guardadas, próxima copia automática y último error."""
    return backup_service.status()


@router.post("/backups", status_code=201)
async def backup_now():
    """Hace una copia ahora (tarda unos segundos)."""
    try:
        backup = await backup_service.run("manual")
    except archive.BackupBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except archive.BackupError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"name": backup.name, "created_at": backup.created_at, "motivo": backup.motivo, "size": backup.size}


@router.get("/backups/{name}", dependencies=[Depends(require_admin)])
async def backup_download(name: str):
    """Descarga una copia. Contiene secretos: guárdala en un sitio seguro."""
    path = archive.backup_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="No existe esa copia")
    return FileResponse(path, media_type="application/gzip", filename=name)
