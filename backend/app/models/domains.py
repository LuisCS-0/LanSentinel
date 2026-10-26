import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class DeviceDomain(Base):
    """
    Dominio que ha usado un dispositivo: consultado por DNS o como servidor de
    una conexión cifrada (SNI de TLS). Una fila por dispositivo y dominio, con
    contadores; se borra a los DOMAIN_HISTORY_DAYS días sin verse.
    """
    __tablename__ = "device_domains"

    device_id:  Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    domain:     Mapped[str]       = mapped_column(String(255), primary_key=True)
    hits:       Mapped[int]       = mapped_column(BigInteger, default=0)
    via_dns:    Mapped[bool]      = mapped_column(Boolean, default=False)
    via_tls:    Mapped[bool]      = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceTlsFingerprint(Base):
    """
    Huella de un cliente TLS de un dispositivo (JA4, o JA3 si no la hay): cada
    programa que abre conexiones cifradas deja la suya. Un programa nuevo en
    un dispositivo que siempre usa los mismos es una pista.
    """
    __tablename__ = "device_tls_fingerprints"

    device_id:   Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    fingerprint: Mapped[str]       = mapped_column(String(128), primary_key=True)
    ja3:         Mapped[str | None] = mapped_column(String(32))
    last_sni:    Mapped[str | None] = mapped_column(String(255))
    hits:        Mapped[int]       = mapped_column(BigInteger, default=0)
    first_seen:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen:   Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=utcnow)
