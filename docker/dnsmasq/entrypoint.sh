#!/bin/sh
# Genera /etc/dnsmasq.conf para la LAN y arranca dnsmasq en primer plano.
#
# Variables (de .env):
#   MONITOR_INTERFACE   interfaz de la LAN (obligatoria)
#   DHCP_RANGE_START    primera IP que se reparte (por defecto .100 de la LAN)
#   DHCP_RANGE_END      última IP (por defecto .199)
#   DHCP_LEASE_TIME     duración de la concesión (por defecto 12h)
#   DNS_UPSTREAM        servidores DNS a los que se reenvían las consultas,
#                       separados por comas (por defecto 1.1.1.1,9.9.9.9)
#   LOCAL_DOMAIN        dominio local: los equipos responden como nombre.lan
set -eu

IFACE="${MONITOR_INTERFACE:?Falta MONITOR_INTERFACE (interfaz de la LAN)}"

# La IP fija de LanSentinel en la LAN: puerta de enlace y DNS de la red.
# Se espera unos segundos por si la interfaz aún no tiene IP al arrancar.
LAN_IP=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
    LAN_IP=$(ip -4 -o addr show dev "$IFACE" | awk '{print $4}' | cut -d/ -f1 | head -n1)
    [ -n "$LAN_IP" ] && break
    sleep 2
done
if [ -z "$LAN_IP" ]; then
    echo "dnsmasq: la interfaz $IFACE no tiene IPv4; no se puede servir DHCP" >&2
    exit 1
fi

PREFIX=${LAN_IP%.*}
START="${DHCP_RANGE_START:-$PREFIX.100}"
END="${DHCP_RANGE_END:-$PREFIX.199}"
LEASE="${DHCP_LEASE_TIME:-12h}"
DOMAIN="${LOCAL_DOMAIN:-lan}"
UPSTREAM="${DNS_UPSTREAM:-1.1.1.1,9.9.9.9}"

{
    echo "# Generado por entrypoint.sh: no editar a mano"
    echo "keep-in-foreground"
    echo "log-facility=-"
    echo "user=root"
    # Solo en la LAN: no responde en la WAN ni choca con el resolvedor del
    # sistema (systemd-resolved escucha en 127.0.0.53)
    echo "interface=$IFACE"
    echo "except-interface=lo"
    echo "bind-interfaces"
    # DNS: reenvía a los servidores indicados, no a los del sistema
    echo "no-resolv"
    echo "$UPSTREAM" | tr ',' '\n' | sed '/^ *$/d; s/^ *//; s/^/server=/'
    echo "domain-needed"
    echo "bogus-priv"
    echo "cache-size=1000"
    echo "domain=$DOMAIN"
    echo "local=/$DOMAIN/"
    echo "expand-hosts"
    # DHCP: LanSentinel es la puerta de enlace y el DNS de la red
    echo "dhcp-range=$START,$END,$LEASE"
    echo "dhcp-option=option:router,$LAN_IP"
    echo "dhcp-option=option:dns-server,$LAN_IP"
    echo "dhcp-authoritative"
    echo "dhcp-leasefile=/var/lib/lansentinel/dnsmasq.leases"
} > /etc/dnsmasq.conf

echo "dnsmasq: LAN $IFACE ($LAN_IP), DHCP $START-$END ($LEASE), DNS hacia $UPSTREAM"
exec dnsmasq --conf-file=/etc/dnsmasq.conf
