"""
Certificado HTTPS del panel.

El panel se sirve por HTTPS (nginx en el contenedor del frontend), y en una
red doméstica no hay un dominio público con el que pedir un certificado a
Let's Encrypt. Por eso LanSentinel tiene su propia autoridad (CA) y firma con
ella el certificado del panel:

- La CA se crea una vez y dura 10 años. Quien la importe en sus dispositivos
  deja de ver el aviso del navegador, y no tiene que repetirlo aunque cambie
  la IP del equipo: solo se renueva el certificado del panel.
- La CA solo puede firmar nombres e IPs de la red local (restricción de
  nombres, RFC 5280). Si alguien robara su clave, no le serviría para
  suplantar webs de Internet ante quien la haya importado.
- El certificado del panel lleva las IPs privadas del equipo y sus nombres
  (lansentinel.lan, el nombre del equipo). Se rehace si cambian o si le
  quedan menos de 30 días.

Todo vive en /var/lib/lansentinel/tls, que el frontend monta en solo lectura.
Si server.crt no lo ha firmado esta CA (un certificado propio, p. ej. de
Let's Encrypt), se respeta y no se toca.
"""

import asyncio
import ipaddress
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import netifaces
import structlog
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.core.config import settings

log = structlog.get_logger(__name__)

TLS_DIR = Path("/var/lib/lansentinel/tls")
CA_CERT = TLS_DIR / "ca.crt"
CA_KEY = TLS_DIR / "ca.key"
SERVER_CERT = TLS_DIR / "server.crt"
SERVER_KEY = TLS_DIR / "server.key"

CA_DAYS = 3650
# 397 días: el máximo que aceptan los navegadores para certificados de servidor
SERVER_DAYS = 397
RENEW_BEFORE = timedelta(days=30)
CHECK_INTERVAL_SECONDS = 600

# Interfaces que no son la red del equipo (Docker, máquinas virtuales, túneles)
IGNORED_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "vnet", "tun", "tap", "wg")

# Lo único que la CA puede firmar: redes privadas, CGNAT (Tailscale y
# similares) y loopback. Los nombres se añaden al crear la CA.
PERMITTED_NETWORKS = [
    ipaddress.ip_network(n) for n in
    ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
]


@dataclass(frozen=True)
class Names:
    """Nombres e IPs que debe cubrir el certificado del panel."""
    dns: tuple[str, ...]
    ips: tuple[str, ...]


# ── Funciones puras ──────────────────────────────────────────────────────────

def _valid_label(name: str) -> bool:
    return 0 < len(name) <= 63 and all(c.isalnum() or c == "-" for c in name) and not name.startswith("-")


def permitted_dns(hostname: str, domain: str) -> list[str]:
    """Nombres que la CA podrá firmar: el dominio local, el nombre del equipo y localhost."""
    names = [domain] if domain and all(_valid_label(p) for p in domain.split(".")) else []
    if _valid_label(hostname):
        names.append(hostname)
    names.append("localhost")
    return names


def is_permitted_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in PERMITTED_NETWORKS)


def wanted_names(hostname: str, domain: str, ips: list[str], permitted: list[str]) -> Names:
    """Lo que debe llevar el certificado, limitado a lo que la CA puede firmar."""
    candidates = [f"lansentinel.{domain}" if domain else "", hostname,
                  f"{hostname}.{domain}" if domain else "", "localhost"]
    allowed = [n for n in dict.fromkeys(c.lower() for c in candidates if c)
               if any(n == p or n.endswith("." + p) for p in permitted)]
    good_ips = sorted({ip for ip in ips if is_permitted_ip(ip)} | {"127.0.0.1"}, key=ipaddress.ip_address)
    return Names(dns=tuple(allowed), ips=tuple(good_ips))


def cert_names(cert: x509.Certificate) -> Names:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return Names(dns=(), ips=())
    return Names(dns=tuple(san.get_values_for_type(x509.DNSName)),
                 ips=tuple(sorted((str(i) for i in san.get_values_for_type(x509.IPAddress)), key=ipaddress.ip_address)))


def signed_by(cert: x509.Certificate, ca: x509.Certificate) -> bool:
    if cert.issuer != ca.subject:
        return False
    try:
        cert.verify_directly_issued_by(ca)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def needs_renewal(cert: x509.Certificate, wanted: Names, now: datetime) -> bool:
    current = cert_names(cert)
    return (cert.not_valid_after_utc - now < RENEW_BEFORE
            or set(current.dns) != set(wanted.dns) or set(current.ips) != set(wanted.ips))


def fingerprint(cert: x509.Certificate) -> str:
    digest = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def make_ca(hostname: str, permitted: list[str], now: datetime) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LanSentinel"),
        x509.NameAttribute(NameOID.COMMON_NAME, f"LanSentinel CA ({hostname})"[:64]),
    ])
    constraints = x509.NameConstraints(
        permitted_subtrees=[x509.DNSName(n) for n in permitted] + [x509.IPAddress(n) for n in PERMITTED_NETWORKS],
        excluded_subtrees=None,
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(constraints, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def make_server_cert(
    names: Names, ca: x509.Certificate, ca_key: ec.EllipticCurvePrivateKey, now: datetime,
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    common_name = names.dns[0] if names.dns else names.ips[0]
    san = [x509.DNSName(n) for n in names.dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in names.ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LanSentinel"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False,
            key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


# ── Ficheros y sistema ───────────────────────────────────────────────────────

def local_ipv4() -> list[str]:
    ips = []
    for iface in netifaces.interfaces():
        if iface.startswith(IGNORED_PREFIXES):
            continue
        ips += [a["addr"] for a in netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])]
    return ips


def _write(path: Path, data: bytes, private: bool = False) -> None:
    """Escritura atómica: nginx nunca lee un fichero a medias."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600 if private else 0o644)
    tmp.replace(path)


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def _load_cert(path: Path) -> x509.Certificate | None:
    try:
        return x509.load_pem_x509_certificate(path.read_bytes())
    except (OSError, ValueError):
        return None


class TlsService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self.last_error: str | None = None

    def ensure(self) -> None:
        """Crea la CA y el certificado del panel si faltan, o rehace este si ha cambiado algo."""
        now = datetime.now(timezone.utc)
        hostname = socket.gethostname().split(".")[0].lower()
        domain = settings.LOCAL_DOMAIN.strip(".").lower()
        TLS_DIR.mkdir(parents=True, exist_ok=True)

        ca = _load_cert(CA_CERT)
        try:
            ca_key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None) if ca else None
        except (OSError, ValueError):
            ca_key = None
        if ca is None or ca_key is None:
            ca, ca_key = make_ca(hostname, permitted_dns(hostname, domain), now)
            _write(CA_KEY, _pem_key(ca_key), private=True)
            _write(CA_CERT, ca.public_bytes(serialization.Encoding.PEM))
            log.info("tls.ca_created", fingerprint=fingerprint(ca))

        server = _load_cert(SERVER_CERT)
        if server is not None and SERVER_KEY.exists() and not signed_by(server, ca):
            # Certificado propio del usuario: no se toca
            return
        try:
            ca_constraints = ca.extensions.get_extension_for_class(x509.NameConstraints).value
            permitted = [n.value for n in ca_constraints.permitted_subtrees or [] if isinstance(n, x509.DNSName)]
        except x509.ExtensionNotFound:
            permitted = permitted_dns(hostname, domain)
        wanted = wanted_names(hostname, domain, local_ipv4(), permitted)
        if server is not None and SERVER_KEY.exists() and not needs_renewal(server, wanted, now):
            return

        server, key = make_server_cert(wanted, ca, ca_key, now)
        _write(SERVER_KEY, _pem_key(key), private=True)
        _write(SERVER_CERT, server.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
        log.info("tls.server_cert_issued", names=list(wanted.dns), ips=list(wanted.ips),
                 valid_until=server.not_valid_after_utc.date().isoformat())

    def _ensure_logged(self) -> None:
        try:
            self.ensure()
            self.last_error = None
        except Exception as exc:     # el panel no debe caerse por esto
            self.last_error = str(exc)
            log.error("tls.ensure_failed", error=str(exc))

    async def start(self) -> None:
        await asyncio.to_thread(self._ensure_logged)
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        # Comprueba de vez en cuando si ha cambiado la IP o se acerca la caducidad
        while True:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await asyncio.to_thread(self._ensure_logged)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def ca_pem(self) -> bytes | None:
        try:
            return CA_CERT.read_bytes()
        except OSError:
            return None

    def status(self) -> dict:
        ca = _load_cert(CA_CERT)
        server = _load_cert(SERVER_CERT)
        own = server is not None and ca is not None and signed_by(server, ca)
        names = cert_names(server) if server else Names(dns=(), ips=())
        return {
            "available": server is not None,
            "issuer": "lansentinel" if own else ("custom" if server else None),
            "dns_names": list(names.dns),
            "ip_addresses": list(names.ips),
            "valid_until": server.not_valid_after_utc if server else None,
            "server_fingerprint": fingerprint(server) if server else None,
            "ca_fingerprint": fingerprint(ca) if ca and own else None,
            "ca_valid_until": ca.not_valid_after_utc if ca and own else None,
            "error": self.last_error,
        }


tls_service = TlsService()
