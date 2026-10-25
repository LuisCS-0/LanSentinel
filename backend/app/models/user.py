from datetime import datetime
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id:                  Mapped[int]             = mapped_column(primary_key=True, autoincrement=True)
    username:            Mapped[str]             = mapped_column(String(64), unique=True, nullable=False)
    password_hash:       Mapped[str]             = mapped_column(String(255), nullable=False)
    is_active:           Mapped[bool]            = mapped_column(Boolean, default=True)
    # Los tokens emitidos antes de esta fecha dejan de valer (cambio de contraseña)
    password_changed_at: Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at:       Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:          Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at:          Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=utcnow)
