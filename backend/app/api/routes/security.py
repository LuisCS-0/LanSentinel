"""
Router de seguridad: escaneo de puertos y estado del IDS.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.device import Device
from app.models.network_usage import PortScan
from app.schemas.security import (
    PortScanResponse, ScanResultResponse, SecurityStatusResponse,
)
from app.services.security.insecure_services import DEFAULT_SCAN_PORTS, assess
from app.services.security.port_scanner import latest_scan_time, scan_and_persist
from app.services.security.security_service import security_service
from app.services.security.threat_lists import threat_lists

router = APIRouter()


# ── Escaneo de puertos ────────────────────────────────────────────────────────

@router.post("/devices/{device_id}/scan", response_model=ScanResultResponse)
async def scan_device_ports(
    device_id: UUID,
    ports: str = DEFAULT_SCAN_PORTS,
    db: AsyncSession = Depends(get_db),
):
    """
    Lanza un escaneo de puertos sobre el dispositivo indicado.
    Por defecto escanea 1-1024 más los puertos de servicios que suelen quedar
    expuestos (DEFAULT_SCAN_PORTS); solo ese escaneo completo genera alertas
    de servicios inseguros y puertos nuevos.
    El parámetro 'ports' acepta el formato de nmap: '22,80,443' o '1-65535'.
    """
    result_q = await db.execute(select(Device).where(Device.id == device_id))
    device = result_q.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    if not device.ip:
        raise HTTPException(status_code=400, detail="El dispositivo no tiene IP conocida")

    scan_result = await scan_and_persist(
        device_id=device.id,
        ip=device.ip,
        db=db,
        ports=ports,
    )
    if not scan_result.ok:
        raise HTTPException(
            status_code=502,
            detail="No se pudo escanear: el dispositivo no responde o nmap ha fallado",
        )

    return ScanResultResponse(
        ip=scan_result.ip,
        ports_found=len(scan_result.ports),
        scanned_at=scan_result.scanned_at,
    )


@router.get("/devices/{device_id}/ports", response_model=list[PortScanResponse])
async def get_device_ports(
    device_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista los puertos detectados en el último escaneo del dispositivo.

    La tabla conserva el histórico de todos los escaneos; aquí solo se
    devuelven las filas del más reciente para no mostrar puertos repetidos.
    Cada puerto abierto indica si es un servicio inseguro y por qué.
    """
    device = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    last_scan_at = await latest_scan_time(db, device)
    if last_scan_at is None:
        return []

    result = await db.execute(
        select(PortScan)
        .where(PortScan.device_id == device_id, PortScan.scanned_at == last_scan_at)
        .order_by(PortScan.port.asc())
    )
    ports = []
    for row in result.scalars().all():
        item = PortScanResponse.model_validate(row)
        risk = assess(row.port, row.service) if row.state == "open" else None
        if risk:
            item.risk_severity = risk.severity.value
            item.risk_reason = risk.reason
        ports.append(item)
    return ports


# ── Estado del IDS ────────────────────────────────────────────────────────────

@router.get("/status", response_model=SecurityStatusResponse)
async def security_status():
    """Estado actual del servicio de seguridad (lector de Suricata)."""
    return security_service.get_status()


# ── Inteligencia de amenazas ─────────────────────────────────────────────────

@router.get("/threat-intel")
async def threat_intel_status():
    """Listas de IPs maliciosas cargadas, tráfico cortado y reglas de Suricata."""
    return threat_lists.status()


@router.post("/threat-intel/update", status_code=202)
async def threat_intel_update():
    """Descarga las listas ahora (tarda unos segundos; el estado se actualiza solo)."""
    if not threat_lists.status()["enabled"]:
        raise HTTPException(status_code=409, detail="Las listas de amenazas están desactivadas (THREAT_LISTS_ENABLED)")
    threat_lists.request_update()
    return {"detail": "Actualización en marcha"}
