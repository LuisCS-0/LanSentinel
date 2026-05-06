"""
Capa de acceso a datos para dispositivos y tráfico.

Centraliza todas las queries relacionadas con DISPOSITIVO y TRAFICO
para que el servicio de monitorización no tenga SQL directo.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.device import Device
from app.models.network_usage import NetworkUsage
from app.services.monitor.arp_scanner import DiscoveredDevice

import structlog

log = structlog.get_logger(__name__)


class DeviceRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Dispositivos ──────────────────────────────────────────────────────────

    async def upsert_device(self, discovered: DiscoveredDevice) -> Device:
        """
        Inserta el dispositivo si es nuevo, o actualiza IP/hostname/last_seen
        si ya existía (identificado por MAC).

        Usa INSERT ... ON CONFLICT (mac) DO UPDATE para que sea atómico.
        """
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
        """Resumen rápido para el dashboard: total, trusted, blocked, new (last 24h)."""
        total_q   = await self.db.execute(select(func.count()).select_from(Device))
        trusted_q = await self.db.execute(select(func.count()).select_from(Device).where(Device.is_trusted == True))   # noqa
        blocked_q = await self.db.execute(select(func.count()).select_from(Device).where(Device.is_blocked == True))   # noqa
        return {
            "total":   total_q.scalar(),
            "trusted": trusted_q.scalar(),
            "blocked": blocked_q.scalar(),
        }

    # ── Tráfico ───────────────────────────────────────────────────────────────

    async def save_traffic_snapshot(
        self,
        device_id: UUID,
        bytes_sent: int,
        bytes_recv: int,
        packets_sent: int = 0,
        packets_recv: int = 0,
    ) -> NetworkUsage:
        """Guarda un snapshot de tráfico para un dispositivo."""
        usage = NetworkUsage(
            device_id=device_id,
            bytes_sent=bytes_sent,
            bytes_recv=bytes_recv,
            packets_sent=packets_sent,
            packets_recv=packets_recv,
        )
        self.db.add(usage)
        await self.db.commit()
        await self.db.refresh(usage)
        return usage

    async def get_traffic_history(
        self,
        device_id: UUID,
        limit: int = 100,
    ) -> list[NetworkUsage]:
        """Últimos N snapshots de tráfico de un dispositivo."""
        result = await self.db.execute(
            select(NetworkUsage)
            .where(NetworkUsage.device_id == device_id)
            .order_by(NetworkUsage.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_global_traffic_last_n(self, limit: int = 60) -> list[NetworkUsage]:
        """Últimas N muestras de tráfico global (todas las interfaces)."""
        result = await self.db.execute(
            select(NetworkUsage)
            .order_by(NetworkUsage.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
