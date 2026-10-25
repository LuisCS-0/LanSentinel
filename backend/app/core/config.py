from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://lansentinel:lansentinel_pass@db:5432/lansentinel"

    # Aplicación
    ENVIRONMENT: str = "production"
    # Secret key (no usada por el momento)
    SECRET_KEY: str = "lansentinelSK"
    # Cors (usadas en desarrollo con vite)
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    LOG_LEVEL: str = "warning"

    # Red
    MONITOR_INTERFACE: str = "eth0"
    MONITOR_INTERVAL_SECONDS: int = 30

    # Suricata
    SURICATA_LOG_PATH: str = "/var/log/suricata/eve.json"
    SURICATA_OFFSET_PATH: str = "/var/lib/lansentinel/suricata.offset"
    # Ignorar las alertas de reconocimiento (escaneos) cuyo origen es el propio
    # LanSentinel: las provoca su escaneo de puertos de los dispositivos nuevos
    SURICATA_IGNORE_OWN_SCANS: bool = True

    # Alertas
    # Ventana (segundos) en la que los eventos repetidos con la misma huella
    # se agrupan en una sola alerta. 0 desactiva la agrupación.
    ALERT_DEDUP_WINDOW_SECONDS: int = 600

    # Firewall
    # True -> Bloquea Ip ante alerta crítica
    FIREWALL_AUTO_BLOCK_CRITICAL: bool = True
    # IPs o rangos CIDR que nunca se bloquean, además de las del propio
    # equipo y su puerta de enlace. En .env como JSON: ["192.168.1.2", "10.0.0.0/24"]
    FIREWALL_NEVER_BLOCK: List[str] = []

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
