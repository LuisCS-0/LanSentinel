import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
import enum


class FwAction(str, enum.Enum):
    accept = "accept"
    drop   = "drop"
    reject = "reject"
    log    = "log"


class FwDirection(str, enum.Enum):
    inbound  = "inbound"
    outbound = "outbound"
    forward  = "forward"


class FwProtocol(str, enum.Enum):
    tcp  = "tcp"
    udp  = "udp"
    icmp = "icmp"
    any  = "any"


class FirewallRule(Base):
    __tablename__ = "firewall_rules"

    id:             Mapped[int]             = mapped_column(primary_key=True, autoincrement=True)
    name:           Mapped[str]             = mapped_column(String(255), nullable=False)
    description:    Mapped[str|None]        = mapped_column(Text)
    is_active:      Mapped[bool]            = mapped_column(Boolean, default=True)
    priority:       Mapped[int]             = mapped_column(Integer, default=100)
    direction:      Mapped[FwDirection]     = mapped_column(SAEnum(FwDirection, name="fw_direction", create_type=False), default=FwDirection.inbound)
    action:         Mapped[FwAction]        = mapped_column(SAEnum(FwAction, name="fw_action", create_type=False),    default=FwAction.drop)
    protocol:       Mapped[FwProtocol]      = mapped_column(SAEnum(FwProtocol, name="fw_protocol", create_type=False),  default=FwProtocol.any)
    src_ip:         Mapped[str|None]        = mapped_column(String(50))
    dst_ip:         Mapped[str|None]        = mapped_column(String(50))
    src_port:       Mapped[str|None]        = mapped_column(String(50))
    dst_port:       Mapped[str|None]        = mapped_column(String(50))
    device_id:      Mapped[uuid.UUID|None]  = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    auto_generated: Mapped[bool]            = mapped_column(Boolean, default=False)
    created_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="firewall_rules")  # noqa
