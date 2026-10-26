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
TanStack Query + Tailwind + Recharts. Todo en Docker Compose; el backend y
Suricata usan `network_mode: host`.

```
backend/app/
  api/routes/      endpoints (auth, devices, network, alerts, firewall, security, system, events)
  api/deps.py      get_current_user (cookie httpOnly o Bearer)
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
    auth/          usuarios y límite de intentos de login
frontend/src/      pages, components, hooks (React Query), lib (api, tipos, toast)
docker/            init.sql y configuración/reglas de Suricata
scripts/           instalar.sh: instalación y modo router
```

## Ramas

**`main` contiene la 1.6.0** (etiqueta `v1.6.0`, subida a GitHub). Las ramas
de fase se fusionaron en `main` por fast-forward y quedan como historial: cada
una parte de la anterior. Las de la 1.1 a la 1.5 están en el remoto; las de
la 1.6, solo en local. El trabajo nuevo sale de `main` en una rama propia.
El estado entregado del TFG (1.0) es el commit `335153b` ("LanSentinel 1.0").

| Rama | Versión | Contenido |
|------|---------|-----------|
| `main` | 1.6.0 | Todo lo de las ramas siguientes |
| `fase0-correcciones` | 1.1 | Cadenas propias, bloqueo MAC+IP, IPv6, IPs protegidas, agrupación de alertas |
| `fase1-seguridad` | 1.2 | Login, compose endurecido, lista OUI local |
| `fase2-historico-trafico` | 1.3 | Histórico de consumo y ranking |
| `fase2-avisos` | 1.4 | SSE, Telegram/ntfy/correo, página Ajustes |
| `fase2-deteccion` | 1.5 | ARP spoofing, servicios inseguros, escaneo periódico, modo cuarentena |
| `fase2-correcciones-lab` | 1.5 | Fallos de las pruebas en laboratorio (H2-H4): página Tráfico, panel en cuarentena, aviso de SECRET_KEY |
| `fase2-conexiones` | 1.5 | Conexiones por dispositivo con conntrack |
| `fase2-interfaz` | 1.6 | Rediseño completo del panel, página Conexiones de toda la red, clasificación de conexiones |
| `fase3-instalador` | 1.7 (en curso) | Modo router (NAT, reenvío, WAN cerrada, DHCP/DNS) con interruptor en Ajustes, `scripts/instalar.sh` |

## Decisiones de diseño (respetarlas en cambios futuros)

- **Cortafuegos en cadenas propias**, que se vacían y reconstruyen desde la BD
  al arrancar, nunca reglas sueltas en INPUT/FORWARD. Orden en FORWARD:
  `LANSENTINEL_FWD` (bloqueos) → `LANSENTINEL_QUAR` (cuarentena) →
  `LANSENTINEL_ACCT` (conteo) → reglas NAT del sistema. Las reglas se
  identifican por el comentario exacto `lansentinel:<id>`.
- **Bloqueo híbrido**: los dispositivos de la LAN, por MAC y por IP (la regla
  se rehace si cambia la IP); las IPs externas, solo por IP (llegan con la MAC
  del router).
- **Nunca bloquear** la IP propia, la puerta de enlace, broadcast ni
  `FIREWALL_NEVER_BLOCK` (`services/firewall/protection.py`). El bloqueo
  automático tampoco toca los dispositivos de confianza.
- **ARP spoofing: solo alertar**, no bloquear (un cambio de router daría un
  falso positivo que dejaría la red sin salida). Un conflicto exige vaivén
  A → B → A, no un cambio único (DHCP, MAC aleatoria).
- **Cuarentena solo en FORWARD**: los retenidos siguen llegando a LanSentinel
  (DHCP, DNS, panel) para que siempre se pueda desactivar. El panel corre en
  un contenedor con el puerto publicado (DNAT), así que `LANSENTINEL_QUAR`
  deja pasar primero las conexiones con `--ctstate DNAT`.
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
- **Conexiones** (`services/monitor/connections.py`): se leen de la tabla
  conntrack con la herramienta `conntrack`. Solo cuentan como abiertas las TCP
  establecidas con tráfico reciente y el UDP sostenido (`[ASSURED]`); las
  consultas sueltas (DNS, NTP) son "done" y las TCP sin tráfico desde hace
  30 min, "idle". Solo se ve lo que atraviesa LanSentinel, y solo IPv4.
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

Panel en `http://<ip>:3000` y API en `http://<ip>:8000/docs`. Si el frontend no
alcanza el backend, define `BACKEND_URL=http://<ip-del-equipo>:8000` en `.env`.

## Verificación

- Backend: `ruff check --select F,E9 backend/app` e importar `app.main`.
- Frontend (en `frontend/`): `npx tsc -b`, `npx eslint .`, `npx vite build`.
- Panel: sin acceso al backend real, se revisa en el navegador con Vite y un
  backend simulado que sirve respuestas capturadas del laboratorio (no está
  en el repositorio).
- Sin Docker ni PostgreSQL, la lógica se ha probado con funciones puras,
  iptables simulado, SQLite en memoria y un backend simulado en el navegador.
  Las consultas específicas de PostgreSQL (`date_trunc`, `AT TIME ZONE`,
  `ON CONFLICT`) solo se pueden validar con la base de datos real.

## Pruebas en laboratorio (VirtualBox)

Hechas el 2026-10-25 con la 1.5 y repasadas el 2026-10-26 con la 1.6, en dos
VMs: LanSentinel (192.168.56.10, interfaz vigilada `enp0s8`) y un equipo de
prueba (192.168.56.20) que usa la .10 como puerta de enlace.

Verificado en real: arranque y migraciones sobre una BD existente, login,
cortafuegos sin duplicados tras reinicios, bloqueo por IP y MAC (también al
cambiar de IP), Suricata (escaneo de puertos y fuerza bruta SSH con una sola
alerta agrupada y bloqueo automático), SSE y avisos por ntfy, histórico de
tráfico, cuarentena (el retenido llega al panel y no a Internet), detección
de ARP spoofing, servicios inseguros y conexiones por conntrack.

Sin probar: avisos por Telegram y correo (sin credenciales) y la alerta
`gateway_changed` (la red de pruebas no tiene puerta de enlace en la
interfaz vigilada).

## Pendiente de desarrollo

Para usarlo en una red real (prioritario):

- IPv6: que no se pueda salir a Internet por IPv6 saltándose LanSentinel, y
  conexiones IPv6 en la página Conexiones.
- HTTPS en el panel (cookie de sesión, portapapeles, notificaciones).
- Copias de seguridad automáticas de la BD y guía de recuperación.

Fase 2:

- Anomalías de tráfico: patrón normal por dispositivo (media móvil) y alerta
  ante picos.
- Inteligencia de amenazas: reglas ET con `suricata-update` y listas de IPs
  maliciosas (FireHOL, abuse.ch) en un `ipset`.
- Tráfico cifrado: eventos `tls`/`dns`/`quic` de Suricata, JA3/JA4 y SNI por
  dispositivo.
- Multiusuario con roles (admin / solo lectura) y registro de acciones.
- Dispositivo dedicado: imágenes arm64, script de instalación y guía para
  Raspberry Pi.
- Fase 3: tests con pytest de la lógica pura (parseo de iptables y eve.json,
  reglas ARP, comparación de escaneos, tramos del histórico).
