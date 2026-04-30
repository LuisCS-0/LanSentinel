import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class NetworkUsage(Base):
    __tablename__ = "network_usage"

    id:           Mapped[int]           = mapped_column(primary_key=True, autoincrement=True)
    device_id:    Mapped[uuid.UUID]     = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    bytes_sent:   Mapped[int]           = mapped_column(BigInteger, default=0)
    bytes_recv:   Mapped[int]           = mapped_column(BigInteger, default=0)
    packets_sent: Mapped[int]           = mapped_column(BigInteger, default=0)
    packets_recv: Mapped[int]           = mapped_column(BigInteger, default=0)
    recorded_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="network_usage")  # noqa


class PortScan(Base):
    __tablename__ = "port_scans"

    id:         Mapped[int]         = mapped_column(primary_key=True, autoincrement=True)
    device_id:  Mapped[uuid.UUID]   = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    port:       Mapped[int]         = mapped_column(Integer, nullable=False)
    protocol:   Mapped[str]         = mapped_column(String(10), default="tcp")
    state:      Mapped[str]         = mapped_column(String(20), nullable=False)
    service:    Mapped[str|None]    = mapped_column(String(100))
    version:    Mapped[str|None]    = mapped_column(String(255))
    scanned_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="port_scans")  # noqa


class ActiveConnection(Base):
    __tablename__ = "active_connections"

    id:        Mapped[int]              = mapped_column(primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID|None]   = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    src_ip:    Mapped[str]              = mapped_column(String(45), nullable=False)
    src_port:  Mapped[int|None]         = mapped_column(Integer)
    dst_ip:    Mapped[str]              = mapped_column(String(45), nullable=False)
    dst_port:  Mapped[int|None]         = mapped_column(Integer)
    protocol:  Mapped[str|None]         = mapped_column(String(10))
    state:     Mapped[str|None]         = mapped_column(String(30))
    pid:       Mapped[int|None]         = mapped_column(Integer)
    process:   Mapped[str|None]         = mapped_column(String(255))
    seen_at:   Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    device: Mapped["Device"] = relationship(back_populates="active_connections")  # noqa
