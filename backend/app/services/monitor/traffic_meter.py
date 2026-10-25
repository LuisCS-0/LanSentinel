"""
Medidor de tráfico por dispositivo.

Aprovecha los contadores que iptables mantiene automáticamente sobre cada
regla para medir, en bytes y paquetes, cuánto tráfico ha pasado a través
de ella. La estrategia:

1. Por cada dispositivo conocido, añadimos dos reglas "fantasma" en la
   cadena propia LANSENTINEL_ACCT, enlazada desde FORWARD justo después de
   la cadena de bloqueos (el tráfico bloqueado no se cuenta):
     - Una con su IP como origen (tráfico SALIENTE del dispositivo)
     - Una con su IP como destino (tráfico ENTRANTE al dispositivo)
   Las reglas no llevan -j (jump), por lo que SOLO incrementan contadores;
   no afectan al enrutamiento real. Al ser una cadena propia, se vacía al
   arrancar y se pueden retirar las IPs que un dispositivo deja de usar.

2. Cada N segundos, leemos los contadores y calculamos la tasa actual:
       rate = (bytes_now - bytes_anterior) / (tiempo_now - tiempo_anterior)

3. La tasa se mantiene en un diccionario en memoria, indexado por IP,
   y se expone vía endpoint REST.

4. Además, los bytes y paquetes de cada intervalo se acumulan por IP hasta
   que traffic_history los recoge (drain_pending) y los guarda en la BD
   como histórico de consumo.

La unidad almacenada internamente son bytes/segundo; el endpoint puede
convertir a KB/s o Mbps según prefiera el frontend.
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from collections import deque
import structlog

from app.services.firewall.iptables_manager import (
    CHAIN_FORWARD, CHAIN_QUARANTINE, comment_of, parse_rule_specs, position_after,
)

log = structlog.get_logger(__name__)


# Marca de comentario para identificar reglas de medición de LanSentinel
TRAFFIC_TAG = "lansentinel-traffic"

# Cadena propia con las reglas de conteo
ACCT_CHAIN = "LANSENTINEL_ACCT"


# ─── Tipos auxiliares ────────────────────────────────────────────────────────

@dataclass
class TrafficSample:
    """Última muestra de tráfico de un dispositivo."""
    ip: str
    rx_bps: float = 0.0     # bytes/segundo entrantes
    tx_bps: float = 0.0     # bytes/segundo salientes
    last_rx_bytes: int = 0
    last_tx_bytes: int = 0
    last_rx_packets: int = 0
    last_tx_packets: int = 0
    last_sample_at: float = 0.0

    @property
    def total_bps(self) -> float:
        return self.rx_bps + self.tx_bps


@dataclass
class TrafficCounters:
    """Contadores acumulados de una IP (o su incremento en un intervalo)."""
    rx_bytes: int = 0       # hacia el dispositivo (descarga)
    tx_bytes: int = 0       # desde el dispositivo (subida)
    rx_packets: int = 0
    tx_packets: int = 0

    def add(self, other: "TrafficCounters") -> None:
        self.rx_bytes += other.rx_bytes
        self.tx_bytes += other.tx_bytes
        self.rx_packets += other.rx_packets
        self.tx_packets += other.tx_packets


def parse_counters(output: str) -> dict[str, TrafficCounters]:
    """
    Interpreta la salida de `iptables -L LANSENTINEL_ACCT -v -n -x`.

    El formato de salida es:
        pkts    bytes  target  prot opt in  out src           dst           opciones...

    Como las reglas no tienen -j (target), el campo 'target' aparece
    vacío. Para identificar si es regla origen o destino, miramos qué
    columna contiene 0.0.0.0/0:
        - 0.0.0.0/0 en src → es regla "-d <ip>" → tráfico ENTRANTE
        - 0.0.0.0/0 en dst → es regla "-s <ip>" → tráfico SALIENTE
    """
    counters: dict[str, TrafficCounters] = {}

    for line in output.splitlines():
        if TRAFFIC_TAG not in line:
            continue

        # Extraer la IP del comentario lansentinel-traffic:<ip>
        try:
            tag_idx = line.index(TRAFFIC_TAG + ":")
            ip = line[tag_idx + len(TRAFFIC_TAG) + 1:].split()[0]
            # Limpiar posibles caracteres extra como */
            ip = ip.rstrip('*/ ')
        except (ValueError, IndexError):
            continue

        # Dividir la línea por espacios. Los dos primeros campos son
        # siempre pkts y bytes; el resto puede variar de posición pero
        # 0.0.0.0/0 siempre aparece exactamente una vez (en src o dst).
        parts = line.split()
        if len(parts) < 2:
            continue

        try:
            packet_count = int(parts[0])
            byte_count = int(parts[1])
        except ValueError:
            continue

        # Localizar 0.0.0.0/0 en la línea para determinar tipo de regla
        try:
            wildcard_idx = parts.index("0.0.0.0/0")
        except ValueError:
            continue

        entry = counters.setdefault(ip, TrafficCounters())
        # La IP del dispositivo aparece justo antes o después de 0.0.0.0/0
        # Si 0.0.0.0/0 viene antes de la IP → la IP está en dst → ENTRANTE
        # Si 0.0.0.0/0 viene después de la IP → la IP está en src → SALIENTE
        if wildcard_idx + 1 < len(parts) and parts[wildcard_idx + 1] == ip:
            # 0.0.0.0/0 → ip   ⇒ regla "-d ip" ⇒ tráfico hacia la IP
            entry.rx_bytes += byte_count
            entry.rx_packets += packet_count
        elif wildcard_idx - 1 >= 0 and parts[wildcard_idx - 1] == ip:
            # ip → 0.0.0.0/0  ⇒ regla "-s ip" ⇒ tráfico desde la IP
            entry.tx_bytes += byte_count
            entry.tx_packets += packet_count

    return counters


# ─── Invocación de iptables ──────────────────────────────────────────────────

def _run_iptables(args: list[str]) -> tuple[bool, str]:
    """Ejecuta iptables y devuelve (ok, stdout)."""
    try:
        proc = subprocess.run(
            ["iptables"] + args,
            capture_output=True, text=True, timeout=5,
        )
        return proc.returncode == 0, proc.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, ""


async def _run_iptables_async(args: list[str]) -> tuple[bool, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_iptables, args)


# ─── Servicio principal ──────────────────────────────────────────────────────

class TrafficMeter:
    """
    Singleton que mantiene reglas-contador en FORWARD y calcula tasas.
    El bucle se arranca desde el lifespan de main.py; monitor_service va
    registrando las IPs de los dispositivos que descubre.
    """

    def __init__(self):
        # IP → última muestra
        self._samples: dict[str, TrafficSample] = {}
        # IPs que actualmente tienen reglas de medición instaladas
        self._tracked_ips: set[str] = set()
        self._running: bool = False
        self._task: asyncio.Task | None = None
        self._total_history: deque = deque(maxlen=120)
        # IP → tráfico acumulado desde el último drain_pending()
        self._pending: dict[str, TrafficCounters] = {}

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    async def start(self, interval_seconds: int = 5):
        """
        Prepara la cadena de conteo y arranca el bucle periódico de lectura
        de contadores. Se llama después de firewall_service.start(), para
        poder enlazar la cadena detrás de la de bloqueos.
        """
        if self._running:
            return
        await self._setup_chain()
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_seconds))
        log.info("traffic_meter.started", interval=interval_seconds)

    async def stop(self):
        """Detiene el bucle. Las reglas de iptables no se eliminan aquí;
        la cadena se vacía en el siguiente arranque."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("traffic_meter.stopped")

    # ── Gestión de reglas ───────────────────────────────────────────────────

    async def _setup_chain(self) -> None:
        """
        Crea (o vacía) la cadena LANSENTINEL_ACCT y la enlaza desde FORWARD
        detrás de los saltos a LANSENTINEL_FWD y LANSENTINEL_QUAR, antes de los
        ACCEPT de NAT.
        Retira además las reglas de conteo que versiones anteriores insertaban
        directamente en FORWARD.
        """
        await _run_iptables_async(["-N", ACCT_CHAIN])
        await _run_iptables_async(["-F", ACCT_CHAIN])
        self._tracked_ips.clear()

        ok, output = await _run_iptables_async(["-S", "FORWARD"])
        if not ok:
            log.warning("traffic_meter.forward_unavailable")
            return
        specs = parse_rule_specs(output)

        for spec in specs:
            if (comment_of(spec) or "").startswith(f"{TRAFFIC_TAG}:"):
                await _run_iptables_async(["-D"] + spec[1:])

        if any(spec[-2:] == ["-j", ACCT_CHAIN] for spec in specs):
            return
        # Detrás de los bloqueos y de la cuarentena: lo descartado no se cuenta
        position = await position_after("FORWARD", {CHAIN_FORWARD, CHAIN_QUARANTINE})
        ok, _ = await _run_iptables_async(["-I", "FORWARD", str(position), "-j", ACCT_CHAIN])
        if not ok:
            log.warning("traffic_meter.jump_failed")

    async def ensure_tracking(self, ip: str) -> None:
        """
        Garantiza que una IP tiene sus dos reglas de conteo instaladas en la
        cadena LANSENTINEL_ACCT. La cadena se vacía al arrancar, así que basta
        con el conjunto en memoria para no duplicarlas.
        """
        if ip in self._tracked_ips:
            return

        comment = f"{TRAFFIC_TAG}:{ip}"

        # Regla para tráfico SALIENTE (la IP es origen)
        ok1, _ = await _run_iptables_async([
            "-A", ACCT_CHAIN,
            "-s", ip,
            "-m", "comment", "--comment", comment,
        ])
        # Regla para tráfico ENTRANTE (la IP es destino)
        ok2, _ = await _run_iptables_async([
            "-A", ACCT_CHAIN,
            "-d", ip,
            "-m", "comment", "--comment", comment,
        ])
        if ok1 and ok2:
            self._tracked_ips.add(ip)
            self._samples[ip] = TrafficSample(ip=ip)
            log.info("traffic_meter.ip_tracked", ip=ip)
        else:
            log.warning("traffic_meter.tracking_failed", ip=ip)

    async def untrack(self, ip: str) -> None:
        """
        Retira las reglas de conteo de una IP que el dispositivo ha dejado de
        usar (cambio de IP). Así no se acumulan reglas de IPs antiguas.
        """
        comment = f"{TRAFFIC_TAG}:{ip}"
        ok, output = await _run_iptables_async(["-S", ACCT_CHAIN])
        if ok:
            for spec in parse_rule_specs(output):
                if comment_of(spec) == comment:
                    await _run_iptables_async(["-D"] + spec[1:])
        self._tracked_ips.discard(ip)
        self._samples.pop(ip, None)
        log.info("traffic_meter.ip_untracked", ip=ip)

    # ── Lectura de contadores ───────────────────────────────────────────────

    async def _loop(self, interval: int):
        """Lee los contadores periódicamente y actualiza las tasas."""
        while self._running:
            try:
                await self._read_counters()
            except Exception as exc:
                log.error("traffic_meter.loop_error", error=str(exc))
            await asyncio.sleep(interval)

    async def _read_counters(self) -> None:
        """
        Llama a `iptables -L LANSENTINEL_ACCT -v -n -x` para obtener los
        contadores actuales, calcula las nuevas tasas y acumula el tráfico
        del intervalo para el histórico.
        """
        ok, output = await _run_iptables_async(
            ["-L", ACCT_CHAIN, "-v", "-n", "-x"]
        )
        if not ok:
            return

        counters = parse_counters(output)
        now = time.monotonic()

        # Actualizar muestras
        for ip in self._tracked_ips:
            sample = self._samples.get(ip)
            if not sample:
                continue
            current = counters.get(ip, TrafficCounters())
            dt = now - sample.last_sample_at

            if dt > 0 and sample.last_sample_at > 0:
                # max(0, ...): si los contadores se reinician (cadena vaciada)
                # el intervalo cuenta como 0 en lugar de negativo
                delta = TrafficCounters(
                    rx_bytes=max(0, current.rx_bytes - sample.last_rx_bytes),
                    tx_bytes=max(0, current.tx_bytes - sample.last_tx_bytes),
                    rx_packets=max(0, current.rx_packets - sample.last_rx_packets),
                    tx_packets=max(0, current.tx_packets - sample.last_tx_packets),
                )
                sample.rx_bps = delta.rx_bytes / dt
                sample.tx_bps = delta.tx_bytes / dt
                self._pending.setdefault(ip, TrafficCounters()).add(delta)

            sample.last_rx_bytes = current.rx_bytes
            sample.last_tx_bytes = current.tx_bytes
            sample.last_rx_packets = current.rx_packets
            sample.last_tx_packets = current.tx_packets
            sample.last_sample_at = now

        total_rx = sum(s.rx_bps for s in self._samples.values())
        total_tx = sum(s.tx_bps for s in self._samples.values())
        self._total_history.append({
            "timestamp": now,
            "rx_bps": total_rx,
            "tx_bps": total_tx,
            "total_bps": total_rx + total_tx,
        })

    # ── Consulta ────────────────────────────────────────────────────────────

    def get_sample(self, ip: str) -> TrafficSample | None:
        return self._samples.get(ip)

    def get_all_samples(self) -> dict[str, TrafficSample]:
        return dict(self._samples)

    def drain_pending(self) -> dict[str, TrafficCounters]:
        """
        Devuelve el tráfico acumulado por IP desde la última llamada y lo pone
        a cero. Lo usa traffic_history para guardar el histórico en la BD.
        """
        pending, self._pending = self._pending, {}
        return {ip: c for ip, c in pending.items() if c.rx_bytes or c.tx_bytes}
    
    def get_total_history(self) -> list[dict]:
        """Devuelve el histórico de las últimas N muestras del total agregado.
        Cada entrada tiene timestamp (monotonic), rx_bps, tx_bps y total_bps."""
        # Recalculamos timestamps relativos para que el frontend sepa
        # cuántos segundos atrás es cada muestra
        now = time.monotonic()
        return [
            {
                "seconds_ago": round(now - entry["timestamp"], 1),
                "rx_bps": round(entry["rx_bps"], 2),
                "tx_bps": round(entry["tx_bps"], 2),
                "total_bps": round(entry["total_bps"], 2),
            }
            for entry in self._total_history
        ]


# Singleton importable desde main.py y monitor_service.py
traffic_meter = TrafficMeter()
