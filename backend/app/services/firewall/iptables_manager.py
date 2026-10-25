"""
Gestor de bajo nivel del cortafuegos iptables.

Encapsula todas las invocaciones al comando iptables del sistema mediante
subprocess. Las operaciones son síncronas, por lo que las funciones públicas
ofrecen una variante async que las ejecuta en un ThreadPoolExecutor para no
bloquear el event loop de FastAPI.

Diseño:
  - Todas las reglas de bloqueo viven en dos cadenas propias:
      LANSENTINEL      (enlazada desde INPUT)   → tráfico hacia el propio gateway
      LANSENTINEL_FWD  (enlazada desde FORWARD) → tráfico reenviado a Internet
    Al ser cadenas propias, al arrancar se vacían y se reconstruyen desde la BD
    sin dejar duplicados, y nunca se tocan reglas ajenas de INPUT o FORWARD.
  - Cada regla lleva el comentario "lansentinel:<rule_id>" que permite
    identificarla para borrarla después. El comentario se compara completo
    (no como subcadena), de forma que la regla 1 no se confunde con la 12.
  - Un bloqueo puede filtrar por IP origen, por MAC origen o por ambas. Cada
    criterio genera su propia línea DROP, así basta con que coincida uno.
  - IPv6: las mismas cadenas se crean con ip6tables. Las líneas por MAC se
    replican en ambas familias, de forma que un dispositivo bloqueado
    tampoco sale por IPv6; las líneas por IP van solo a la familia de esa IP.
    Si ip6tables no está disponible, se continúa solo con IPv4.

Requisitos:
  - El contenedor debe ejecutarse con cap_add: NET_ADMIN.
  - Los binarios iptables e ip6tables deben estar instalados (paquete
    iptables del Dockerfile).
"""

import asyncio
import ipaddress
import shlex
import subprocess
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)


CHAIN_INPUT = "LANSENTINEL"
CHAIN_FORWARD = "LANSENTINEL_FWD"
COMMENT_PREFIX = "lansentinel:"

# Cadena propia → cadena estándar desde la que se enlaza
_CHAINS = {
    CHAIN_INPUT: "INPUT",
    CHAIN_FORWARD: "FORWARD",
}

# Familia IP → binario
_BINARIES = {4: "iptables", 6: "ip6tables"}

# Familias con las cadenas preparadas; ensure_chains_exist() la rellena
_active_families: set[int] = {4}


@dataclass
class IptablesResult:
    """Resultado de una invocación a iptables."""
    ok: bool
    stdout: str
    stderr: str
    returncode: int


# ── Invocación de bajo nivel ─────────────────────────────────────────────────

def _run_iptables(args: list[str], family: int = 4) -> IptablesResult:
    """
    Ejecuta iptables (o ip6tables si family=6) con los argumentos dados.
    Captura stdout y stderr. No lanza excepción si el comando devuelve error:
    el que llama inspecciona ok.
    """
    cmd = [_BINARIES[family]] + args
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        return IptablesResult(
            ok=(proc.returncode == 0),
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        log.error("iptables.timeout", cmd=" ".join(cmd))
        return IptablesResult(False, "", "timeout", -1)
    except FileNotFoundError:
        log.error("iptables.not_found", binary=cmd[0])
        return IptablesResult(False, "", f"{cmd[0]} binary not found", -1)


async def _run_iptables_async(args: list[str], family: int = 4) -> IptablesResult:
    """Versión async — ejecuta iptables en thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_iptables, args, family)


# ── Lectura de reglas ────────────────────────────────────────────────────────

def parse_rule_specs(output: str) -> list[list[str]]:
    """
    Convierte la salida de `iptables -S <cadena>` en una lista de reglas,
    cada una como lista de argumentos ("-A", "CADENA", "-s", ...).
    Las líneas que no son reglas (-N, -P) se descartan.
    """
    specs = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("-A "):
            continue
        try:
            specs.append(shlex.split(line))
        except ValueError:
            log.warning("iptables.unparseable_rule", line=line)
    return specs


def comment_of(spec: list[str]) -> str | None:
    """Devuelve el texto del comentario de una regla, o None si no tiene."""
    try:
        return spec[spec.index("--comment") + 1]
    except (ValueError, IndexError):
        return None


async def _list_specs(chain: str, family: int = 4) -> list[list[str]] | None:
    """Reglas actuales de una cadena, o None si no se pudo listar."""
    result = await _run_iptables_async(["-S", chain], family)
    if not result.ok:
        return None
    return parse_rule_specs(result.stdout)


async def _delete_spec(spec: list[str], family: int = 4) -> bool:
    """Borra una regla a partir de su especificación (-A cadena ... → -D cadena ...)."""
    result = await _run_iptables_async(["-D"] + spec[1:], family)
    return result.ok


# ── Inicialización de las cadenas propias ────────────────────────────────────

async def ensure_chains_exist() -> bool:
    """
    Garantiza que las cadenas propias existen y están enlazadas al principio
    de INPUT y FORWARD. Además elimina las reglas DROP que versiones anteriores
    insertaban directamente en FORWARD.

    Idempotente: se puede llamar varias veces sin efectos negativos.
    Se invoca al arrancar el firewall_service. Devuelve False solo si falla
    IPv4; un fallo en IPv6 desactiva esa familia y se registra como aviso.
    """
    if not await _setup_family(4):
        return False

    if await _setup_family(6):
        _active_families.add(6)
    else:
        _active_families.discard(6)
        log.warning("iptables.ipv6_unavailable", hint="Los bloqueos solo se aplicarán en IPv4")

    await _purge_legacy_rules()
    return True


async def _setup_family(family: int) -> bool:
    """Crea y enlaza las cadenas propias en una familia (4 o 6)."""
    for chain, parent in _CHAINS.items():
        # 1. Crear la cadena si no existe (-N falla si ya existe, ignoramos error)
        create = await _run_iptables_async(["-N", chain], family)
        if create.ok:
            log.info("iptables.chain_created", chain=chain, family=family)

        # 2. Comprobar si la cadena estándar ya enlaza con la nuestra (-C consulta sin aplicar)
        check_jump = await _run_iptables_async(["-C", parent, "-j", chain], family)
        if not check_jump.ok:
            # Al principio (-I 1) para evaluarse antes de los ACCEPT de NAT
            jump = await _run_iptables_async(["-I", parent, "1", "-j", chain], family)
            if jump.ok:
                log.info("iptables.jump_added", parent=parent, chain=chain, family=family)
            else:
                log.error("iptables.jump_failed", parent=parent, family=family, error=jump.stderr)
                return False
    return True


async def _purge_legacy_rules() -> None:
    """
    Hasta la versión 1.0 los DROP se insertaban directamente en FORWARD y se
    duplicaban en cada arranque. Ahora viven en LANSENTINEL_FWD, así que se
    eliminan los restos que pudieran quedar en FORWARD.
    """
    specs = await _list_specs("FORWARD")
    if not specs:
        return
    removed = 0
    for spec in specs:
        comment = comment_of(spec) or ""
        if comment.startswith(COMMENT_PREFIX) and await _delete_spec(spec):
            removed += 1
    if removed:
        log.info("iptables.legacy_rules_removed", count=removed)


async def flush_chains() -> bool:
    """Borra todas las reglas de las cadenas propias (no las cadenas en sí)."""
    ok = True
    for family in sorted(_active_families):
        for chain in _CHAINS:
            result = await _run_iptables_async(["-F", chain], family)
            if result.ok:
                log.info("iptables.chain_flushed", chain=chain, family=family)
            ok = ok and result.ok
    return ok


# ── Bloqueo y desbloqueo ─────────────────────────────────────────────────────

def _ip_family(ip: str) -> int | None:
    try:
        return ipaddress.ip_network(ip, strict=False).version
    except ValueError:
        return None


def _match_args(ip: str | None, mac: str | None, family: int) -> list[list[str]]:
    """
    Criterios de coincidencia de un bloqueo en una familia: uno por IP (solo
    si la IP es de esa familia) y uno por MAC (en todas).
    """
    matches = []
    if ip and _ip_family(ip) == family:
        matches.append(["-s", ip])
    if mac:
        matches.append(["-m", "mac", "--mac-source", mac])
    return matches


async def block(rule_id: int | str, ip: str | None = None, mac: str | None = None) -> bool:
    """
    Aplica las reglas DROP de un bloqueo en las dos cadenas propias:
      - LANSENTINEL     → corta el tráfico hacia el gateway.
      - LANSENTINEL_FWD → corta el reenvío a Internet.

    Si se indican IP y MAC, se crea una línea por cada criterio: el bloqueo
    por MAC sigue funcionando aunque el dispositivo cambie de IP, y el de IP
    aunque cambie de MAC.

    Las líneas por MAC se aplican en IPv4 e IPv6; la línea por IP, solo en
    la familia de esa IP.

    Si alguna inserción falla se deshace lo aplicado y se devuelve False.
    """
    plan = {
        family: _match_args(ip, mac, family) for family in sorted(_active_families)
    }
    if not any(plan.values()):
        log.error("iptables.block_without_criteria", rule_id=rule_id, ip=ip, mac=mac)
        return False

    comment = f"{COMMENT_PREFIX}{rule_id}"
    for family, matches in plan.items():
        for chain in _CHAINS:
            for match in matches:
                result = await _run_iptables_async(
                    ["-A", chain] + match + ["-m", "comment", "--comment", comment, "-j", "DROP"],
                    family,
                )
                if not result.ok:
                    log.error(
                        "iptables.block_failed",
                        rule_id=rule_id, chain=chain, family=family,
                        ip=ip, mac=mac, error=result.stderr,
                    )
                    await unblock(rule_id)
                    return False

    log.info("iptables.blocked", rule_id=rule_id, ip=ip, mac=mac)
    return True


async def unblock(rule_id: int | str) -> bool:
    """
    Elimina todas las líneas etiquetadas con el rule_id dado en las cadenas
    propias. Devuelve True si no queda ninguna (idempotente: si ya no estaban
    también es un éxito).
    """
    comment = f"{COMMENT_PREFIX}{rule_id}"
    ok = True
    for family in sorted(_active_families):
        for chain in _CHAINS:
            specs = await _list_specs(chain, family)
            if specs is None:
                ok = False
                continue
            for spec in specs:
                if comment_of(spec) == comment and not await _delete_spec(spec, family):
                    ok = False

    if ok:
        log.info("iptables.unblocked", rule_id=rule_id)
    else:
        log.warning("iptables.unblock_partial", rule_id=rule_id)
    return ok


# ── Consulta del estado ──────────────────────────────────────────────────────

async def is_firewall_available() -> bool:
    """Comprueba que iptables responde. Útil para el endpoint de status."""
    result = await _run_iptables_async(["-L", "-n"])
    return result.ok


def ipv6_enabled() -> bool:
    """True si las cadenas propias también están activas en ip6tables."""
    return 6 in _active_families
