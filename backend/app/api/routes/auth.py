"""
Router de autenticación: login, logout, usuario actual y cambio de contraseña.

El login del panel devuelve el token en una cookie httpOnly (el JavaScript de
la página no puede leerla, así que un XSS no puede robar la sesión) con
SameSite=Strict (otra web no puede hacer peticiones con ella). /token emite el
mismo token en el cuerpo para Swagger y scripts.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.api.deps import SESSION_COOKIE, get_current_user, get_optional_user
from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.alert import AlertSeverity, AlertSource
from app.models.user import User
from app.services.alerts.alert_service import create_alert
from app.services.auth import login_guard
from app.services.auth.user_service import authenticate, change_password, initial_password_pending

log = structlog.get_logger(__name__)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class SessionResponse(BaseModel):
    username: str
    expires_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    username: str
    role: str
    last_login_at: datetime | None
    must_change_password: bool = False   # sigue con la contraseña inicial


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=10, max_length=256)


# ── Lógica común de login ────────────────────────────────────────────────────

async def _login(request: Request, db: AsyncSession, username: str, password: str) -> User:
    """
    Comprueba las credenciales aplicando el límite de intentos. Al alcanzar el
    máximo de fallos se registra una alerta (agrupada por IP de origen).
    """
    ip = login_guard.client_ip(request)

    wait = login_guard.seconds_locked(ip, username)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Vuelve a intentarlo en {wait} s.",
            headers={"Retry-After": str(wait)},
        )

    user = await authenticate(db, username, password)
    if user:
        request.state.user = user           # para el registro de acciones
        login_guard.reset(ip, username)
        log.info("auth.login_ok", username=user.username, ip=ip)
        return user

    failures = login_guard.register_failure(ip, username)
    log.warning("auth.login_failed", username=username, ip=ip, failures=failures)
    if failures == settings.LOGIN_MAX_ATTEMPTS:
        await create_alert(
            db,
            severity=AlertSeverity.medium,
            source=AlertSource.system,
            title="Intentos fallidos de acceso al panel",
            description=(
                f"{failures} intentos de inicio de sesión fallidos desde {ip} "
                f"(usuario \"{username}\"). El acceso desde esa IP queda bloqueado "
                f"{settings.LOGIN_LOCKOUT_SECONDS} s."
            ),
            raw_payload={"ip": ip, "username": username, "failures": failures},
            fingerprint=f"login_failed:{ip}",
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Usuario o contraseña incorrectos",
    )


def _is_https(request: Request) -> bool:
    """El panel llega por nginx, que termina el HTTPS y lo indica en X-Forwarded-Proto."""
    return settings.SESSION_COOKIE_SECURE or request.headers.get("x-forwarded-proto") == "https"


def _set_session_cookie(request: Request, response: Response, user: User) -> datetime:
    token, expires_at = create_access_token(user.username, user.password_changed_at)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="strict",
        secure=_is_https(request),
        path="/",
    )
    return expires_at


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=SessionResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Inicia sesión en el panel; el token viaja en una cookie httpOnly."""
    user = await _login(request, db, payload.username, payload.password)
    expires_at = _set_session_cookie(request, response, user)
    return SessionResponse(username=user.username, expires_at=expires_at)


@router.post("/token", response_model=TokenResponse)
async def token(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login OAuth2 (formulario) para Swagger y scripts; devuelve el token en el cuerpo."""
    user = await _login(request, db, form.username, form.password)
    access_token, _ = create_access_token(user.username, user.password_changed_at)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=204)
async def logout(response: Response, _user: User | None = Depends(get_optional_user)):
    # El usuario solo se busca para que el cierre quede en el registro
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse(
        username=user.username, role=user.role, last_login_at=user.last_login_at,
        must_change_password=initial_password_pending(user),
    )


@router.post("/password", response_model=SessionResponse)
async def update_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cambia la contraseña del usuario actual. Cierra las demás sesiones y
    renueva la cookie de esta para que siga abierta.
    """
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe ser distinta de la actual")

    await change_password(db, user, payload.new_password)
    expires_at = _set_session_cookie(request, response, user)
    return SessionResponse(username=user.username, expires_at=expires_at)
