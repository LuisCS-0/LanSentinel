#!/usr/bin/env bash
# Ejecuta los tests del backend dentro de su imagen de Docker (mismas
# versiones de Python y librerías que en producción), con pytest encima.
#
# Uso (desde la carpeta del proyecto):
#   scripts/tests.sh                 # todos
#   scripts/tests.sh -k copias -v    # los argumentos van a pytest
#
# No necesita root ni toca la red ni el cortafuegos del equipo: solo prueba
# lógica pura y ficheros temporales.

set -euo pipefail
cd "$(dirname "$0")/.."

docker build -q -t lansentinel-backend:tests backend >/dev/null
docker build -q -t lansentinel-backend:pytest -f - backend >/dev/null <<'DOCKERFILE'
FROM lansentinel-backend:tests
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
DOCKERFILE

# El código se monta en solo lectura: los tests no escriben en el repositorio
exec docker run --rm -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/backend:/app:ro" -w /app \
    lansentinel-backend:pytest python -m pytest "$@"
