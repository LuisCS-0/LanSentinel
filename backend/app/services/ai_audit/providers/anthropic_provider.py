"""
Adaptador de Claude (API de Anthropic, SDK oficial).

- Salida estructurada (output_config.format) con el esquema de report.py.
- Esfuerzo configurable (AI_AUDIT_EFFORT, "high" por defecto): en los
  modelos actuales el razonamiento siempre está activo y el esfuerzo es lo
  que lo regula.
- En streaming, para no chocar con los tiempos de espera de una respuesta
  larga.
- Respaldo ante rechazos: un informe de seguridad puede activar los filtros
  del modelo; con fallbacks "default" la API repite la petición en el modelo
  que Anthropic recomienda para ese caso. Haiku no lo admite.
- La clave sale de AI_AUDIT_API_KEY o, si está vacía, de ANTHROPIC_API_KEY.
"""

import json
import os

import anthropic

from app.services.ai_audit.providers.base import AuditResult, ProviderError
from app.services.ai_audit.report import REPORT_SCHEMA

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 32000


class AnthropicProvider:
    name = "anthropic"
    local = False

    def __init__(self, model: str, api_key: str = "", effort: str = "high", timeout: float = 600):
        self.model = model
        self.effort = effort
        # Sin clave explícita, el SDK la busca en el entorno (ANTHROPIC_API_KEY)
        if not api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderError("Falta la clave de Anthropic: ponla en Ajustes → Auditoría con IA")
        self.client = anthropic.AsyncAnthropic(api_key=api_key or None, timeout=timeout, max_retries=2)

    def _fallbacks(self) -> dict:
        if self.model.startswith("claude-haiku"):
            return {}
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"}

    async def audit(self, instructions: str, message: str) -> AuditResult:
        try:
            async with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=instructions,
                messages=[{"role": "user", "content": message}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": REPORT_SCHEMA},
                },
                **self._fallbacks(),
            ) as stream:
                response = await stream.get_final_message()
        except Exception as exc:
            raise _translate(exc) from exc

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            raise ProviderError(f"El modelo rechazó la petición ({category or 'sin categoría'})")
        if response.stop_reason == "max_tokens":
            raise ProviderError("El informe no cupo en la respuesta del modelo")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise ProviderError("El modelo no devolvió ningún informe")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ProviderError("El modelo devolvió un JSON no válido") from exc
        return AuditResult(
            data=data, model=response.model,
            input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
        )

    async def check(self) -> str:
        """Consulta el modelo en la API de modelos: valida clave y nombre sin gastar tokens."""
        try:
            info = await self.client.models.retrieve(self.model)
        except Exception as exc:
            raise _translate(exc) from exc
        return f"Conectado: {info.display_name}"


def _translate(exc: Exception) -> Exception:
    """Errores del SDK → mensajes para el panel, del más concreto al más general."""
    if isinstance(exc, anthropic.AuthenticationError):
        return ProviderError("La clave de la API de Anthropic no es válida")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return ProviderError("La clave no tiene permiso para usar este modelo")
    if isinstance(exc, anthropic.NotFoundError):
        return ProviderError("El modelo no existe o la clave no tiene acceso a él")
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderError("Límite de peticiones de Anthropic alcanzado: prueba más tarde")
    if isinstance(exc, anthropic.BadRequestError):
        return ProviderError(f"Anthropic rechazó la petición: {exc.message}")
    if isinstance(exc, anthropic.APIStatusError):
        return ProviderError(f"Error de la API de Anthropic ({exc.status_code})")
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError("No se pudo conectar con la API de Anthropic")
    if isinstance(exc, ProviderError):
        return exc
    return ProviderError(f"Error inesperado del proveedor: {type(exc).__name__}")
