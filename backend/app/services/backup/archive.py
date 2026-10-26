"""
Copias de seguridad: crear, listar y rotar.

Cada copia es un único lansentinel-<fecha>-<hora>-<motivo>.tar.gz con:

- lansentinel.dump   la base de datos completa (pg_dump, formato custom)
- estado/            /var/lib/lansentinel: clave de sesión, CA y certificado
                     del panel, configuración de dnsmasq... (sin las copias
                     ni la lista OUI, que se vuelve a descargar)
- env                el .env del proyecto (contraseñas de la BD y de los avisos)
- manifiesto.json    versión, fecha, motivo y contenido

El volcado se hace con pg_dump 16, la misma versión que la base de datos:
el pg_dump de Debian 13 es el 17, y su formato no lo entiende el pg_restore
del contenedor de la base de datos, que es con el que restaura
scripts/restaurar.sh. Tras volcar se comprueba que pg_restore puede leerlo.

Las copias contienen secretos (contraseñas cifradas, clave de la CA, .env):
solo root puede leerlas (0600). Este módulo no usa asyncio para que el
mismo código sirva al backend (en un hilo) y a la línea de órdenes
(python -m app.services.backup, que usa el instalador antes de actualizar).
Un cerrojo de fichero impide dos copias a la vez desde ambos sitios.
"""

import fcntl
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.engine import make_url

from app.core.config import VERSION, settings

BACKUP_DIR = Path("/var/lib/lansentinel/backups")
STATE_DIR = Path("/var/lib/lansentinel")
STATUS_FILE = BACKUP_DIR / ".estado.json"
LOCK_FILE = BACKUP_DIR / ".lock"

PG_BIN = Path("/usr/lib/postgresql/16/bin")

# Lo que no se copia de /var/lib/lansentinel: las propias copias y la lista
# de fabricantes (unos MB que se vuelven a descargar solos)
EXCLUDED_STATE = {"backups", "oui.csv"}

MOTIVOS = ("inicial", "diaria", "manual", "actualizacion", "restauracion")
NAME_RE = re.compile(r"^lansentinel-(\d{8})-(\d{6})-([a-z]+)\.tar\.gz$")


class BackupError(Exception):
    """La copia no se ha podido hacer (el mensaje se muestra en el panel)."""


class BackupBusy(BackupError):
    pass


@dataclass(frozen=True)
class BackupFile:
    name: str
    created_at: datetime        # UTC
    motivo: str
    size: int


# ── Funciones puras ──────────────────────────────────────────────────────────

def backup_name(created_at: datetime, motivo: str) -> str:
    """Nombre con la fecha en hora local, que es la que ve el usuario."""
    local = created_at.astimezone(ZoneInfo(settings.TIMEZONE))
    return f"lansentinel-{local:%Y%m%d-%H%M%S}-{motivo}.tar.gz"


def parse_name(name: str) -> tuple[datetime, str] | None:
    m = NAME_RE.match(name)
    if not m:
        return None
    local = datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo(settings.TIMEZONE))
    return local.astimezone(timezone.utc), m[3]


def select_to_delete(backups: list[BackupFile], keep_daily: int, keep_weekly: int) -> list[BackupFile]:
    """
    Rotación: se conservan las keep_daily copias más recientes y, de las
    anteriores, la más reciente de cada semana hasta sumar keep_weekly
    semanas que no estuvieran ya cubiertas.
    """
    ordered = sorted(backups, key=lambda b: b.created_at, reverse=True)
    keep = ordered[:max(keep_daily, 1)]
    weeks = {b.created_at.isocalendar()[:2] for b in keep}
    extra_weeks = 0
    delete = []
    for b in ordered[len(keep):]:
        week = b.created_at.isocalendar()[:2]
        if week not in weeks and extra_weeks < keep_weekly:
            weeks.add(week)
            extra_weeks += 1
        else:
            delete.append(b)
    return delete


def is_due(now_local: datetime, hour: int, backups: list[BackupFile]) -> str | None:
    """
    Motivo de la copia automática que toca ahora, o None. "inicial" si no hay
    ninguna copia; "diaria" si ya ha pasado la hora y hoy no se ha hecho una
    automática (si el equipo estaba apagado a esa hora, se hace al volver).
    """
    if hour < 0:
        return None
    if not backups:
        return "inicial"
    if now_local.hour < hour:
        return None
    today = now_local.date()
    tz = now_local.tzinfo
    done_today = any(
        b.motivo in ("inicial", "diaria") and b.created_at.astimezone(tz).date() == today for b in backups
    )
    return None if done_today else "diaria"


# ── Sistema ──────────────────────────────────────────────────────────────────

def list_backups() -> list[BackupFile]:
    result = []
    try:
        entries = list(BACKUP_DIR.iterdir())
    except OSError:
        return []
    for path in entries:
        parsed = parse_name(path.name)
        if parsed and path.is_file():
            result.append(BackupFile(path.name, parsed[0], parsed[1], path.stat().st_size))
    return sorted(result, key=lambda b: b.created_at, reverse=True)


def read_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _write_status(**changes) -> None:
    status = read_status() | changes
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(status))
    tmp.replace(STATUS_FILE)


def _pg_tool(name: str) -> str:
    path = PG_BIN / name
    return str(path) if path.exists() else name


def _dump_database(target: Path) -> None:
    url = make_url(settings.DATABASE_URL)
    env = os.environ | {"PGPASSWORD": url.password or ""}
    cmd = [
        _pg_tool("pg_dump"), "--format=custom", "--no-owner",
        "--host", url.host or "localhost", "--port", str(url.port or 5432),
        "--username", url.username or "", "--dbname", url.database or "", "--file", str(target),
    ]
    run = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if run.returncode != 0:
        raise BackupError(f"pg_dump falló: {run.stderr.strip()[-300:] or run.returncode}")
    # Comprobación: que el volcado se pueda leer (cabecera e índice completos)
    check = subprocess.run([_pg_tool("pg_restore"), "--list", str(target)], capture_output=True, text=True, timeout=120)
    if check.returncode != 0:
        raise BackupError(f"El volcado no se puede leer: {check.stderr.strip()[-300:]}")


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = 0o600
    info.mtime = int(datetime.now().timestamp())
    tar.addfile(info, io.BytesIO(data))


def _state_files() -> list[Path]:
    files = []
    for root, dirs, names in os.walk(STATE_DIR):
        rel_root = Path(root).relative_to(STATE_DIR)
        if rel_root == Path("."):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_STATE]
        for n in names:
            path = Path(root) / n
            if rel_root == Path(".") and n in EXCLUDED_STATE:
                continue
            if n.endswith(".tmp") or not path.is_file():
                continue
            files.append(path)
    return sorted(files)


def create_backup(motivo: str) -> BackupFile:
    """Hace una copia completa y rota las antiguas. Lanza BackupError si falla."""
    if motivo not in MOTIVOS:
        raise BackupError(f"Motivo desconocido: {motivo}")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUP_DIR, 0o700)
    lock = open(LOCK_FILE, "w")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupBusy("Ya se está haciendo una copia")
        now = datetime.now(timezone.utc)
        _write_status(last_attempt_at=now.isoformat())
        try:
            backup = _create_locked(motivo, now)
        except BackupError as exc:
            _write_status(last_error=str(exc), last_error_at=now.isoformat())
            raise
        except Exception as exc:     # cualquier otro fallo se informa igual
            _write_status(last_error=str(exc), last_error_at=now.isoformat())
            raise BackupError(str(exc)) from exc
        _write_status(last_error=None, last_success_at=now.isoformat())
        return backup
    finally:
        lock.close()


def is_running() -> bool:
    """Si hay una copia en marcha (del backend o de la línea de órdenes)."""
    try:
        with open(LOCK_FILE, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
    except BlockingIOError:
        return True
    except OSError:
        return False


def _create_locked(motivo: str, now: datetime) -> BackupFile:
    # Dos copias en el mismo segundo (p. ej. el botón del panel justo después
    # de otra) tendrían el mismo nombre: se avanza un segundo para no pisarla
    while (BACKUP_DIR / backup_name(now, motivo)).exists():
        now += timedelta(seconds=1)
    name = backup_name(now, motivo)
    final = BACKUP_DIR / name
    with tempfile.TemporaryDirectory(dir=BACKUP_DIR, prefix=".tmp-") as tmp:
        dump = Path(tmp) / "lansentinel.dump"
        _dump_database(dump)

        state = _state_files()
        env_path = Path(settings.PROJECT_DIR) / ".env"
        env_data = env_path.read_bytes() if env_path.is_file() else None
        manifest = {
            "version": VERSION,
            "created_at": now.isoformat(),
            "motivo": motivo,
            "hostname": socket.gethostname(),
            "database_bytes": dump.stat().st_size,
            "state_files": [str(p.relative_to(STATE_DIR)) for p in state],
            "env": env_data is not None,
        }

        partial = Path(tmp) / name
        with tarfile.open(partial, "w:gz") as tar:
            _add_bytes(tar, "manifiesto.json", json.dumps(manifest, indent=2).encode())
            tar.add(dump, arcname="lansentinel.dump")
            for path in state:
                tar.add(path, arcname=f"estado/{path.relative_to(STATE_DIR)}")
            if env_data is not None:
                _add_bytes(tar, "env", env_data)
        os.chmod(partial, 0o600)
        shutil.move(partial, final)

    backup = BackupFile(name, now, motivo, final.stat().st_size)
    rotate()
    return backup


def rotate() -> list[str]:
    deleted = []
    for b in select_to_delete(list_backups(), settings.BACKUP_KEEP_DAILY, settings.BACKUP_KEEP_WEEKLY):
        try:
            (BACKUP_DIR / b.name).unlink()
            deleted.append(b.name)
        except OSError:
            pass
    return deleted


def backup_path(name: str) -> Path | None:
    """Ruta de una copia por su nombre, solo si es un nombre válido y existe."""
    if not NAME_RE.match(name):
        return None
    path = BACKUP_DIR / name
    return path if path.is_file() else None
