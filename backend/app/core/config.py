from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://lansentinel:lansentinel_pass@db:5432/lansentinel"

    # Aplicación
    ENVIRONMENT: str = "production"
    # Clave para firmar los tokens de sesión (JWT). Si no se define o es
    # demasiado corta, se genera una y se guarda en SECRET_KEY_PATH.
    SECRET_KEY: str = ""
    SECRET_KEY_PATH: str = "/var/lib/lansentinel/secret_key"
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

    # Autenticación del panel
    # Primer administrador: se crea al arrancar si no hay ningún usuario. Sin
    # ADMIN_PASSWORD se genera una aleatoria y se guarda en INITIAL_PASSWORD_PATH.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""
    INITIAL_PASSWORD_PATH: str = "/var/lib/lansentinel/initial_admin_password"
    # Duración de la sesión
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    # Marcar la cookie de sesión como Secure (solo viaja por HTTPS). Actívalo
    # si sirves el panel detrás de un proxy con TLS.
    SESSION_COOKIE_SECURE: bool = False
    # Bloqueo temporal tras varios intentos de login fallidos
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 300
    # Proxies cuya cabecera X-Real-IP se acepta como IP real del cliente (el
    # nginx del frontend llega desde la red de Docker). Desde otras IPs la
    # cabecera se ignora para que no se pueda falsificar.
    TRUSTED_PROXIES: List[str] = ["127.0.0.1/32", "172.16.0.0/12"]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
