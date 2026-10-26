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
    # Interfaz de la LAN: la que se vigila y, en modo router, la de los dispositivos
    MONITOR_INTERFACE: str = "eth0"
    MONITOR_INTERVAL_SECONDS: int = 30
    # Modo router: LanSentinel enruta entre WAN_INTERFACE (hacia el router de
    # la operadora) y MONITOR_INTERFACE, con NAT, la WAN cerrada a conexiones
    # entrantes y DHCP/DNS (dnsmasq). El reenvío del sistema lo activa
    # scripts/instalar.sh. ROUTER_MODE es el estado inicial: luego se enciende
    # y apaga desde el panel (si cambia en .env, manda en el siguiente arranque)
    ROUTER_MODE: bool = False
    WAN_INTERFACE: str = ""
    # DHCP y DNS en modo router (False si ya los da otro equipo de la LAN)
    ROUTER_DHCP: bool = True
    DHCP_RANGE_START: str = ""      # por defecto .100 de la red de la LAN
    DHCP_RANGE_END: str = ""        # por defecto .199
    DHCP_LEASE_TIME: str = "12h"
    DNS_UPSTREAM: str = "1.1.1.1,9.9.9.9"
    LOCAL_DOMAIN: str = "lan"

    # Histórico de tráfico
    # Cada cuántos segundos se guarda en BD el tráfico acumulado por dispositivo
    TRAFFIC_HISTORY_INTERVAL_SECONDS: int = 60
    # Días que se conservan los datos por minuto y los agregados por hora
    TRAFFIC_RAW_RETENTION_DAYS: int = 7
    TRAFFIC_HOURLY_RETENTION_DAYS: int = 365
    # Zona horaria para agrupar el consumo por días en las gráficas
    TIMEZONE: str = "Europe/Madrid"

    # Fabricantes (OUI)
    # Lista pública del IEEE descargada al equipo y renovada cada N días
    OUI_DB_PATH: str = "/var/lib/lansentinel/oui.csv"
    OUI_DOWNLOAD_URL: str = "https://standards-oui.ieee.org/oui/oui.csv"
    OUI_MAX_AGE_DAYS: int = 30
    # Consultar macvendors.com para los prefijos que no estén en la lista
    # local. Desactivado por defecto: enviaría las MACs de la red a un tercero
    OUI_ONLINE_LOOKUP: bool = False

    # Suricata
    SURICATA_LOG_PATH: str = "/var/log/suricata/eve.json"
    SURICATA_OFFSET_PATH: str = "/var/lib/lansentinel/suricata.offset"
    # Ignorar las alertas de reconocimiento (escaneos) cuyo origen es el propio
    # LanSentinel: las provoca su escaneo de puertos de los dispositivos nuevos
    SURICATA_IGNORE_OWN_SCANS: bool = True

    # Escaneo periódico de puertos (0 lo desactiva)
    PORT_SCAN_INTERVAL_HOURS: int = 24
    # Solo se escanean los dispositivos vistos en estas últimas horas
    PORT_SCAN_ACTIVE_HOURS: int = 24

    # Detección de ARP spoofing (escucha pasiva de ARP en MONITOR_INTERFACE)
    ARP_SPOOF_DETECTION: bool = True
    # Una IP que alterna entre dos MAC dentro de esta ventana es un conflicto
    ARP_CONFLICT_WINDOW_SECONDS: int = 300
    # MAC de referencia de la puerta de enlace
    ARP_BASELINE_PATH: str = "/var/lib/lansentinel/arp_baseline.json"

    # Alertas
    # Ventana (segundos) en la que los eventos repetidos con la misma huella
    # se agrupan en una sola alerta. 0 desactiva la agrupación.
    ALERT_DEDUP_WINDOW_SECONDS: int = 600

    # Avisos por canales externos (solo alertas nuevas)
    # Severidad mínima que se avisa: info | low | medium | high | critical
    NOTIFY_MIN_SEVERITY: str = "high"
    # Límite de avisos por hora; el resto se resume en un aviso posterior
    NOTIFY_MAX_PER_HOUR: int = 20
    # URL del panel para incluir un enlace en los avisos (p. ej. http://192.168.1.10:3000)
    PANEL_URL: str = ""
    # Telegram: token de @BotFather y chat al que escribir
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    # ntfy (notificaciones push en el móvil): servidor, tema y token opcional
    NTFY_SERVER: str = "https://ntfy.sh"
    NTFY_TOPIC: str = ""
    NTFY_TOKEN: str = ""
    # Correo (SMTP). SMTP_SECURITY: starttls | ssl | none. SMTP_TO admite varias
    # direcciones separadas por comas
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_SECURITY: str = "starttls"
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TO: str = ""

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
