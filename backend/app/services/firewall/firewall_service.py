"""
Servicio de cortafuegos — orquestador del módulo.

Funciones principales:
  1. Al arrancar (lifespan FastAPI), reaplica en iptables todas las reglas
     activas que tiene la BD. Esto es necesario porque iptables no persiste
     las reglas entre reinicios del sistema o del contenedor.
  2. Expone las operaciones de alto nivel (block_ip, unblock_rule) que
     coordinan la doble escritura: kernel (iptables) + BD (firewall_rules).
  3. Mantiene contadores expuestos por la API para el endpoint de estado.
"""

from datetime import datetime, timezone
from uuid import UUID

import structlog

from app.db.session import AsyncSessionLocal
from app.services.firewall import iptables_manager
from app.services.firewall.rule_repository import FirewallRuleRepository

log = structlog.get_logger(__name__)


class FirewallService:
    """Singleton que coordina las operaciones del cortafuegos."""

    def __init__(self):
        self._running: bool = False
        self.rules_applied: int = 0
        self.last_action_at: datetime | None = None
        self.iptables_available: bool = False

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
        log.info("firewall_service.stopped")

    async def _reapply_active_rules(self) -> None:
        """Lee todas las reglas activas de la BD y las inserta en iptables."""
        # Primero vaciamos las cadenas propias para evitar duplicados
        await iptables_manager.flush_chains()

        async with AsyncSessionLocal() as db:
            repo = FirewallRuleRepository(db)
            active_rules = await repo.get_all_active()

            applied = 0
            for rule in active_rules:
                if not rule.src_ip:
                    continue
                si = await iptables_manager.block(rule.id, ip=rule.src_ip)
                if si:
                    applied += 1
            self.rules_applied = applied
            log.info(
                "firewall_service.rules_reapplied",
                total=len(active_rules), applied=applied,
            )

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
        """
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

    async def unblock_rule(self, rule_id: int) -> bool:
        """Quita una regla: la borra de iptables y la marca inactiva en BD."""
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

            # 3. Decrementar contador de reglas aplicadas
            if self.rules_applied > 0:
                self.rules_applied -= 1

            self.last_action_at = datetime.now(timezone.utc)
            log.info("firewall_service.ip_unblocked", rule_id=rule_id)
            return True

    # ── Estado expuesto a la API ────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "iptables_available": self.iptables_available,
            "rules_applied": self.rules_applied,
            "last_action_at": (
                self.last_action_at.isoformat() if self.last_action_at else None
            ),
        }


# Singleton importable desde main.py
firewall_service = FirewallService()
