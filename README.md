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
preguntar, `--sin-dhcp` si DHCP y DNS los da otro equipo, `--ipv6` para dar
también IPv6 a la red (ver abajo) y `--sin-router` para solo vigilar (con una sola interfaz; entonces no hay bloqueos ni
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

### IPv6

Con `--ipv6` (o `IPV6_LAN=true` en `.env`), en modo router LanSentinel da
también IPv6 a la LAN. El prefijo de la red sale, por este orden, de:

1. `IPV6_PREFIX`: un prefijo fijo que la operadora enruta hacia este equipo.
2. Un **prefijo delegado (DHCPv6-PD)** que se pide a la operadora por la WAN
   (`IPV6_PD`): es lo habitual en fibra.
3. Si la operadora no delega ninguno, una **dirección privada (ULA) con
   NAT66** (`IPV6_NAT_FALLBACK`), para que la red tenga IPv6 igualmente. En
   cuanto llega un prefijo delegado, se pasa a él.

Los dispositivos se configuran solos (anuncios de router y DNS por DHCPv6 sin
estado, con dnsmasq). En IPv6 los equipos de casa tienen direcciones
públicas, sin NAT que los esconda, así que el cortafuegos **no deja entrar
nada desde Internet** salvo las respuestas a lo que ellos piden; con IPv6
apagado, no se reenvía nada en IPv6 entre la WAN y la LAN. Los bloqueos por
MAC, la cuarentena, el conteo de tráfico, las conexiones y los dominios
funcionan también en IPv6: las direcciones de cada equipo (también las de
privacidad, que cambian cada día) se sacan de la tabla de vecinos y se suman
a su IPv4. **Ajustes → Modo router** muestra el prefijo y de dónde sale, y la
ficha de cada dispositivo, sus direcciones IPv6.

Las listas de IPs maliciosas son solo IPv4. Con un prefijo delegado público,
añádelo a `HOME_NET` en `docker/suricata/suricata.yaml` para que las reglas
de Suricata traten esas direcciones como de casa (las ULA ya están).

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

## Copias de seguridad

Cada copia es un `lansentinel-<fecha>-<hora>-<motivo>.tar.gz` con la base de
datos completa (dispositivos, alertas, reglas, histórico, usuarios, ajustes),
`/var/lib/lansentinel` (clave de sesión, CA y certificado del panel,
dnsmasq) y el `.env`.

- **Cuándo:** una al día a las 3:00 (`BACKUP_HOUR`, `-1` las desactiva; si el
  equipo estaba apagado, se hace al volver), la primera al poco de instalar,
  antes de cada actualización con el instalador, antes de restaurar y cuando
  se pulsa **Ajustes → Copias de seguridad → Hacer copia ahora**.
- **Cuántas:** las 7 más recientes y, de las anteriores, una por semana
  durante 4 semanas (`BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`).
- **Dónde:** en `/var/lib/lansentinel/backups`, o en la carpeta de
  `BACKUP_PATH`. Mejor en otro disco (un USB montado siempre en la misma
  ruta): si se estropea el del sistema, se pierden las copias con él. Desde
  el panel se pueden descargar para guardarlas fuera.
- **Avisos:** alerta si una copia falla (se reintenta en una hora) y si la
  última correcta tiene más de dos días.
- **Seguridad:** contienen las contraseñas cifradas, la clave de la CA y el
  `.env`, así que solo root puede leerlas. Guarda las descargas en un sitio
  seguro.

La base de datos se vuelca con `pg_dump` 16, la misma versión que la base de
datos, y se comprueba que el volcado se pueda leer antes de darlo por bueno.

### Restaurar

```bash
sudo scripts/restaurar.sh lansentinel-20261026-030000-diaria.tar.gz
```

Con solo el nombre la busca en la carpeta de las copias; también acepta una
ruta. Antes hace una copia del estado actual (para deshacerlo, restaurando
esa), para el panel, restaura la base de datos en una sola transacción (si
falla, queda como estaba) y los ficheros de `/var/lib/lansentinel`, y vuelve
a arrancarlo. El `.env` no se sustituye: el de la copia queda en `.env.copia`
y se listan las variables que difieren.

**Equipo nuevo** (disco roto, cambio de equipo): clona el repositorio,
ejecuta `sudo scripts/instalar.sh`, copia el fichero de la copia al equipo y
restaura. Si importaste la CA de LanSentinel en tus dispositivos, sigue
valiendo: se restaura la misma.

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

### Tests

```bash
scripts/tests.sh            # todos
scripts/tests.sh -k copias  # los argumentos van a pytest
```

Se ejecutan dentro de la imagen del backend (mismas versiones de Python y
librerías que en producción) con pytest encima; solo hace falta Docker. Cubren
la lógica que más se puede romper sin que se note: parseo de conntrack e
iptables, reglas del modo router, direcciones protegidas, dnsmasq, lectura de
eve.json (líneas a medias y rotaciones), reglas de ARP spoofing, servicios
inseguros, contraseñas y tokens, IP real tras el proxy y límite de intentos,
la CA del panel (incluida su restricción de nombres), copias de seguridad y
tramos del histórico (con cambios de hora). No tocan iptables, la base de
datos ni la red: lo que depende de ellos se prueba en el laboratorio.

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

### Usuarios y registro de acciones

En **Ajustes → Usuarios** el administrador da de alta a más personas con uno
de dos roles:

| Rol | Puede |
|-----|-------|
| Administrador | Todo |
| Solo lectura | Ver todo el panel: dispositivos, conexiones, tráfico, alertas, cortafuegos, ajustes. No puede cambiar nada (bloquear, marcar de confianza, resolver alertas, cuarentena, modo router, copias…), ni ver el historial de dominios de los dispositivos, ni descargar copias (llevan secretos), ni ver usuarios o el registro. Sí puede cambiar su propia contraseña |

- Los permisos los aplica el backend (un usuario de solo lectura recibe 403
  aunque llame a la API directamente); el panel, además, esconde los botones.
- Un cambio de rol vale al momento, sin cerrar sesión. Desactivar o borrar a
  alguien, o ponerle una contraseña nueva, cierra sus sesiones.
- Siempre queda al menos un administrador activo: no se puede quitar el
  último, ni borrarse a uno mismo.

**Ajustes → Registro de acciones** (solo administradores) guarda cada cambio
hecho desde el panel o la API: quién, desde qué IP, qué (con el dispositivo,
usuario o regla afectados) y con qué resultado, incluidos los intentos
denegados de los usuarios de solo lectura y los inicios de sesión fallidos.
Las contraseñas, tokens y secretos de las peticiones se guardan tapados
(`***`). Se conserva `AUDIT_LOG_DAYS` días (365) y no se puede borrar desde
el panel.

## Detección

**Suricata** analiza el tráfico de la LAN con las reglas de **Emerging
Threats (ET Open)**, unas 47.000 firmas de malware, exploits, botnets,
escaneos y abusos conocidos, más las reglas propias de LanSentinel
(`docker/suricata/rules/lansentinel.rules`: fuerza bruta, escaneos internos).

- Se descargan con `suricata-update` la primera vez que arranca Suricata y
  se actualizan cada día (`RULES_UPDATE_HOURS`), recargándolas sin
  reiniciarlo: si una actualización trae reglas que fallan, sigue con las
  anteriores (`docker/suricata/arranque.sh` y `actualizar-reglas.sh`).
- No se cargan las categorías que en casa solo generan ruido (`emerging-info`
  y `emerging-hunting`) ni las de protocolos industriales:
  `docker/suricata/disable.conf`.
- Suricata pasa a usar unos 500 MB de memoria con todas las reglas.
- En `eve.json` solo escribe lo que usa LanSentinel (alertas, DNS y TLS).
  Sus registros se rotan al pasar de `SURICATA_LOG_MAX_MB` (100 MB): se
  guardan el actual y uno anterior, y el backend termina de leer el
  anterior antes de seguir, así que no se pierde ninguna alerta.

### Listas de IPs maliciosas

El cortafuegos corta todo el tráfico con las redes de listas públicas de
amenazas, que se descargan cada día (`THREAT_LISTS_UPDATE_HOURS`) y se
cargan en un `ipset` de forma atómica:

- **FireHOL nivel 1**: botnets, malware, redes secuestradas (Spamhaus DROP,
  DShield...). Pensada para bloquear sin falsos positivos.
- **abuse.ch Feodo Tracker**: servidores de control de botnets bancarias.
- **Lista propia**: `/var/lib/lansentinel/amenazas/propia.txt` (una IP o red
  por línea), para bloquear a mano; se aplica con **Actualizar listas**.

Si un dispositivo intenta conectar con una IP de las listas, se corta y se
crea una **alerta alta** con el dispositivo y las redes contactadas (suele
ser malware llamando a casa). Lo que llega de Internet desde ellas solo se
cuenta. **Cortafuegos → Inteligencia de amenazas** muestra las listas, cuánto
se ha cortado y el estado de las reglas de Suricata.

Algunas listas incluyen rangos reservados (FireHOL trae `192.168.0.0/16`):
cualquier red que se solape con rangos privados o especiales, con el propio
equipo, su puerta de enlace o `FIREWALL_NEVER_BLOCK` se descarta, para no
dejar la LAN sin red. Se configuran con `THREAT_LISTS` (`nombre=url`, separadas
por comas) y se desactivan con `THREAT_LISTS_ENABLED=false`. Solo IPv4.

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
- **Picos de consumo:** cada dispositivo tiene su patrón (una cámara sube
  poco y siempre parecido; un portátil, de todo). Al acabar cada hora se
  compara lo que ha subido y bajado con sus horas de actividad de las dos
  últimas semanas: si se dispara (5 veces lo habitual, 6 desviaciones por
  encima y al menos 100 MB de subida), alerta media de "Subida inusual",
  que puede ser un equipo sacando datos o atacando a otros. La descarga solo
  avisa con picos muy grandes (2 GB/h) y como alerta baja. Hacen falta 48
  horas con actividad antes de juzgar un dispositivo. La ficha de cada
  dispositivo (pestaña Consumo) muestra lo habitual y a partir de cuánto se
  avisa. Se ajusta con las variables `ANOMALY_*`.
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
pregunta la red y bloquear una IP de Internet. Debajo de cada IP remota
aparece el dominio al que corresponde, si se ha visto en una consulta DNS o
en el SNI de una conexión TLS de las últimas 6 horas. Solo aparece lo que
atraviesa LanSentinel (no el tráfico directo entre equipos de la LAN), en
IPv4 e IPv6.

## Dominios y huellas TLS

Casi todo el tráfico va cifrado, pero Suricata sigue viendo dos cosas en
claro: las consultas DNS y el **SNI**, el nombre del servidor que el cliente
pone en el saludo TLS. Con eso, la pestaña **Dominios** de la ficha de cada
dispositivo muestra:

- **Dominios** que ha usado (últimas 24 h, 7 o 30 días), con cuántas veces,
  cuándo fue la última y si se vio por DNS, por TLS o por los dos.
- **Huellas TLS (JA4, o JA3 si no hay)**: identifican el programa que abre
  la conexión (un navegador, una app, una librería), no el contenido. Un
  equipo que de repente estrena huellas raras está ejecutando algo nuevo.

Se guarda agregado (un registro por dispositivo y dominio, con contadores),
no cada consulta. Es el historial de navegación de cada equipo: solo lo ve
el administrador, se borra a los `DOMAIN_HISTORY_DAYS` días (30) sin verse y
se desactiva con `DOMAIN_TRACKING_ENABLED=false`. Lo que va por DNS cifrado
(DoH/DoT) o ECH no se ve: de eso solo queda el SNI del servidor DNS o del
frontal. Solo se ve el tráfico que atraviesa LanSentinel.

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
| `LANSENTINEL_THREAT` | `FORWARD` e `INPUT` (las primeras) | Listas de IPs maliciosas (ipset `lansentinel-amenazas`), una regla por dispositivo |
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
- El bloqueo automático (alertas críticas de Suricata) corta las IPs
  externas con cualquier regla, pero a un dispositivo de la LAN solo con las
  reglas propias de LanSentinel (fuerza bruta, escaneos internos). Con una
  regla de Emerging Threats queda la alerta crítica y decides tú: bloquear o
  poner en cuarentena. Una sola firma (que puede ser un falso positivo) no
  deja sin red a un equipo de casa.

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
- [x] **v1.7** — Instalador y modo router (NAT, WAN cerrada, DHCP y DNS) con
  interruptor en el panel; panel por HTTPS con CA propia y HTTP/2; la API
  solo escucha en local
- [x] **v1.8** — Copias de seguridad automáticas (base de datos, estado y
  .env) con rotación, alertas, descarga desde el panel y `scripts/restaurar.sh`
- [x] **v1.9** — Tests con pytest (`scripts/tests.sh`); inteligencia de
  amenazas: reglas de Emerging Threats para Suricata y listas de IPs
  maliciosas en el cortafuegos, con alerta por dispositivo
- [x] **v1.10** — Picos de consumo por dispositivo respecto a su patrón
  habitual; dominios (DNS y SNI) y huellas TLS JA4/JA3 por dispositivo, con
  el nombre de cada IP en las conexiones
- [x] **v1.11** — Usuarios con rol (administrador / solo lectura) y registro
  de acciones; IPv6 en la LAN (prefijo delegado o ULA con NAT66) con
  cortafuegos, conteo y conexiones; registros de Suricata más ligeros y
  rotados
