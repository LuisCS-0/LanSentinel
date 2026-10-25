"""
Schemas Pydantic para serialización/deserialización de dispositivos.

Separamos el modelo ORM (Device) del schema de la API para poder
cambiar uno sin afectar al otro, y para controlar qué campos se exponen.
"""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DeviceBase(BaseModel):
    mac: str
    ip: str | None
    hostname: str | None
    vendor: str | None
    device_type: str | None
    notes: str | None


class DeviceResponse(DeviceBase):
    """Schema de respuesta completo para un dispositivo."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_trusted: bool
    is_blocked: bool
    first_seen: datetime
    last_seen: datetime
    last_port_scan_at: datetime | None = None


class DeviceUpdate(BaseModel):
    """Campos editables por el usuario."""
    hostname: str | None = None
    device_type: str | None = None
    notes: str | None = None


class DeviceSummary(BaseModel):
    """Vista compacta para listados."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mac: str
    ip: str | None
    hostname: str | None
    vendor: str | None
    device_type: str | None
    is_trusted: bool
    is_blocked: bool
    last_seen: datetime
    last_port_scan_at: datetime | None = None


class DeviceStatusCount(BaseModel):
    total: int
    trusted: int
    blocked: int
