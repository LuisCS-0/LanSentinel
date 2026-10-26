"""
Usuarios del panel (solo administradores): alta con rol, cambio de rol,
activar o desactivar, poner contraseña y borrar.

Un usuario desactivado o borrado pierde sus sesiones al momento (se
comprueba en cada petición); poner contraseña también las cierra.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.auth import user_service
from app.services.auth.user_service import UserError

router = APIRouter()

Role = Literal["admin", "viewer"]


class UserResponse(BaseModel):
    id: int
    username: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=10, max_length=256)
    role: Role = "viewer"


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class UserPassword(BaseModel):
    new_password: str = Field(..., min_length=10, max_length=256)


async def _get(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.get("", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    return await user_service.list_users(db)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await user_service.create_user(db, payload.username, payload.password, payload.role)
    except UserError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Cambia el rol o activa/desactiva. No se puede dejar el sistema sin administrador."""
    user = await _get(db, user_id)
    try:
        return await user_service.update_user(db, user, role=payload.role, is_active=payload.is_active)
    except UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{user_id}/password", status_code=204)
async def set_password(
    user_id: int,
    payload: UserPassword,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Pone una contraseña nueva a otro usuario y cierra sus sesiones."""
    user = await _get(db, user_id)
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="Tu propia contraseña se cambia en Cuenta, con la actual")
    await user_service.change_password(db, user, payload.new_password)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    user = await _get(db, user_id)
    request.state.audit_target = user.username      # después ya no se podrá buscar
    if user.id == current.id:
        raise HTTPException(status_code=400, detail="No puedes borrar tu propio usuario")
    try:
        await user_service.delete_user(db, user)
    except UserError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
