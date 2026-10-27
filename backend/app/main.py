from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import VERSION, settings
from app.core.logging import setup_logging
from app.db.session import init_db
from app.api.deps import get_current_user_short_session, require_admin, require_write
from app.api.routes import auth, devices, network, alerts, firewall, system, security, events, users, audit, ai_audit
from app.services.monitor.monitor_service import monitor_service
from app.services.security.security_service import security_service
from app.services.firewall.firewall_service import firewall_service
from app.services.monitor.traffic_meter import traffic_meter
from app.services.monitor.traffic_history import traffic_history
from app.services.auth.user_service import ensure_admin_user
from app.services.monitor import oui_resolver
from app.services.notifications.notifier import notifier
from app.services.security.arp_watch import arp_watch
from app.services.security.scan_scheduler import scan_scheduler
from app.services.tls_cert import tls_service
from app.services.backup.backup_service import backup_service
from app.services.security.threat_lists import threat_lists
from app.services.monitor.anomalies import anomaly_service
from app.services.security.domain_tracker import domain_tracker
from app.services.auth.audit import AuditMiddleware
from app.services.monitor.neighbors import neighbors
from app.services.ai_audit.service import ai_audit_service



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ciclo de vida de la aplicación.
    setup_logging()
    # Lo primero: nginx espera el certificado para servir el panel por HTTPS
    await tls_service.start()
    await init_db()
    await ensure_admin_user()
    oui_resolver.start_background_update()
    # Antes que los servicios que generan alertas, para no perder ninguna
    notifier.start()
    await firewall_service.start()
    # Tras el cortafuegos: su cadena se enlaza al principio de FORWARD e INPUT
    await threat_lists.start()
    neighbors.start()
    await traffic_meter.start(interval_seconds=5)
    await traffic_history.start()
    await arp_watch.start()
    await monitor_service.start()
    await security_service.start()
    scan_scheduler.start()
    backup_service.start()
    anomaly_service.start()
    domain_tracker.start()
    await ai_audit_service.start()
    yield
    await domain_tracker.stop()
    await anomaly_service.stop()
    await backup_service.stop()
    await scan_scheduler.stop()
    await security_service.stop()
    await monitor_service.stop()
    await arp_watch.stop()
    await traffic_history.stop()    # guarda el último tramo antes de parar el medidor
    await traffic_meter.stop()
    await neighbors.stop()
    await threat_lists.stop()
    await firewall_service.stop()
    await notifier.stop()
    await tls_service.stop()


# Inicialización de la API
app = FastAPI(
    title="LanSentinel API",
    description="Sistema de monitorización y seguridad para redes domésticas",
    version=VERSION,
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

# Registro de acciones: cada cambio, con usuario, IP y resultado
app.add_middleware(AuditMiddleware)


# Routers
# Todos los endpoints requieren sesión salvo los de autenticación y /health.
# Los de solo lectura pueden consultar, no cambiar nada (deps.require_write)
_auth_required = [Depends(require_write)]
_admin_only = [Depends(require_admin)]

app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["auth"])
app.include_router(devices.router,  prefix="/api/v1/devices",  tags=["devices"],  dependencies=_auth_required)
app.include_router(network.router,  prefix="/api/v1/network",  tags=["network"],  dependencies=_auth_required)
app.include_router(alerts.router,   prefix="/api/v1/alerts",   tags=["alerts"],   dependencies=_auth_required)
app.include_router(firewall.router, prefix="/api/v1/firewall", tags=["firewall"], dependencies=_auth_required)
app.include_router(security.router, prefix="/api/v1/security", tags=["security"], dependencies=_auth_required)
app.include_router(system.router,   prefix="/api/v1/system",   tags=["system"],   dependencies=_auth_required)
app.include_router(users.router,    prefix="/api/v1/users",    tags=["users"],    dependencies=_admin_only)
app.include_router(audit.router,    prefix="/api/v1/audit",    tags=["audit"],    dependencies=_admin_only)
app.include_router(ai_audit.router, prefix="/api/v1/ai-audit", tags=["ai-audit"], dependencies=_admin_only)
# El canal SSE dura minutos: no debe retener una conexión de BD todo ese tiempo
app.include_router(events.router,   prefix="/api/v1/events",   tags=["events"],
                   dependencies=[Depends(get_current_user_short_session)])

# Estado de la API (público: lo usan el healthcheck de Docker y el frontend)
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": VERSION}
