"""
Medidor de tráfico por dispositivo.

Aprovecha los contadores que iptables mantiene automáticamente sobre cada
regla para medir, en bytes y paquetes, cuánto tráfico ha pasado a través
de ella. La estrategia:

1. Por cada dispositivo conocido, añadimos dos reglas "fantasma" en la
   cadena FORWARD:
     - Una con su IP como origen (tráfico SALIENTE del dispositivo)
     - Una con su IP como destino (tráfico ENTRANTE al dispositivo)
   Las reglas no llevan -j (jump), por lo que SOLO incrementan contadores;
   no afectan al enrutamiento real.

2. Cada N segundos, leemos los contadores y calculamos la tasa actual:
       rate = (bytes_now - bytes_anterior) / (tiempo_now - tiempo_anterior)

3. La tasa se mantiene en un diccionario en memoria, indexado por IP,
   y se expone vía endpoint REST.

La unidad almacenada internamente son bytes/segundo; el endpoint puede
convertir a KB/s o Mbps según prefiera el frontend.
"""

import asyncio
import re
import subprocess
import time
from dataclasses import dataclass
from collections import deque
import structlog

log = structlog.get_logger(__name__)


# Marca de comentario para identificar reglas de medición de LanSentinel
TRAFFIC_TAG = "lansentinel-traffic"


# ─── Tipos auxiliares ────────────────────────────────────────────────────────

@dataclass
class TrafficSample:
    """Última muestra de tráfico de un dispositivo."""
    ip: str
    rx_bps: float = 0.0     # bytes/segundo entrantes
    tx_bps: float = 0.0     # bytes/segundo salientes
    last_rx_bytes: int = 0
    last_tx_bytes: int = 0
    last_sample_at: float = 0.0

    @property
    def total_bps(self) -> float:
        return self.rx_bps + self.tx_bps


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
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_iptables, args)


# ─── Servicio principal ──────────────────────────────────────────────────────

class TrafficMeter:
    """
    Singleton que mantiene reglas-contador en FORWARD y calcula tasas.
    El bucle se arranca desde monitor_service.
    """

    def __init__(self):
        # IP → última muestra
        self._samples: dict[str, TrafficSample] = {}
        # IPs que actualmente tienen reglas de medición instaladas
        self._tracked_ips: set[str] = set()
        self._running: bool = False
        self._task: asyncio.Task | None = None
        self._total_history: deque = deque(maxlen=120)

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    async def start(self, interval_seconds: int = 5):
        """Arranca el bucle periódico de lectura de contadores."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(interval_seconds))
        log.info("traffic_meter.started", interval=interval_seconds)

    async def stop(self):
        """Detiene el bucle. Las reglas de iptables NO se eliminan,
        para que sigan contando si el servicio se reinicia."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("traffic_meter.stopped")

    # ── Gestión de reglas ───────────────────────────────────────────────────

    async def ensure_tracking(self, ip: str) -> None:
        """
        Garantiza que una IP tiene sus dos reglas de conteo instaladas.

        IMPORTANTE: usamos -I (insert al principio) en lugar de -A (append),
        porque las reglas ACCEPT posteriores en FORWARD harían que los
        paquetes nunca llegaran a evaluarse contra nuestras reglas de conteo.
        Además, antes de insertar comprobamos si ya existe la regla para
        evitar duplicados al reiniciar el backend.
        """
        if ip in self._tracked_ips:
            return

        comment = f"{TRAFFIC_TAG}:{ip}"

        # Comprobar primero si ya existen reglas con este comentario
        ok_check, output = await _run_iptables_async(
            ["-L", "FORWARD", "-n"]
        )
        if ok_check and comment in output:
            # Ya hay reglas previas, simplemente marcar como rastreado
            self._tracked_ips.add(ip)
            self._samples[ip] = TrafficSample(ip=ip)
            log.info("traffic_meter.ip_already_tracked", ip=ip)
            return

        # Regla para tráfico SALIENTE (la IP es origen)
        ok1, _ = await _run_iptables_async([
            "-I", "FORWARD", "1",
            "-s", ip,
            "-m", "comment", "--comment", comment,
        ])
        # Regla para tráfico ENTRANTE (la IP es destino)
        ok2, _ = await _run_iptables_async([
            "-I", "FORWARD", "1",
            "-d", ip,
            "-m", "comment", "--comment", comment,
        ])
        if ok1 and ok2:
            self._tracked_ips.add(ip)
            self._samples[ip] = TrafficSample(ip=ip)
            log.info("traffic_meter.ip_tracked", ip=ip)
        else:
            log.warning("traffic_meter.tracking_failed", ip=ip)

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
        Llama a `iptables -L FORWARD -v -n -x` para obtener los contadores
        actuales y calcula las nuevas tasas.
 
        El formato de salida es:
            pkts    bytes  target  prot opt in  out src           dst           opciones...
 
        Como las reglas no tienen -j (target), el campo 'target' aparece
        vacío. Para identificar si es regla origen o destino, miramos qué
        columna contiene 0.0.0.0/0:
            - 0.0.0.0/0 en src → es regla "-d <ip>" → tráfico ENTRANTE
            - 0.0.0.0/0 en dst → es regla "-s <ip>" → tráfico SALIENTE
        """
        ok, output = await _run_iptables_async(
            ["-L", "FORWARD", "-v", "-n", "-x"]
        )
        if not ok:
            return
 
        rx_bytes: dict[str, int] = {}
        tx_bytes: dict[str, int] = {}
 
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
                byte_count = int(parts[1])
            except ValueError:
                continue
 
            # Localizar 0.0.0.0/0 en la línea para determinar tipo de regla
            try:
                wildcard_idx = parts.index("0.0.0.0/0")
            except ValueError:
                continue
 
            # La IP del dispositivo aparece justo antes o después de 0.0.0.0/0
            # Si 0.0.0.0/0 viene antes de la IP → la IP está en dst → ENTRANTE
            # Si 0.0.0.0/0 viene después de la IP → la IP está en src → SALIENTE
            if wildcard_idx + 1 < len(parts) and parts[wildcard_idx + 1] == ip:
                # 0.0.0.0/0 → ip   ⇒ regla "-d ip" ⇒ tráfico hacia la IP
                rx_bytes[ip] = rx_bytes.get(ip, 0) + byte_count
            elif wildcard_idx - 1 >= 0 and parts[wildcard_idx - 1] == ip:
                # ip → 0.0.0.0/0  ⇒ regla "-s ip" ⇒ tráfico desde la IP
                tx_bytes[ip] = tx_bytes.get(ip, 0) + byte_count
 
        now = time.monotonic()
 
        # Actualizar muestras
        for ip in self._tracked_ips:
            sample = self._samples.get(ip)
            if not sample:
                continue
            new_rx = rx_bytes.get(ip, 0)
            new_tx = tx_bytes.get(ip, 0)
            dt = now - sample.last_sample_at
 
            if dt > 0 and sample.last_sample_at > 0:
                d_rx = max(0, new_rx - sample.last_rx_bytes)
                d_tx = max(0, new_tx - sample.last_tx_bytes)
                sample.rx_bps = d_rx / dt
                sample.tx_bps = d_tx / dt
 
            sample.last_rx_bytes = new_rx
            sample.last_tx_bytes = new_tx
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
