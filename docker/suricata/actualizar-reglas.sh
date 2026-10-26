#!/bin/bash
# Descarga y actualiza las reglas de Emerging Threats (ET Open) con
# suricata-update, y deja un estado que el backend muestra en el panel.
#
#   actualizar-reglas.sh            descarga y recarga Suricata si está en marcha
#   actualizar-reglas.sh --inicial  solo descarga (Suricata aún no ha arrancado)
#
# Las reglas quedan en /var/lib/suricata/rules/suricata.rules, junto con su
# classification.config. Las categorías que no se quieren están en
# /etc/lansentinel/disable.conf. Las reglas propias de LanSentinel van en otro
# fichero (/etc/suricata/rules/lansentinel.rules) y no dependen de esto.

set -u

RULES_DIR=/var/lib/suricata/rules
STATUS=/var/lib/suricata/lansentinel-estado.json
INICIAL=false
[ "${1:-}" = "--inicial" ] && INICIAL=true

ahora() { date -u +%Y-%m-%dT%H:%M:%SZ; }

estado() {  # estado <ok:true|false> <mensaje>
    local rules=0
    [ -f "$RULES_DIR/suricata.rules" ] && rules=$(grep -cE '^(alert|drop|reject|pass)' "$RULES_DIR/suricata.rules" || true)
    local success
    success=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('last_success_at') or '')" "$STATUS" 2>/dev/null || true)
    [ "$1" = true ] && success=$(ahora)
    python3 - "$STATUS" "$1" "$2" "$rules" "$success" "$(ahora)" <<'EOF'
import json, sys
path, ok, msg, rules, success, attempt = sys.argv[1:]
json.dump({
    "last_attempt_at": attempt,
    "last_success_at": success or None,
    "error": None if ok == "true" else msg,
    "rules": int(rules),
}, open(path + ".tmp", "w"))
EOF
    mv "$STATUS.tmp" "$STATUS"
}

mkdir -p "$RULES_DIR"
echo "lansentinel: actualizando las reglas de Emerging Threats"
if OUT=$(timeout 600 suricata-update --suricata-conf /etc/suricata/suricata.yaml \
        --disable-conf /etc/lansentinel/disable.conf --no-test --no-reload 2>&1); then
    estado true ""
    echo "lansentinel: reglas actualizadas"
else
    MSG=$(echo "$OUT" | grep -iE "error|fail" | tail -1)
    estado false "${MSG:-suricata-update falló}"
    echo "lansentinel: no se pudieron actualizar las reglas: ${MSG:-?}" >&2
fi

# Sin descarga posible la primera vez, Suricata arranca solo con las reglas
# propias: el fichero tiene que existir, y la clasificación también
[ -f "$RULES_DIR/suricata.rules" ] || : > "$RULES_DIR/suricata.rules"
[ -f "$RULES_DIR/classification.config" ] || cp /usr/share/suricata/classification.config "$RULES_DIR/"

if ! $INICIAL; then
    # Recarga sin reiniciar (si las reglas nuevas fallan, Suricata sigue con las anteriores)
    suricatasc -c reload-rules >/dev/null 2>&1 || kill -USR2 1 2>/dev/null || true
fi
