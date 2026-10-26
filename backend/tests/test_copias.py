"""Copias de seguridad: nombres, rotación, programación y creación (con un volcado simulado)."""

import json
import tarfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.config import settings
from app.services.backup import archive as a

TZ = ZoneInfo("Europe/Madrid")


def _b(dt: datetime, motivo: str = "diaria") -> a.BackupFile:
    return a.BackupFile(a.backup_name(dt, motivo), dt.astimezone(timezone.utc), motivo, 1)


# ── Funciones puras ──────────────────────────────────────────────────────────

def test_nombre_en_hora_local_y_vuelta():
    t = datetime(2026, 10, 26, 2, 30, 5, tzinfo=timezone.utc)
    name = a.backup_name(t, "diaria")
    assert name == "lansentinel-20261026-033005-diaria.tar.gz"         # +1 h en Madrid (invierno)
    assert a.parse_name(name) == (t, "diaria")


@pytest.mark.parametrize("name", [
    "../secret_key", "lansentinel-20261026-033005-Diaria.tar.gz", "lansentinel-2026-diaria.tar.gz",
    "lansentinel-20261026-033005-diaria.tar.gz.tmp", ".estado.json",
])
def test_nombres_no_validos(name):
    assert a.parse_name(name) is None and a.backup_path(name) is None


def test_rotacion_7_diarias_y_4_semanales():
    now = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)
    backups = [_b(now - timedelta(days=i)) for i in range(60)]
    deleted = {b.name for b in a.select_to_delete(backups, 7, 4)}
    kept = sorted((b.created_at.date() for b in backups if b.name not in deleted), reverse=True)
    assert len(kept) == 11
    assert kept[:7] == [(now - timedelta(days=i)).date() for i in range(7)]
    # Las 4 semanales son de semanas distintas y anteriores
    weeks = {d.isocalendar()[:2] for d in kept[7:]}
    assert len(weeks) == 4


def test_rotacion_con_pocas_copias_no_borra():
    now = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert a.select_to_delete([_b(now - timedelta(hours=i)) for i in range(5)], 7, 4) == []


def test_rotacion_muchas_manuales_el_mismo_dia():
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    backups = [_b(now - timedelta(minutes=i), "manual") for i in range(10)]
    assert len(a.select_to_delete(backups, 7, 4)) == 3


def test_cuando_toca_copia():
    yesterday = _b(datetime(2026, 10, 25, 3, 1, tzinfo=TZ))
    assert a.is_due(datetime(2026, 10, 26, 10, tzinfo=TZ), 3, []) == "inicial"
    assert a.is_due(datetime(2026, 10, 26, 2, 59, tzinfo=TZ), 3, [yesterday]) is None       # aún no es la hora
    assert a.is_due(datetime(2026, 10, 26, 3, 5, tzinfo=TZ), 3, [yesterday]) == "diaria"
    assert a.is_due(datetime(2026, 10, 26, 18, tzinfo=TZ), 3, [yesterday]) == "diaria"      # estaba apagado
    today = _b(datetime(2026, 10, 26, 3, 1, tzinfo=TZ))
    assert a.is_due(datetime(2026, 10, 26, 9, tzinfo=TZ), 3, [today]) is None
    # Una manual no cuenta como la diaria; una inicial sí
    assert a.is_due(datetime(2026, 10, 26, 9, tzinfo=TZ), 3, [_b(datetime(2026, 10, 26, 3, 1, tzinfo=TZ), "manual")]) == "diaria"
    assert a.is_due(datetime(2026, 10, 26, 20, tzinfo=TZ), 3, [_b(datetime(2026, 10, 26, 15, tzinfo=TZ), "inicial")]) is None
    assert a.is_due(datetime(2026, 10, 26, 9, tzinfo=TZ), -1, []) is None                  # desactivadas


# ── Creación de una copia (pg_dump simulado) ─────────────────────────────────

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    state = tmp_path / "estado"
    backups = state / "backups"
    project = tmp_path / "proyecto"
    (state / "tls").mkdir(parents=True)
    project.mkdir()
    (state / "secret_key").write_text("clave")
    (state / "tls" / "ca.key").write_text("clave de la CA")
    (state / "oui.csv").write_text("lista grande que no se copia")
    (state / "algo.tmp").write_text("temporal")
    (project / ".env").write_text("POSTGRES_PASSWORD=secreta\n")
    monkeypatch.setattr(a, "STATE_DIR", state)
    monkeypatch.setattr(a, "BACKUP_DIR", backups)
    monkeypatch.setattr(a, "STATUS_FILE", backups / ".estado.json")
    monkeypatch.setattr(a, "LOCK_FILE", backups / ".lock")
    monkeypatch.setattr(settings, "PROJECT_DIR", str(project))
    monkeypatch.setattr(a, "_dump_database", lambda target: target.write_bytes(b"PGDMP volcado simulado"))
    return state, backups


def test_crea_copia_completa(entorno):
    state, backups = entorno
    backup = a.create_backup("manual")
    path = backups / backup.name
    assert oct(path.stat().st_mode & 0o777) == "0o600" and oct(backups.stat().st_mode & 0o777) == "0o700"
    with tarfile.open(path) as tar:
        names = set(tar.getnames())
        manifest = json.load(tar.extractfile("manifiesto.json"))
        env = tar.extractfile("env").read()
    assert names == {"manifiesto.json", "lansentinel.dump", "estado/secret_key", "estado/tls/ca.key", "env"}
    assert manifest["motivo"] == "manual" and manifest["env"] is True
    assert env == b"POSTGRES_PASSWORD=secreta\n"
    status = a.read_status()
    assert status["last_error"] is None and status["last_success_at"]
    assert [b.name for b in a.list_backups()] == [backup.name]
    assert not any(p.name.startswith(".tmp-") for p in backups.iterdir())


def test_dos_copias_en_el_mismo_segundo_no_se_pisan(entorno, monkeypatch):
    fixed = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

    class Fijo(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(a, "datetime", Fijo)
    first, second = a.create_backup("manual"), a.create_backup("manual")
    assert first.name != second.name and len(a.list_backups()) == 2


def test_fallo_del_volcado(entorno, monkeypatch):
    def falla(target):
        raise a.BackupError("pg_dump falló: sin conexión")
    monkeypatch.setattr(a, "_dump_database", falla)
    with pytest.raises(a.BackupError):
        a.create_backup("diaria")
    assert a.read_status()["last_error"] == "pg_dump falló: sin conexión"
    assert a.list_backups() == []


def test_cerrojo(entorno):
    import fcntl
    _, backups = entorno
    backups.mkdir(parents=True, exist_ok=True)
    with open(backups / ".lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert a.is_running()
        with pytest.raises(a.BackupBusy):
            a.create_backup("manual")
    assert not a.is_running()


def test_motivo_desconocido(entorno):
    with pytest.raises(a.BackupError):
        a.create_backup("borrar-todo")
