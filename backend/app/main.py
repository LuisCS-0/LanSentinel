"""
LanSentinel — punto de entrada de la aplicación FastAPI.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.api.routes import devices, network, alerts, firewall, system
from app.services.monitor.monitor_service import monitor_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Tareas de arranque y apagado de la aplicación."""
    setup_logging()
    await init_db()
    await monitor_service.start()
    yield
    await monitor_service.stop()


app = FastAPI(
    title="LanSentinel API",
    description="Sistema de monitorización y seguridad para redes domésticas",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(devices.router,  prefix="/api/v1/devices",  tags=["devices"])
app.include_router(network.router,  prefix="/api/v1/network",  tags=["network"])
app.include_router(alerts.router,   prefix="/api/v1/alerts",   tags=["alerts"])
app.include_router(firewall.router, prefix="/api/v1/firewall", tags=["firewall"])
app.include_router(system.router,   prefix="/api/v1/system",   tags=["system"])


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": "0.1.0"}
