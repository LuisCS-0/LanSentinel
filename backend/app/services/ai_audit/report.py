"""
Informe de auditoría: el esquema que se pide al modelo y su validación.

El esquema está escrito a mano en JSON Schema (no generado por un SDK) para
que sirva igual a cualquier proveedor con salida estructurada. Después,
Pydantic valida la respuesta y validate() descarta lo que no se sostiene:
un hallazgo que cita un dispositivo que no está en la instantánea es una
invención del modelo y no llega al panel.
"""

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Gravedad = Literal["critica", "alta", "media", "baja", "info"]
Categoria = Literal[
    "dispositivo", "servicio_expuesto", "alertas", "cortafuegos", "configuracion", "privacidad", "otro",
]
Accion = Literal["ninguna", "revisar", "bloquear", "escanear_puertos", "marcar_confianza", "activar_cuarentena"]

# Acciones que necesitan al menos un dispositivo
DEVICE_ACTIONS = {"bloquear", "escanear_puertos", "marcar_confianza"}


class Hallazgo(BaseModel):
    gravedad: Gravedad
    categoria: Categoria
    titulo: str = Field(max_length=200)
    detalle: str = Field(max_length=2000)
    dispositivos: list[str]
    recomendacion: str = Field(max_length=1500)
    accion: Accion


class Informe(BaseModel):
    puntuacion: int
    resumen: str = Field(max_length=3000)
    hallazgos: list[Hallazgo]
    positivos: list[str]


def _strict(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _enum(values) -> dict:
    return {"type": "string", "enum": list(values.__args__)}


REPORT_SCHEMA = _strict({
    "puntuacion": {"type": "integer", "description": "0 (muy mal) a 100 (impecable)"},
    "resumen": {"type": "string"},
    "hallazgos": {"type": "array", "items": _strict({
        "gravedad": _enum(Gravedad),
        "categoria": _enum(Categoria),
        "titulo": {"type": "string"},
        "detalle": {"type": "string"},
        "dispositivos": {"type": "array", "items": {"type": "string"}},
        "recomendacion": {"type": "string"},
        "accion": _enum(Accion),
    })},
    "positivos": {"type": "array", "items": {"type": "string"}},
})

_ORDER = {"critica": 0, "alta": 1, "media": 2, "baja": 3, "info": 4}


class ReportError(ValueError):
    """La respuesta del modelo no es un informe válido."""


def validate(raw: dict, known_devices: set[str]) -> tuple[Informe, list[dict]]:
    """
    Informe validado y lo descartado (con el motivo). Se descartan los
    hallazgos que citan dispositivos que no existen; una acción sobre
    dispositivos sin ninguno citado pasa a "revisar".
    """
    try:
        report = Informe.model_validate(raw)
    except ValidationError as exc:
        raise ReportError(f"El modelo devolvió un informe que no cumple el esquema: {exc.error_count()} errores") from exc

    kept, discarded = [], []
    for h in report.hallazgos:
        unknown = [d for d in h.dispositivos if d not in known_devices]
        if unknown:
            discarded.append({"hallazgo": h.model_dump(), "motivo": f"Cita dispositivos inexistentes: {', '.join(unknown)}"})
            continue
        if h.accion in DEVICE_ACTIONS and not h.dispositivos:
            h.accion = "revisar"
        h.dispositivos = list(dict.fromkeys(h.dispositivos))
        kept.append(h)
    kept.sort(key=lambda h: _ORDER[h.gravedad])
    report.hallazgos = kept
    report.puntuacion = max(0, min(100, report.puntuacion))
    return report, discarded
