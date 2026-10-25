"""
Routers stub — se irán rellenando por módulo.
Estructura de endpoints planificada para LanSentinel v1.
"""

# ─── devices.py ──────────────────────────────────────────────────────────────
# GET    /api/v1/devices/              → listar todos los dispositivos
# GET    /api/v1/devices/{id}          → detalle de un dispositivo
# PATCH  /api/v1/devices/{id}          → editar (notas, tipo, hostname…)
# POST   /api/v1/devices/{id}/trust    → marcar como confiable
# POST   /api/v1/devices/{id}/block    → bloquear dispositivo
# POST   /api/v1/devices/{id}/scan     → lanzar escaneo de puertos
# GET    /api/v1/devices/{id}/ports    → puertos abiertos del dispositivo
# GET    /api/v1/devices/{id}/usage    → histórico de uso de red
# GET    /api/v1/devices/{id}/connections → conexiones activas

# ─── network.py ──────────────────────────────────────────────────────────────
# GET    /api/v1/network/stats         → estadísticas globales (bytes, paquetes)
# GET    /api/v1/network/connections   → conexiones abiertas de todos los dispositivos (conntrack)
# POST   /api/v1/network/scan          → forzar nuevo escaneo ARP/nmap
# GET    /api/v1/network/topology      → grafo de red (para visualización)

# ─── alerts.py ───────────────────────────────────────────────────────────────
# GET    /api/v1/alerts/               → listar alertas (filtros: status, severity)
# GET    /api/v1/alerts/{id}           → detalle de alerta
# PATCH  /api/v1/alerts/{id}/ack       → marcar como gestionada
# PATCH  /api/v1/alerts/{id}/ignore    → ignorar
# DELETE /api/v1/alerts/{id}           → eliminar
# GET    /api/v1/alerts/summary        → resumen por severidad

# ─── firewall.py ─────────────────────────────────────────────────────────────
# GET    /api/v1/firewall/rules        → listar reglas
# POST   /api/v1/firewall/rules        → crear regla
# PATCH  /api/v1/firewall/rules/{id}   → editar regla
# DELETE /api/v1/firewall/rules/{id}   → eliminar regla
# POST   /api/v1/firewall/rules/{id}/toggle → activar/desactivar
# GET    /api/v1/firewall/status       → estado del firewall (iptables)

# ─── system.py ───────────────────────────────────────────────────────────────
# GET    /api/v1/system/settings       → configuración actual
# PATCH  /api/v1/system/settings       → actualizar configuración
# GET    /api/v1/system/status         → estado de servicios (Suricata, monitor…)
# GET    /api/v1/system/info           → info del host (CPU, RAM, uptime)
