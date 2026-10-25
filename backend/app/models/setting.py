from datetime import datetime
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class SystemSetting(Base):
    """Ajustes que se cambian desde el panel (tabla clave-valor de init.sql)."""
    __tablename__ = "settings"

    key:         Mapped[str]         = mapped_column(String(100), primary_key=True)
    value:       Mapped[object]      = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None]  = mapped_column(Text)
    updated_at:  Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=utcnow)
