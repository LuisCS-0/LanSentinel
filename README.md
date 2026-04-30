# LanSentinel
LanSentinel es un programa de monitorización y securización de red para redes domésticas o pequeñas.

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.12 + FastAPI |
| Base de datos | PostgreSQL 16 |
| IDS | Suricata |
| Firewall | iptables (nativo Linux) |
| Frontend | React + TypeScript + Vite |
| Contenedores | Docker + Docker Compose |
| Pruebas | VirtualBox (laboratorio de red) |

## Estructura del proyecto

```
lansentinel/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # Endpoints FastAPI
│   │   ├── core/             # Config, logging
│   │   ├── db/               # Sesión SQLAlchemy
│   │   ├── models/           # Modelos ORM
│   │   ├── schemas/          # Schemas Pydantic (request/response)
│   │   └── services/         # Lógica de negocio
│   │       ├── monitor/      # Módulo de monitorización
│   │       ├── security/     # Módulo de seguridad + Suricata
│   │       ├── firewall/     # Módulo de firewall (iptables)
│   │       └── alerts/       # Sistema de alertas
│   ├── migrations/           # Alembic
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/       # Componentes reutilizables
│       ├── pages/            # Dashboard, Devices, Alerts, Firewall
│       ├── hooks/            # Custom hooks (useDevices, useAlerts…)
│       ├── store/            # Estado global
│       ├── api/              # Cliente HTTP al backend
│       └── types/            # Tipos TypeScript
├── docker/
│   ├── db/init.sql           # Esquema inicial de PostgreSQL
│   └── suricata/             # Configuración de Suricata
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example
```

## Inicio rápido (desarrollo)

```bash
# 1. Clonar y configurar entorno
cp .env.example .env

# 2. Levantar servicios (BD + backend + frontend con hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# 3. API disponible en:  http://localhost:8000/docs
#    Frontend en:        http://localhost:3000
```

## Fases de desarrollo

- [x] **Fase 0** — Arquitectura base, Docker, esquema de BD
- [ ] **Fase 1** — Módulo de monitorización (ARP scan, psutil, estadísticas)
- [ ] **Fase 2** — Frontend: dashboard y listado de dispositivos
- [ ] **Fase 3** — Seguridad: integración Suricata, escaneo de puertos
- [ ] **Fase 4** — Firewall: gestión de reglas iptables
- [ ] **Fase 5** — Sistema de alertas
- [ ] **Fase 6** — Pruebas en laboratorio VirtualBox
