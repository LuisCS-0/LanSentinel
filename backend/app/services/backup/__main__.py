"""
Copia de seguridad desde la línea de órdenes (la usan el instalador antes de
actualizar y scripts/restaurar.sh antes de restaurar):

    docker exec lansentinel_backend python -m app.services.backup crear --motivo actualizacion

Imprime el nombre de la copia; si falla, el motivo por stderr y sale con 1.
"""

import argparse
import sys

from app.services.backup.archive import MOTIVOS, BackupError, create_backup


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.services.backup")
    sub = parser.add_subparsers(dest="orden", required=True)
    crear = sub.add_parser("crear", help="hace una copia ahora")
    crear.add_argument("--motivo", choices=MOTIVOS, default="manual")
    args = parser.parse_args()

    try:
        backup = create_backup(args.motivo)
    except BackupError as exc:
        print(f"No se pudo hacer la copia: {exc}", file=sys.stderr)
        return 1
    print(backup.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
