"""Capa de acceso a datos para dispositivos."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.device import Device
from app.services.monitor.arp_scanner import DiscoveredDevice

import structlog

log = structlog.get_logger(__name__)


class DeviceRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # Dispositivos 

    async def upsert_device(self, discovered: DiscoveredDevice) -> Device:
        """Inserta el dispositivo si es nuevo, o actualiza IP/hostname/last_seen si ya existía (identificado por MAC)."""
        stmt = (
            pg_insert(Device)
            .values(
                mac=discovered.mac,
                ip=discovered.ip,
                hostname=discovered.hostname,
                vendor=discovered.vendor,
                last_seen=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["mac"],
                set_={
                    "ip":        discovered.ip,
                    "hostname":  discovered.hostname,
                    "vendor":    discovered.vendor,
                    "last_seen": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            .returning(Device)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        device = result.scalar_one()
        return device

    async def get_all(self, include_blocked: bool = True) -> list[Device]:
        """Lista todos los dispositivos, ordenados por last_seen desc."""
        stmt = select(Device).order_by(Device.last_seen.desc())
        if not include_blocked:
            stmt = stmt.where(Device.is_blocked == False)  # noqa: E712
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_mac(self, mac: str) -> Device | None:
        result = await self.db.execute(select(Device).where(Device.mac == mac.upper()))
        return result.scalar_one_or_none()

    async def get_by_macs(self, macs: list[str]) -> dict[str, Device]:
        """Dispositivos ya registrados con alguna de esas MACs, indexados por MAC."""
        if not macs:
            return {}
        result = await self.db.execute(
            select(Device).where(Device.mac.in_({m.upper() for m in macs}))
        )
        return {d.mac: d for d in result.scalars().all()}

    async def get_by_id(self, device_id: UUID) -> Device | None:
        result = await self.db.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def set_trusted(self, mac: str, trusted: bool) -> bool:
        result = await self.db.execute(
            update(Device)
            .where(Device.mac == mac.upper())
            .values(is_trusted=trusted, updated_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def set_blocked(self, mac: str, blocked: bool) -> bool:
        result = await self.db.execute(
            update(Device)
            .where(Device.mac == mac.upper())
            .values(is_blocked=blocked, updated_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount > 0

    async def count_by_status(self) -> dict:
        """Resumen rápido para el dashboard: total, trusted, blocked."""
        total_q   = await self.db.execute(select(func.count()).select_from(Device))
        trusted_q = await self.db.execute(select(func.count()).select_from(Device).where(Device.is_trusted == True))   # noqa
        blocked_q = await self.db.execute(select(func.count()).select_from(Device).where(Device.is_blocked == True))   # noqa
        return {
            "total":   total_q.scalar(),
            "trusted": trusted_q.scalar(),
            "blocked": blocked_q.scalar(),
        }