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


class DeviceConnection(BaseModel):
    """Conexión de un dispositivo vista desde él (tabla conntrack del gateway)."""
    protocol: str                       # tcp | udp | icmp...
    direction: Literal["outgoing", "incoming"]
    local_port: int | None              # puerto del dispositivo
    remote_ip: str
    remote_port: int | None
    remote_is_lan: bool                 # el otro extremo es una IP privada
    service: str | None                 # nombre del servicio por el puerto (HTTPS, DNS...)
    remote_name: str | None = None      # dominio de la IP remota (DNS o SNI vistos por Suricata)
    state: str | None                   # estado TCP según el kernel
    # open: en uso · idle: TCP sin tráfico hace rato · pending: sin respuesta
    # done: intercambio suelto ya terminado (DNS, NTP) · closing: TCP cerrándose
    status: Literal["open", "idle", "pending", "done", "closing"]
    idle_seconds: int | None            # tiempo sin tráfico, si se puede deducir
    expires_in: int                     # segundos hasta que el kernel la olvide


class DeviceConnectionsResponse(BaseModel):
    available: bool                     # False si no se pudo leer la tabla conntrack
    connections: list[DeviceConnection]


class NetworkConnection(DeviceConnection):
    device_id: UUID                     # dispositivo desde el que se ve la conexión


class NetworkConnectionsResponse(BaseModel):
    available: bool
    connections: list[NetworkConnection]
    omitted: int = 0              # las menos relevantes que no se envían (connections.MAX_NETWORK_CONNECTIONS)


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
