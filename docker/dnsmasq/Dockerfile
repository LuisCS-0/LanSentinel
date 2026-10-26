# DHCP y DNS de la LAN en modo router (perfil "router" del docker-compose).
# La configuración se genera al arrancar a partir de las variables de .env.
FROM alpine:3.20
RUN apk add --no-cache dnsmasq iproute2
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
