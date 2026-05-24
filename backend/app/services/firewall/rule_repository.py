"""
Capa de acceso a datos para las reglas de cortafuegos.

Centraliza todas las operaciones sobre la tabla firewall_rules siguiendo
el mismo patrón Repository que device_repository.py.
"""

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.firewall_rule import (
    FirewallRule, FwAction, FwDirection, FwProtocol,
)

log = structlog.get_logger(__name__)


class FirewallRuleRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Operaciones de creación ──────────────────────────────────────────────

    async def create_block_rule(
        self,
        ip: str,
        name: str,
        description: str | None = None,
        device_id: UUID | None = None,
        auto_generated: bool = False,
    ) -> FirewallRule:
        """
        Crea una regla de bloqueo (DROP) por IP origen. Es la operación más
        habitual y, en la fase actual, la única que el sistema utiliza.
        """
        rule = FirewallRule(
            name=name,
            description=description,
            is_active=True,
            priority=100,
            direction=FwDirection.inbound,
            action=FwAction.drop,
            protocol=FwProtocol.any,
            src_ip=ip,
            device_id=device_id,
            auto_generated=auto_generated,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        log.info(
            "firewall_repo.rule_created",
            rule_id=rule.id, ip=ip, auto=auto_generated,
        )
        return rule

    # ── Consultas ────────────────────────────────────────────────────────────

    async def get_all_active(self) -> list[FirewallRule]:
        """Devuelve todas las reglas activas, ordenadas por prioridad."""
        result = await self.db.execute(
            select(FirewallRule)
            .where(FirewallRule.is_active == True) 
            .order_by(FirewallRule.priority.desc(), FirewallRule.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_all(self) -> list[FirewallRule]:
        """Devuelve todas las reglas (activas e inactivas) más recientes primero."""
        result = await self.db.execute(
            select(FirewallRule).order_by(FirewallRule.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, rule_id: int) -> FirewallRule | None:
        result = await self.db.execute(
            select(FirewallRule).where(FirewallRule.id == rule_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_ip(self, ip: str) -> FirewallRule | None:
        """Comprueba si ya existe una regla activa de bloqueo para esta IP."""
        result = await self.db.execute(
            select(FirewallRule).where(
                (FirewallRule.src_ip == ip)
                & (FirewallRule.is_active == True) 
                & (FirewallRule.action == FwAction.drop)
            )
        )
        return result.scalar_one_or_none()

    # ── Operaciones de modificación ──────────────────────────────────────────

    async def deactivate(self, rule_id: int) -> bool:
        """
        Marca la regla como inactiva en BD. La eliminación real en iptables
        la realiza el firewall_service tras llamar a este método.
        """
        rule = await self.get_by_id(rule_id)
        if not rule:
            return False
        rule.is_active = False
        rule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        log.info("firewall_repo.rule_deactivated", rule_id=rule_id)
        return True

    async def delete(self, rule_id: int) -> bool:
        """Borrado físico de una regla. Solo se usa en limpieza administrativa."""
        rule = await self.get_by_id(rule_id)
        if not rule:
            return False
        await self.db.delete(rule)
        await self.db.commit()
        log.info("firewall_repo.rule_deleted", rule_id=rule_id)
        return True
