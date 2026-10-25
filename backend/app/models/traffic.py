import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class NetworkUsage(Base):
    """
    Tráfico de un dispositivo en un intervalo corto (por defecto, un minuto).
    Es el dato en bruto: se conserva TRAFFIC_RAW_RETENTION_DAYS días.
    sent = subida (desde el dispositivo), recv = descarga (hacia él).
    """
    __tablename__ = "network_usage"

    id:           Mapped[int]       = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id:    Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    bytes_sent:   Mapped[int]       = mapped_column(BigInteger, default=0)
    bytes_recv:   Mapped[int]       = mapped_column(BigInteger, default=0)
    packets_sent: Mapped[int]       = mapped_column(BigInteger, default=0)
    packets_recv: Mapped[int]       = mapped_column(BigInteger, default=0)
    recorded_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)


class NetworkUsageHourly(Base):
    """
    Tráfico de un dispositivo agregado por horas, calculado a partir de
    network_usage. Es lo que consultan las gráficas de días y semanas; se
    conserva TRAFFIC_HOURLY_RETENTION_DAYS días.
    """
    __tablename__ = "network_usage_hourly"

    device_id:    Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    hour:         Mapped[datetime]  = mapped_column(DateTime(timezone=True), primary_key=True)
    bytes_sent:   Mapped[int]       = mapped_column(BigInteger, default=0)
    bytes_recv:   Mapped[int]       = mapped_column(BigInteger, default=0)
    packets_sent: Mapped[int]       = mapped_column(BigInteger, default=0)
    packets_recv: Mapped[int]       = mapped_column(BigInteger, default=0)
