"""
Interfaz común de los proveedores de IA.

La auditoría no sabe con qué modelo habla: recibe un proveedor que, con
unas instrucciones y un mensaje, devuelve el informe como diccionario (que
luego valida report.py, igual para todos). Cada adaptador pide la salida
estructurada a su manera y traduce sus errores a ProviderError, con un
mensaje que se puede enseñar en el panel.
"""

from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """Fallo del proveedor, con un mensaje para el panel (sin secretos)."""


@dataclass
class AuditResult:
    data: dict                    # el informe, sin validar todavía
    model: str                    # el modelo que respondió (puede ser el de respaldo)
    input_tokens: int | None
    output_tokens: int | None


class AuditProvider(Protocol):
    name: str
    model: str
    local: bool                   # True si los datos no salen de la red de casa

    async def audit(self, instructions: str, message: str) -> AuditResult: ...

    async def check(self) -> str:
        """Comprueba la conexión y el modelo sin gastar tokens si se puede; devuelve un texto para el panel."""
        ...
