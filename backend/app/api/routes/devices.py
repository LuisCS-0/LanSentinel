from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.device import DeviceResponse, DeviceSummary, DeviceUpdate, DeviceStatusCount
from app.schemas.network import NetworkUsageResponse, ActiveConnectionResponse
from app.services.monitor.device_repository import DeviceRepository
from app.services.monitor.traffic_collector import get_active_connections

router = APIRouter()


def _repo(db: AsyncSession = Depends(get_db)) -> DeviceRepository:
    return DeviceRepository(db)


@router.get("/", response_model=list[DeviceSummary])
async def list_devices(repo: DeviceRepository = Depends(_repo)):
    """Lista todos los dispositivos detectados, ordenados por última conexión."""
    return await repo.get_all()


@router.get("/summary", response_model=DeviceStatusCount)
async def device_summary(repo: DeviceRepository = Depends(_repo)):
    """Conteo de dispositivos por estado (total, trusted, blocked)."""
    return await repo.count_by_status()


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: UUID,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    repo: DeviceRepository = Depends(_repo),
):
    from datetime import datetime, timezone
    from sqlalchemy import update
    from app.models.device import Device

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No hay campos que actualizar")
    updates["updated_at"] = datetime.now(timezone.utc)
    await db.execute(update(Device).where(Device.id == device_id).values(**updates))
    await db.commit()
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@router.post("/{device_id}/trust")
async def trust_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    """Añade el dispositivo a la lista de confianza."""
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await repo.set_trusted(device.mac, trusted=True)
    return {"mac": device.mac, "is_trusted": True}


@router.delete("/{device_id}/trust")
async def untrust_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await repo.set_trusted(device.mac, trusted=False)
    return {"mac": device.mac, "is_trusted": False}


@router.post("/{device_id}/block")
async def block_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    """Bloquea el dispositivo (marca en BD; iptables se aplica desde firewall module)."""
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await repo.set_blocked(device.mac, blocked=True)
    return {"mac": device.mac, "is_blocked": True}


@router.delete("/{device_id}/block")
async def unblock_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    await repo.set_blocked(device.mac, blocked=False)
    return {"mac": device.mac, "is_blocked": False}


@router.get("/{device_id}/usage", response_model=list[NetworkUsageResponse])
async def device_usage(device_id: UUID, limit: int = 60, repo: DeviceRepository = Depends(_repo)):
    return await repo.get_traffic_history(device_id, limit=limit)


@router.get("/{device_id}/connections", response_model=list[ActiveConnectionResponse])
async def device_connections(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    all_conns = get_active_connections()
    return [c for c in all_conns if c.get("src_ip") == device.ip]
