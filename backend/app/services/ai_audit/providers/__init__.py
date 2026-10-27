"""
Elección del proveedor según .env (AI_AUDIT_PROVIDER). Vacío: auditoría con
IA sin configurar. De momento solo "anthropic"; "openai" y "compatible"
(modelos locales con API de OpenAI) llegan en la fase 3.
"""

from app.core.config import settings
from app.services.ai_audit.providers.base import AuditProvider, AuditResult, ProviderError

__all__ = ["AuditProvider", "AuditResult", "ProviderError", "get_provider", "configuration_problem"]

PLANNED = {"openai", "compatible"}


def configuration_problem() -> str | None:
    """Por qué no se puede auditar con la configuración actual, o None."""
    name = settings.AI_AUDIT_PROVIDER.strip().lower()
    if not name:
        return "Sin proveedor: pon AI_AUDIT_PROVIDER en .env (por ahora, anthropic)"
    if name in PLANNED:
        return f"El proveedor {name} aún no está disponible"
    if name != "anthropic":
        return f"Proveedor desconocido: {name}"
    if not settings.AI_AUDIT_MODEL.strip():
        return "Falta AI_AUDIT_MODEL en .env"
    return None


def get_provider() -> AuditProvider:
    problem = configuration_problem()
    if problem:
        raise ProviderError(problem)
    from app.services.ai_audit.providers.anthropic_provider import AnthropicProvider
    return AnthropicProvider(
        model=settings.AI_AUDIT_MODEL.strip(),
        api_key=settings.AI_AUDIT_API_KEY,
        effort=settings.AI_AUDIT_EFFORT,
        timeout=settings.AI_AUDIT_TIMEOUT_SECONDS,
    )
