from pydantic import BaseModel


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
