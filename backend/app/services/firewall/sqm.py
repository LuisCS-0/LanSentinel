"""
Control de latencia en modo router (SQM con cake).

Cuando una descarga o una subida llena la conexión, los paquetes se acumulan
en la cola más lenta del camino (normalmente el router de la operadora, con
colas enormes) y la latencia de todo lo demás se dispara: el juego, la
videollamada o la web van a tirones aunque no les falte ancho de banda. Es el
"bufferbloat". En el laboratorio, con la WAN en pfifo_fast, saturar la subida
y la bajada a la vez llevó la latencia de un tráfico tipo juego de 2 a 12 ms
(30 ms en el 1 % peor) y el jitter de 0,4 a 3,8 ms.

La solución habitual es limitar el caudal un poco por debajo de lo contratado
para que la cola se forme aquí, donde cake la gestiona: reparte el enlace
entre flujos y entre dispositivos (dual-srchost/dual-dsthost con "nat", que
mira la tabla de NAT para saber qué equipo de casa hay detrás) y descarta
pronto lo que se acumula, así que los paquetes pequeños e interactivos no
esperan detrás de una descarga.

- Subida: cake en la propia WAN.
- Bajada: el tráfico que entra por la WAN se redirige a una interfaz ifb
  (lsifb0) y se le pone cake con "ingress" (cuenta también lo que descarta).
- Una velocidad 0 deja esa dirección sin límite: cake solo reparte la cola.

Como las reglas de iptables, sobrevive a un reinicio del backend; se quita al
apagar el modo router o el control de latencia.
"""

import asyncio
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

IFB = "lsifb0"
COMMAND_TIMEOUT = 10
_ALREADY_THERE_OK = (["ip", "link", "add"], ["tc", "filter", "replace"])


@dataclass
class SqmStatus:
    enabled: bool = False             # pedido en los ajustes
    active: bool = False              # aplicado
    download_mbps: int = 0
    upload_mbps: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _rate(mbps: int) -> list[str]:
    return ["bandwidth", f"{mbps}mbit"] if mbps > 0 else ["unlimited"]


def plan(wan: str, download_mbps: int, upload_mbps: int) -> list[list[str]]:
    """Órdenes para aplicarlo (función pura). Todas idempotentes salvo crear la ifb."""
    return [
        ["tc", "qdisc", "replace", "dev", wan, "root", "cake", *_rate(upload_mbps),
         "besteffort", "dual-srchost", "nat"],
        ["ip", "link", "add", IFB, "type", "ifb"],
        ["ip", "link", "set", IFB, "up"],
        ["tc", "qdisc", "replace", "dev", wan, "handle", "ffff:", "ingress"],
        # matchall no admite cambiar un filtro que ya existe ("File exists"):
        # al reaplicar se deja el que hay, que es siempre el mismo (a la ifb)
        ["tc", "filter", "replace", "dev", wan, "parent", "ffff:", "protocol", "all", "prio", "10",
         "handle", "1", "matchall", "action", "mirred", "egress", "redirect", "dev", IFB],
        ["tc", "qdisc", "replace", "dev", IFB, "root", "cake", *_rate(download_mbps),
         "besteffort", "dual-dsthost", "nat", "wash", "ingress"],
    ]


def teardown(wan: str) -> list[list[str]]:
    """Órdenes para quitarlo (función pura): la WAN vuelve a su cola por defecto."""
    return [
        ["tc", "qdisc", "del", "dev", wan, "root"],
        ["tc", "qdisc", "del", "dev", wan, "ingress"],
        ["ip", "link", "del", IFB],
    ]


async def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(proc.communicate(), COMMAND_TIMEOUT)
        return proc.returncode == 0, err.decode(errors="replace").strip()
    except (OSError, asyncio.TimeoutError) as exc:
        return False, str(exc)


class SqmService:
    def __init__(self):
        self._status = SqmStatus()
        self._wan: str | None = None

    def status(self) -> dict:
        return self._status.to_dict()

    async def apply(self, enabled: bool, wan: str, download_mbps: int, upload_mbps: int) -> None:
        """Lo pone o lo quita según los ajustes y el estado del modo router."""
        self._status = SqmStatus(enabled=enabled, download_mbps=download_mbps, upload_mbps=upload_mbps)
        if not enabled or not wan:
            await self.remove()
            return
        if self._wan and self._wan != wan:
            await self.remove()
        for cmd in plan(wan, download_mbps, upload_mbps):
            ok, err = await _run(cmd)
            # Al reaplicar (cambio de velocidades, reinicio) la ifb y el filtro
            # que lleva a ella ya existen y no cambian nunca
            if not ok and not (cmd[:3] in _ALREADY_THERE_OK and "exists" in err):
                self._status.error = f"No se pudo aplicar ({' '.join(cmd[:3])}): {err or 'error desconocido'}"
                log.error("sqm.apply_failed", cmd=cmd, error=err)
                await self.remove()
                return
        self._wan = wan
        self._status.active = True
        log.info("sqm.applied", wan=wan, download_mbps=download_mbps, upload_mbps=upload_mbps)

    async def remove(self) -> None:
        wan = self._wan
        self._wan = None
        self._status.active = False
        if not wan:
            # Tras reiniciar el backend no se sabe si estaba puesto: se mira la ifb
            ok, _ = await _run(["ip", "link", "show", IFB])
            if not ok:
                return
            from app.core.config import settings
            wan = settings.WAN_INTERFACE.strip()
            if not wan:
                return
        for cmd in teardown(wan):
            await _run(cmd)                       # lo que no esté puesto da error y no importa
        log.info("sqm.removed", wan=wan)


sqm = SqmService()
