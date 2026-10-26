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
│       ├── pages/            # Panel, Dispositivos, Conexiones, Tráfico, Alertas, Cortafuegos, Ajustes
│       ├── hooks/            # Hooks de React Query (consultas y mutaciones)
│       └── lib/              # Cliente HTTP, tipos y utilidades
├── docker/
│   ├── db/init.sql           # Esquema inicial de PostgreSQL
│   └── suricata/             # Configuración y reglas de Suricata
├── docker-compose.yml
├── docker-compose.dev.yml
└── .env.example
```

## Instalación en una red real

LanSentinel funciona mejor como **router de la red**: así ve, mide y puede
cortar todo el tráfico. Necesita un equipo Linux (Debian o Ubuntu) con dos
interfaces de red:

```
Internet ── router de la operadora ── [WAN] LanSentinel [LAN] ── switch / Wi-Fi ── dispositivos
            (DHCP desactivado o en modo bridge)
```

1. Pon una **IP fija en la interfaz LAN** (por ejemplo `192.168.50.1/24`); el
   instalador lo comprueba y explica cómo hacerlo si falta.
2. Desde la carpeta del proyecto:

   ```bash
   sudo scripts/instalar.sh
   ```

   Instala Docker si hace falta, detecta y confirma las interfaces, avisa si
   ya hay otro servidor DHCP en la LAN, activa el reenvío
   (`/etc/sysctl.d/90-lansentinel.conf`) y la hora por NTP, prepara `.env` y
   arranca todo con el modo router encendido, incluidos el **DHCP y el DNS**
   de la red. Se puede volver a ejecutar sin perder datos.
3. Desactiva el DHCP del router de la operadora (o ponlo en modo bridge),
   conecta el punto de acceso Wi-Fi en modo AP y reconecta los dispositivos.

Opciones: `--wan`/`--lan` para elegir las interfaces, `--si` para no
preguntar, `--sin-dhcp` si DHCP y DNS los da otro equipo y `--sin-router`
para solo vigilar (con una sola interfaz; entonces no hay bloqueos ni
medición del tráfico que no pase por el equipo).

En modo router (`ROUTER_MODE=true`), LanSentinel enruta con NAT entre
`WAN_INTERFACE` y `MONITOR_INTERFACE` y **cierra la WAN**: desde Internet solo
entran las respuestas a conexiones salientes, de modo que el panel, la API y
el SSH no quedan expuestos. Además reparte las IPs y resuelve los nombres de
la red (dnsmasq, que el backend arranca y para; `ROUTER_DHCP=false` si lo
hace otro equipo): cada dispositivo responde como `nombre.lan`.

El modo router se **enciende y apaga desde Ajustes → Modo router**, con
confirmación: apagado, las cadenas quedan vacías y el DHCP/DNS se detiene, y
los dispositivos que usan LanSentinel como puerta de enlace se quedan sin
Internet. El estado elegido se guarda; si `ROUTER_MODE` cambia en `.env` (por
ejemplo al volver a ejecutar el instalador), manda en el siguiente arranque.

## HTTPS

El panel se sirve por **HTTPS en el puerto 443** (`https://<ip-del-equipo>`
o, con el DHCP de LanSentinel, `https://lansentinel.lan`), con HTTP/2. Por
HTTP (puertos 80 y 3000) solo se redirige, así que la contraseña y la cookie
de sesión nunca viajan en claro. Los puertos se cambian en `.env` con
`PANEL_HTTPS_PORT` y `PANEL_HTTP_PORT`.

En una red doméstica no hay un dominio público con el que pedir un
certificado, así que LanSentinel tiene **su propia autoridad (CA)**, que crea
el backend en `/var/lib/lansentinel/tls`, y firma con ella el certificado del
panel (IPs privadas del equipo y sus nombres). El certificado se renueva solo
al cambiar la IP o un mes antes de caducar; la CA dura 10 años.

- La primera vez el navegador avisa de que no conoce el certificado. Para
  quitar el aviso, descarga la CA en **Ajustes → Conexión segura** e
  impórtala en cada dispositivo (hay instrucciones para cada sistema).
  Comprueba antes que su huella coincide con la que muestra el instalador.
- La CA lleva **restricción de nombres**: solo puede firmar nombres de la red
  local (`.lan`, el nombre del equipo) e IPs privadas. Aunque alguien robara
  su clave, no le serviría para suplantar webs de Internet ante quien la haya
  importado.
- Para usar un certificado propio (p. ej. de Let's Encrypt con un dominio),
  sustituye `server.crt` (con la cadena) y `server.key` en esa carpeta: el
  backend no toca un certificado que no haya firmado él.
- Sin HSTS a propósito: con un certificado que el navegador aún no conoce,
  impediría aceptar el aviso y el panel quedaría inaccesible.
- La API no escucha en la red: solo en `127.0.0.1:8000`, detrás del mismo
  nginx (`https://<ip>/api/v1/...` y `https://<ip>/docs`). Para scripts, pide
  un token en `/api/v1/auth/token` y úsalo como `Authorization: Bearer`.

## Inicio rápido (desarrollo)

```bash
# 1. Clonar y configurar entorno
cp .env.example .env

# 2. Levantar servicios (BD + backend + frontend con hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# 3. API disponible en:  http://localhost:8000/docs
#    Frontend en:        http://localhost:3000 (en desarrollo, sin HTTPS)
```

En producción, con Suricata:

```bash
docker compose --profile production up -d
```

El backend solo escucha en `127.0.0.1:8000`: desde la red, la API y su
documentación (`https://<ip>/docs`) se alcanzan a través del nginx del
panel, siempre cifradas. El frontend comparte la red del equipo (como el
backend y Suricata) para llegar a ella.

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
  (`ACCESS_TOKEN_EXPIRE_MINUTES`). Al entrar por HTTPS se marca además
  `Secure` (solo viaja cifrada); `SESSION_COOKIE_SECURE=true` lo fuerza siempre,
  p. ej. detrás de otro proxy con TLS.
- **Swagger (`https://<ip>/docs`):** botón *Authorize* con el mismo usuario y
  contraseña.
- **Fuerza bruta:** 5 intentos fallidos desde una IP bloquean el login de ese
  usuario desde esa IP durante 5 minutos y generan una alerta.
- **Clave de firma:** si `SECRET_KEY` está vacía se genera una y se guarda en
  `/var/lib/lansentinel/secret_key`. También se ignora (con un aviso en los
  logs) si tiene menos de 32 caracteres o es uno de los valores de ejemplo de
  versiones anteriores, así que un `.env` heredado de la 1.0 no la usa.

## Detección

Además de Suricata, LanSentinel vigila por su cuenta:

- **ARP spoofing:** escucha los paquetes ARP de la interfaz LAN y revisa cada
  escaneo. Alerta crítica si otro equipo reclama la IP de LanSentinel o si
  cambia la MAC de la puerta de enlace (una MAC nueva de un dispositivo de
  confianza se acepta, p. ej. al cambiar de router); alerta alta si una IP
  alterna entre dos MAC. Solo alerta, no bloquea.
- **Servicios inseguros:** cada dispositivo se escanea al descubrirlo y luego
  cada `PORT_SCAN_INTERVAL_HOURS` (24 h). Se avisa de servicios con riesgo
  (Telnet, FTP, VNC, SMB, ADB, Redis, MongoDB…) y de puertos que se abren
  nuevos respecto al escaneo anterior; lo ya conocido no repite aviso.
- **Cambios de IP** de dispositivos conocidos y **dispositivos nuevos**.

## Modo cuarentena

Desde **Cortafuegos → Modo cuarentena**: solo los dispositivos de confianza
pueden salir a Internet; el resto (también los nuevos) queda retenido hasta
que lo marques como de confianza. Se aplica por MAC en la cadena
`LANSENTINEL_QUAR` de `FORWARD`, de modo que los equipos retenidos siguen
llegando a LanSentinel (DHCP, DNS, panel; el panel en Docker se alcanza por
DNAT y esas conexiones se dejan pasar). Requiere que LanSentinel sea la
puerta de enlace de la red. Marca tus dispositivos como de confianza antes
de activarlo.

## Conexiones

La página **Conexiones** muestra lo que tiene abierto cada dispositivo en
este momento, leído de la tabla conntrack del equipo (herramienta
`conntrack`, incluida en la imagen del backend). Cada conexión se clasifica:

| Estado | Significado |
|--------|-------------|
| Abierta | TCP establecida con tráfico reciente, o UDP sostenido (QUIC, VPN…) |
| Inactiva | TCP establecida sin tráfico desde hace 30 min: en reposo o un resto |
| Sin respuesta | El otro extremo no ha contestado |
| Consulta | Intercambio suelto ya terminado (DNS, NTP, ping); dura ~30 s |
| Cerrándose | TCP en proceso de cierre |

Se puede filtrar por estado, Internet/LAN, dispositivo, servicio o texto,
ver los destinos y servicios más frecuentes, a qué servidores DNS/NTP
pregunta la red y bloquear una IP de Internet. Solo aparece lo que
atraviesa LanSentinel (no el tráfico directo entre equipos de la LAN) y, por
ahora, solo IPv4.

## Panel

- Tema oscuro (por defecto), claro o el del sistema.
- **Buscador global** con `Ctrl+K` o `/`: salta a un dispositivo por nombre,
  IP o MAC, a una página o a acciones como escanear la red o bloquear una IP.
- El detalle de cada dispositivo se abre en un panel lateral desde cualquier
  pantalla (`?device=<id>` en la URL) con resumen, conexiones, consumo y
  puertos.

## Avisos

- **En el panel, al instante:** el frontend mantiene abierta una conexión de
  eventos (SSE, `/api/v1/events/stream`). Cada alerta nueva aparece como aviso
  flotante y refresca las listas; el indicador *En directo* de la barra
  lateral muestra el estado. Si se permite en **Ajustes**, las alertas altas y
  críticas también generan una notificación del navegador con la pestaña en
  segundo plano (los navegadores solo lo permiten con HTTPS, como el panel).
- **Fuera del panel:** Telegram, ntfy (push al móvil) y correo. Se configuran
  en `.env` (ver `.env.example`) y se prueban desde **Ajustes → Enviar
  prueba**. Solo se avisa de alertas nuevas con severidad
  `NOTIFY_MIN_SEVERITY` o superior (por defecto *high*); las repeticiones
  agrupadas no vuelven a avisar. Como máximo `NOTIFY_MAX_PER_HOUR` avisos por
  hora: el resto se resume en un aviso posterior.

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
| `LANSENTINEL_QUAR` | `FORWARD` | Modo cuarentena (vacía si está desactivado) |
| `LANSENTINEL_ACCT` | `FORWARD` | Reglas de conteo de tráfico por dispositivo |
| `LANSENTINEL_ROUTE` | `FORWARD` | Modo router: LAN → WAN y respuestas; nada publicado se abre desde la WAN |
| `LANSENTINEL_WAN_IN` | `INPUT` | Modo router: desde la WAN solo respuestas, ICMP y DHCP del equipo |
| `LANSENTINEL_NAT` | `POSTROUTING` (nat) | Modo router: NAT de lo que sale por la WAN |

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
- [x] **v1.4** — Alertas en tiempo real (SSE) y avisos por Telegram, ntfy y correo
- [x] **v1.5** — ARP spoofing, servicios inseguros con escaneo periódico y modo cuarentena
- [x] **v1.6** — Correcciones de las pruebas en laboratorio, conexiones por
  dispositivo y de toda la red (conntrack), rediseño completo del panel
