from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class AiAuditRun(Base):
    """
    Una auditoría con IA: lo que se envió (snapshot), con qué proveedor y
    modelo, cuánto costó y el informe validado (o el error). La equivalencia
    de seudónimos (mapping) solo sirve para el panel: nunca se envía.
    """
    __tablename__ = "ai_audits"

    id:            Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at:    Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status:        Mapped[str]             = mapped_column(String(16), nullable=False)   # running | done | error
    requested_by:  Mapped[str | None]      = mapped_column(String(64))
    provider:      Mapped[str]             = mapped_column(String(32), nullable=False)
    model:         Mapped[str]             = mapped_column(String(100), nullable=False)
    local:         Mapped[bool]            = mapped_column(Boolean, default=False)
    input_tokens:  Mapped[int | None]      = mapped_column(Integer)
    output_tokens: Mapped[int | None]      = mapped_column(Integer)
    cost_usd:      Mapped[float | None]    = mapped_column(Float)
    snapshot:      Mapped[dict | None]     = mapped_column(JSONB)
    mapping:       Mapped[list | None]     = mapped_column(JSONB)
    report:        Mapped[dict | None]     = mapped_column(JSONB)
    discarded:     Mapped[list | None]     = mapped_column(JSONB)
    error:         Mapped[str | None]      = mapped_column(Text)
