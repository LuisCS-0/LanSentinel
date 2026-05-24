"""
Gestor de bajo nivel del cortafuegos iptables.

Encapsula todas las invocaciones al comando iptables del sistema mediante
subprocess. Las operaciones son síncronas, por lo que las funciones públicas
ofrecen una variante async que las ejecuta en un ThreadPoolExecutor para no
bloquear el event loop de FastAPI.

Diseño:
  - Todas las reglas se aplican en una cadena propia llamada LANSENTINEL,
    no en la INPUT estándar. Esto facilita la inspección, el listado y la
    limpieza completa sin afectar a otras reglas del sistema.
  - La cadena LANSENTINEL se enlaza desde INPUT al arrancar, de forma que
    los paquetes son evaluados contra nuestras reglas antes de continuar.
  - Cada regla incluye un comentario con el ID lógico (UUID del dispositio o
    similar) que permite identificarla unívocamente para borrarla después.

Requisitos:
  - El contenedor debe ejecutarse con cap_add: NET_ADMIN.
  - El binario iptables debe estar instalado (incluido en el Dockerfile).
"""

import asyncio
import subprocess
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)


CHAIN_NAME = "LANSENTINEL"
COMMENT_PREFIX = "lansentinel:"


@dataclass
class IptablesResult:
    """Resultado de una invocación a iptables."""
    ok: bool
    stdout: str
    stderr: str
    returncode: int


# ── Invocación de bajo nivel ─────────────────────────────────────────────────

def _run_iptables(args: list[str]) -> IptablesResult:
    """
    Ejecuta iptables con los argumentos dados. Captura stdout y stderr.
    No lanza excepción si iptables devuelve error: el que llama inspecciona ok.
    """
    cmd = ["iptables"] + args
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
        log.error("iptables.not_found")
        return IptablesResult(False, "", "iptables binary not found", -1)


async def _run_iptables_async(args: list[str]) -> IptablesResult:
    """Versión async — ejecuta iptables en thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_iptables, args)


# ── Inicialización de la cadena propia ───────────────────────────────────────

async def ensure_chain_exists() -> bool:
    """
    Garantiza que la cadena LANSENTINEL existe y está enlazada desde INPUT.

    Idempotente: se puede llamar varias veces sin efectos negativos.
    Se invoca al arrancar el firewall_service.
    """
    # 1. Crear la cadena si no existe (-N falla si ya existe, ignoramos error)
    create = await _run_iptables_async(["-N", CHAIN_NAME])
    if create.ok:
        log.info("iptables.chain_created", chain=CHAIN_NAME)
    else:
        log.debug("iptables.chain_already_exists", chain=CHAIN_NAME)

    # 2. Comprobar si INPUT ya enlaza con nuestra cadena (-C consulta sin aplicar)
    check_jump = await _run_iptables_async(
        ["-C", "INPUT", "-j", CHAIN_NAME]
    )
    if not check_jump.ok:
        # No existe el enlace: lo añadimos al principio de INPUT (-I)
        jump = await _run_iptables_async(["-I", "INPUT", "-j", CHAIN_NAME])
        if jump.ok:
            log.info("iptables.input_jump_added", chain=CHAIN_NAME)
        else:
            log.error("iptables.input_jump_failed", error=jump.stderr)
            return False
    return True


async def flush_chain() -> bool:
    """Borra todas las reglas de la cadena LANSENTINEL (no la cadena en sí)."""
    result = await _run_iptables_async(["-F", CHAIN_NAME])
    if result.ok:
        log.info("iptables.chain_flushed", chain=CHAIN_NAME)
    return result.ok


# ── Reglas DROP por IP ───────────────────────────────────────────────────────

async def block_ip(ip: str, rule_id: int | str) -> bool:
    """
    Aplica una regla DROP en la cadena LANSENTINEL para la IP dada.

    Args:
        ip: Dirección IP origen a bloquear (ej. "192.168.56.20").
        rule_id: Identificador lógico para etiquetar la regla (se usa en el
                 comentario para poder borrarla luego sin ambigüedad).

    Returns:
        True si la regla se aplicó correctamente, False en caso contrario.
    """
    comment = f"{COMMENT_PREFIX}{rule_id}"
    args = [
        "-A", CHAIN_NAME,            # append a la cadena propia
        "-s", ip,                    # source IP
        "-m", "comment",
        "--comment", comment,
        "-j", "DROP",                # acción
    ]
    result = await _run_iptables_async(args)
    if result.ok:
        log.info("iptables.ip_blocked", ip=ip, rule_id=rule_id)
    else:
        log.error("iptables.block_failed", ip=ip, error=result.stderr)
    return result.ok


async def unblock_ip(ip: str, rule_id: int | str) -> bool:
    """
    Elimina la regla DROP correspondiente al rule_id dado.

    Como iptables no permite borrar por comentario directamente, primero
    listamos las reglas, buscamos la que tiene nuestro comentario y la
    eliminamos por número de línea.
    """
    comment = f"{COMMENT_PREFIX}{rule_id}"

    # 1. Listar reglas con numeración
    list_result = await _run_iptables_async(
        ["-L", CHAIN_NAME, "--line-numbers", "-n"]
    )
    if not list_result.ok:
        log.error("iptables.list_failed", error=list_result.stderr)
        return False

    # 2. Buscar la línea con nuestro comentario
    target_line = None
    for line in list_result.stdout.splitlines():
        if comment in line:
            parts = line.split(None, 1)
            if parts and parts[0].isdigit():
                target_line = parts[0]
                break

    if target_line is None:
        log.warning("iptables.rule_not_found", rule_id=rule_id, ip=ip)
        return False

    # 3. Borrar por número
    delete = await _run_iptables_async(
        ["-D", CHAIN_NAME, target_line]
    )
    if delete.ok:
        log.info("iptables.ip_unblocked", ip=ip, rule_id=rule_id)
    else:
        log.error("iptables.unblock_failed", error=delete.stderr)
    return delete.ok


# ── Consulta del estado ──────────────────────────────────────────────────────

async def list_active_rules() -> list[dict]:
    """
    Devuelve la lista de reglas activas en la cadena LANSENTINEL.

    Cada entrada incluye el número de línea, la IP origen y el comentario
    (que contiene el rule_id lógico).
    """
    result = await _run_iptables_async(
        ["-L", CHAIN_NAME, "--line-numbers", "-n", "-v"]
    )
    if not result.ok:
        return []

    rules = []
    for line in result.stdout.splitlines():
        # Solo nos interesan las líneas que tienen nuestro prefijo de comentario
        if COMMENT_PREFIX not in line:
            continue
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue

        # Extraer IP origen (columna "source" de iptables -L -v)
        # El formato es: num pkts bytes target prot opt in out source dest ...
        try:
            src_ip = parts[7]
        except IndexError:
            src_ip = None

        # Extraer el rule_id del comentario
        comment_idx = line.find(COMMENT_PREFIX)
        rule_id = None
        if comment_idx >= 0:
            tail = line[comment_idx + len(COMMENT_PREFIX):]
            rule_id = tail.split()[0].rstrip('"*/ ')

        rules.append({
            "line_number": int(parts[0]),
            "src_ip": src_ip,
            "rule_id": rule_id,
        })
    return rules


async def is_firewall_available() -> bool:
    """Comprueba que iptables responde. Útil para el endpoint de status."""
    result = await _run_iptables_async(["-L", "-n"])
    return result.ok
