import uuid
from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
import enum


class AlertSeverity(str, enum.Enum):
    info     = "info"
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"


class AlertSource(str, enum.Enum):
    suricata = "suricata"
    monitor  = "monitor"
    firewall = "firewall"
    system   = "system"


class AlertStatus(str, enum.Enum):
    new          = "new"
    acknowledged = "acknowledged"
    resolved     = "resolved"
    ignored      = "ignored"


class Alert(Base):
    __tablename__ = "alerts"

    id:              Mapped[int]            = mapped_column(primary_key=True, autoincrement=True)
    device_id:       Mapped[uuid.UUID|None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    severity:        Mapped[AlertSeverity]  = mapped_column(SAEnum(AlertSeverity, name="alert_severity", create_type=False), default=AlertSeverity.info)
    source:          Mapped[AlertSource]    = mapped_column(SAEnum(AlertSource, name="alert_source", create_type=False),   default=AlertSource.system)
    status:          Mapped[AlertStatus]    = mapped_column(SAEnum(AlertStatus, name="alert_status", create_type=False),   default=AlertStatus.new)
    title:           Mapped[str]            = mapped_column(String(255), nullable=False)
    description:     Mapped[str|None]       = mapped_column(Text)
    raw_payload:     Mapped[dict|None]      = mapped_column(JSONB)
    acknowledged_by: Mapped[str|None]       = mapped_column(String(100))
    acknowledged_at: Mapped[datetime|None]  = mapped_column(DateTime(timezone=True))
    fingerprint:     Mapped[str|None]       = mapped_column(String(255))
    occurrences:     Mapped[int]            = mapped_column(Integer, default=1)
    created_at:      Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen_at:    Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:      Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="alerts")  # noqa
