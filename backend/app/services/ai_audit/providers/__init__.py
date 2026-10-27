"""
Elección del proveedor según .env (AI_AUDIT_PROVIDER). Vacío: auditoría con
IA sin configurar.

  anthropic   Claude (API de Anthropic). Modelo por defecto: claude-opus-5-5
  openai      OpenAI. Hay que decir el modelo
  compatible  cualquier servidor con la API de OpenAI (Ollama, LM Studio,
              llama.cpp, vLLM...) en AI_AUDIT_BASE_URL; modelo obligatorio
"""

from app.core.config import settings
from app.services.ai_audit.providers.base import AuditProvider, AuditResult, ProviderError

__all__ = [
    "AuditProvider", "AuditResult", "ProviderError", "get_provider", "configuration_problem",
    "provider_name", "model_name", "wants_compact",
]

PROVIDERS = ("anthropic", "openai", "compatible")
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}


def provider_name() -> str:
    return settings.AI_AUDIT_PROVIDER.strip().lower()


def model_name() -> str:
    return settings.AI_AUDIT_MODEL.strip() or DEFAULT_MODELS.get(provider_name(), "")


def configuration_problem() -> str | None:
    """Por qué no se puede auditar con la configuración actual, o None."""
    name = provider_name()
    if not name:
        return "Sin proveedor: pon AI_AUDIT_PROVIDER en .env (anthropic, openai o compatible)"
    if name not in PROVIDERS:
        return f"Proveedor desconocido: {name} (anthropic, openai o compatible)"
    if not model_name():
        return "Falta AI_AUDIT_MODEL en .env (el nombre del modelo en el servidor)"
    base_url = settings.AI_AUDIT_BASE_URL.strip()
    if name == "compatible" and not base_url:
        return "Falta AI_AUDIT_BASE_URL en .env (por ejemplo, http://192.168.1.50:11434/v1 para Ollama)"
    if base_url and not base_url.startswith(("http://", "https://")):
        return "AI_AUDIT_BASE_URL tiene que empezar por http:// o https://"
    return None


def wants_compact() -> bool:
    """Instantánea compacta: si se pide o, en "auto", con un servidor compatible (modelos pequeños)."""
    mode = settings.AI_AUDIT_COMPACT.strip().lower()
    if mode in ("true", "1", "si", "sí", "yes"):
        return True
    if mode in ("false", "0", "no"):
        return False
    return provider_name() == "compatible"


def get_provider() -> AuditProvider:
    problem = configuration_problem()
    if problem:
        raise ProviderError(problem)
    name = provider_name()
    if name == "anthropic":
        from app.services.ai_audit.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(
            model=model_name(), api_key=settings.AI_AUDIT_API_KEY,
            effort=settings.AI_AUDIT_EFFORT, timeout=settings.AI_AUDIT_TIMEOUT_SECONDS,
        )
    from app.services.ai_audit.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(
        model=model_name(), api_key=settings.AI_AUDIT_API_KEY,
        base_url=settings.AI_AUDIT_BASE_URL.strip() if name == "compatible" else "",
        effort=settings.AI_AUDIT_EFFORT, timeout=settings.AI_AUDIT_TIMEOUT_SECONDS,
    )
