"""
Catálogo de servicios inseguros y evaluación de los escaneos de puertos.

Tras cada escaneo de un dispositivo se comparan sus puertos abiertos con los
del escaneo anterior:
  - Servicio inseguro recién abierto (o visto por primera vez): alerta con la
    severidad del servicio más grave y una explicación de cada uno.
  - Otros puertos que no estaban abiertos en el escaneo anterior: alerta baja
    "Nuevos puertos abiertos" (puede ser un servicio legítimo nuevo o una
    puerta trasera). En el primer escaneo de un dispositivo no se avisa de
    estos, para no generar ruido con todo lo que ya tenía.
Lo que ya estaba abierto en el escaneo anterior no vuelve a avisar.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertSeverity, AlertSource
from app.services.alerts.alert_service import create_alert


@dataclass(frozen=True)
class ServiceRisk:
    severity: AlertSeverity
    reason: str


# Puertos que se escanean por defecto: los privilegiados (1-1024) más los de
# servicios que suelen quedar expuestos en redes domésticas
DEFAULT_SCAN_PORTS = (
    "1-1024,1433,1521,1883,2049,2323,3306,3389,5000,5432,5555,5900,5901,"
    "6379,8080,8443,8888,9200,11211,27017"
)

_M, _H = AlertSeverity.medium, AlertSeverity.high

RISKS_BY_PORT: dict[int, ServiceRisk] = {
    21:    ServiceRisk(_M, "FTP: el usuario y la contraseña viajan sin cifrar."),
    23:    ServiceRisk(_H, "Telnet: acceso remoto sin cifrar, muy atacado por botnets de IoT (Mirai)."),
    2323:  ServiceRisk(_H, "Telnet en puerto alternativo, típico de cámaras y routers con firmware vulnerable."),
    69:    ServiceRisk(_M, "TFTP: transferencia de ficheros sin autenticación."),
    111:   ServiceRisk(_M, "RPCbind: expone qué servicios RPC/NFS ofrece el equipo."),
    139:   ServiceRisk(_M, "NetBIOS: compartición de Windows; ha sido vía de gusanos como WannaCry."),
    445:   ServiceRisk(_M, "SMB: compartición de archivos de Windows; revisa que no tenga carpetas abiertas sin contraseña."),
    873:   ServiceRisk(_M, "rsync: puede permitir leer o escribir ficheros sin autenticación."),
    1433:  ServiceRisk(_M, "Base de datos SQL Server accesible por red."),
    1521:  ServiceRisk(_M, "Base de datos Oracle accesible por red."),
    1883:  ServiceRisk(_M, "MQTT sin cifrar, habitual en domótica y a menudo sin contraseña."),
    2049:  ServiceRisk(_M, "NFS: carpetas compartidas que pueden montarse desde otros equipos."),
    3306:  ServiceRisk(_M, "Base de datos MySQL/MariaDB accesible por red."),
    3389:  ServiceRisk(_M, "Escritorio remoto (RDP): objetivo frecuente de fuerza bruta."),
    5432:  ServiceRisk(_M, "Base de datos PostgreSQL accesible por red."),
    5555:  ServiceRisk(_H, "ADB de Android por red: permite controlar el dispositivo por completo."),
    5900:  ServiceRisk(_H, "VNC: escritorio remoto, a menudo sin contraseña o con una débil."),
    5901:  ServiceRisk(_H, "VNC: escritorio remoto, a menudo sin contraseña o con una débil."),
    6379:  ServiceRisk(_H, "Redis: sin autenticación por defecto; permite leer y modificar datos."),
    9200:  ServiceRisk(_H, "Elasticsearch: API sin autenticación por defecto."),
    11211: ServiceRisk(_M, "Memcached: sin autenticación; usado en ataques de amplificación."),
    27017: ServiceRisk(_H, "MongoDB: versiones antiguas sin autenticación por defecto."),
}

# Por nombre de servicio que detecta nmap (-sV), para cuando corre en otro puerto
RISKS_BY_SERVICE: dict[str, ServiceRisk] = {
    "telnet": RISKS_BY_PORT[23],
    "ftp": RISKS_BY_PORT[21],
    "vnc": RISKS_BY_PORT[5900],
    "ms-wbt-server": RISKS_BY_PORT[3389],
    "microsoft-ds": RISKS_BY_PORT[445],
    "netbios-ssn": RISKS_BY_PORT[139],
    "redis": RISKS_BY_PORT[6379],
    "mongodb": RISKS_BY_PORT[27017],
    "mqtt": RISKS_BY_PORT[1883],
    "adb": RISKS_BY_PORT[5555],
}

_SEVERITY_ORDER = [AlertSeverity.info, AlertSeverity.low, AlertSeverity.medium, AlertSeverity.high, AlertSeverity.critical]


def assess(port: int, service: str | None) -> ServiceRisk | None:
    """Riesgo de un puerto abierto, por número de puerto o por servicio detectado."""
    risk = RISKS_BY_PORT.get(port)
    if risk is None and service:
        risk = RISKS_BY_SERVICE.get(service.lower())
    return risk


@dataclass
class ScanFindings:
    insecure: list[tuple[int, str | None, ServiceRisk]]   # (puerto, servicio, riesgo)
    new_ports: list[tuple[int, str | None]]               # otros puertos nuevos


def compare_scans(
    previous_open: set[int] | None,
    current_open: list[tuple[int, str | None]],
) -> ScanFindings:
    """
    Compara los puertos abiertos ahora con los del escaneo anterior
    (None si es el primer escaneo del dispositivo).
    """
    known = previous_open or set()
    insecure, new_ports = [], []
    for port, service in sorted(current_open):
        if port in known:
            continue
        risk = assess(port, service)
        if risk:
            insecure.append((port, service, risk))
        elif previous_open is not None:
            new_ports.append((port, service))
    return ScanFindings(insecure=insecure, new_ports=new_ports)


async def report_findings(db: AsyncSession, device_id: UUID, device_name: str, findings: ScanFindings) -> None:
    """Registra las alertas de un escaneo (como mucho una de cada tipo)."""
    if findings.insecure:
        severity = max((risk.severity for *_, risk in findings.insecure), key=_SEVERITY_ORDER.index)
        lines = [
            f"- {port}/tcp{f' ({service})' if service else ''}: {risk.reason}"
            for port, service, risk in findings.insecure
        ]
        await create_alert(
            db,
            device_id=device_id,
            severity=severity,
            source=AlertSource.monitor,
            title=f"Servicios inseguros expuestos en {device_name}",
            description=(
                "El escaneo de puertos ha encontrado servicios con riesgo:\n" + "\n".join(lines) +
                "\nSi no los usas, desactívalos en el dispositivo; si los necesitas, protégelos "
                "con contraseña y no los expongas a Internet."
            ),
            raw_payload={"ports": [p for p, *_ in findings.insecure]},
            fingerprint=f"insecure_services:{device_id}",
        )

    if findings.new_ports:
        ports = ", ".join(f"{p}/tcp{f' ({s})' if s else ''}" for p, s in findings.new_ports)
        await create_alert(
            db,
            device_id=device_id,
            severity=AlertSeverity.low,
            source=AlertSource.monitor,
            title=f"Nuevos puertos abiertos en {device_name}",
            description=(
                f"Desde el escaneo anterior se han abierto: {ports}. Puede ser un servicio "
                f"nuevo que hayas instalado o algo que no esperas."
            ),
            raw_payload={"ports": [p for p, _ in findings.new_ports]},
            fingerprint=f"new_ports:{device_id}",
        )
