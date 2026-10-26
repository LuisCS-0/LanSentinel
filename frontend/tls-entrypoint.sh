#!/bin/sh
# Certificado HTTPS del panel. Lo genera el backend en /var/lib/lansentinel/tls
# (montado en /run/lansentinel-tls), pero puede no estar aún cuando arranca
# nginx: mientras tanto se sirve uno provisional, y en cuanto aparece el
# bueno (o cambia, p. ej. al renovarse o cambiar la IP) se copia y se recarga
# nginx sin cortar conexiones.
set -eu
SRC=/run/lansentinel-tls
DST=/etc/nginx/tls
mkdir -p "$DST"

copy_if_changed() {
    [ -s "$SRC/server.crt" ] && [ -s "$SRC/server.key" ] || return 1
    if ! cmp -s "$SRC/server.crt" "$DST/server.crt" 2>/dev/null; then
        cp "$SRC/server.key" "$DST/server.key.new" && cp "$SRC/server.crt" "$DST/server.crt.new"
        chmod 600 "$DST/server.key.new"
        mv "$DST/server.key.new" "$DST/server.key" && mv "$DST/server.crt.new" "$DST/server.crt"
        return 0
    fi
    return 1
}

if ! copy_if_changed && [ ! -s "$DST/server.crt" ]; then
    echo "lansentinel-tls: aún no hay certificado del backend; se usa uno provisional"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 2 \
        -subj "/O=LanSentinel/CN=LanSentinel (provisional)" \
        -keyout "$DST/server.key" -out "$DST/server.crt" 2>/dev/null
fi

# Vigilancia en segundo plano
(
    while sleep 30; do
        if copy_if_changed; then
            echo "lansentinel-tls: certificado nuevo, recargando nginx"
            nginx -s reload || true
        fi
    done
) &
