"""
Adaptador de OpenAI y de los servidores compatibles con su API (Ollama,
LM Studio, llama.cpp, vLLM...), con el SDK oficial de OpenAI y la API de
Chat Completions, que es la que todos imitan.

- OpenAI: salida estructurada estricta (response_format json_schema) y
  esfuerzo de razonamiento (reasoning_effort). Si el modelo no razona y
  rechaza ese parámetro, se repite sin él.
- Compatibles: no todos entienden lo mismo. Se pide primero el esquema; si
  el servidor lo rechaza, JSON libre y, si tampoco, texto normal. En los
  dos últimos casos el esquema va en las instrucciones. Lo que devuelven se
  limpia antes de leerlo: bloques <think> de los modelos que razonan en
  voz alta y los ``` alrededor del JSON. Como siempre, report.py valida.
- Un compatible es "local" si su dirección es de la red de casa: entonces
  los datos no salen y el coste es cero.
"""

import ipaddress
import json
import re
from urllib.parse import urlparse

import openai

from app.services.ai_audit.providers.base import AuditResult, ProviderError
from app.services.ai_audit.report import REPORT_SCHEMA, SCHEMA_HINT

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LOCAL_SUFFIXES = (".lan", ".local", ".home.arpa", ".internal", ".localhost")

SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "informe_auditoria", "strict": True, "schema": REPORT_SCHEMA},
}
# Formatos de salida, del mejor al más básico (None: sin response_format)
COMPATIBLE_FORMATS = [SCHEMA_FORMAT, {"type": "json_object"}, None]


def is_local_url(url: str) -> bool:
    """True si la dirección es el propio equipo o la red de casa."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES) or "." not in host:
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local


class OpenAIProvider:

    def __init__(self, model: str, api_key: str = "", base_url: str = "", effort: str = "high",
                 timeout: float = 600):
        self.model = model
        self.effort = effort
        self.compatible = bool(base_url)
        self.name = "compatible" if self.compatible else "openai"
        self.local = self.compatible and is_local_url(base_url)
        # Un servidor local no suele pedir clave, pero el SDK necesita una;
        # sin base_url y sin clave, el SDK la busca en OPENAI_API_KEY
        key = api_key or ("sin-clave" if self.compatible else None)
        try:
            self.client = openai.AsyncOpenAI(
                api_key=key, base_url=base_url or None, timeout=timeout, max_retries=0 if self.compatible else 2,
            )
        except openai.OpenAIError as exc:
            raise ProviderError("Falta la clave de OpenAI: pon AI_AUDIT_API_KEY u OPENAI_API_KEY en .env") from exc

    async def audit(self, instructions: str, message: str) -> AuditResult:
        if self.compatible:
            response = await self._compatible(instructions, message)
        else:
            response = await self._openai(instructions, message)

        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise ProviderError("El modelo no devolvió ningún informe")
        if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
            raise ProviderError("El modelo rechazó la petición")
        if choice.finish_reason == "length":
            raise ProviderError("El informe no cupo en la respuesta del modelo (¿contexto demasiado pequeño?)")
        data = parse_json(choice.message.content)
        usage = response.usage
        return AuditResult(
            data=data, model=response.model or self.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    def _messages(self, instructions: str, message: str) -> list[dict]:
        return [{"role": "system", "content": instructions}, {"role": "user", "content": message}]

    async def _openai(self, instructions: str, message: str):
        kwargs = {"model": self.model, "messages": self._messages(instructions, message),
                  "response_format": SCHEMA_FORMAT, "reasoning_effort": self.effort}
        try:
            return await self.client.chat.completions.create(**kwargs)
        except openai.BadRequestError as exc:
            if "reasoning" not in str(exc.message).lower():
                raise _translate(exc) from exc
        except Exception as exc:
            raise _translate(exc) from exc
        # Modelo sin razonamiento: igual, sin el esfuerzo
        del kwargs["reasoning_effort"]
        try:
            return await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise _translate(exc) from exc

    async def _compatible(self, instructions: str, message: str):
        last: Exception | None = None
        for fmt in COMPATIBLE_FORMATS:
            system = instructions if fmt is SCHEMA_FORMAT else f"{instructions}\n{SCHEMA_HINT}"
            kwargs = {"model": self.model, "messages": self._messages(system, message)}
            if fmt is not None:
                kwargs["response_format"] = fmt
            try:
                return await self.client.chat.completions.create(**kwargs)
            except (openai.BadRequestError, openai.UnprocessableEntityError) as exc:
                last = exc                  # no entiende ese formato: el siguiente
            except Exception as exc:
                raise _translate(exc) from exc
        raise _translate(last) from last

    async def check(self) -> str:
        """Lista los modelos del servidor (no gasta tokens) y comprueba que está el configurado."""
        try:
            ids = [m.id async for m in self.client.models.list()]
        except openai.NotFoundError:
            return "Conectado (el servidor no lista sus modelos)"
        except Exception as exc:
            raise _translate(exc) from exc
        if self.model in ids:
            return f"Conectado: {self.model}"
        if not ids:
            return "Conectado (el servidor no lista sus modelos)"
        shown = ", ".join(sorted(ids)[:8]) + ("…" if len(ids) > 8 else "")
        raise ProviderError(f"El servidor responde, pero no tiene el modelo {self.model} (tiene: {shown})")


def parse_json(text: str | None) -> dict:
    """El JSON del informe, quitando lo que los modelos pequeños añaden alrededor."""
    if not text or not text.strip():
        raise ProviderError("El modelo no devolvió ningún informe")
    text = _THINK.sub("", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ProviderError("El modelo no devolvió un JSON")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as exc:
        raise ProviderError("El modelo devolvió un JSON no válido") from exc
    if not isinstance(data, dict):
        raise ProviderError("El modelo no devolvió un objeto JSON")
    return data


def _translate(exc: Exception) -> Exception:
    """Errores del SDK → mensajes para el panel, del más concreto al más general."""
    if isinstance(exc, openai.AuthenticationError):
        return ProviderError("La clave de la API no es válida")
    if isinstance(exc, openai.PermissionDeniedError):
        return ProviderError("La clave no tiene permiso para usar este modelo")
    if isinstance(exc, openai.NotFoundError):
        return ProviderError("El modelo no existe en el servidor o la dirección no es la de la API")
    if isinstance(exc, openai.RateLimitError):
        return ProviderError("Límite de peticiones alcanzado: prueba más tarde")
    if isinstance(exc, (openai.BadRequestError, openai.UnprocessableEntityError)):
        return ProviderError(f"El servidor rechazó la petición: {str(exc.message)[:300]}")
    if isinstance(exc, openai.APITimeoutError):
        return ProviderError("El modelo tardó demasiado en responder (AI_AUDIT_TIMEOUT_SECONDS)")
    if isinstance(exc, openai.APIStatusError):
        return ProviderError(f"Error del servidor del modelo ({exc.status_code})")
    if isinstance(exc, openai.APIConnectionError):
        return ProviderError("No se pudo conectar con el servidor del modelo")
    if isinstance(exc, ProviderError):
        return exc
    return ProviderError(f"Error inesperado del proveedor: {type(exc).__name__}")
