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
│   │   ├── db/               # Sesión SQLAlchemy y migraciones ligeras
│   │   ├── models/           # Modelos ORM
│   │   ├── schemas/          # Schemas Pydantic (request/response)
│   │   └── services/         # Lógica de negocio
│   │       ├── monitor/      # Descubrimiento ARP, fabricantes, tráfico
│   │       ├── security/     # Suricata, clasificador, escaneo de puertos
│   │       ├── firewall/     # iptables/ip6tables, bloqueo automático
│   │       └── alerts/       # Creación y agrupación de alertas
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/       # Componentes reutilizables
│       ├── pages/            # Dashboard, Devices, Alerts, Firewall
│       ├── hooks/            # Hooks de React Query (consultas y mutaciones)
│       └── lib/              # Cliente HTTP, tipos y utilidades
├── docker/
│   ├── db/init.sql           # Esquema inicial de PostgreSQL
│   └── suricata/             # Configuración y reglas de Suricata
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

En producción, con Suricata:

```bash
docker compose --profile production up -d
```

El frontend llega al backend a través de `BACKEND_URL` (por defecto
`http://host.docker.internal:8000`). Si tu instalación no resuelve ese nombre,
define en `.env` la IP del equipo, p. ej. `BACKEND_URL=http://192.168.56.10:8000`.

## Acceso al panel

La API y el panel requieren usuario y contraseña (salvo `/health`).

- **Primer arranque:** si no hay usuarios se crea el administrador
  `ADMIN_USERNAME` (por defecto `admin`). Si definiste `ADMIN_PASSWORD` en
  `.env` se usa esa; si no, se genera una aleatoria:

  ```bash
  sudo cat /var/lib/lansentinel/initial_admin_password
  ```

  Cámbiala desde el panel (barra lateral → *Cambiar contraseña*); al hacerlo
  el fichero se borra y se cierran las demás sesiones.
- **Sesión:** cookie `httpOnly` y `SameSite=Strict` de 12 horas
  (`ACCESS_TOKEN_EXPIRE_MINUTES`). Si sirves el panel por HTTPS, activa
  `SESSION_COOKIE_SECURE=true`.
- **Swagger (`/docs`):** botón *Authorize* con el mismo usuario y contraseña.
- **Fuerza bruta:** 5 intentos fallidos desde una IP bloquean el login de ese
  usuario desde esa IP durante 5 minutos y generan una alerta.
- **Clave de firma:** si `SECRET_KEY` está vacía se genera una y se guarda en
  `/var/lib/lansentinel/secret_key`.

## Histórico de tráfico

Cuando LanSentinel actúa como gateway, el consumo de cada dispositivo se
guarda en dos niveles:

| Tabla | Contenido | Retención |
|-------|-----------|-----------|
| `network_usage` | Bytes y paquetes de subida y bajada por dispositivo, cada minuto | `TRAFFIC_RAW_RETENTION_DAYS` (7 días) |
| `network_usage_hourly` | Lo mismo agregado por horas (se recalcula cada 5 minutos) | `TRAFFIC_HOURLY_RETENTION_DAYS` (365 días) |

La sección **Tráfico** del panel muestra el consumo de la red por horas, días
o meses y el ranking de dispositivos; el detalle de cada dispositivo muestra
su propio histórico. Los días se agrupan en la zona horaria `TIMEZONE`
(por defecto `Europe/Madrid`).

## Esquema de la base de datos

`docker/db/init.sql` crea el esquema solo cuando el volumen de PostgreSQL está
vacío. Los cambios posteriores se aplican al arrancar el backend mediante
sentencias idempotentes en `backend/app/db/migrations.py`, de modo que una
instalación existente se actualiza sin borrar datos.

## Cortafuegos

LanSentinel usa cadenas propias en iptables e ip6tables:

| Cadena | Enlazada desde | Contenido |
|--------|----------------|-----------|
| `LANSENTINEL` | `INPUT` | Bloqueos del tráfico hacia el propio gateway |
| `LANSENTINEL_FWD` | `FORWARD` | Bloqueos del tráfico reenviado a Internet |
| `LANSENTINEL_ACCT` | `FORWARD` | Reglas de conteo de tráfico por dispositivo |

- Los dispositivos de la LAN se bloquean por **MAC e IP**: cambiar de IP no
  esquiva el bloqueo, y si el dispositivo cambia de IP la regla se actualiza.
- Las IPs externas se bloquean solo por IP.
- Nunca se bloquean las IPs del propio equipo, su puerta de enlace ni las de
  `FIREWALL_NEVER_BLOCK`. El bloqueo automático omite además los dispositivos
  de confianza.

## Fases de desarrollo

- [x] **Fase 0** — Arquitectura base, Docker, esquema de BD
- [x] **Fase 1** — Módulo de monitorización (ARP scan, psutil, estadísticas)
- [x] **Fase 2** — Frontend: dashboard y listado de dispositivos
- [x] **Fase 3** — Seguridad: integración Suricata, escaneo de puertos
- [x] **Fase 4** — Firewall: gestión de reglas iptables
- [x] **Fase 5** — Sistema de alertas
- [x] **Fase 6** — Pruebas en laboratorio VirtualBox
- [x] **v1.1** — Correcciones: cadenas propias, bloqueo por MAC, IPv6,
  agrupación de alertas, IPs protegidas
- [x] **v1.2** — Seguridad del propio sistema: autenticación, base de datos
  solo en loopback, sin socket de Docker, fabricantes con la lista OUI local
- [x] **v1.3** — Histórico de tráfico por dispositivo y ranking de consumo
