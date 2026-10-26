"""
Servicio de cortafuegos — orquestador del módulo.

Funciones principales:
  1. Al arrancar (lifespan FastAPI), reaplica en iptables todas las reglas
     activas que tiene la BD. Esto es necesario porque iptables no persiste
     las reglas entre reinicios del sistema o del contenedor.
  2. Expone las operaciones de alto nivel que coordinan la doble escritura
     kernel (iptables) + BD (firewall_rules):
       - block_ip:       IPs externas o bloqueos manuales por IP.
       - block_device:   dispositivos de la LAN, por MAC e IP a la vez.
       - sync_device_ip: mantiene al día la IP de un bloqueo por MAC cuando
                         el dispositivo cambia de IP.
       - unblock_rule / unblock_device.
  3. Mantiene contadores expuestos por la API para el endpoint de estado.
"""

import ipaddress
import os
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.device import Device
from app.services.firewall import iptables_manager
from app.services.firewall.protection import ProtectedAddressError, protected_reason
from app.services.firewall.rule_repository import FirewallRuleRepository
from app.services.firewall.dhcp_dns import dhcp_dns
from app.services.settings_store import QUARANTINE_MODE, ROUTER_MODE, ROUTER_MODE_ENV, get_setting, set_setting

log = structlog.get_logger(__name__)


class FirewallService:
    """Singleton que coordina las operaciones del cortafuegos."""

    def __init__(self):
        self._running: bool = False
        self.rules_applied: int = 0
        self.last_action_at: datetime | None = None
        self.iptables_available: bool = False
        self.quarantine_enabled: bool = False
        self.router_active: bool = False

    # ── Ciclo de vida ───────────────────────────────────────────────────────

    async def start(self):
        """
        Arranque: prepara las cadenas propias en iptables y reaplica las
        reglas activas que tenga la BD. Operación idempotente.
        """
        # 1. Comprobar que iptables está disponible
        self.iptables_available = await iptables_manager.is_firewall_available()
        if not self.iptables_available:
            log.warning("firewall_service.iptables_unavailable")
            self._running = False
            return

        # 2. Garantizar que las cadenas propias existen y están enlazadas
        perfe = await iptables_manager.ensure_chains_exist()
        if not perfe:
            log.error("firewall_service.chain_setup_failed")
            self._running = False
            return

        # 3. Reaplicar reglas activas de la BD (reconciliación inicial)
        await self._reapply_active_rules()

        self._running = True
        await self.apply_router()
        await self.apply_quarantine()
        log.info(
            "firewall_service.started",
            rules_applied=self.rules_applied,
        )

    async def stop(self):
        """
        Apagado limpio. NO se borran las reglas de iptables: deben sobrevivir
        a un reinicio del backend para que un atacante no recupere el acceso
        en la ventana de tiempo en que el backend está caído.
        """
        self._running = False
        await dhcp_dns.stop()
        log.info("firewall_service.stopped")

    async def _reapply_active_rules(self) -> None:
        """Lee todas las reglas activas de la BD y las inserta en iptables."""
        # Primero vaciamos las cadenas propias para evitar duplicados
        await iptables_manager.flush_chains()

        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)
            active_rules = await repo.get_all_active()

            await self._upgrade_legacy_device_rules(db, active_rules)

            applied = 0
            for rule in active_rules:
                if not rule.src_ip and not rule.src_mac:
                    continue
                si = await iptables_manager.block(rule.id, ip=rule.src_ip, mac=rule.src_mac)
                if si:
                    applied += 1
            self.rules_applied = applied
            log.info(
                "firewall_service.rules_reapplied",
                total=len(active_rules), applied=applied,
            )

    @staticmethod
    async def _upgrade_legacy_device_rules(db, rules) -> None:
        """
        Las reglas de dispositivos creadas antes del bloqueo por MAC solo
        tenían IP. Si una regla activa está asociada a un dispositivo de la
        LAN cuya IP coincide, se le añade su MAC para que también sobreviva
        a un cambio de IP.
        """
        upgraded = 0
        for rule in rules:
            if rule.src_mac or not rule.device_id:
                continue
            result = await db.execute(select(Device).where(Device.id == rule.device_id))
            device = result.scalar_one_or_none()
            if device and device.mac and (not rule.src_ip or rule.src_ip == device.ip):
                rule.src_mac = device.mac
                upgraded += 1
        if upgraded:
            await db.commit()
            log.info("firewall_service.legacy_rules_upgraded", count=upgraded)

    # ── Operaciones públicas ────────────────────────────────────────────────

    async def block_ip(
        self,
        ip: str,
        reason: str = "Bloqueo manual",
        device_id: UUID | None = None,
        auto_generated: bool = False,
    ):
        """
        Bloquea una IP: aplica la regla DROP en iptables y la persiste en BD.

        Si ya existe una regla activa para esa IP, no hace nada y devuelve
        la existente. Esto evita duplicados ante peticiones repetidas.

        Lanza ProtectedAddressError si la IP es del propio sistema, su
        puerta de enlace u otra dirección que nunca debe bloquearse.
        """
        reason_protected = protected_reason(ip)
        if reason_protected:
            log.warning("firewall_service.protected_ip", ip=ip, reason=reason_protected)
            raise ProtectedAddressError(reason_protected)
        # Forma canónica (sobre todo IPv6: "2001:DB8:0::1" → "2001:db8::1")
        # para que la comprobación de duplicados no dependa de cómo se escriba
        ip = str(ipaddress.ip_address(ip))

        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)

            # Comprobación de idempotencia
            existing = await repo.get_active_by_ip(ip)
            if existing:
                log.info("firewall_service.already_blocked", ip=ip)
                return existing

            # 1. Crear la entrada en BD para obtener el ID
            rule = await repo.create_block_rule(
                ip=ip,
                name=f"Bloqueo de {ip}",
                description=reason,
                device_id=device_id,
                auto_generated=auto_generated,
            )

            # 2. Aplicar la regla en iptables usando el ID como etiqueta
            ok = await iptables_manager.block(rule.id, ip=ip)
            if not ok:
                # Si falla iptables revertimos la entrada en BD
                await repo.delete(rule.id)
                log.error("firewall_service.block_failed", ip=ip)
                return None

            self.rules_applied += 1
            self.last_action_at = datetime.now(timezone.utc)
            log.info(
                "firewall_service.ip_blocked",
                ip=ip, rule_id=rule.id, auto=auto_generated,
            )
            return rule

    async def block_device(
        self,
        device: Device,
        reason: str | None = None,
        auto_generated: bool = False,
    ):
        """
        Bloquea un dispositivo de la LAN por su MAC y, si la conoce, también
        por su IP actual:
          - La línea por MAC sigue bloqueándolo aunque cambie de IP.
          - La línea por IP lo sigue bloqueando aunque falsifique la MAC
            conservando la IP.
        Marca además el dispositivo como bloqueado en BD.

        Idempotente: si ya existe una regla activa para esa MAC, la devuelve.
        Lanza ProtectedAddressError si la IP del dispositivo está protegida.
        """
        if device.ip:
            reason_protected = protected_reason(device.ip)
            if reason_protected:
                log.warning("firewall_service.protected_device", ip=device.ip, reason=reason_protected)
                raise ProtectedAddressError(reason_protected)

        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)

            existing = await repo.get_active_by_mac(device.mac)
            if existing:
                log.info("firewall_service.device_already_blocked", mac=device.mac)
                await self._set_device_blocked(db, device.id, True)
                return existing

            rule = await repo.create_block_rule(
                ip=device.ip,
                mac=device.mac,
                name=f"Bloqueo de dispositivo {device.hostname or device.mac}",
                description=reason or f"Bloqueo del dispositivo {device.mac}",
                device_id=device.id,
                auto_generated=auto_generated,
            )

            ok = await iptables_manager.block(rule.id, ip=device.ip, mac=device.mac)
            if not ok:
                await repo.delete(rule.id)
                log.error("firewall_service.device_block_failed", mac=device.mac)
                return None

            await self._set_device_blocked(db, device.id, True)
            self.rules_applied += 1
            self.last_action_at = datetime.now(timezone.utc)
            log.info(
                "firewall_service.device_blocked",
                mac=device.mac, ip=device.ip, rule_id=rule.id, auto=auto_generated,
            )
            return rule

    async def unblock_device(self, device: Device) -> int:
        """
        Quita todas las reglas que afectan al dispositivo (por MAC, por su IP
        actual o asociadas a él) y lo marca como no bloqueado.
        Devuelve cuántas reglas se han eliminado.
        """
        async with AsyncSessionLocal() as db:
            rules = await FirewallRuleRepository(db).get_active_for_device(
                device.id, device.mac, device.ip,
            )
        removed = 0
        for rule in rules:
            if await self.unblock_rule(rule.id):
                removed += 1

        async with AsyncSessionLocal() as db:
            await self._set_device_blocked(db, device.id, False)
        return removed

    async def sync_device_ip(self, mac: str, ip: str | None) -> bool:
        """
        Si un dispositivo bloqueado por MAC aparece con otra IP, rehace su
        regla con la nueva dirección. La línea por MAC ya lo bloqueaba; así se
        cubre también el caso de que después cambie de MAC conservando la IP.
        Devuelve True si la regla se ha actualizado.
        """
        if not self._running:
            return False
        new_ip = ip if ip and not protected_reason(ip) else None

        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)
            rule = await repo.get_active_by_mac(mac)
            if not rule or rule.src_ip == new_ip:
                return False

            old_ip = rule.src_ip
            await iptables_manager.unblock(rule.id)
            ok = await iptables_manager.block(rule.id, ip=new_ip, mac=rule.src_mac)
            if not ok:
                # Al menos mantener el bloqueo por MAC
                await iptables_manager.block(rule.id, mac=rule.src_mac)
                log.error("firewall_service.sync_ip_failed", mac=mac, ip=new_ip)
                return False

            await repo.update_src_ip(rule.id, new_ip)
            self.last_action_at = datetime.now(timezone.utc)
            log.info("firewall_service.device_ip_synced", mac=mac, old_ip=old_ip, new_ip=new_ip)
            return True

    async def unblock_rule(self, rule_id: int) -> bool:
        """
        Quita una regla: la borra de iptables y la marca inactiva en BD. Si
        era la última regla activa de un dispositivo, este deja de figurar
        como bloqueado.
        """
        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)
            rule = await repo.get_by_id(rule_id)
            if not rule or not rule.is_active:
                return False

            # 1. Quitar de iptables
            ok = await iptables_manager.unblock(rule.id)
            if not ok:
                log.warning(
                    "firewall_service.iptables_unblock_failed",
                    rule_id=rule_id,
                )
                # Continuamos para limpiar la BD aunque iptables haya fallado

            # 2. Marcar inactiva en BD
            await repo.deactivate(rule_id)
            if rule.device_id and await repo.count_active_for_device(rule.device_id) == 0:
                await self._set_device_blocked(db, rule.device_id, False)

            # 3. Decrementar contador de reglas aplicadas
            if self.rules_applied > 0:
                self.rules_applied -= 1

            self.last_action_at = datetime.now(timezone.utc)
            log.info("firewall_service.ip_unblocked", rule_id=rule_id)
            return True

    @staticmethod
    async def _set_device_blocked(db, device_id: UUID, blocked: bool) -> None:
        await db.execute(
            update(Device)
            .where(Device.id == device_id)
            .values(is_blocked=blocked, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

    # ── Modo cuarentena ─────────────────────────────────────────────────────

    async def apply_quarantine(self) -> bool:
        """
        Aplica el modo cuarentena guardado en BD: si está activo, solo los
        dispositivos de confianza pueden salir a Internet. Se llama al
        arrancar, al activarlo o desactivarlo y cada vez que cambia la lista
        de confianza.
        """
        if not self._running:
            return False
        enabled = bool(await get_setting(QUARANTINE_MODE, False))
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Device.mac).where(Device.is_trusted == True))  # noqa: E712
            trusted = set(result.scalars().all())
        ok = await iptables_manager.set_quarantine(enabled, trusted, settings.MONITOR_INTERFACE)
        self.quarantine_enabled = enabled and ok
        return ok

    async def set_quarantine(self, enabled: bool) -> bool:
        """Activa o desactiva el modo cuarentena y lo aplica."""
        await set_setting(QUARANTINE_MODE, enabled, "Solo los dispositivos de confianza salen a Internet")
        self.last_action_at = datetime.now(timezone.utc)
        log.warning("firewall_service.quarantine_changed", enabled=enabled)
        return await self.apply_quarantine()

    # ── Modo router ─────────────────────────────────────────────────────────

    @staticmethod
    def router_problem() -> str | None:
        """Por qué no se puede activar el modo router, o None si se puede."""
        wan, lan = settings.WAN_INTERFACE.strip(), settings.MONITOR_INTERFACE
        if not wan:
            return "Falta WAN_INTERFACE en .env (configúralo con scripts/instalar.sh)"
        if wan == lan:
            return "WAN_INTERFACE y MONITOR_INTERFACE son la misma interfaz"
        return next((f"No existe la interfaz {i}" for i in (wan, lan) if not _interface_exists(i)), None)

    async def router_enabled(self) -> bool:
        """
        Estado elegido: el del panel (tabla settings). Si ROUTER_MODE de .env
        ha cambiado desde el último arranque (p. ej. al volver a ejecutar el
        instalador), manda .env: gana siempre la decisión más reciente.
        """
        if await get_setting(ROUTER_MODE_ENV) != settings.ROUTER_MODE:
            await set_setting(ROUTER_MODE_ENV, settings.ROUTER_MODE, "Último ROUTER_MODE visto en .env")
            await set_setting(ROUTER_MODE, settings.ROUTER_MODE, "LanSentinel enruta la red y da DHCP/DNS")
            return settings.ROUTER_MODE
        return bool(await get_setting(ROUTER_MODE, settings.ROUTER_MODE))

    async def apply_router(self) -> bool:
        """
        Aplica el modo router: NAT, reenvío y WAN cerrada (iptables) y DHCP/DNS
        (dnsmasq). Con una WAN mal configurada no se activa: se dejaría la red
        sin salida y la WAN sin proteger.
        """
        enabled = await self.router_enabled()
        wan, lan = settings.WAN_INTERFACE.strip(), settings.MONITOR_INTERFACE
        if enabled and (problem := self.router_problem()):
            log.error("firewall_service.router_misconfigured", problem=problem)
            enabled = False
        if enabled and not ip_forward_enabled():
            log.warning(
                "firewall_service.ip_forward_disabled",
                hint="El reenvío está desactivado en el sistema: ejecuta scripts/instalar.sh "
                     "o pon net.ipv4.ip_forward=1",
            )
        ok = await iptables_manager.set_router(enabled, wan, lan)
        self.router_active = enabled and ok
        if self.router_active and settings.ROUTER_DHCP:
            await dhcp_dns.start(lan)
        else:
            await dhcp_dns.stop()
        return ok

    async def set_router(self, enabled: bool) -> bool:
        """Enciende o apaga el modo router desde el panel y lo aplica."""
        await set_setting(ROUTER_MODE, enabled, "LanSentinel enruta la red y da DHCP/DNS")
        self.last_action_at = datetime.now(timezone.utc)
        log.warning("firewall_service.router_changed", enabled=enabled)
        return await self.apply_router()

    def router_status(self) -> dict:
        return {
            "available": self.router_problem() is None,
            "problem": self.router_problem(),
            "active": self.router_active,
            "wan_interface": settings.WAN_INTERFACE or None,
            "lan_interface": settings.MONITOR_INTERFACE,
            "ip_forward": ip_forward_enabled(),
            "dhcp_enabled": settings.ROUTER_DHCP,
            "dhcp": dhcp_dns.status(),
        }

    # ── Estado expuesto a la API ────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "iptables_available": self.iptables_available,
            "ipv6_enabled": self._running and iptables_manager.ipv6_enabled(),
            "quarantine_enabled": self.quarantine_enabled,
            "router": self.router_status(),
            "rules_applied": self.rules_applied,
            "last_action_at": (
                self.last_action_at.isoformat() if self.last_action_at else None
            ),
        }


def _interface_exists(name: str) -> bool:
    # El backend usa la red del equipo (network_mode: host): ve sus interfaces
    return bool(name) and os.path.exists(f"/sys/class/net/{name}")


def ip_forward_enabled() -> bool:
    try:
        with open("/proc/sys/net/ipv4/ip_forward") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


# Singleton importable desde main.py
firewall_service = FirewallService()
