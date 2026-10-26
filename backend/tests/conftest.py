"""
Configuración común de los tests.

Solo se prueba lógica pura o con ficheros temporales: nada de iptables, base
de datos ni red reales. Las variables de entorno se fijan antes de importar
la aplicación, para que la configuración no dependa del equipo.
"""

import os

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-" + "0123456789abcdef" * 4)
os.environ.setdefault("SECRET_KEY_PATH", "/tmp/lansentinel-tests/secret_key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://prueba:prueba@localhost:5432/prueba")
os.environ.setdefault("TIMEZONE", "Europe/Madrid")
os.environ.setdefault("LOG_LEVEL", "error")
