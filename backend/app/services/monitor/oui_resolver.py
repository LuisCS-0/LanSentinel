"""
Resolución de fabricante a partir del prefijo OUI (primeros 3 octetos de la MAC).

Estrategia en dos capas:
  1. Caché en memoria (dict) para evitar llamadas repetidas durante la sesión.
  2. Consulta a la API pública macvendors.com si no está en caché.

En producción se podría sustituir por una base de datos OUI local (fichero .csv
del IEEE) para no depender de conectividad externa y reducir latencia.
"""

import asyncio
import httpx
import structlog

log = structlog.get_logger(__name__)

# Caché en memoria: { "AA:BB:CC": "Apple, Inc." }
_cache: dict[str, str | None] = {}

# API pública gratuita, sin auth, límite ~1 req/s
_OUI_API_URL = "https://api.macvendors.com/{mac}"
_HTTP_TIMEOUT = 3.0  # segundos


async def resolve_vendor(mac: str) -> str | None:
    """
    Devuelve el nombre del fabricante para una dirección MAC dada.
    Retorna None si no se puede determinar.

    Args:
        mac: Dirección MAC en formato 'AA:BB:CC:DD:EE:FF' (mayúsculas).
    """
    prefix = mac[:8].upper()  # Primeros 3 octetos: "AA:BB:CC"

    if prefix in _cache:
        return _cache[prefix]

    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            url = _OUI_API_URL.format(mac=prefix)
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


async def resolve_vendors_batch(macs: list[str]) -> dict[str, str | None]:
    """
    Resuelve múltiples MACs en paralelo con un pequeño throttle
    para no superar el rate limit de la API.

    Retorna: { mac: vendor_name_or_None }
    """
    # Primero los que ya están en caché (gratis)
    results: dict[str, str | None] = {}
    pending: list[str] = []

    for mac in macs:
        prefix = mac[:8].upper()
        if prefix in _cache:
            results[mac] = _cache[prefix]
        else:
            pending.append(mac)

    if not pending:
        return results

    # Resuelve los pendientes con un semáforo de 3 requests concurrentes
    sem = asyncio.Semaphore(3)

    async def _fetch(mac: str) -> tuple[str, str | None]:
        async with sem:
            vendor = await resolve_vendor(mac)
            # Pequeña pausa entre requests para respetar el rate limit
            await asyncio.sleep(0.4)
            return mac, vendor

    tasks = [_fetch(mac) for mac in pending]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)

    for item in resolved:
        if isinstance(item, Exception):
            log.warning("oui_resolver.batch_error", error=str(item))
            continue
        mac, vendor = item
        results[mac] = vendor

    return results
