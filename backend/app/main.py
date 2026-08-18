from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.api.routes import devices, network, alerts, firewall, system, security
from app.services.monitor.monitor_service import monitor_service
from app.services.security.security_service import security_service
from app.services.firewall.firewall_service import firewall_service
from app.services.monitor.traffic_meter import traffic_meter



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ciclo de vida de la aplicación.
    setup_logging()
    await init_db()
    await firewall_service.start()
    await traffic_meter.start(interval_seconds=5)
    await monitor_service.start()
    await security_service.start()
    yield
    await security_service.stop()
    await monitor_service.stop()
    await traffic_meter.stop()
    await firewall_service.stop()


# Inicialización de la API
app = FastAPI(
    title="LanSentinel API",
    description="Sistema de monitorización y seguridad para redes domésticas",
    version="1.0.0",
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
app.include_router(devices.router,  prefix="/api/v1/devices",  tags=["devices"])
app.include_router(network.router,  prefix="/api/v1/network",  tags=["network"])
app.include_router(alerts.router,   prefix="/api/v1/alerts",   tags=["alerts"])
app.include_router(firewall.router, prefix="/api/v1/firewall", tags=["firewall"])
app.include_router(security.router, prefix="/api/v1/security", tags=["security"])
app.include_router(system.router,   prefix="/api/v1/system",   tags=["system"])

# Estado de la API
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
