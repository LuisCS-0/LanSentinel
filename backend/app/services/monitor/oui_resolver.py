"""Resolución de fabricante a partir del prefijo OUI (primeros 3 octetos de la MAC)."""


"""
Estrategia:
  1. MAC aleatoria (bit "localmente administrada" activo): los móviles y
     portátiles actuales usan direcciones privadas que no pertenecen a ningún
     fabricante. Se indica así en lugar de buscarlas.
  2. Base de datos local: la lista pública MA-L del IEEE (oui.csv), que se
     descarga al equipo y se renueva cada OUI_MAX_AGE_DAYS días. Así las MACs
     de la red no salen a ningún servicio externo.
  3. Opcional (OUI_ONLINE_LOOKUP=true): consulta a la API pública
     macvendors.com para los prefijos que no estén en la lista local.
"""

import asyncio
import csv
import io
import os
import time
from pathlib import Path

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

RANDOM_MAC_VENDOR = "MAC aleatoria (dirección privada)"

# Prefijo "AABBCC" → fabricante, cargado desde oui.csv
_oui_db: dict[str, str] = {}
_update_task: asyncio.Task | None = None

# Caché de la consulta online
_cache: dict[str, str | None] = {}

# API pública gratuita, sin auth, límite ~1 req/s
_OUI_API_URL = "https://api.macvendors.com/{prefix}"
_HTTP_TIMEOUT = 3.0  # segundos
_DOWNLOAD_TIMEOUT = 60.0


# ── Base de datos local ──────────────────────────────────────────────────────

def _parse_oui_csv(text: str) -> dict[str, str]:
    """Columnas del IEEE: Registry, Assignment (6 hex), Organization Name, Organization Address."""
    db: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        prefix = (row.get("Assignment") or "").strip().upper()
        name = (row.get("Organization Name") or "").strip()
        if len(prefix) == 6 and name:
            db[prefix] = name
    return db


def _load_from_disk(path: Path) -> bool:
    global _oui_db
    try:
        db = _parse_oui_csv(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        log.warning("oui_resolver.load_error", path=str(path), error=str(exc))
        return False
    if not db:
        log.warning("oui_resolver.empty_database", path=str(path))
        return False
    _oui_db = db
    log.info("oui_resolver.database_loaded", prefixes=len(db))
    return True


async def _download(path: Path) -> bool:
    """Descarga oui.csv del IEEE. Se escribe a un temporal y se renombra al final."""
    try:
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            # El servidor del IEEE rechaza algunos clientes sin User-Agent
            headers={"User-Agent": "Mozilla/5.0 (compatible; LanSentinel)"},
        ) as client:
            response = await client.get(settings.OUI_DOWNLOAD_URL)
            response.raise_for_status()
        if not _parse_oui_csv(response.text):
            log.warning("oui_resolver.download_invalid")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(response.text, encoding="utf-8")
        os.replace(tmp, path)
        log.info("oui_resolver.database_downloaded", path=str(path))
        return True
    except (httpx.HTTPError, OSError) as exc:
        log.warning("oui_resolver.download_error", error=str(exc))
        return False


async def ensure_oui_database() -> None:
    """
    Carga la base de datos OUI, descargándola si no existe o si tiene más de
    OUI_MAX_AGE_DAYS días. Si la descarga falla se usa la copia que haya.
    """
    path = Path(settings.OUI_DB_PATH)
    max_age = settings.OUI_MAX_AGE_DAYS * 86400
    stale = not path.exists() or (time.time() - path.stat().st_mtime) > max_age

    if stale:
        await _download(path)
    if path.exists():
        await asyncio.get_running_loop().run_in_executor(None, _load_from_disk, path)
    else:
        log.warning(
            "oui_resolver.no_database",
            hint="Sin oui.csv los fabricantes aparecerán como desconocidos hasta la próxima descarga",
        )


def start_background_update() -> None:
    """Lanza ensure_oui_database() sin retrasar el arranque del backend."""
    global _update_task
    if _update_task is None or _update_task.done():
        _update_task = asyncio.create_task(ensure_oui_database(), name="oui_update")


# ── Resolución ───────────────────────────────────────────────────────────────

def is_randomized_mac(mac: str) -> bool:
    """Bit 1 del primer octeto: dirección administrada localmente (aleatoria)."""
    try:
        return bool(int(mac[:2], 16) & 0x02)
    except ValueError:
        return False


async def _resolve_online(prefix: str) -> str | None:
    if prefix in _cache:
        return _cache[prefix]

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            url = _OUI_API_URL.format(prefix=prefix)
            response = await client.get(url)

            if response.status_code == 200:
                vendor = response.text.strip()
                _cache[prefix] = vendor
                log.debug("oui_resolver.hit", prefix=prefix, vendor=vendor)
                return vendor

            elif response.status_code == 404:
                # Prefijo OUI desconocido (dispositivos genéricos, VMs, etc.)
                _cache[prefix] = None
                return None

            else:
                log.warning("oui_resolver.api_error", status=response.status_code)
                return None

    except httpx.TimeoutException:
        log.warning("oui_resolver.timeout", prefix=prefix)
        return None
    except Exception as exc:
        log.error("oui_resolver.error", error=str(exc))
        return None


async def resolve_vendor(mac: str) -> str | None:
    """
    Devuelve el nombre del fabricante para una dirección MAC dada.
    Devuelve None si no se puede determinar.
    """
    if is_randomized_mac(mac):
        return RANDOM_MAC_VENDOR

    vendor = _oui_db.get(mac.replace(":", "").replace("-", "")[:6].upper())
    if vendor:
        return vendor

    if settings.OUI_ONLINE_LOOKUP:
        return await _resolve_online(mac[:8].upper())  # "AA:BB:CC"
    return None


async def resolve_vendors_batch(macs: list[str]) -> dict[str, str | None]:
    """
    Resuelve múltiples MACs. Las búsquedas locales son inmediatas; si la
    consulta online está activada, se limita a 3 peticiones concurrentes con
    una pequeña espera para respetar el límite de la API.
    """
    semaf = asyncio.Semaphore(3)

    async def _fetch(mac: str) -> tuple[str, str | None]:
        async with semaf:
            # ¿Esta MAC acabará en una petición a la API? (ni aleatoria, ni en
            # la lista local, ni en caché)
            goes_online = (
                settings.OUI_ONLINE_LOOKUP
                and not is_randomized_mac(mac)
                and mac.replace(":", "")[:6].upper() not in _oui_db
                and mac[:8].upper() not in _cache
            )
            vendor = await resolve_vendor(mac)
            if goes_online:
                # Pequeña pausa entre requests para intentar respetar el límite
                await asyncio.sleep(0.4)
            return mac, vendor

    results: dict[str, str | None] = {}
    resolved = await asyncio.gather(*[_fetch(mac) for mac in macs], return_exceptions=True)
    for item in resolved:
        if isinstance(item, Exception):
            log.warning("oui_resolver.batch_error", error=str(item))
            continue
        mac, vendor = item
        results[mac] = vendor
    return results
