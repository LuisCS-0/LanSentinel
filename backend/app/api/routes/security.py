"""
Router de seguridad: escaneo de puertos y estado del IDS.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.device import Device
from app.models.network_usage import PortScan
from app.schemas.security import (
    PortScanResponse, ScanResultResponse, SecurityStatusResponse,
)
from app.services.security.port_scanner import scan_and_persist
from app.services.security.security_service import security_service

router = APIRouter()


# ── Escaneo de puertos ────────────────────────────────────────────────────────

@router.post("/devices/{device_id}/scan", response_model=ScanResultResponse)
async def scan_device_ports(
    device_id: UUID,
    ports: str = "1-1024",
    db: AsyncSession = Depends(get_db),
):
    """
    Lanza un escaneo de puertos sobre el dispositivo indicado.
    Por defecto escanea el rango 1-1024 (puertos privilegiados).
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
    """
    latest = await db.execute(
        select(func.max(PortScan.scanned_at)).where(PortScan.device_id == device_id)
    )
    last_scan_at = latest.scalar()
    if last_scan_at is None:
        return []

    result = await db.execute(
        select(PortScan)
        .where(PortScan.device_id == device_id, PortScan.scanned_at == last_scan_at)
        .order_by(PortScan.port.asc())
    )
    return list(result.scalars().all())


# ── Estado del IDS ────────────────────────────────────────────────────────────

@router.get("/status", response_model=SecurityStatusResponse)
async def security_status():
    """Estado actual del servicio de seguridad (lector de Suricata)."""
    return security_service.get_status()
