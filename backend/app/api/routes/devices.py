from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.device import DeviceResponse, DeviceSummary, DeviceUpdate, DeviceStatusCount
from app.schemas.network import ActiveConnectionResponse
from app.services.monitor.device_repository import DeviceRepository
from app.services.monitor.traffic_collector import get_active_connections
from app.services.monitor.traffic_meter import traffic_meter

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


@router.get("/{device_id}/traffic")
async def device_traffic(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    """
    Tasa actual (bytes/segundo) de tráfico entrante y saliente del dispositivo.

    El valor refleja el promedio de los últimos N segundos (intervalo de
    lectura del TrafficMeter, configurable). Si LanSentinel no está
    actuando como gateway de este dispositivo, devuelve ceros.
    """
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    if not device.ip:
        return {
            "device_id": str(device_id), "ip": None,
            "rx_bps": 0, "tx_bps": 0, "total_bps": 0,
            "tracking": False,
        }

    sample = traffic_meter.get_sample(device.ip)
    if not sample:
        return {
            "device_id": str(device_id), "ip": device.ip,
            "rx_bps": 0, "tx_bps": 0, "total_bps": 0,
            "tracking": False,
        }
    return {
        "device_id": str(device_id),
        "ip": device.ip,
        "rx_bps": round(sample.rx_bps, 2),
        "tx_bps": round(sample.tx_bps, 2),
        "total_bps": round(sample.total_bps, 2),
        "tracking": True,
    }


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
    """
    Bloquea el dispositivo:
      1. Marca is_blocked=True en BD para que el frontend lo refleje.
      2. Crea una regla activa en firewall_rules e instala el DROP en iptables.
    """
    from app.services.firewall.firewall_service import firewall_service
    from app.services.firewall.protection import ProtectedAddressError

    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    # 1. Aplicar regla real en iptables (si tiene IP conocida)
    if device.ip:
        try:
            await firewall_service.block_ip(
                ip=device.ip,
                reason=f"Bloqueo de dispositivo {device.mac}",
                device_id=device.id,
                auto_generated=False,
            )
        except ProtectedAddressError as exc:
            raise HTTPException(status_code=400, detail=f"No se puede bloquear este dispositivo: {exc}")

    # 2. Marcar como bloqueado en BD
    await repo.set_blocked(device.mac, blocked=True)

    return {"mac": device.mac, "is_blocked": True}


@router.delete("/{device_id}/block")
async def unblock_device(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    """
    Desbloquea el dispositivo:
      1. Quita la regla activa de iptables y la marca inactiva en BD.
      2. Pone is_blocked=False en el dispositivo.
    """
    from app.services.firewall.firewall_service import firewall_service
    from app.services.firewall.rule_repository import FirewallRuleRepository
    from app.db.session import AsyncSessionLocal

    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")

    # 1. Buscar y quitar reglas activas asociadas a esta IP
    if device.ip:
        async with AsyncSessionLocal() as db:
            fw_repo = FirewallRuleRepository(db)
            existing = await fw_repo.get_active_by_ip(device.ip)
            if existing:
                await firewall_service.unblock_rule(existing.id)

    # 2. Marcar como no bloqueado en BD
    await repo.set_blocked(device.mac, blocked=False)

    return {"mac": device.mac, "is_blocked": False}


@router.get("/{device_id}/connections", response_model=list[ActiveConnectionResponse])
async def device_connections(device_id: UUID, repo: DeviceRepository = Depends(_repo)):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    all_conns = get_active_connections()
    return [c for c in all_conns if c.get("src_ip") == device.ip]
