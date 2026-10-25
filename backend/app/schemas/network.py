from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GlobalStatsResponse(BaseModel):
    interface: str
    devices_online: int
    monitor_running: bool
    last_scan_at: str | None
    system: dict


class ActiveConnectionResponse(BaseModel):
    src_ip: str
    src_port: int | None
    dst_ip: str | None
    dst_port: int | None
    protocol: str | None
    state: str | None
    pid: int | None
    process: str | None


class ScanTriggerResponse(BaseModel):
    message: str
    triggered_at: str


# ── Histórico de tráfico ─────────────────────────────────────────────────────

class UsageBucket(BaseModel):
    """Consumo de un tramo de la gráfica (hora, día o mes)."""
    # Se construye desde la dataclass Bucket de traffic_queries
    model_config = ConfigDict(from_attributes=True)

    start: datetime          # inicio del tramo, en hora local con zona
    bytes_sent: int          # subida
    bytes_recv: int          # descarga


class UsageSeriesResponse(BaseModel):
    range: str
    unit: str                # hour | day | month
    buckets: list[UsageBucket]
    total_sent: int
    total_recv: int


class DeviceUsage(BaseModel):
    device_id: UUID
    mac: str
    ip: str | None
    hostname: str | None
    vendor: str | None
    bytes_sent: int
    bytes_recv: int
    total_bytes: int


class TopDevicesResponse(BaseModel):
    range: str
    devices: list[DeviceUsage]
