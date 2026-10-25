"""
Escáner de puertos basado en python-nmap.

Cumple dos casos de uso:
  1. Escaneo manual desde el frontend (POST /devices/{id}/scan).
  2. Escaneo automático al detectar un dispositivo nuevo en la red, si la
     opción 'scan_ports_on_discovery' está activa en settings.

El escaneo es síncrono (nmap es un proceso externo bloqueante), por lo que
se ejecuta en un ThreadPoolExecutor para no bloquear el event loop.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import nmap
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.network_usage import PortScan

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


# ── Escaneo síncrono (corre en thread) ────────────────────────────────────────

def _run_nmap_scan(ip: str, ports: str = "1-1024") -> ScanResult:
    """
    Ejecuta nmap contra una IP y devuelve los puertos detectados.

    'ports' acepta el formato de nmap: "1-1024", "22,80,443", etc.
    Por defecto se escanea el rango de puertos privilegiados (1-1024) que
    cubre la mayoría de servicios habituales en una red doméstica.
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
        return result
    except Exception as exc:
        log.error("port_scanner.error", ip=ip, error=str(exc))
        return result


# ── API pública async ─────────────────────────────────────────────────────────

async def scan_device(ip: str, ports: str = "1-1024") -> ScanResult:
    """Versión async del escaneo. Corre en thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_nmap_scan, ip, ports)


async def scan_and_persist(
    device_id: UUID,
    ip: str,
    db: AsyncSession,
    ports: str = "1-1024",
) -> ScanResult:
    """
    Escanea el dispositivo y persiste cada puerto encontrado en la BD.
    Retorna el resultado para que el endpoint pueda responder al frontend.
    """
    result = await scan_device(ip, ports=ports)

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

    await db.commit()
    return result
