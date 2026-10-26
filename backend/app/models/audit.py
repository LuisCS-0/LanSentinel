from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class AuditEntry(Base):
    """
    Una acción hecha desde el panel o la API (services/auth/audit.py). Guarda
    el nombre del usuario, no su id, para que siga ahí si se borra el usuario.
    """
    __tablename__ = "audit_log"

    id:          Mapped[int]             = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at:  Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=utcnow)
    username:    Mapped[str | None]      = mapped_column(String(64))
    ip:          Mapped[str | None]      = mapped_column(String(45))
    method:      Mapped[str]             = mapped_column(String(8), nullable=False)
    path:        Mapped[str]             = mapped_column(String(255), nullable=False)
    action:      Mapped[str]             = mapped_column(String(128), nullable=False)
    target:      Mapped[str | None]      = mapped_column(String(255))
    status_code: Mapped[int]             = mapped_column(Integer, nullable=False)
    details:     Mapped[dict | None]     = mapped_column(JSONB)
