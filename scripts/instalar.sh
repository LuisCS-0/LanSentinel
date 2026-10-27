#!/usr/bin/env bash
# Instala LanSentinel en el equipo. Por defecto solo vigila la red, sin
# tocar cómo funciona: no enruta ni reparte IPs. Si el equipo tiene dos
# interfaces de red, deja preparado el modo router (LanSentinel entre el
# router de la operadora y los dispositivos, con NAT, DHCP y DNS), que se
# enciende cuando se quiera desde Ajustes → Modo router, o ya al instalar
# con --router.
#
# Uso (desde la carpeta del proyecto):
#   sudo scripts/instalar.sh                  # pregunta lo necesario
#   sudo scripts/instalar.sh --si             # acepta lo detectado
#   sudo scripts/instalar.sh --router --wan eth0 --lan eth1
#
# Opciones:
#   --router        dejarlo ya como router de la red (necesita dos interfaces)
#   --sin-router    apagar el modo router (si una instalación anterior lo tenía)
#   --wan IFACE     interfaz hacia Internet (por defecto, la de la ruta por defecto)
#   --lan IFACE     interfaz de la red local (por defecto, la otra interfaz)
#   --sin-dhcp      en modo router, sin DHCP/DNS (ya los da otro equipo)
#   --ipv6          dar también IPv6 a la LAN: prefijo delegado por la operadora
#                   o, si no delega ninguno, una ULA con NAT66 (IPV6_* en .env)
#   --si            no preguntar: acepta los valores detectados
#
# Se puede volver a ejecutar: no pisa los valores que ya tenga .env salvo las
# interfaces, conserva el modo (salvo --router o --sin-router) y la base de
# datos.

set -euo pipefail

ROUTER=""          # vacío: el que ya tenga .env o, si es nuevo, solo vigilar
DHCP=true
IPV6=false
ASSUME_YES=false
WAN=""
LAN=""

while [ $# -gt 0 ]; do
    case "$1" in
        --wan) WAN="$2"; shift 2 ;;
        --lan) LAN="$2"; shift 2 ;;
        --router) ROUTER=true; shift ;;
        --sin-router) ROUTER=false; shift ;;
        --sin-dhcp) DHCP=false; shift ;;
        --ipv6) IPV6=true; shift ;;
        --si) ASSUME_YES=true; shift ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Opción desconocida: $1 (usa --help)" >&2; exit 2 ;;
    esac
done

# ── Utilidades ───────────────────────────────────────────────────────────────

paso() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
aviso() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fallo() { printf '\n\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

confirmar() {  # confirmar "pregunta" → 0 si sí
    $ASSUME_YES && return 0
    local r
    read -r -p "  $1 [s/N] " r
    [[ "$r" =~ ^[sSyY] ]]
}

preguntar() {  # preguntar "texto" "valor por defecto" → imprime la respuesta
    local r
    if $ASSUME_YES; then echo "$2"; return; fi
    read -r -p "  $1 [$2]: " r
    echo "${r:-$2}"
}

# Pone KEY=valor en .env: sustituye la línea (también si está comentada) o la añade
env_set() {
    local key="$1" value="$2"
    if grep -qE "^#? *${key}=" .env; then
        sed -i -E "s|^#? *${key}=.*|${key}=${value}|" .env
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

# Valor actual de KEY en .env (vacío si no está o está comentada)
env_get() {
    grep -E "^${1}=" .env | tail -n1 | cut -d= -f2- | sed 's/ *#.*//' || true
}

interfaces_fisicas() {
    ls /sys/class/net | grep -vE '^(lo|docker|br-|veth|virbr|tun|tap|wg)' || true
}

# ── 1. Comprobaciones previas ────────────────────────────────────────────────

cd "$(dirname "$0")/.."
[ -f docker-compose.yml ] || fallo "Ejecuta el script desde la carpeta de LanSentinel"
[ "$(id -u)" -eq 0 ] || fallo "Hace falta ejecutarlo como administrador: sudo $0"

paso "Comprobando el sistema"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    command -v apt-get >/dev/null || fallo "Falta Docker con el plugin compose. Instálalo (https://docs.docker.com/engine/install/) y vuelve a ejecutar."
    aviso "Docker o su plugin compose no están instalados"
    confirmar "¿Instalarlos desde los repositorios del sistema (docker.io y docker-compose-v2)?" || fallo "Sin Docker no se puede continuar"
    apt-get update -q
    apt-get install -y -q docker.io docker-compose-v2 || apt-get install -y -q docker.io docker-compose-plugin
    systemctl enable --now docker
fi
ok "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
# Las versiones anteriores daban DHCP/DNS con un contenedor aparte; ahora lo
# hace el backend
# (docker rm -f no falla si no existe: se mira antes)
if docker inspect lansentinel_dnsmasq >/dev/null 2>&1; then
    docker rm -f lansentinel_dnsmasq >/dev/null
    ok "Eliminado el contenedor de DHCP/DNS de una versión anterior"
fi

# ── 2. Interfaces ────────────────────────────────────────────────────────────

paso "Interfaces de red"
mapfile -t IFACES < <(interfaces_fisicas)
for i in "${IFACES[@]}"; do
    echo "    - $i  $(ip -4 -o addr show dev "$i" | awk '{print $4}' | paste -sd' ')"
done

# Modo: el pedido; si no, el que ya tenía esta instalación; si es nueva, solo vigilar
if [ -z "$ROUTER" ]; then
    if [ -f .env ] && [ "$(env_get ROUTER_MODE)" = true ]; then ROUTER=true; else ROUTER=false; fi
fi
if $ROUTER; then ok "Modo: router de la red"; else ok "Modo: solo vigilar (el modo router se puede encender después en el panel)"; fi

DEFAULT_WAN=$(ip route show default | awk '/default/ {print $5; exit}')
OTRA=$(printf '%s\n' "${IFACES[@]}" | grep -vx "$DEFAULT_WAN" | head -n1 || true)
if $ROUTER; then
    [ ${#IFACES[@]} -ge 2 ] || fallo "El modo router necesita dos interfaces de red (WAN y LAN). Con una sola, instala sin --router: LanSentinel vigilará la red."
fi
# Con dos interfaces (y la segunda con IP, o pidiendo el modo router), WAN y
# LAN: así el modo router queda listo para encenderlo desde el panel
if $ROUTER || { [ -n "$OTRA" ] && [ -n "$WAN$LAN" -o -n "$(ip -4 -o addr show dev "$OTRA" 2>/dev/null)" ]; }; then
    WAN="${WAN:-$(preguntar "Interfaz WAN (hacia el router de la operadora)" "$DEFAULT_WAN")}"
    DEFAULT_LAN=$(printf '%s\n' "${IFACES[@]}" | grep -vx "$WAN" | head -n1)
    LAN="${LAN:-$(preguntar "Interfaz LAN (la de tus dispositivos)" "$DEFAULT_LAN")}"
    [ "$WAN" != "$LAN" ] || fallo "La WAN y la LAN no pueden ser la misma interfaz"
    [ -e "/sys/class/net/$WAN" ] || fallo "No existe la interfaz $WAN"
else
    WAN=""
    LAN="${LAN:-$(preguntar "Interfaz a vigilar" "$DEFAULT_WAN")}"
fi
[ -e "/sys/class/net/$LAN" ] || fallo "No existe la interfaz $LAN"

LAN_CIDR=$(ip -4 -o addr show dev "$LAN" | awk '{print $4}' | head -n1)
LAN_IP=${LAN_CIDR%/*}

if $ROUTER; then
    # La LAN necesita una IP fija: es la puerta de enlace de toda la red.
    # No se configura aquí para no arriesgarse a cortar la conexión.
    if [ -z "$LAN_CIDR" ] || ip -4 -o addr show dev "$LAN" | grep -q dynamic; then
        cat >&2 <<EOF

  La interfaz $LAN necesita una IP fija (ahora: ${LAN_CIDR:-sin IP}${LAN_CIDR:+, asignada por DHCP}).
  Por ejemplo, con netplan, en /etc/netplan/60-lansentinel.yaml:

      network:
        version: 2
        ethernets:
          $LAN:
            dhcp4: false
            addresses: [192.168.50.1/24]

  Aplícala con 'sudo netplan try' (se deshace sola si pierdes la conexión)
  y vuelve a ejecutar este script.
EOF
        fallo "Falta la IP fija en la LAN"
    fi
    ok "WAN: $WAN · LAN: $LAN ($LAN_CIDR, IP fija)"
elif [ -n "$WAN" ]; then
    ok "Interfaz vigilada: $LAN (${LAN_CIDR:-sin IPv4}) · WAN para el modo router: $WAN"
    if [ -z "$LAN_CIDR" ] || ip -4 -o addr show dev "$LAN" | grep -q dynamic; then
        aviso "Para encender el modo router, $LAN necesitará una IP fija (será la puerta de enlace de la red)."
    fi
else
    ok "Interfaz vigilada: $LAN (${LAN_CIDR:-sin IPv4}) · una sola interfaz: sin modo router"
fi

# ── 3. ¿Hay otro servidor DHCP en la LAN? ────────────────────────────────────

# ¿Sirve ya DHCP el propio LanSentinel (reinstalación)? Entonces no es "otro"
dhcp_propio() {
    docker exec lansentinel_backend sh -c 'for c in /proc/[0-9]*/comm; do grep -qx dnsmasq "$c" 2>/dev/null && exit 0; done; exit 1' 2>/dev/null
}

if $ROUTER && $DHCP && ! dhcp_propio; then
    paso "Buscando otros servidores DHCP en la LAN"
    # Pide una IP sin aplicarla (-s /bin/true): si alguien responde, hay otro DHCP
    if OFERTA=$(timeout 20 docker run --rm --net host --cap-add NET_RAW --cap-add NET_ADMIN busybox:1.36 \
        udhcpc -i "$LAN" -n -q -t 3 -T 2 -s /bin/true 2>&1); then
        aviso "Ya hay un servidor DHCP en $LAN:"
        echo "$OFERTA" | grep -iE 'lease|offer' | sed 's/^/      /' || true
        aviso "Dos servidores DHCP en la misma red reparten direcciones distintas. Desactiva el del"
        aviso "router de la operadora (o ponlo en modo bridge) antes de usar LanSentinel como router."
        confirmar "¿Continuar de todos modos?" || fallo "Instalación cancelada"
    else
        ok "Ningún otro servidor DHCP responde"
    fi
fi

# ── 4. Reenvío y hora ────────────────────────────────────────────────────────

paso "Configurando el sistema"
# Una instalación anterior con IPv6 lo conserva aunque no se pase --ipv6
if [ -f .env ] && [ "$(env_get IPV6_LAN)" = "true" ]; then IPV6=true; fi
# Con WAN, el reenvío queda puesto para poder encender el modo router desde
# el panel (un contenedor no puede cambiarlo). Docker ya lo activa para sus
# redes y deja la política de FORWARD en DROP: sin el modo router, LanSentinel
# no enruta nada.
if [ -n "$WAN" ]; then
    {
        echo "# LanSentinel: reenvío de paquetes entre la WAN y la LAN (modo router)"
        echo "net.ipv4.ip_forward=1"
        if $IPV6; then
            echo "net.ipv6.conf.all.forwarding=1"
            # Con el reenvío activo, el kernel deja de atender los anuncios de
            # router de la WAN (y el equipo perdería su ruta IPv6) salvo con
            # accept_ra=2. Solo si es el kernel quien los atiende (valor 1):
            # con systemd-networkd o NetworkManager vale 0 y no hace falta.
            if [ "$(cat "/proc/sys/net/ipv6/conf/$WAN/accept_ra" 2>/dev/null)" = "1" ]; then
                echo "net.ipv6.conf.${WAN//./\/}.accept_ra=2"
            fi
        fi
    } > /etc/sysctl.d/90-lansentinel.conf
    sysctl -q -p /etc/sysctl.d/90-lansentinel.conf
    if $IPV6; then
        ok "Reenvío IPv4 e IPv6 activado (/etc/sysctl.d/90-lansentinel.conf)"
    else
        ok "Reenvío IPv4 activado (/etc/sysctl.d/90-lansentinel.conf)"
    fi
fi
if command -v timedatectl >/dev/null; then
    timedatectl set-ntp true 2>/dev/null || true
    ok "Hora sincronizada por NTP: $(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo desconocido)"
fi
if [ -f /etc/iptables/rules.v4 ] && grep -q MASQUERADE /etc/iptables/rules.v4 && $ROUTER; then
    aviso "/etc/iptables/rules.v4 tiene reglas de NAT propias: LanSentinel ya gestiona el NAT,"
    aviso "puedes quitarlas para no duplicarlas."
fi

# ── 5. Configuración (.env) ──────────────────────────────────────────────────

paso "Preparando .env"
if [ ! -f .env ]; then
    cp .env.example .env
    ok "Creado a partir de .env.example"
fi
chmod 600 .env

env_set MONITOR_INTERFACE "$LAN"
env_set ROUTER_MODE "$ROUTER"
env_set WAN_INTERFACE "$WAN"
env_set ROUTER_DHCP "$DHCP"
env_set IPV6_LAN "$IPV6"
if [ -n "$WAN" ] && [ -n "$LAN_IP" ]; then
    PREFIX=${LAN_IP%.*}
    [ -n "$(env_get DHCP_RANGE_START)" ] || env_set DHCP_RANGE_START "$PREFIX.100"
    [ -n "$(env_get DHCP_RANGE_END)" ] || env_set DHCP_RANGE_END "$PREFIX.199"
    [ -n "$(env_get DNS_UPSTREAM)" ] || env_set DNS_UPSTREAM "1.1.1.1,9.9.9.9"
fi
HTTPS_PORT=$(env_get PANEL_HTTPS_PORT); HTTPS_PORT=${HTTPS_PORT:-443}
HTTP_PORT=$(env_get PANEL_HTTP_PORT); HTTP_PORT=${HTTP_PORT:-80}
PANEL="https://${LAN_IP:-<ip-del-equipo>}$([ "$HTTPS_PORT" = 443 ] || echo ":$HTTPS_PORT")"
# El enlace de los avisos: se pone si falta o si es el de HTTP que ponían
# versiones anteriores del instalador
case "$(env_get PANEL_URL)" in
    ""|"http://$LAN_IP:3000") [ -z "$LAN_IP" ] || env_set PANEL_URL "$PANEL" ;;
esac

# Contraseña de la base de datos: solo en una instalación nueva. Con datos ya
# guardados no se toca, o el backend dejaría de poder entrar.
if [ "$(env_get POSTGRES_PASSWORD)" = "lansentinel_pass" ] && ! docker volume inspect "$(basename "$PWD" | tr '[:upper:]' '[:lower:]')_postgres_data" >/dev/null 2>&1; then
    env_set POSTGRES_PASSWORD "$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)"
    ok "Contraseña de la base de datos generada"
fi
ok "MONITOR_INTERFACE=$LAN · ROUTER_MODE=$ROUTER${WAN:+ · WAN_INTERFACE=$WAN}"

# ── 6. Arranque ──────────────────────────────────────────────────────────────

# El nginx del panel escucha en la red del equipo: necesita los puertos HTTPS
# y HTTP, y el 3000 (redirección para quien tenga guardada la dirección de
# versiones anteriores). Los procesos del propio LanSentinel, si ya estaba en
# marcha, no cuentan (docker-proxy: versiones que publicaban el puerto).
[ "$HTTP_PORT" != 3000 ] || fallo "PANEL_HTTP_PORT no puede ser 3000: ese puerto ya redirige siempre a HTTPS."
PROPIOS=" $(docker top lansentinel_frontend -eo pid 2>/dev/null | tail -n +2 | tr '\n' ' ' || true) "
for port in "$HTTPS_PORT" "$HTTP_PORT" 3000; do
    while read -r nombre pid; do
        case "$PROPIOS" in *" $pid "*) continue ;; esac
        [ "$nombre" = docker-proxy ] && continue
        fallo "El puerto $port lo usa '$nombre'. Libéralo o elige otro en .env (PANEL_HTTPS_PORT / PANEL_HTTP_PORT)."
    done < <(ss -ltnpH "sport = :$port" 2>/dev/null | grep -o '"[^"]*",pid=[0-9]*' | sed 's/"\([^"]*\)",pid=/\1 /' || true)
done

# Si ya estaba instalado, copia de seguridad antes de actualizar (las
# versiones anteriores a la 1.8 no saben hacerla: se avisa y se sigue)
if [ "$(docker inspect -f '{{.State.Running}}' lansentinel_backend 2>/dev/null)" = true ]; then
    paso "Copia de seguridad antes de actualizar"
    if COPIA=$(docker exec lansentinel_backend python -m app.services.backup crear --motivo actualizacion 2>&1); then
        ok "$COPIA"
    else
        aviso "No se pudo hacer: $(echo "$COPIA" | tail -1)"
    fi
fi

paso "Arrancando LanSentinel (la primera vez tarda unos minutos)"
docker compose --profile production up -d --build

for _ in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_backend 2>/dev/null)" = healthy ] && break
    sleep 3
done
[ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_backend 2>/dev/null)" = healthy ] \
    || fallo "El backend no arranca: revisa 'docker logs lansentinel_backend'"
ok "Backend en marcha"

# ── Resumen ──────────────────────────────────────────────────────────────────

paso "Listo"
echo "  Panel:               $PANEL (usuario admin)"
if $ROUTER && $DHCP; then
    DOMAIN=$(env_get LOCAL_DOMAIN); echo "                       también https://lansentinel.${DOMAIN:-lan} desde la red"
fi
CA=/var/lib/lansentinel/tls/ca.crt
for _ in $(seq 1 10); do [ -s "$CA" ] && break; sleep 1; done
if [ -s "$CA" ] && command -v openssl >/dev/null; then
    echo "  Certificado:         el navegador avisará hasta que importes la CA de LanSentinel"
    echo "                       (Ajustes → Conexión segura). Comprueba que su huella es:"
    echo "                       $(openssl x509 -in "$CA" -noout -fingerprint -sha256 | cut -d= -f2)"
fi
if [ -f /var/lib/lansentinel/initial_admin_password ]; then
    echo "  Contraseña inicial:  sudo cat /var/lib/lansentinel/initial_admin_password"
fi
if $ROUTER; then
    echo "  Puerta de enlace:    $LAN_IP (los dispositivos salen a Internet por $WAN)"
elif [ -n "$WAN" ]; then
    echo "  Modo:                solo vigilar. Para que LanSentinel sea el router de la red"
    echo "                       (ve y protege todo el tráfico): Ajustes → Modo router"
else
    echo "  Modo:                solo vigilar (con una sola interfaz no puede hacer de router)"
fi
if $ROUTER && $DHCP; then
    echo "  DHCP:                $(env_get DHCP_RANGE_START) - $(env_get DHCP_RANGE_END), DNS en $LAN_IP"
    echo "  Encender/apagar:     Ajustes → Modo router, en el panel"
    echo
    echo "  Siguientes pasos:"
    echo "    1. Desactiva el DHCP del router de la operadora (o ponlo en modo bridge)."
    echo "    2. Conecta el punto de acceso Wi-Fi a la LAN en modo AP (sin router ni DHCP)."
    echo "    3. Reconecta los dispositivos para que pidan IP a LanSentinel."
fi
