from datetime import datetime
from typing import Literal
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


class DeviceConnection(BaseModel):
    """Conexión de un dispositivo vista desde él (tabla conntrack del gateway)."""
    protocol: str                       # tcp | udp | icmp...
    direction: Literal["outgoing", "incoming"]
    local_port: int | None              # puerto del dispositivo
    remote_ip: str
    remote_port: int | None
    remote_is_lan: bool                 # el otro extremo es una IP privada
    service: str | None                 # nombre del servicio por el puerto (HTTPS, DNS...)
    state: str | None                   # estado TCP según el kernel
    status: Literal["open", "pending", "closing"]
    expires_in: int                     # segundos hasta que el kernel la olvide


class DeviceConnectionsResponse(BaseModel):
    available: bool                     # False si no se pudo leer la tabla conntrack
    connections: list[DeviceConnection]


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
