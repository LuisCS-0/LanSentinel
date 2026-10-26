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
  - Modo cuarentena: cadena LANSENTINEL_QUAR, enlazada en FORWARD justo
    detrás de LANSENTINEL_FWD. Vacía cuando el modo está desactivado; activo,
    deja pasar las MAC de confianza (RETURN) y descarta el resto de lo que
    entra por la interfaz LAN. Solo afecta al reenvío: los equipos retenidos
    siguen llegando a LanSentinel (DHCP, DNS, panel). El panel en Docker se
    alcanza por reenvío (DNAT del puerto publicado), así que esas conexiones
    también se dejan pasar.
  - Modo router (ROUTER_MODE): LanSentinel hace de router entre la WAN y la
    LAN con tres cadenas propias, vacías si el modo está desactivado:
      LANSENTINEL_NAT     (nat POSTROUTING) → enmascara lo que sale por la WAN
      LANSENTINEL_ROUTE   (FORWARD, tras bloqueos, cuarentena y conteo) →
                          deja salir LAN→WAN y entrar solo las respuestas
      LANSENTINEL_WAN_IN  (INPUT) → desde la WAN solo entran respuestas, ICMP
                          y el DHCP del propio equipo
    Los puertos que publica Docker (el panel) se alcanzan por DNAT y pasan
    por FORWARD, así que LANSENTINEL_ROUTE también los corta desde la WAN.
    El reenvío (net.ipv4.ip_forward) lo activa el instalador en el sistema:
    un contenedor no puede cambiarlo.
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
CHAIN_QUARANTINE = "LANSENTINEL_QUAR"
CHAIN_ROUTE = "LANSENTINEL_ROUTE"
CHAIN_WAN_IN = "LANSENTINEL_WAN_IN"
CHAIN_NAT = "LANSENTINEL_NAT"
CHAIN_ACCT = "LANSENTINEL_ACCT"
WAN_COMMENT = "lansentinel-wan"
COMMENT_PREFIX = "lansentinel:"
QUARANTINE_COMMENT = "lansentinel-quarantine"

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

    # Cuarentena: detrás de los bloqueos, para que un bloqueo siempre gane
    await _run_iptables_async(["-N", CHAIN_QUARANTINE], family)
    check_jump = await _run_iptables_async(["-C", "FORWARD", "-j", CHAIN_QUARANTINE], family)
    if not check_jump.ok:
        position = await position_after("FORWARD", {CHAIN_FORWARD}, family)
        jump = await _run_iptables_async(["-I", "FORWARD", str(position), "-j", CHAIN_QUARANTINE], family)
        if not jump.ok:
            log.error("iptables.quarantine_jump_failed", family=family, error=jump.stderr)
            return False
    return True


async def position_after(parent: str, chains: set[str], family: int = 4) -> int:
    """
    Posición (1-based, para -I) justo detrás del último salto de `parent` a
    alguna de `chains`; 1 si no hay ninguno.
    """
    specs = await _list_specs(parent, family) or []
    position = 1
    for index, spec in enumerate(specs, start=1):
        if spec[-2:-1] == ["-j"] and spec[-1] in chains:
            position = index + 1
    return position


async def set_quarantine(enabled: bool, allowed_macs: set[str], interface: str) -> bool:
    """
    Reconstruye la cadena de cuarentena. Desactivada queda vacía (no filtra
    nada); activada, solo pueden reenviar tráfico las MAC indicadas.
    """
    ok = True
    for family in sorted(_active_families):
        if not (await _run_iptables_async(["-F", CHAIN_QUARANTINE], family)).ok:
            ok = False
            continue
        if not enabled:
            continue
        # El panel corre en un contenedor con el puerto publicado (3000:80):
        # Docker hace DNAT y la conexión al panel se reenvía en vez de entrar
        # por INPUT, así que sin esta línea los retenidos no podrían abrirlo.
        # Docker solo hace DNAT del tráfico dirigido a una IP del propio
        # equipo, de modo que esto no abre la salida a Internet.
        result = await _run_iptables_async(
            ["-A", CHAIN_QUARANTINE, "-i", interface, "-m", "conntrack", "--ctstate", "DNAT", "-j", "RETURN"],
            family,
        )
        ok = ok and result.ok
        for mac in sorted(m.upper() for m in allowed_macs):
            result = await _run_iptables_async(
                ["-A", CHAIN_QUARANTINE, "-i", interface, "-m", "mac", "--mac-source", mac, "-j", "RETURN"],
                family,
            )
            ok = ok and result.ok
        result = await _run_iptables_async(
            ["-A", CHAIN_QUARANTINE, "-i", interface,
             "-m", "comment", "--comment", QUARANTINE_COMMENT, "-j", "DROP"],
            family,
        )
        ok = ok and result.ok
    log.info("iptables.quarantine_applied", enabled=enabled, allowed=len(allowed_macs), ok=ok)
    return ok


# ── Modo router ──────────────────────────────────────────────────────────────

async def _ensure_jump(parent: str, chain: str, family: int, table: str = "filter", after: set[str] | None = None) -> bool:
    """Crea la cadena si no existe y la enlaza desde `parent` (una sola vez)."""
    t = ["-t", table]
    await _run_iptables_async(t + ["-N", chain], family)
    if (await _run_iptables_async(t + ["-C", parent, "-j", chain], family)).ok:
        return True
    position = 1
    if after:
        position = await position_after(parent, after, family) if table == "filter" else 1
    result = await _run_iptables_async(t + ["-I", parent, str(position), "-j", chain], family)
    if not result.ok:
        log.error("iptables.router_jump_failed", chain=chain, family=family, error=result.stderr)
    return result.ok


def router_rules(wan: str, lan: str, family: int) -> dict[tuple[str, str], list[list[str]]]:
    """
    Reglas del modo router de una familia, por (tabla, cadena). Función pura
    para poder revisarlas sin tocar iptables.
    """
    icmp = "icmp" if family == 4 else "ipv6-icmp"
    dhcp_client_port = "68" if family == 4 else "546"
    rules: dict[tuple[str, str], list[list[str]]] = {
        ("filter", CHAIN_WAN_IN): [
            ["-i", wan, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "RETURN"],
            # ICMP: ping, errores y, en IPv6, el descubrimiento de vecinos
            ["-i", wan, "-p", icmp, "-j", "RETURN"],
            # Respuestas del DHCP de la operadora al propio equipo
            ["-i", wan, "-p", "udp", "--dport", dhcp_client_port, "-j", "RETURN"],
            ["-i", wan, "-m", "comment", "--comment", WAN_COMMENT, "-j", "DROP"],
        ],
    }
    if family == 4:
        rules[("filter", CHAIN_ROUTE)] = [
            # Nadie de fuera llega a un puerto publicado por Docker (el panel)
            ["-i", wan, "-m", "conntrack", "--ctstate", "DNAT", "-m", "comment", "--comment", WAN_COMMENT, "-j", "DROP"],
            ["-i", lan, "-o", wan, "-j", "ACCEPT"],
            ["-i", wan, "-o", lan, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT"],
        ]
        rules[("nat", CHAIN_NAT)] = [["-o", wan, "-j", "MASQUERADE"]]
    return rules


async def set_router(enabled: bool, wan: str, lan: str) -> bool:
    """
    Reconstruye las cadenas del modo router. Desactivado quedan vacías (el
    equipo no enruta por sí mismo); activado, enruta y protege la WAN.
    """
    ok = True
    for family in sorted(_active_families):
        ok = await _ensure_jump("INPUT", CHAIN_WAN_IN, family, after={CHAIN_INPUT}) and ok
        if family == 4:
            ok = await _ensure_jump("FORWARD", CHAIN_ROUTE, family, after={CHAIN_FORWARD, CHAIN_QUARANTINE, CHAIN_ACCT}) and ok
            ok = await _ensure_jump("POSTROUTING", CHAIN_NAT, family, table="nat") and ok
        planned = router_rules(wan, lan, family) if enabled else {}
        chains = [("filter", CHAIN_WAN_IN)] + ([("filter", CHAIN_ROUTE), ("nat", CHAIN_NAT)] if family == 4 else [])
        for table, chain in chains:
            if not (await _run_iptables_async(["-t", table, "-F", chain], family)).ok:
                ok = False
                continue
            for rule in planned.get((table, chain), []):
                result = await _run_iptables_async(["-t", table, "-A", chain] + rule, family)
                if not result.ok:
                    log.error("iptables.router_rule_failed", chain=chain, family=family, rule=rule, error=result.stderr)
                ok = ok and result.ok
    log.info("iptables.router_applied", enabled=enabled, wan=wan, lan=lan, ok=ok)
    return ok


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
