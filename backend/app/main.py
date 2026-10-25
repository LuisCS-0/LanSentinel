from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.api.deps import get_current_user
from app.api.routes import auth, devices, network, alerts, firewall, system, security
from app.services.monitor.monitor_service import monitor_service
from app.services.security.security_service import security_service
from app.services.firewall.firewall_service import firewall_service
from app.services.monitor.traffic_meter import traffic_meter
from app.services.monitor.traffic_history import traffic_history
from app.services.auth.user_service import ensure_admin_user
from app.services.monitor import oui_resolver



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ciclo de vida de la aplicación.
    setup_logging()
    await init_db()
    await ensure_admin_user()
    oui_resolver.start_background_update()
    await firewall_service.start()
    await traffic_meter.start(interval_seconds=5)
    await traffic_history.start()
    await monitor_service.start()
    await security_service.start()
    yield
    await security_service.stop()
    await monitor_service.stop()
    await traffic_history.stop()    # guarda el último tramo antes de parar el medidor
    await traffic_meter.stop()
    await firewall_service.stop()


# Inicialización de la API
app = FastAPI(
    title="LanSentinel API",
    description="Sistema de monitorización y seguridad para redes domésticas",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configuración de CORS para permitir solicitudes desde React
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Routers
# Todos los endpoints requieren sesión salvo los de autenticación y /health
_auth_required = [Depends(get_current_user)]

app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["auth"])
app.include_router(devices.router,  prefix="/api/v1/devices",  tags=["devices"],  dependencies=_auth_required)
app.include_router(network.router,  prefix="/api/v1/network",  tags=["network"],  dependencies=_auth_required)
app.include_router(alerts.router,   prefix="/api/v1/alerts",   tags=["alerts"],   dependencies=_auth_required)
app.include_router(firewall.router, prefix="/api/v1/firewall", tags=["firewall"], dependencies=_auth_required)
app.include_router(security.router, prefix="/api/v1/security", tags=["security"], dependencies=_auth_required)
app.include_router(system.router,   prefix="/api/v1/system",   tags=["system"],   dependencies=_auth_required)

# Estado de la API (público: lo usan el healthcheck de Docker y el frontend)
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "1.2.0"}
