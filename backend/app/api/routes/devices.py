from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.device import Device

router = APIRouter()


@router.get("/")
async def list_devices(db: AsyncSession = Depends(get_db)):
    """Devuelve todos los dispositivos detectados en la red."""
    result = await db.execute(select(Device).order_by(Device.last_seen.desc()))
    devices = result.scalars().all()
    return devices


@router.get("/{device_id}")
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Detalle de un dispositivo."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device
