#!/bin/bash
# Arranque del contenedor de Suricata (sustituye al entrypoint de la imagen y
# luego le cede el control):
#   1. Si aún no hay reglas de Emerging Threats, las descarga antes de arrancar.
#   2. En segundo plano, las actualiza cada RULES_UPDATE_HOURS horas (24 por
#      defecto; 0 lo desactiva) y recarga Suricata sin reiniciarlo.
#   3. Arranca Suricata con el entrypoint original de la imagen.

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

exec /docker-entrypoint.sh "$@"
