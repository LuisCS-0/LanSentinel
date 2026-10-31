from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


# Versión de LanSentinel (API, /health y manifiesto de las copias)
VERSION = "1.16.0"


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
    # Control de latencia en modo router (services/firewall/sqm.py): cake con
    # el caudal un poco por debajo de lo contratado (0: esa dirección sin límite)
    SQM_ENABLED: bool = False
    SQM_DOWNLOAD_MBPS: int = 0
    SQM_UPLOAD_MBPS: int = 0
    # IPv6 en la LAN (solo en modo router; services/firewall/ipv6_lan.py).
    # El prefijo de la LAN sale, por este orden, de IPV6_PREFIX (un /64 fijo
    # que la operadora enruta hacia este equipo), de un prefijo delegado por
    # DHCPv6-PD en la WAN o, si la operadora no delega ninguno, de una ULA
    # propia con NAT66 (IPV6_NAT_FALLBACK). Apagado, no se reenvía IPv6.
    IPV6_LAN: bool = False
    IPV6_PREFIX: str = ""
    IPV6_PD: bool = True
    IPV6_NAT_FALLBACK: bool = True

    # Histórico de tráfico
    # Cada cuántos segundos se guarda en BD el tráfico acumulado por dispositivo
    TRAFFIC_HISTORY_INTERVAL_SECONDS: int = 60
    # Días que se conservan los datos por minuto y los agregados por hora
    TRAFFIC_RAW_RETENTION_DAYS: int = 7
    TRAFFIC_HOURLY_RETENTION_DAYS: int = 365
    # Zona horaria para agrupar el consumo por días en las gráficas
    TIMEZONE: str = "Europe/Madrid"

    # Anomalías de tráfico (services/monitor/anomalies): picos de consumo
    # respecto a lo habitual de cada dispositivo, hora a hora
    ANOMALY_DETECTION_ENABLED: bool = True
    # Días de historia con los que se calcula lo habitual
    ANOMALY_BASELINE_DAYS: int = 14
    # Horas con actividad que necesita un dispositivo antes de juzgarlo
    ANOMALY_MIN_HISTORY_HOURS: int = 48
    # Cuántas veces lo habitual tiene que ser una hora para ser un pico
    ANOMALY_FACTOR: float = 5.0
    # Mínimo en una hora para avisar (por debajo no merece la pena)
    ANOMALY_UPLOAD_MIN_MB: int = 100
    ANOMALY_DOWNLOAD_MIN_MB: int = 2048

    # Copias de seguridad (services/backup). Se guardan en
    # /var/lib/lansentinel/backups dentro del contenedor; en el equipo, en
    # BACKUP_PATH (docker-compose.yml), p. ej. un disco USB.
    # Hora local de la copia diaria; -1 desactiva las copias automáticas
    BACKUP_HOUR: int = 3
    # Rotación: las N copias más recientes y, de las anteriores, una por
    # semana durante M semanas más
    BACKUP_KEEP_DAILY: int = 7
    BACKUP_KEEP_WEEKLY: int = 4
    # Carpeta del equipo donde se guardan (la monta docker-compose.yml); aquí
    # solo se usa para mostrarla en el panel
    BACKUP_PATH: str = ""
    # Carpeta del proyecto (solo lectura) para incluir el .env en la copia
    PROJECT_DIR: str = "/run/lansentinel/proyecto"

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

    # Dominios y huellas TLS por dispositivo (services/security/domain_tracker):
    # qué dominios usa cada equipo (DNS y SNI) y con qué programas (JA4/JA3).
    # Es su historial de navegación: se borra a los N días sin verse
    DOMAIN_TRACKING_ENABLED: bool = True
    DOMAIN_HISTORY_DAYS: int = 30

    # Registro de acciones (services/auth/audit): días que se guarda
    AUDIT_LOG_DAYS: int = 365

    # Auditoría con IA (services/ai_audit): qué incluye la instantánea de la
    # red. Por defecto, sin nombres de red ni historial de dominios: cada
    # dispositivo va como "disp-NN" con su fabricante
    AI_AUDIT_INCLUDE_NAMES: bool = False
    AI_AUDIT_INCLUDE_DOMAINS: bool = False
    AI_AUDIT_ALERT_DAYS: int = 30
    # Proveedor y modelo (services/ai_audit/providers): anthropic, openai o
    # compatible (API de OpenAI en otra dirección: Ollama, LM Studio...).
    # Vacío: sin auditoría. La clave nunca se devuelve por la API; vacía, se
    # usa ANTHROPIC_API_KEY u OPENAI_API_KEY (los compatibles locales no
    # suelen pedirla). Sin modelo, Claude usa claude-opus-5-5; los demás lo
    # necesitan
    AI_AUDIT_PROVIDER: str = ""
    AI_AUDIT_MODEL: str = ""
    AI_AUDIT_API_KEY: str = ""
    AI_AUDIT_BASE_URL: str = ""               # solo compatible: http://equipo:11434/v1
    AI_AUDIT_EFFORT: str = "high"             # low | medium | high | xhigh | max
    AI_AUDIT_TIMEOUT_SECONDS: int = 600
    # Modo compacto (modelos con poco contexto): instantánea reducida que
    # cabe en AI_AUDIT_SNAPSHOT_TOKENS. "auto": solo con compatible
    AI_AUDIT_COMPACT: str = "auto"            # auto | true | false
    AI_AUDIT_SNAPSHOT_TOKENS: int = 3000
    # Precio en USD por millón de tokens (entrada, salida) para estimar el
    # coste de modelos que LanSentinel no conoce. 0: sin estimación
    AI_AUDIT_PRICE_INPUT: float = 0
    AI_AUDIT_PRICE_OUTPUT: float = 0

    # Listas de IPs maliciosas (services/security/threat_lists). Se descargan,
    # se cargan en un ipset y el cortafuegos corta el tráfico con ellas.
    THREAT_LISTS_ENABLED: bool = True
    # nombre=url separados por comas. FireHOL nivel 1 (botnets, malware y
    # redes secuestradas, pensada para bloquear sin falsos positivos) y los
    # servidores de control de botnets de abuse.ch
    THREAT_LISTS: str = (
        "firehol_level1=https://iplists.firehol.org/files/firehol_level1.netset,"
        "feodo=https://feodotracker.abuse.ch/downloads/ipblocklist.txt"
    )
    THREAT_LISTS_UPDATE_HOURS: int = 24

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
    # Marcar siempre la cookie de sesión como Secure (solo viaja por HTTPS).
    # Por el panel de nginx no hace falta: se marca sola cuando llega por HTTPS
    # (cabecera X-Forwarded-Proto). Útil detrás de otro proxy con TLS.
    SESSION_COOKIE_SECURE: bool = False
    # Bloqueo temporal tras varios intentos de login fallidos
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 300
    # Proxies cuya cabecera X-Real-IP se acepta como IP real del cliente (el
    # nginx del frontend, que comparte la red del equipo y llega por
    # 127.0.0.1). Desde otras IPs la cabecera se ignora para que no se pueda
    # falsificar.
    TRUSTED_PROXIES: List[str] = ["127.0.0.1/32"]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
