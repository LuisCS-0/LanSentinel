from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PortScanResponse(BaseModel):
    """Un puerto detectado en un escaneo."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: UUID
    port: int
    protocol: str
    state: str
    service: str | None
    version: str | None
    scanned_at: datetime


class ScanResultResponse(BaseModel):
    """Respuesta inmediata al lanzar un escaneo de puertos."""
    ip: str
    ports_found: int
    scanned_at: datetime


class SecurityStatusResponse(BaseModel):
    """Estado del servicio de Suricata."""
    running: bool
    eve_path: str
    events_processed: int
    alerts_generated: int
    last_event_at: str | None
