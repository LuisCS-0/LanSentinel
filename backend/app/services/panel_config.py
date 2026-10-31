"""
Ajustes que se cambian desde el panel en lugar de en .env.

Solo los que tiene sentido tocar en el día a día (proveedor de IA, avisos,
detección, copias, DHCP y DNS del modo router). Lo que se fija una vez al
instalar (interfaces de red, IPv6, base de datos, SECRET_KEY, rutas, listas
de IPs que nunca se bloquean, URLs de descarga de listas) sigue en .env.

Cómo funciona:
  - El valor del panel se guarda en la tabla settings ("config:<NOMBRE>")
    y, al arrancar y al cambiarlo, se escribe encima del objeto settings:
    los servicios lo leen de ahí cada vez, así que se aplica en el momento
    (salvo los marcados con `restart`, que solo se miran al arrancar).
  - Quitar el valor del panel vuelve al de .env (o al de por defecto).
  - Los secretos (claves de API, tokens, contraseña SMTP) se guardan
    cifrados con una clave derivada de la SECRET_KEY y nunca se devuelven
    por la API: solo si están puestos.
  - Cambiar un secreto o a dónde salen los datos (proveedor de IA y su
    dirección, destinos de los avisos) pide la contraseña del administrador:
    con una sesión robada no basta para desviar la información de la red.

Las funciones de validación y descripción son puras, para los tests.
"""

import base64
import hashlib
import ipaddress
import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select

from app.core.config import Settings, settings
from app.db.session import AsyncSessionLocal
from app.models.setting import SystemSetting

log = structlog.get_logger(__name__)

PREFIX = "config:"


@dataclass(frozen=True)
class Field:
    name: str                     # atributo de settings (y variable de .env)
    group: str                    # ia | avisos | deteccion | copias | sistema | router | latencia
    label: str
    kind: str                     # bool | int | float | text | select | secret | url | emails
    help: str = ""
    options: tuple = ()           # para select: (valor, etiqueta)
    min: float | None = None
    max: float | None = None
    sensitive: bool = False       # cambiarlo pide la contraseña
    restart: bool = False         # solo se aplica al reiniciar LanSentinel
    placeholder: str = ""


SEVERITIES = (("info", "Todas"), ("low", "Baja o más"), ("medium", "Media o más"),
              ("high", "Alta o más"), ("critical", "Solo críticas"))

FIELDS: tuple[Field, ...] = (
    # ── Auditoría con IA ─────────────────────────────────────────────────
    Field("AI_AUDIT_PROVIDER", "ia", "Proveedor", "select", sensitive=True,
          options=(("", "Ninguno (desactivada)"), ("anthropic", "Claude (Anthropic)"), ("openai", "OpenAI"),
                   ("compatible", "Compatible con OpenAI (Ollama, LM Studio…)")),
          help="Adónde se envía la instantánea seudonimizada de la red."),
    Field("AI_AUDIT_MODEL", "ia", "Modelo", "text", placeholder="claude-opus-5-5",
          help="Vacío con Claude: claude-opus-5-5. Con OpenAI o un servidor compatible, el nombre que da el servidor."),
    Field("AI_AUDIT_API_KEY", "ia", "Clave de la API", "secret", sensitive=True,
          help="Vacía: se usa ANTHROPIC_API_KEY u OPENAI_API_KEY de .env. Los servidores locales no suelen pedirla."),
    Field("AI_AUDIT_BASE_URL", "ia", "Dirección del servidor compatible", "url", sensitive=True,
          placeholder="http://192.168.1.50:11434/v1", help="Solo con «Compatible con OpenAI»."),
    Field("AI_AUDIT_EFFORT", "ia", "Esfuerzo de razonamiento", "select",
          options=(("low", "Bajo"), ("medium", "Medio"), ("high", "Alto"), ("xhigh", "Muy alto"), ("max", "Máximo")),
          help="Más esfuerzo: informes mejores, más lentos y más caros."),
    Field("AI_AUDIT_COMPACT", "ia", "Instantánea compacta", "select",
          options=(("auto", "Automática (con servidores compatibles)"), ("true", "Siempre"), ("false", "Nunca")),
          help="Para modelos con poco contexto."),
    Field("AI_AUDIT_SNAPSHOT_TOKENS", "ia", "Tamaño máximo de la compacta (tokens)", "int", min=500, max=200_000),
    Field("AI_AUDIT_TIMEOUT_SECONDS", "ia", "Tiempo máximo de respuesta (s)", "int", min=30, max=7200),
    Field("AI_AUDIT_INCLUDE_NAMES", "ia", "Enviar los nombres de red de los equipos", "bool", sensitive=True),
    Field("AI_AUDIT_INCLUDE_DOMAINS", "ia", "Enviar los dominios que visita cada equipo", "bool", sensitive=True),
    Field("AI_AUDIT_ALERT_DAYS", "ia", "Días de alertas que se envían", "int", min=1, max=365),
    Field("AI_AUDIT_PRICE_INPUT", "ia", "Precio de entrada (USD por millón de tokens)", "float", min=0, max=1000,
          help="Para estimar el coste de modelos que LanSentinel no conoce. 0: sin estimación."),
    Field("AI_AUDIT_PRICE_OUTPUT", "ia", "Precio de salida (USD por millón de tokens)", "float", min=0, max=1000),

    # ── Avisos ───────────────────────────────────────────────────────────
    Field("NOTIFY_MIN_SEVERITY", "avisos", "Avisar de alertas", "select", options=SEVERITIES),
    Field("NOTIFY_MAX_PER_HOUR", "avisos", "Máximo de avisos por hora", "int", min=1, max=1000),
    Field("PANEL_URL", "avisos", "Dirección del panel en los avisos", "url", placeholder="https://192.168.1.10",
          help="Para que cada aviso lleve un enlace al panel."),
    Field("TELEGRAM_BOT_TOKEN", "avisos", "Telegram: token del bot", "secret", sensitive=True,
          help="El que da @BotFather al crear el bot."),
    Field("TELEGRAM_CHAT_ID", "avisos", "Telegram: chat", "text", sensitive=True,
          help="Tu identificador de chat (se lo dice @userinfobot)."),
    Field("NTFY_SERVER", "avisos", "ntfy: servidor", "url", sensitive=True, placeholder="https://ntfy.sh"),
    Field("NTFY_TOPIC", "avisos", "ntfy: tema", "text", sensitive=True,
          help="Un nombre difícil de adivinar: cualquiera que lo sepa puede leer los avisos."),
    Field("NTFY_TOKEN", "avisos", "ntfy: token", "secret", sensitive=True, help="Solo si el servidor lo pide."),
    Field("SMTP_HOST", "avisos", "Correo: servidor SMTP", "text", sensitive=True, placeholder="smtp.gmail.com"),
    Field("SMTP_PORT", "avisos", "Correo: puerto", "int", min=1, max=65535),
    Field("SMTP_SECURITY", "avisos", "Correo: cifrado", "select",
          options=(("starttls", "STARTTLS (puerto 587)"), ("ssl", "SSL/TLS (puerto 465)"), ("none", "Ninguno"))),
    Field("SMTP_USER", "avisos", "Correo: usuario", "text", sensitive=True),
    Field("SMTP_PASSWORD", "avisos", "Correo: contraseña", "secret", sensitive=True,
          help="Con Gmail u Outlook, una contraseña de aplicación."),
    Field("SMTP_FROM", "avisos", "Correo: remitente", "emails", sensitive=True),
    Field("SMTP_TO", "avisos", "Correo: destinatarios", "emails", sensitive=True, help="Separados por comas."),

    # ── Detección y protección ───────────────────────────────────────────
    Field("FIREWALL_AUTO_BLOCK_CRITICAL", "deteccion", "Bloqueo automático ante alertas críticas", "bool",
          help="Las IPs de Internet con cualquier alerta crítica; los equipos de casa, solo con las reglas propias."),
    Field("THREAT_LISTS_ENABLED", "deteccion", "Listas de IPs maliciosas", "bool", restart=True),
    Field("THREAT_LISTS_UPDATE_HOURS", "deteccion", "Actualizar las listas cada (horas)", "int", min=1, max=720),
    Field("PORT_SCAN_INTERVAL_HOURS", "deteccion", "Escanear los puertos de los equipos cada (horas)", "int",
          min=0, max=720, restart=True, help="0 lo desactiva."),
    Field("ARP_SPOOF_DETECTION", "deteccion", "Detectar suplantación ARP", "bool", restart=True),
    Field("ANOMALY_DETECTION_ENABLED", "deteccion", "Detectar picos de consumo", "bool"),
    Field("DOMAIN_TRACKING_ENABLED", "deteccion", "Guardar los dominios de cada equipo", "bool",
          help="Es su historial de navegación: solo lo ve el administrador."),
    Field("DOMAIN_HISTORY_DAYS", "deteccion", "Días que se guardan los dominios", "int", min=1, max=365),
    Field("OUI_ONLINE_LOOKUP", "deteccion", "Buscar fabricantes desconocidos en Internet", "bool", sensitive=True,
          help="Envía a macvendors.com las MAC que no estén en la lista local."),

    # ── Copias de seguridad y sistema ────────────────────────────────────
    Field("BACKUP_HOUR", "copias", "Hora de la copia diaria", "int", min=-1, max=23, help="-1 las desactiva."),
    Field("BACKUP_KEEP_DAILY", "copias", "Copias recientes que se guardan", "int", min=1, max=60),
    Field("BACKUP_KEEP_WEEKLY", "copias", "Copias semanales que se guardan", "int", min=0, max=52),
    # ── DHCP y DNS del modo router (dnsmasq se relanza al cambiarlos) ──────
    Field("ROUTER_DHCP", "router", "LanSentinel reparte las IPs y el DNS", "bool",
          help="Desactívalo si las IPs las sigue dando otro equipo (por ejemplo, el router de la operadora)."),
    Field("DHCP_RANGE_START", "router", "Primera IP que se reparte", "text", placeholder="192.168.50.100",
          help="Vacía: la .100 de la red de la LAN."),
    Field("DHCP_RANGE_END", "router", "Última IP que se reparte", "text", placeholder="192.168.50.199",
          help="Vacía: la .199. Deja fuera del rango las IPs fijas que pongas a mano."),
    Field("DHCP_LEASE_TIME", "router", "Duración de cada IP", "text", placeholder="12h",
          help="Cuánto vale una IP antes de renovarla: 30m, 12h, 7d… o infinite."),
    Field("DNS_UPSTREAM", "router", "Servidores DNS de Internet", "text", sensitive=True, placeholder="1.1.1.1,9.9.9.9",
          help="A quién pregunta LanSentinel los nombres que no conoce (ven todos los dominios de la red). Separados por comas."),
    Field("LOCAL_DOMAIN", "router", "Dominio de la red local", "text", placeholder="lan",
          help="Los equipos se llaman nombre.lan y el panel, lansentinel.lan."),

    # ── Control de latencia del modo router (cake se reaplica al cambiarlos) ─
    Field("SQM_ENABLED", "latencia", "Control de latencia (cake)", "bool",
          help="Que una descarga o subida grande no dispare la latencia de juegos y videollamadas."),
    Field("SQM_DOWNLOAD_MBPS", "latencia", "Velocidad de bajada (Mbps)", "int", min=0, max=100_000,
          help="Un 90 % de lo que da un test de velocidad sin nada más en marcha. 0: sin límite (solo reparte)."),
    Field("SQM_UPLOAD_MBPS", "latencia", "Velocidad de subida (Mbps)", "int", min=0, max=100_000,
          help="Igual, con la subida. Es la que más se nota: suele ser la más pequeña."),

    Field("AUDIT_LOG_DAYS", "sistema", "Días del registro de acciones", "int", min=30, max=3650),
    Field("TIMEZONE", "sistema", "Zona horaria", "text", placeholder="Europe/Madrid",
          help="Para las gráficas por días, la hora de la copia y el tráfico de madrugada."),
)
BY_NAME = {f.name: f for f in FIELDS}

_EMAIL = re.compile(r"^[^@\s,]+@[^@\s,]+\.[^@\s,]+$")
_LEASE = re.compile(r"^(\d+[smhdw]?|infinite)$")
_DNS_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class ConfigError(ValueError):
    pass


# ── Lógica pura ──────────────────────────────────────────────────────────────

def coerce(f: Field, value):
    """El valor del formulario convertido y comprobado, o ConfigError con el motivo."""
    if f.kind == "bool":
        if isinstance(value, bool):
            return value
        raise ConfigError(f"{f.label}: tiene que ser sí o no")
    if f.kind in ("int", "float"):
        try:
            number = int(value) if f.kind == "int" else float(value)
        except (TypeError, ValueError):
            raise ConfigError(f"{f.label}: no es un número") from None
        if isinstance(value, bool) or (f.kind == "int" and isinstance(value, float) and not value.is_integer()):
            raise ConfigError(f"{f.label}: no es un número entero")
        if (f.min is not None and number < f.min) or (f.max is not None and number > f.max):
            raise ConfigError(f"{f.label}: entre {_num(f.min)} y {_num(f.max)}")
        return number
    if not isinstance(value, str):
        raise ConfigError(f"{f.label}: tiene que ser texto")
    value = value.strip()
    if len(value) > 2000 or any(c in value for c in "\r\n\0"):
        raise ConfigError(f"{f.label}: valor no válido")
    if f.kind == "select":
        if value not in {o[0] for o in f.options}:
            raise ConfigError(f"{f.label}: opción desconocida")
    elif f.kind == "url":
        if value and not re.match(r"^https?://[^\s/]+", value):
            raise ConfigError(f"{f.label}: tiene que empezar por http:// o https://")
    elif f.kind == "emails":
        if value and not all(_EMAIL.match(e.strip()) for e in value.split(",")):
            raise ConfigError(f"{f.label}: dirección de correo no válida")
    if f.name in ("DHCP_RANGE_START", "DHCP_RANGE_END") and value:
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            raise ConfigError(f"{f.label}: no es una dirección IPv4 (por ejemplo, 192.168.50.100)") from None
    if f.name == "DHCP_LEASE_TIME" and not _LEASE.match(value.lower()):
        raise ConfigError(f"{f.label}: un número con s, m, h, d o w (12h, 7d…) o infinite")
    if f.name == "DNS_UPSTREAM":
        servers = [s.strip() for s in value.split(",") if s.strip()]
        try:
            if not servers or any(ipaddress.ip_address(s).is_loopback for s in servers):
                raise ValueError
        except ValueError:
            raise ConfigError(f"{f.label}: direcciones IP separadas por comas (por ejemplo, 1.1.1.1,9.9.9.9)") from None
        value = ",".join(servers)
    if f.name == "LOCAL_DOMAIN":
        value = value.lower().strip(".")
        if not value or len(value) > 253 or not all(_DNS_LABEL.match(p) for p in value.split(".")):
            raise ConfigError(f"{f.label}: letras, números y guiones (por ejemplo, lan o casa.lan)")
    if f.name == "TIMEZONE":
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"{f.label}: zona horaria desconocida (por ejemplo, Europe/Madrid)") from None
    return value


def _num(value) -> str:
    return str(int(value)) if value is not None and float(value).is_integer() else str(value)


def check_dhcp_range(start: str, end: str, lan: ipaddress.IPv4Interface | None) -> None:
    """
    El rango efectivo (vacío: .100 y .199 de la LAN) tiene que estar en la red
    de la LAN, en orden y sin la IP de LanSentinel; ConfigError si no.
    """
    if lan is None:
        return      # sin IP en la LAN todavía: se comprobará al encender el modo router
    prefix = str(lan.ip).rsplit(".", 1)[0]
    first = ipaddress.IPv4Address(start or f"{prefix}.100")
    last = ipaddress.IPv4Address(end or f"{prefix}.199")
    net = lan.network
    if first not in net or last not in net:
        raise ConfigError(f"El rango de IPs tiene que estar en la red de la LAN ({net})")
    if first > last:
        raise ConfigError("La primera IP del rango tiene que ir antes que la última")
    if first <= lan.ip <= last:
        raise ConfigError(f"El rango no puede incluir la IP de LanSentinel ({lan.ip})")


def needs_password(changes: dict) -> bool:
    return any(BY_NAME[name].sensitive for name in changes)


def _cipher(secret_key: str) -> Fernet:
    digest = hashlib.sha256(f"lansentinel-config:{secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text: str, secret_key: str) -> str:
    return _cipher(secret_key).encrypt(text.encode()).decode()


def decrypt(token: str, secret_key: str) -> str:
    return _cipher(secret_key).decrypt(token.encode()).decode()


@dataclass
class Snapshot:
    """Lo que hay ahora: valores del panel, de .env y por defecto."""
    panel: dict = field(default_factory=dict)     # nombre → valor (secretos ya descifrados)
    env: dict = field(default_factory=dict)       # nombre → valor de .env (o por defecto)


def describe(snap: Snapshot) -> list[dict]:
    """Los ajustes para el panel: valor efectivo, de dónde sale y, de los secretos, solo si están."""
    result = []
    for f in FIELDS:
        default = Settings.model_fields[f.name].default
        if f.name in snap.panel:
            value, source = snap.panel[f.name], "panel"
        else:
            value = snap.env.get(f.name, default)
            source = "env" if value != default else "default"
        item = {
            "name": f.name, "group": f.group, "label": f.label, "kind": f.kind, "help": f.help,
            "options": [{"value": v, "label": label} for v, label in f.options],
            "min": f.min, "max": f.max, "sensitive": f.sensitive, "restart": f.restart,
            "placeholder": f.placeholder, "source": source,
        }
        if f.kind == "secret":
            item["value"] = None
            item["is_set"] = bool(value)
        else:
            item["value"] = value
        result.append(item)
    return result


# ── Guardar y aplicar ────────────────────────────────────────────────────────

class PanelConfig:

    def __init__(self):
        # Los valores de .env tal como se cargaron, antes de nada del panel
        self.env = {f.name: getattr(settings, f.name) for f in FIELDS}
        self.panel: dict = {}

    def _secret_key(self) -> str:
        from app.core.security import get_secret_key
        return get_secret_key()

    async def load(self) -> None:
        """Al arrancar: aplica lo guardado en el panel encima de .env."""
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(SystemSetting.key, SystemSetting.value).where(SystemSetting.key.like(f"{PREFIX}%"))
            )).all()
        for key, stored in rows:
            name = key[len(PREFIX):]
            f = BY_NAME.get(name)
            if f is None or not isinstance(stored, dict):
                continue
            try:
                value = decrypt(stored["enc"], self._secret_key()) if "enc" in stored else coerce(f, stored.get("v"))
            except (InvalidToken, ConfigError, KeyError) as exc:
                # Un secreto cifrado con otra SECRET_KEY (o un valor que ya no vale): se ignora
                log.warning("panel_config.ignored", name=name, error=type(exc).__name__)
                continue
            self._apply(name, value)
        if self.panel:
            log.info("panel_config.loaded", names=sorted(self.panel))

    def _apply(self, name: str, value) -> None:
        self.panel[name] = value
        setattr(settings, name, value)

    def _reset(self, name: str) -> None:
        self.panel.pop(name, None)
        setattr(settings, name, self.env[name])

    def describe(self) -> list[dict]:
        return describe(Snapshot(panel=dict(self.panel), env=dict(self.env)))

    def validate(self, changes: dict, lan: ipaddress.IPv4Interface | None = None) -> dict:
        """{nombre: valor convertido | None (volver a .env)}; ConfigError si algo no vale."""
        result = {}
        for name, value in changes.items():
            f = BY_NAME.get(name)
            if f is None:
                raise ConfigError(f"No se puede cambiar {name} desde el panel")
            result[name] = None if value is None else coerce(f, value)
        if {"DHCP_RANGE_START", "DHCP_RANGE_END"} & result.keys():
            check_dhcp_range(*(self.effective(n, result) for n in ("DHCP_RANGE_START", "DHCP_RANGE_END")), lan)
        return result

    def effective(self, name: str, changes: dict):
        """El valor que quedará tras los cambios (None en un cambio: el de .env)."""
        if name in changes:
            return self.env[name] if changes[name] is None else changes[name]
        return getattr(settings, name)

    async def update(self, changes: dict) -> list[str]:
        """Guarda y aplica los cambios ya validados; devuelve los nombres que cambiaron."""
        changed = [n for n, v in changes.items() if v is None and n in self.panel or v is not None and self.panel.get(n) != v]
        if not changed:
            return []
        async with AsyncSessionLocal() as db:
            for name in changed:
                value = changes[name]
                key = f"{PREFIX}{name}"
                await db.execute(delete(SystemSetting).where(SystemSetting.key == key))
                if value is not None:
                    stored = {"enc": encrypt(value, self._secret_key())} if BY_NAME[name].kind == "secret" else {"v": value}
                    db.add(SystemSetting(key=key, value=stored, description=f"Ajuste del panel: {BY_NAME[name].label}"))
            await db.commit()
        for name in changed:
            if changes[name] is None:
                self._reset(name)
            else:
                self._apply(name, changes[name])
        log.info("panel_config.updated", names=changed)
        return changed


panel_config = PanelConfig()
