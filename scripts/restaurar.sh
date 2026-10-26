#!/usr/bin/env bash
# Restaura una copia de seguridad de LanSentinel: la base de datos completa y
# /var/lib/lansentinel (clave de sesión, CA y certificado del panel, dnsmasq).
#
# Uso (desde la carpeta del proyecto):
#   sudo scripts/restaurar.sh lansentinel-20261026-030000-diaria.tar.gz
#   sudo scripts/restaurar.sh /ruta/a/la/copia.tar.gz --si
#
# Con solo el nombre, la busca en la carpeta de las copias (BACKUP_PATH de
# .env, por defecto /var/lib/lansentinel/backups).
#
# Antes de tocar nada hace una copia del estado actual ("Antes de restaurar"),
# para poder deshacerlo. Para el panel mientras restaura y lo vuelve a
# arrancar al terminar, también si algo falla. La base de datos se restaura
# en una sola transacción: si falla, queda como estaba.
#
# El .env no se sustituye (en un equipo nuevo las interfaces y la contraseña
# de la base de datos son otras): el de la copia queda en .env.copia y se
# listan las variables que difieren.
#
# En un equipo nuevo: instala con scripts/instalar.sh y luego restaura.
#
# Opciones:
#   --si    no preguntar

set -euo pipefail

ASSUME_YES=false
ARCHIVE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --si) ASSUME_YES=true; shift ;;
        -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) echo "Opción desconocida: $1 (usa --help)" >&2; exit 2 ;;
        *) ARCHIVE="$1"; shift ;;
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

env_get() {
    [ -f .env ] || return 0
    grep -E "^${1}=" .env | tail -n1 | cut -d= -f2- | sed 's/ *#.*//' || true
}

# ── Comprobaciones ───────────────────────────────────────────────────────────

[ "$(id -u)" -eq 0 ] || fallo "Hay que ejecutarlo como root: sudo scripts/restaurar.sh <copia>"
cd "$(dirname "$0")/.."
[ -f docker-compose.yml ] || fallo "No encuentro docker-compose.yml: ejecútalo desde la carpeta de LanSentinel"
[ -n "$ARCHIVE" ] || fallo "Indica la copia a restaurar (usa --help)"

BACKUP_DIR=$(env_get BACKUP_PATH); BACKUP_DIR=${BACKUP_DIR:-/var/lib/lansentinel/backups}
if [ ! -f "$ARCHIVE" ] && [ -f "$BACKUP_DIR/$ARCHIVE" ]; then
    ARCHIVE="$BACKUP_DIR/$ARCHIVE"
fi
[ -f "$ARCHIVE" ] || fallo "No existe la copia: $ARCHIVE"

DB_USER=$(env_get POSTGRES_USER); DB_USER=${DB_USER:-lansentinel}
DB_NAME=$(env_get POSTGRES_DB); DB_NAME=${DB_NAME:-lansentinel}

# ── 1. Leer la copia ─────────────────────────────────────────────────────────
# Se extrae antes de hacer la copia previa: la rotación de esa copia nueva
# podría borrar la que se va a restaurar si es de las antiguas.

paso "Leyendo la copia"
TMP=$(mktemp -d /tmp/lansentinel-restaurar.XXXXXX)
chmod 700 "$TMP"
PARADO=false
limpiar() {
    rm -rf "$TMP"
    if $PARADO; then
        aviso "Volviendo a arrancar el panel"
        docker compose up -d backend frontend >/dev/null 2>&1 || true
    fi
}
trap limpiar EXIT

tar -xzf "$ARCHIVE" -C "$TMP" || fallo "La copia está dañada o no es un .tar.gz"
[ -f "$TMP/manifiesto.json" ] && [ -f "$TMP/lansentinel.dump" ] || fallo "No es una copia de LanSentinel (falta el manifiesto o la base de datos)"
python3 - "$TMP/manifiesto.json" <<'EOF' || true
import json, sys
m = json.load(open(sys.argv[1]))
print(f"  Versión {m.get('version')} · {m.get('created_at', '')[:19].replace('T', ' ')} UTC · "
      f"motivo {m.get('motivo')} · equipo {m.get('hostname')}")
EOF
ok "$(basename "$ARCHIVE") ($(du -h "$ARCHIVE" | cut -f1))"

echo
echo "  Se sustituirán la base de datos (dispositivos, alertas, reglas, histórico,"
echo "  usuarios y ajustes) y los ficheros de /var/lib/lansentinel por los de la copia."
confirmar "¿Restaurar?" || { echo "  Cancelado."; exit 0; }

# ── 2. Copia del estado actual ───────────────────────────────────────────────

paso "Copia del estado actual (para poder deshacerlo)"
if [ "$(docker inspect -f '{{.State.Running}}' lansentinel_backend 2>/dev/null)" = true ]; then
    if PREVIA=$(docker exec lansentinel_backend python -m app.services.backup crear --motivo restauracion 2>&1); then
        ok "$PREVIA"
    else
        aviso "No se pudo: $PREVIA"
        PREVIA=""
        confirmar "¿Seguir sin copia del estado actual?" || fallo "Cancelado"
    fi
else
    aviso "El backend no está en marcha: no se puede hacer la copia previa"
    confirmar "¿Seguir sin copia del estado actual?" || fallo "Cancelado"
fi

# ── 3. Parar el panel ────────────────────────────────────────────────────────

paso "Parando el panel"
PARADO=true
docker compose stop backend frontend >/dev/null
docker compose up -d db >/dev/null
for _ in $(seq 1 30); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_db 2>/dev/null)" = healthy ] && break
    sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_db 2>/dev/null)" = healthy ] || fallo "La base de datos no arranca"
ok "Backend y panel parados; base de datos en marcha"

# ── 4. Base de datos ─────────────────────────────────────────────────────────
# Con el pg_restore del propio contenedor de la base de datos (misma versión),
# en una sola transacción: si algo falla, no se cambia nada.

paso "Restaurando la base de datos"
if ! ERR=$(docker exec -i lansentinel_db pg_restore --username "$DB_USER" --dbname "$DB_NAME" \
        --clean --if-exists --no-owner --single-transaction --exit-on-error < "$TMP/lansentinel.dump" 2>&1); then
    fallo "No se pudo restaurar (la base de datos queda como estaba): $(echo "$ERR" | tail -3)"
fi
ok "Base de datos restaurada"

# ── 5. Ficheros de estado ────────────────────────────────────────────────────

paso "Restaurando /var/lib/lansentinel"
if [ -d "$TMP/estado" ]; then
    mkdir -p /var/lib/lansentinel
    cp -a "$TMP/estado/." /var/lib/lansentinel/
    ok "$(find "$TMP/estado" -type f | wc -l) ficheros (clave de sesión, CA y certificado, dnsmasq...)"
else
    aviso "La copia no trae ficheros de estado"
fi

# ── 6. .env ──────────────────────────────────────────────────────────────────

if [ -f "$TMP/env" ]; then
    if [ -f .env ]; then
        install -m 600 "$TMP/env" .env.copia
        DIFF=$(python3 - .env .env.copia <<'EOF'
import sys
def read(p):
    out = {}
    for line in open(p):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out
a, b = read(sys.argv[1]), read(sys.argv[2])
print(" ".join(sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))))
EOF
) || DIFF="(no se pudieron comparar: revisa .env.copia a mano)"
        if [ -n "$DIFF" ]; then
            aviso "El .env de la copia está en .env.copia. Variables distintas: $DIFF"
            aviso "Revisa si quieres pasar alguna (p. ej. las de los avisos) y reinicia el backend."
        else
            ok ".env igual al de la copia"
            rm -f .env.copia
        fi
    else
        install -m 600 "$TMP/env" .env
        ok "No había .env: se usa el de la copia"
    fi
fi

# ── 7. Arrancar ──────────────────────────────────────────────────────────────

paso "Arrancando LanSentinel"
docker compose up -d backend frontend >/dev/null
PARADO=false
for _ in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_backend 2>/dev/null)" = healthy ] && break
    sleep 3
done
[ "$(docker inspect -f '{{.State.Health.Status}}' lansentinel_backend 2>/dev/null)" = healthy ] \
    || fallo "El backend no arranca: revisa 'docker logs lansentinel_backend'"
ok "Backend en marcha"

paso "Listo"
echo "  Restaurada: $(basename "$ARCHIVE")"
[ -n "${PREVIA:-}" ] && echo "  Para deshacerlo: sudo scripts/restaurar.sh $PREVIA"
echo "  Las sesiones abiertas en el panel pueden pedir volver a entrar."
