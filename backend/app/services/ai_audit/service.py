"""
Auditorías con IA: lanzarlas, guardarlas y consultarlas.

Una auditoría tarda (el modelo razona sobre toda la red), así que run()
guarda una fila "running" y la ejecuta en segundo plano; el panel consulta
su estado. Solo una a la vez. Al arrancar, las que quedaron a medias por un
reinicio se marcan como fallidas.
"""

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.ai_audit import AiAuditRun
from app.services.ai_audit import collect, prompt
from app.services.ai_audit.providers import ProviderError, get_provider
from app.services.ai_audit.report import ReportError, validate, with_action_state, with_finding_state
from app.services.ai_audit.snapshot import public_ips

log = structlog.get_logger(__name__)

# Precio por millón de tokens (entrada, salida) en USD, para estimar el coste.
# Un modelo que no esté aquí sale sin coste estimado salvo que se den
# AI_AUDIT_PRICE_INPUT/OUTPUT (que mandan); los locales, gratis
PRICES = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


def estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None, local: bool) -> float | None:
    if local:
        return 0.0
    price = PRICES.get(model)
    if settings.AI_AUDIT_PRICE_INPUT or settings.AI_AUDIT_PRICE_OUTPUT:
        price = (settings.AI_AUDIT_PRICE_INPUT, settings.AI_AUDIT_PRICE_OUTPUT)
    if price is None or input_tokens is None or output_tokens is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 4)


class AuditBusy(Exception):
    pass


class AiAuditService:

    def __init__(self):
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Las auditorías que un reinicio dejó a medias ya no van a terminar."""
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(AiAuditRun).where(AiAuditRun.status == "running")
                .values(status="error", error="Interrumpida por un reinicio del backend",
                        finished_at=datetime.now(timezone.utc))
            )
            await db.commit()

    async def run(self, requested_by: str | None) -> int:
        if self.running:
            raise AuditBusy("Ya hay una auditoría en marcha")
        provider = get_provider()           # ProviderError si no está configurado
        snapshot = await collect.build()
        async with AsyncSessionLocal() as db:
            row = AiAuditRun(
                status="running", requested_by=requested_by, provider=provider.name,
                model=provider.model, local=provider.local,
                snapshot=snapshot.data, mapping=snapshot.mapping,
            )
            db.add(row)
            await db.commit()
            audit_id = row.id
        self._task = asyncio.create_task(self._execute(audit_id, provider, snapshot))
        log.info("ai_audit.started", id=audit_id, provider=provider.name, model=provider.model)
        return audit_id

    async def _execute(self, audit_id: int, provider, snapshot) -> None:
        values: dict = {}
        try:
            instructions, message = prompt.render(snapshot)
            result = await provider.audit(instructions, message)
            known = {d["id"] for d in snapshot.data["dispositivos"]}
            report, discarded = validate(result.data, known, public_ips(snapshot.data))
            values = {
                "status": "done", "model": result.model, "report": report.model_dump(), "discarded": discarded,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "cost_usd": estimate_cost(result.model, result.input_tokens, result.output_tokens, provider.local),
            }
            log.info("ai_audit.done", id=audit_id, findings=len(report.hallazgos), discarded=len(discarded))
        except (ProviderError, ReportError) as exc:
            values = {"status": "error", "error": str(exc)}
            log.warning("ai_audit.failed", id=audit_id, error=str(exc))
        except Exception as exc:
            values = {"status": "error", "error": f"Error inesperado: {type(exc).__name__}"}
            log.error("ai_audit.crashed", id=audit_id, error=str(exc))
        finally:
            values["finished_at"] = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                await db.execute(update(AiAuditRun).where(AiAuditRun.id == audit_id).values(**values))
                await db.commit()

    async def set_finding_state(self, audit_id: int, index: int, estado: str, user: str | None) -> AiAuditRun | None:
        """Marca un hallazgo como aplicado, descartado o pendiente (ValueError si no existe)."""
        async with AsyncSessionLocal() as db:
            row = await db.get(AiAuditRun, audit_id)
            if row is None:
                return None
            row.finding_states = with_finding_state(
                row.finding_states, row.report, index, estado, user, datetime.now(timezone.utc),
            )
            await db.commit()
            await db.refresh(row)
            return row

    async def set_action_state(self, audit_id: int, index: int, estado: str, user: str | None) -> AiAuditRun | None:
        """Marca una acción del plan como aplicada, descartada o pendiente (ValueError si no existe)."""
        async with AsyncSessionLocal() as db:
            row = await db.get(AiAuditRun, audit_id)
            if row is None:
                return None
            row.action_states = with_action_state(
                row.action_states, row.report, index, estado, user, datetime.now(timezone.utc),
            )
            await db.commit()
            await db.refresh(row)
            return row

    async def delete(self, audit_id: int) -> bool:
        """Borra un informe; el que está en marcha no (AuditBusy)."""
        async with AsyncSessionLocal() as db:
            row = await db.get(AiAuditRun, audit_id)
            if row is None:
                return False
            if row.status == "running":
                raise AuditBusy("Esa auditoría sigue en marcha")
            await db.delete(row)
            await db.commit()
            return True

    async def list(self, limit: int = 20) -> list[AiAuditRun]:
        async with AsyncSessionLocal() as db:
            return list((await db.execute(
                select(AiAuditRun).order_by(AiAuditRun.id.desc()).limit(limit)
            )).scalars().all())

    async def get(self, audit_id: int) -> AiAuditRun | None:
        async with AsyncSessionLocal() as db:
            return await db.get(AiAuditRun, audit_id)


ai_audit_service = AiAuditService()
