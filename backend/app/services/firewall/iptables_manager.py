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



async def block_ip(ip: str, rule_id: int | str) -> bool:
    """
    Aplica una regla DROP en dos cadenas:
      - LANSENTINEL (enganchada a INPUT) → corta tráfico hacia el gateway.
      - FORWARD                          → corta el reenvío a Internet.

    De esta forma, en una topología donde LanSentinel actúa como gateway,
    el bloqueo es total: el dispositivo no puede ni hablar con LanSentinel
    ni salir a Internet.

    Args:
        ip: Dirección IP origen a bloquear.
        rule_id: Identificador lógico para etiquetar la regla.
    """
    comment = f"{COMMENT_PREFIX}{rule_id}"

    # Regla 1: tráfico hacia LanSentinel (cadena propia LANSENTINEL)
    args_input = [
        "-A", CHAIN_NAME,
        "-s", ip,
        "-m", "comment", "--comment", comment,
        "-j", "DROP",
    ]
    res1 = await _run_iptables_async(args_input)

    # Regla 2: tráfico reenviado hacia Internet (cadena FORWARD)
    # IMPORTANTE: usamos -I (insert al principio) para que esta regla se
    # evalúe ANTES de las ACCEPT de NAT/MASQUERADE que dejan pasar todo.
    args_forward = [
        "-I", "FORWARD", "1",
        "-s", ip,
        "-m", "comment", "--comment", comment,
        "-j", "DROP",
    ]
    res2 = await _run_iptables_async(args_forward)

    if res1.ok and res2.ok:
        log.info("iptables.ip_blocked", ip=ip, rule_id=rule_id)
        return True
    else:
        log.error(
            "iptables.block_failed",
            ip=ip, input_ok=res1.ok, forward_ok=res2.ok,
            error_input=res1.stderr, error_forward=res2.stderr,
        )
        return False


async def unblock_ip(ip: str, rule_id: int | str) -> bool:
    """
    Elimina las reglas DROP correspondientes al rule_id dado, tanto en
    la cadena LANSENTINEL como en FORWARD.
    """
    comment = f"{COMMENT_PREFIX}{rule_id}"

    async def _delete_in_chain(chain: str) -> bool:
        list_result = await _run_iptables_async(
            ["-L", chain, "--line-numbers", "-n"]
        )
        if not list_result.ok:
            return False
        # Buscar la línea con nuestro comentario
        for line in list_result.stdout.splitlines():
            if comment in line:
                parts = line.split(None, 1)
                if parts and parts[0].isdigit():
                    delete_result = await _run_iptables_async(
                        ["-D", chain, parts[0]]
                    )
                    return delete_result.ok
        # No encontrada — devolvemos True (idempotencia: ya no está)
        return True

    ok1 = await _delete_in_chain(CHAIN_NAME)
    ok2 = await _delete_in_chain("FORWARD")

    if ok1 and ok2:
        log.info("iptables.ip_unblocked", ip=ip, rule_id=rule_id)
        return True
    else:
        log.warning(
            "iptables.unblock_partial",
            ip=ip, rule_id=rule_id,
            input_ok=ok1, forward_ok=ok2,
        )
        return ok1 or ok2  # devuelve true si al menos una se quitó


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
