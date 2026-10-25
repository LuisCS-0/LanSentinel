from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class FirewallRuleResponse(BaseModel):
    """Respuesta de una regla del cortafuegos."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    is_active: bool
    src_ip: str | None
    src_mac: str | None
    action: str
    direction: str
    protocol: str
    device_id: UUID | None
    auto_generated: bool
    created_at: datetime
    updated_at: datetime


class BlockIpRequest(BaseModel):
    """Petición para bloquear una IP manualmente."""
    ip: str = Field(..., min_length=2, max_length=45, examples=["192.168.56.20", "2001:db8::20"])
    reason: str | None = Field(None, max_length=500)
    device_id: UUID | None = None


class FirewallStatusResponse(BaseModel):
    """Estado del servicio de cortafuegos."""
    running: bool
    iptables_available: bool
    ipv6_enabled: bool
    rules_applied: int
    last_action_at: str | None
