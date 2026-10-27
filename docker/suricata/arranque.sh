#!/bin/bash
# Arranque del contenedor de Suricata (sustituye al entrypoint de la imagen y
# luego le cede el control):
#   1. Si aún no hay reglas de Emerging Threats, las descarga antes de arrancar.
#   2. En segundo plano, las actualiza cada RULES_UPDATE_HOURS horas (24 por
#      defecto; 0 lo desactiva) y recarga Suricata sin reiniciarlo.
#   3. En segundo plano, rota los registros (eve.json, fast.log, stats.log)
#      cuando pasan de LOG_MAX_MB megas: el actual pasa a .1 (se pierde el .1
#      anterior) y SIGHUP hace que Suricata los reabra. El backend termina de
#      leer el .1 antes de seguir con el nuevo.
#   4. Arranca Suricata con el entrypoint original de la imagen.

if [ ! -s /var/lib/suricata/rules/suricata.rules ]; then
    /usr/local/bin/actualizar-reglas.sh --inicial
fi

HOURS="${RULES_UPDATE_HOURS:-24}"
if [ "$HOURS" -gt 0 ] 2>/dev/null; then
    (
        while sleep $((HOURS * 3600)); do
            /usr/local/bin/actualizar-reglas.sh
        done
    ) &
fi

LOG_DIR=/var/log/suricata
MAX_BYTES=$(( ${LOG_MAX_MB:-100} * 1024 * 1024 ))
(
    while sleep 600; do
        rotated=0
        for f in eve.json fast.log stats.log; do
            size=$(stat -c %s "$LOG_DIR/$f" 2>/dev/null || echo 0)
            if [ "$size" -gt "$MAX_BYTES" ]; then
                mv -f "$LOG_DIR/$f" "$LOG_DIR/$f.1"
                rotated=1
            fi
        done
        # Suricata es el PID 1 del contenedor (el entrypoint le cede el control)
        [ "$rotated" = 1 ] && kill -HUP 1
    done
) &

exec /docker-entrypoint.sh "$@"
