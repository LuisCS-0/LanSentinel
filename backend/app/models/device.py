import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base, utcnow


class Device(Base):
    __tablename__ = "devices"

    id:          Mapped[uuid.UUID]  = mapped_column(primary_key=True, default=uuid.uuid4)
    mac:         Mapped[str]        = mapped_column(String(17), unique=True, nullable=False)
    ip:          Mapped[str | None] = mapped_column(String(45))
    hostname:    Mapped[str | None] = mapped_column(String(255))
    vendor:      Mapped[str | None] = mapped_column(String(255))
    device_type: Mapped[str | None] = mapped_column(String(100))
    is_trusted:  Mapped[bool]       = mapped_column(Boolean, default=False)
    is_blocked:  Mapped[bool]       = mapped_column(Boolean, default=False)
    notes:       Mapped[str | None] = mapped_column(Text)
    first_seen:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen:   Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:  Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relaciones
    alerts:            Mapped[list["Alert"]]          = relationship(back_populates="device")           # noqa
    port_scans:        Mapped[list["PortScan"]]       = relationship(back_populates="device")           # noqa
    firewall_rules:    Mapped[list["FirewallRule"]]   = relationship(back_populates="device")           # noqa
    active_connections: Mapped[list["ActiveConnection"]] = relationship(back_populates="device")        # noqa
