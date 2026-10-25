"""
Dependencias comunes de la API.

get_current_user protege los endpoints: acepta el token de sesión desde la
cookie httpOnly que pone el login del panel o desde la cabecera
"Authorization: Bearer <token>" (Swagger, scripts). Si no hay token válido
responde 401.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, password_stamp
from app.db.session import get_db
from app.models.user import User
from app.services.auth.user_service import get_by_username

SESSION_COOKIE = "lansentinel_session"

# auto_error=False: si no hay cabecera se mira la cookie antes de rechazar.
# tokenUrl habilita el botón "Authorize" de Swagger (/docs).
_bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sesión no válida o caducada",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    bearer_token: str | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = bearer_token or request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _UNAUTHORIZED

    payload = decode_access_token(token)
    if not payload:
        raise _UNAUTHORIZED

    user = await get_by_username(db, payload["sub"])
    if not user or not user.is_active:
        raise _UNAUTHORIZED
    # Token emitido antes del último cambio de contraseña
    if payload["pwd"] != password_stamp(user.password_changed_at):
        raise _UNAUTHORIZED
    return user
