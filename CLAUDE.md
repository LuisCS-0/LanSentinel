# LanSentinel: contexto para Claude Code

Monitor de seguridad para redes domésticas: descubre dispositivos (ARP), mide
su tráfico, detecta intrusiones (Suricata y reglas propias), bloquea con
iptables y avisa por el panel y por canales externos. Fue el TFG de Luis
Corral (Ingeniería Informática, UDC), ya defendido; ahora se sigue
desarrollando como proyecto personal.

## Reglas de trabajo

- **No modificar la memoria del TFG** (proyecto LaTeX fuera de este repo). Si
  está disponible, solo se consulta.
- Todo en español: código comentado, mensajes de commit, textos del panel,
  logs explicativos y respuestas.
- Una rama por fase y un commit por punto, con mensajes que expliquen el
  problema que había y cómo se resuelve.
- Explicar siempre qué está verificado y qué no se ha podido probar en real.
- No hacer push ni merge sin que el usuario lo pida.

## Stack y estructura

Python 3.12 + FastAPI + SQLAlchemy async (asyncpg), PostgreSQL 16, Suricata
8.0, iptables/ip6tables, scapy, nmap. Frontend en React + TypeScript + Vite +
TanStack Query + Tailwind + Recharts. Todo en Docker Compose; el backend, el
frontend (nginx) y Suricata usan `network_mode: host`. La API solo escucha en
`127.0.0.1:8000`: desde la red se llega por el nginx del panel, con HTTPS.

```
backend/app/
  api/routes/      endpoints (auth, devices, network, alerts, firewall, security, system, events, users, audit)
  api/deps.py      get_current_user (cookie httpOnly o Bearer), require_write, require_admin
  core/            config (pydantic-settings), security (Argon2, JWT), logging
  db/              sesión y migrations.py (sentencias idempotentes al arrancar)
  models/          ORM
  services/
    monitor/       ARP scan, OUI local, medidor de tráfico, histórico
    security/      Suricata, clasificador, nmap, servicios inseguros, ARP spoofing, escaneo periódico
    firewall/      iptables_manager, firewall_service, auto_block, protection
    alerts/        alert_service (creación y agrupación de alertas)
    events/        bus de eventos en memoria (SSE)
    notifications/ Telegram, ntfy, correo
    auth/          usuarios y roles, límite de intentos de login, registro de acciones (audit)
    backup/        copias de seguridad (archive: crear/rotar; backup_service: programación y alertas)
frontend/src/      pages, components, hooks (React Query), lib (api, tipos, toast)
docker/            init.sql y configuración/reglas de Suricata
scripts/           instalar.sh: instalación y modo router; restaurar.sh: restaurar una copia
```

## Ramas

**`main` contiene la 1.10.0** (etiqueta `v1.10.0`). Las ramas de fase se
fusionaron en `main` por fast-forward y quedan como historial: cada una parte
de la anterior. Las de la 1.1 a la 1.5 están en el remoto; las de la 1.6 a la
1.10, solo en local. El trabajo nuevo sale de `main` en una rama propia.
El estado entregado del TFG (1.0) es el commit `335153b` ("LanSentinel 1.0").

| Rama | Versión | Contenido |
|------|---------|-----------|
| `main` | 1.10.0 | Todo lo de las ramas siguientes |
| `fase0-correcciones` | 1.1 | Cadenas propias, bloqueo MAC+IP, IPv6, IPs protegidas, agrupación de alertas |
| `fase1-seguridad` | 1.2 | Login, compose endurecido, lista OUI local |
| `fase2-historico-trafico` | 1.3 | Histórico de consumo y ranking |
| `fase2-avisos` | 1.4 | SSE, Telegram/ntfy/correo, página Ajustes |
| `fase2-deteccion` | 1.5 | ARP spoofing, servicios inseguros, escaneo periódico, modo cuarentena |
| `fase2-correcciones-lab` | 1.5 | Fallos de las pruebas en laboratorio (H2-H4): página Tráfico, panel en cuarentena, aviso de SECRET_KEY |
| `fase2-conexiones` | 1.5 | Conexiones por dispositivo con conntrack |
| `fase2-interfaz` | 1.6 | Rediseño completo del panel, página Conexiones de toda la red, clasificación de conexiones |
| `fase3-instalador` | 1.7 | Modo router (NAT, reenvío, WAN cerrada, DHCP/DNS) con interruptor en Ajustes, `scripts/instalar.sh` |
| `fase3-https` | 1.7 | Panel por HTTPS con CA propia, HTTP/2 y redirección desde HTTP |
| `fase3-copias` | 1.8 | Copias de seguridad automáticas, descarga desde el panel y `scripts/restaurar.sh` |
| `fase4-tests` | 1.9 | Tests con pytest de la lógica pura (`scripts/tests.sh`) |
| `fase4-amenazas` | 1.9 | Reglas ET con suricata-update, listas de IPs maliciosas en un ipset y bloqueo automático de la LAN solo con reglas propias |
| `fase5-anomalias` | 1.10 | Picos de consumo por dispositivo respecto a su patrón habitual |
| `fase5-cifrado` | 1.10 | Dominios (DNS y SNI) y huellas TLS JA4/JA3 por dispositivo, nombre de cada IP en las conexiones |
| `fase6-usuarios` | 1.11 (en curso) | Usuarios con rol (administrador / solo lectura) y registro de acciones |
| `fase6-mantenimiento` | 1.11 (en curso) | eve.json sin eventos que no se usan, rotación de los registros de Suricata, `.dockerignore` |

## Decisiones de diseño (respetarlas en cambios futuros)

- **Cortafuegos en cadenas propias**, que se vacían y reconstruyen desde la BD
  al arrancar, nunca reglas sueltas en INPUT/FORWARD. Orden en FORWARD:
  `LANSENTINEL_THREAT` (listas de amenazas) → `LANSENTINEL_FWD` (bloqueos)
  → `LANSENTINEL_QUAR` (cuarentena) →
  `LANSENTINEL_ACCT` (conteo) → reglas NAT del sistema. Las reglas se
  identifican por el comentario exacto `lansentinel:<id>`.
- **Bloqueo híbrido**: los dispositivos de la LAN, por MAC y por IP (la regla
  se rehace si cambia la IP); las IPs externas, solo por IP (llegan con la MAC
  del router).
- **Nunca bloquear** la IP propia, la puerta de enlace, broadcast ni
  `FIREWALL_NEVER_BLOCK` (`services/firewall/protection.py`). El bloqueo
  automático tampoco toca los dispositivos de confianza.
- **Bloqueo automático de la LAN solo con reglas propias**
  (`firewall/auto_block.py`, sid 1000000-1999999): con las de Emerging
  Threats, un dispositivo de casa solo genera la alerta crítica. Las IPs
  externas se bloquean con cualquier regla crítica.
- **ARP spoofing: solo alertar**, no bloquear (un cambio de router daría un
  falso positivo que dejaría la red sin salida). Un conflicto exige vaivén
  A → B → A, no un cambio único (DHCP, MAC aleatoria).
- **Cuarentena solo en FORWARD**: los retenidos siguen llegando a LanSentinel
  (DHCP, DNS, panel) para que siempre se pueda desactivar. `LANSENTINEL_QUAR`
  deja pasar primero las conexiones con `--ctstate DNAT` (puertos publicados
  por contenedores; el panel ya no lo es: nginx usa la red del equipo y le
  llega por INPUT).
- **Modo router** (`ROUTER_MODE`, `WAN_INTERFACE`): el NAT, el reenvío y la
  protección de la WAN viven en cadenas propias (`LANSENTINEL_ROUTE`,
  `LANSENTINEL_WAN_IN`, `LANSENTINEL_NAT`) que el backend reconstruye al
  arrancar; nada de reglas guardadas a mano. Lo único que hace el sistema es
  `net.ipv4.ip_forward=1` (un contenedor no puede cambiarlo). DHCP/DNS los da
  dnsmasq como proceso hijo del backend (`services/firewall/dhcp_dns.py`),
  no en un contenedor: así se enciende y apaga desde el panel sin dar al
  backend el socket de Docker. El estado elegido en el panel va en la tabla
  `settings`; `ROUTER_MODE` de `.env` es el inicial y, si cambia, manda en el
  siguiente arranque. `scripts/instalar.sh` no toca la configuración de red:
  solo comprueba la IP fija de la LAN.
- **HTTPS** (`services/tls_cert.py`): el backend crea una CA propia con
  restricción de nombres (solo `.lan`, el nombre del equipo e IPs privadas)
  y firma el certificado del panel, que rehace si cambian las IPs o le queda
  menos de un mes. nginx (contenedor del frontend, en la red del equipo)
  termina el TLS y es la única entrada a la API, que solo escucha en
  127.0.0.1; avisa al backend con `X-Forwarded-Proto`, que marca la cookie
  `Secure`, y con `X-Real-IP` (solo se acepta desde 127.0.0.1). Un
  `server.crt` que no haya firmado la CA es del usuario y no se toca. Sin
  HSTS: con un certificado aún no importado dejaría el panel inaccesible.
- **Copias de seguridad** (`services/backup`): un `.tar.gz` con el volcado
  de la BD (`pg_dump` 16 del repositorio de PostgreSQL, no el 17 de Debian:
  el `pg_restore` del contenedor de la BD no leería su formato), los ficheros
  de `/var/lib/lansentinel` y el `.env` (el proyecto se monta en solo
  lectura). Se restauran con `scripts/restaurar.sh` usando las herramientas
  del contenedor de la BD. Un cerrojo de fichero evita dos copias a la vez
  (backend y `python -m app.services.backup`, que usa el instalador). Si se
  sube la versión de la imagen de PostgreSQL, subir también el cliente.
- **Anomalías de tráfico** (`services/monitor/anomalies.py`): por
  dispositivo y hora, con mediana y MAD (robustas frente a horas raras) de
  sus horas con actividad en `network_usage_hourly`. Un pico tiene que
  superar a la vez el factor sobre la mediana, 6 desviaciones y un mínimo
  absoluto. Se evalúa la hora terminada con 10 min de margen (el agregado
  se recalcula cada 5). La subida pesa más que la descarga.
- **Listas de amenazas** (`services/security/threat_lists.py`): ipset
  `lansentinel-amenazas` cargado con restore + swap (atómico), con contadores
  por entrada; cadena `LANSENTINEL_THREAT` con una regla por dispositivo para
  saber quién intentó contactar (alerta alta por contadores, cada minuto).
  Toda red que se solape con rangos privados/especiales, el propio equipo, su
  puerta de enlace o `FIREWALL_NEVER_BLOCK` se descarta antes de cargarla.
  Las listas se guardan en `/var/lib/lansentinel/amenazas` y se aplican al
  arrancar sin esperar a la red.
- **Reglas de Suricata**: ET Open con `suricata-update` dentro del propio
  contenedor de Suricata (`docker/suricata/arranque.sh`, sin acceso a Docker
  desde el backend), en el volumen `suricata_data`, que el backend monta en
  solo lectura para mostrar el estado. Se recargan con `suricatasc` sin
  reiniciar. Sin `--init-errors-fatal`: una regla que no cargue no tumba el
  IDS. Las variables de `suricata.yaml` son las que usan las reglas ET.
  `eve.json` solo lleva alert, dns y tls (flow y http eran el 90 % y no se
  usaban); si el backend empieza a leer otro tipo, añadirlo ahí. El propio
  contenedor rota los registros por tamaño (renombrar a `.1` y SIGHUP);
  `suricata_reader` lee lo que quedaba en el `.1` (lo reconoce por el
  inodo, que guarda con la posición) antes de seguir con el nuevo.
- **Conexiones** (`services/monitor/connections.py`): se leen de la tabla
  conntrack con la herramienta `conntrack`. Solo cuentan como abiertas las TCP
  establecidas con tráfico reciente y el UDP sostenido (`[ASSURED]`); las
  consultas sueltas (DNS, NTP) son "done" y las TCP sin tráfico desde hace
  30 min, "idle". Una TCP con datos sin confirmar (el kernel la deja en el
  temporizador `unacknowledged`, 300 s) es una transferencia en curso, no
  "idle". Solo se ve lo que atraviesa LanSentinel, y solo IPv4.
- **Dominios y huellas TLS** (`services/security/domain_tracker.py`): de los
  eventos `dns` y `tls` de Suricata (JA3/JA4 activados en `suricata.yaml`).
  Se acumula en memoria y se vuelca cada minuto con `ON CONFLICT` (sumando
  contadores) en `device_domains` y `device_tls_fingerprints`; se purga a
  los `DOMAIN_HISTORY_DAYS`. La IP de una respuesta DNS se asocia al nombre
  consultado, no al final de la cadena de CNAME (dice más que el del CDN).
  El mapa IP → nombre para las conexiones vive solo en memoria (6 h, 20.000
  entradas): tras reiniciar el backend los nombres vuelven con el tráfico.
  Es información sensible: solo para el administrador y desactivable.
- **Roles** (`api/deps.py`): `admin` o `viewer` (solo lectura) en
  `users.role`. Una sola regla para todos los routers: `require_write` deja
  pasar cualquier GET y exige administrador para lo demás; `require_admin`
  cierra además los GET sensibles (historial de dominios, descarga de copias,
  usuarios y registro). Toda ruta nueva hereda la regla sin hacer nada; si
  un GET muestra algo sensible, ponerle `require_admin`. El rol se lee de la
  BD en cada petición (cambia al momento). Siempre queda un administrador
  activo (`user_service.leaves_without_admin`). El panel esconde los
  botones con `useIsAdmin()`, pero quien manda es el backend.
- **Registro de acciones** (`services/auth/audit.py`): middleware ASGI que
  guarda en `audit_log` toda petición a la API que no sea GET (y las
  descargas de copias) cuando termina: usuario (lo deja `get_current_user`
  en `request.state.user`), IP real, descripción, objetivo con nombre,
  código de respuesta y cuerpo con los secretos tapados. Cada ruta nueva que
  cambie algo necesita su descripción en `ACTIONS` (un test lo comprueba).
  Se guarda el nombre del usuario, no su id, para que el registro sobreviva
  a su borrado; una ruta que borra algo deja el nombre en
  `request.state.audit_target`. El sello de contraseña de los tokens va en
  segundos: `next_password_change` evita dos cambios en el mismo segundo.
- **Alertas**: todas pasan por `alert_service.create_alert`; con `fingerprint`
  se agrupan las repeticiones. Los avisos externos solo salen con alertas
  nuevas (`alert.created`), nunca con las agrupadas.
- **Esquema**: las columnas nuevas van en `docker/db/init.sql` (instalaciones
  nuevas) y en `backend/app/db/migrations.py` (existentes, con IF NOT EXISTS).
- **Configuración**: lo que se fija al desplegar va en `.env` (llega al
  backend por `env_file`); lo que el usuario cambia desde el panel, en la
  tabla `settings` (`services/settings_store.py`).
- **Secretos**: nunca se devuelven por la API ni se escriben en logs.

## Arranque

```bash
sudo scripts/instalar.sh                                               # red real: lo deja como router
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up      # desarrollo
docker compose --profile production up -d                              # producción con Suricata
sudo cat /var/lib/lansentinel/initial_admin_password                   # primer acceso (usuario admin)
```

Panel en `https://<ip>` (HTTP en el 80 y el 3000 solo redirige; en desarrollo,
`http://localhost:3000`) y documentación de la API en `https://<ip>/docs`. La
API solo escucha en `127.0.0.1:8000`.

## Verificación

- Backend: `scripts/tests.sh` (pytest en la imagen del backend, sin root ni
  red; `backend/tests/`), `ruff check --select F,E9 backend/app` e importar
  `app.main`. Lógica nueva y pura, con su test.
- Frontend (en `frontend/`): `npx tsc -b`, `npx eslint .`, `npx vite build`.
- Panel: sin acceso al backend real, se revisa en el navegador con Vite y un
  backend simulado que sirve respuestas capturadas del laboratorio (no está
  en el repositorio).
- Sin Docker ni PostgreSQL, la lógica se ha probado con funciones puras,
  iptables simulado, SQLite en memoria y un backend simulado en el navegador.
  Las consultas específicas de PostgreSQL (`date_trunc`, `AT TIME ZONE`,
  `ON CONFLICT`) solo se pueden validar con la base de datos real.

## Pruebas en laboratorio (VirtualBox)

Hechas el 2026-10-25 con la 1.5 y repasadas el 2026-10-26 con la 1.6 y la
1.7, en dos VMs: LanSentinel (192.168.56.10, interfaz vigilada `enp0s8`) y un equipo de
prueba (192.168.56.20) que usa la .10 como puerta de enlace.

Verificado en real: arranque y migraciones sobre una BD existente, login,
cortafuegos sin duplicados tras reinicios, bloqueo por IP y MAC (también al
cambiar de IP), Suricata (escaneo de puertos y fuerza bruta SSH con una sola
alerta agrupada y bloqueo automático), SSE y avisos por ntfy, histórico de
tráfico, cuarentena (el retenido llega al panel y no a Internet), detección
de ARP spoofing, servicios inseguros y conexiones por conntrack. Con la 1.7:
instalador (también actualizando una instalación existente), modo router
(NAT, DHCP con ciclo completo en la .20, DNS, interruptor del panel y estado
tras reinicios), HTTPS (validación con la CA, HTTP/2, redirecciones, cookie
Secure, renovación del certificado sin reiniciar nginx) y la API cerrada a
la red (solo 127.0.0.1). Con la 1.8: copias (manual, automática, rotación,
cerrojo, errores) y restauración real con deshacer. Con la 1.9: reglas ET
(descarga, recarga en caliente, alerta con una regla de User-Agent), listas
de IPs en ipset (sin cortar la LAN; bloqueo y alerta con una IP de la lista
propia), bloqueo automático de la LAN solo con reglas propias y el nuevo
umbral de fuerza bruta SSH interna. Con la 1.10: alerta de subida inusual
(con el mínimo de historia rebajado), dominios DNS/SNI y huellas JA4 de la
.20 y su nombre en las conexiones, y una descarga larga como conexión
abierta.

Sin probar: avisos por Telegram y correo (sin credenciales), la alerta
`gateway_changed` (la red de pruebas no tiene puerta de enlace en la
interfaz vigilada), un intento real de entrar desde la WAN (en el
laboratorio es el NAT de VirtualBox), importar la CA en navegadores y
móviles reales, copias en otro disco (`BACKUP_PATH`), la alerta de copias
de más de dos días, tráfico real hacia una IP de FireHOL o abuse.ch y el
ciclo automático de anomalías con 48 h reales de historia.

## Pendiente de desarrollo

Descartado: la imagen para Raspberry Pi (no hay una para probarla) y
aislar los dispositivos entre sí (se hace con el hardware de red:
aislamiento de clientes en la wifi, VLANs o puertos aislados).

Para usarlo en una red real (prioritario):

- IPv6 en la LAN: en modo router es solo IPv4 (sin reenvío ni anuncios
  IPv6, así que nada sale por IPv6 sin pasar por LanSentinel). Falta darlo de
  verdad: prefijo de la operadora (DHCPv6-PD), anuncios en la LAN,
  cortafuegos, conteo y conexiones IPv6.

