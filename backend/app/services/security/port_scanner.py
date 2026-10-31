"""
Escáner de puertos basado en python-nmap.

Cumple tres casos de uso:
  1. Escaneo manual desde el frontend (POST /devices/{id}/scan).
  2. Escaneo automático al detectar un dispositivo nuevo en la red.
  3. Escaneo periódico de todos los dispositivos (scan_scheduler).

Tras cada escaneo completo (con los puertos por defecto) se compara con el
anterior y se avisa de servicios inseguros y puertos nuevos
(insecure_services.py). Los escaneos con un rango a medida se guardan pero
no sirven de referencia para esa comparación.

El escaneo es síncrono (nmap es un proceso externo bloqueante), por lo que
se ejecuta en un ThreadPoolExecutor para no bloquear el event loop.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import nmap
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.network_usage import PortScan
from app.services.security.insecure_services import (
    DEFAULT_SCAN_PORTS, compare_scans, report_findings,
)

log = structlog.get_logger(__name__)


@dataclass
class ScannedPort:
    """Representa un puerto detectado por nmap."""
    port: int
    protocol: str           # tcp | udp
    state: str              # open | closed | filtered
    service: str | None = None
    version: str | None = None


@dataclass
class ScanResult:
    """Resultado completo de un escaneo a un dispositivo."""
    ip: str
    ports: list[ScannedPort] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # False si nmap falló o el equipo no respondió: el resultado vacío no
    # significa "sin puertos abiertos" y no debe guardarse como tal
    ok: bool = True


# ── Escaneo síncrono (corre en thread) ────────────────────────────────────────

def _run_nmap_scan(ip: str, ports: str = DEFAULT_SCAN_PORTS) -> ScanResult:
    """
    Ejecuta nmap contra una IP y devuelve los puertos detectados.

    'ports' acepta el formato de nmap: "1-1024", "22,80,443", etc.
    Por defecto se escanean los puertos privilegiados (1-1024) más los de
    servicios que suelen quedar expuestos en casa (DEFAULT_SCAN_PORTS).
    """
    result = ScanResult(ip=ip)
    try:
        scanner = nmap.PortScanner()
        # -sT: scan TCP connect (no requiere root)
        # -sV: detección de versión del servicio
        # -T4: timing agresivo pero razonable
        scanner.scan(ip, ports=ports, arguments="-sT -sV -T4")

        if ip not in scanner.all_hosts():
            log.warning("port_scanner.host_unreachable", ip=ip)
            result.ok = False
            return result

        host_data = scanner[ip]
        for proto in host_data.all_protocols():
            for port in host_data[proto].keys():
                port_data = host_data[proto][port]
                result.ports.append(
                    ScannedPort(
                        port=port,
                        protocol=proto,
                        state=port_data.get("state", "unknown"),
                        service=port_data.get("name") or None,
                        version=(port_data.get("product", "") + " "
                                 + port_data.get("version", "")).strip() or None,
                    )
                )

        log.info("port_scanner.scan_done", ip=ip, ports_found=len(result.ports))
        return result

    except nmap.PortScannerError as exc:
        log.error("port_scanner.nmap_error", ip=ip, error=str(exc))
        result.ok = False
        return result
    except Exception as exc:
        log.error("port_scanner.error", ip=ip, error=str(exc))
        result.ok = False
        return result


# ── API pública async ─────────────────────────────────────────────────────────

async def scan_device(ip: str, ports: str = DEFAULT_SCAN_PORTS) -> ScanResult:
    """Versión async del escaneo. Corre en thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_nmap_scan, ip, ports)


async def _reference_open_ports(db: AsyncSession, device: Device) -> set[int] | None:
    """
    Puertos abiertos en el último escaneo completo del dispositivo, o None si
    nunca se ha hecho uno (las instalaciones anteriores no lo registraban).
    """
    if device.last_port_scan_at is None:
        return None
    result = await db.execute(
        select(PortScan.port).where(
            PortScan.device_id == device.id,
            PortScan.scanned_at == device.last_port_scan_at,
            PortScan.state == "open",
        )
    )
    return set(result.scalars().all())


async def scan_and_persist(
    device_id: UUID,
    ip: str,
    db: AsyncSession,
    ports: str = DEFAULT_SCAN_PORTS,
) -> ScanResult:
    """
    Escanea el dispositivo y persiste cada puerto encontrado en la BD.
    Si es un escaneo completo, lo compara con el anterior y genera las
    alertas de servicios inseguros y puertos nuevos.
    Retorna el resultado para que el endpoint pueda responder al frontend.
    """
    device = (await db.execute(select(Device).where(Device.id == device_id))).scalar_one_or_none()
    if device is None:
        return ScanResult(ip=ip, ok=False)

    full_scan = ports == DEFAULT_SCAN_PORTS
    previous_open = await _reference_open_ports(db, device) if full_scan else None
    # Se cierra la transacción de lectura antes de esperar a nmap: si no, la
    # conexión a la BD queda ocupada todo el escaneo (y lo que espera en la
    # cola). Con muchos dispositivos nuevos a la vez agotaba el pool y el
    # panel respondía 500 hasta que acababan. La sesión no expira los
    # objetos al confirmar, así que device sigue valiendo para guardar.
    await db.commit()

    result = await scan_device(ip, ports=ports)
    if not result.ok:
        return result

    for port in result.ports:
        scan_record = PortScan(
            device_id=device_id,
            port=port.port,
            protocol=port.protocol,
            state=port.state,
            service=port.service,
            version=port.version,
            scanned_at=result.scanned_at,
        )
        db.add(scan_record)

    if full_scan:
        # Se registra aunque no haya puertos: "sin puertos abiertos" también es
        # un resultado, y marca cuándo toca el siguiente escaneo periódico
        device.last_port_scan_at = result.scanned_at
    await db.commit()

    if full_scan:
        findings = compare_scans(
            previous_open,
            [(p.port, p.service) for p in result.ports if p.state == "open"],
        )
        name = device.hostname or device.vendor or device.mac
        await report_findings(db, device_id, f"{name} ({ip})", findings)
    return result


async def latest_scan_time(db: AsyncSession, device: Device):
    """
    Momento del último escaneo con resultados que mostrar: el más reciente
    con filas guardadas, salvo que después haya un escaneo completo sin
    ningún puerto (entonces no hay nada que mostrar).
    """
    rows_at = (await db.execute(
        select(func.max(PortScan.scanned_at)).where(PortScan.device_id == device.id)
    )).scalar()
    if device.last_port_scan_at and (rows_at is None or device.last_port_scan_at > rows_at):
        return None
    return rows_at
