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
```

## Ramas

Ninguna está subida ni fusionada en `main`. Cada una parte de la anterior, así
que **`fase2-deteccion` contiene todo**.

| Rama | Versión | Contenido |
|------|---------|-----------|
| `main` | 1.0 | Estado entregado del TFG |
| `fase0-correcciones` | 1.1 | Cadenas propias, bloqueo MAC+IP, IPv6, IPs protegidas, agrupación de alertas |
| `fase1-seguridad` | 1.2 | Login, compose endurecido, lista OUI local |
| `fase2-historico-trafico` | 1.3 | Histórico de consumo y ranking |
| `fase2-avisos` | 1.4 | SSE, Telegram/ntfy/correo, página Ajustes |
| `fase2-deteccion` | 1.5 | ARP spoofing, servicios inseguros, escaneo periódico, modo cuarentena |

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
  (DHCP, DNS, panel) para que siempre se pueda desactivar.
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
- Sin Docker ni PostgreSQL, la lógica se ha probado con funciones puras,
  iptables simulado, SQLite en memoria y un backend simulado en el navegador.
  Las consultas específicas de PostgreSQL (`date_trunc`, `AT TIME ZONE`,
  `ON CONFLICT`) solo se pueden validar con la base de datos real.

## Pendiente de probar en real (laboratorio VirtualBox)

Nada de las ramas 1.1 a 1.5 se ha probado aún con iptables, Suricata,
PostgreSQL y red reales. Orden sugerido:

1. **Arranque y migraciones** sobre la BD existente: el backend arranca sin
   errores y en los logs aparece la creación del admin.
2. **Login**: entrar con la contraseña inicial y cambiarla; sin sesión la API
   responde 401.
3. **Cortafuegos**: bloquear una VM, reiniciar el backend dos veces y revisar
   `sudo iptables -S FORWARD` y `sudo iptables -S LANSENTINEL_FWD` (sin
   duplicados). Desbloquear: la cadena queda vacía.
4. **Bloqueo por MAC**: bloquear una VM, cambiarle la IP y comprobar que sigue
   sin salida y que aparece la alerta de cambio de IP.
5. **Suricata**: escaneo de puertos y fuerza bruta SSH desde la VM atacante →
   una sola alerta con contador ×N y bloqueo automático. Versión de Suricata:
   `docker exec lansentinel_suricata suricata -V` (si es 7.x, usar la imagen
   `jasonish/suricata:7.0`).
6. **Tiempo real y avisos**: el aviso aparece en el panel al instante;
   configurar ntfy o Telegram en `.env` y usar Ajustes → Enviar prueba.
7. **Histórico**: dejar tráfico unos minutos y revisar la página Tráfico.
8. **Cuarentena**: marcar el equipo propio como de confianza, activarla,
   comprobar que una VM sin confianza pierde Internet pero llega al panel, y
   que la recupera al marcarla.
9. **ARP spoofing**: desde la VM atacante,
   `sudo arpspoof -i eth0 -t <IP_LanSentinel> <IP_otra_VM>` → alerta.
10. **Servicios inseguros**: activar Telnet o VNC en una VM y lanzar un
    escaneo desde su detalle → alerta y puerto marcado con su riesgo.

## Pendiente de desarrollo (Fase 2)

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
