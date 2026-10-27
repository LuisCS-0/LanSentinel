"""
Informe de auditoría: el esquema que se pide al modelo y su validación.

El esquema está escrito a mano en JSON Schema (no generado por un SDK) para
que sirva igual a cualquier proveedor con salida estructurada. Después,
Pydantic valida la respuesta y validate() descarta lo que no se sostiene:
un hallazgo que cita un dispositivo que no está en la instantánea es una
invención del modelo y no llega al panel.
"""

import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Gravedad = Literal["critica", "alta", "media", "baja", "info"]
Categoria = Literal[
    "dispositivo", "servicio_expuesto", "alertas", "cortafuegos", "configuracion", "privacidad", "otro",
]
Accion = Literal["ninguna", "revisar", "bloquear", "escanear_puertos", "marcar_confianza", "activar_cuarentena"]

# Acciones que necesitan al menos un dispositivo
DEVICE_ACTIONS = {"bloquear", "escanear_puertos", "marcar_confianza"}

# Lo que el dueño hace con un hallazgo; "pendiente" es no haber hecho nada
EstadoHallazgo = Literal["pendiente", "aplicado", "descartado"]


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

# Para los servidores que no admiten salida estructurada: el esquema va en
# las instrucciones
SCHEMA_HINT = (
    "Responde solo con un objeto JSON, sin texto alrededor, que cumpla este esquema JSON:\n"
    + json.dumps(REPORT_SCHEMA, ensure_ascii=False, separators=(",", ":"))
)

_ORDER = {"critica": 0, "alta": 1, "media": 2, "baja": 3, "info": 4}
# Lo que escriben los modelos pequeños cuando no siguen el esquema al pie de la letra
_SYNONYMS = {
    "critical": "critica", "high": "alta", "medium": "media", "moderada": "media", "low": "baja",
    "informativa": "info", "informacion": "info", "ninguno": "ninguna", "none": "ninguna",
}


class ReportError(ValueError):
    """La respuesta del modelo no es un informe válido."""


def validate(raw: dict, known_devices: set[str]) -> tuple[Informe, list[dict]]:
    """
    Informe validado y lo descartado (con el motivo). Se descartan los
    hallazgos que citan dispositivos que no existen; una acción sobre
    dispositivos sin ninguno citado pasa a "revisar".
    """
    try:
        report = Informe.model_validate(_lenient(raw))
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


def _word(value) -> str:
    """"Crítica " → "critica"; "Escanear puertos" → "escanear_puertos"."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().strip().lower()
    text = text.replace(" ", "_").replace("-", "_")
    return _SYNONYMS.get(text, text)


def _lenient(raw):
    """
    Arregla lo que no cambia el sentido (mayúsculas, tildes, sinónimos en
    inglés, una lista que llega como texto, una puntuación decimal) antes de
    validar. Una categoría desconocida pasa a "otro" y una acción
    desconocida, a "revisar". Lo que no se entienda sigue fallando.
    """
    if not isinstance(raw, dict):
        return raw
    raw = dict(raw)
    if isinstance(raw.get("puntuacion"), (float, str)):
        try:
            raw["puntuacion"] = round(float(raw["puntuacion"]))
        except ValueError:
            pass
    raw.setdefault("positivos", [])
    if isinstance(raw.get("positivos"), str):
        raw["positivos"] = [raw["positivos"]]
    findings = raw.get("hallazgos")
    if isinstance(findings, list):
        fixed = []
        for h in findings:
            if isinstance(h, dict):
                h = dict(h)
                for key in ("gravedad", "categoria", "accion"):
                    if isinstance(h.get(key), str):
                        h[key] = _word(h[key])
                if h.get("categoria") not in Categoria.__args__:
                    h["categoria"] = "otro"
                if h.get("accion") not in Accion.__args__:
                    h["accion"] = "revisar"
                if isinstance(h.get("dispositivos"), str):
                    h["dispositivos"] = [h["dispositivos"]] if h["dispositivos"] else []
                h.setdefault("dispositivos", [])
            fixed.append(h)
        raw["hallazgos"] = fixed
    return raw


# ── Seguimiento de los hallazgos ─────────────────────────────────────────────

def with_finding_state(states: dict | None, report: dict | None, index: int, estado: str,
                       user: str | None, now) -> dict:
    """
    Estados de los hallazgos con el de `index` cambiado (un dict nuevo, para
    que SQLAlchemy vea el cambio en la columna JSONB). "pendiente" lo quita.
    """
    findings = (report or {}).get("hallazgos", [])
    if not 0 <= index < len(findings):
        raise ValueError("Ese hallazgo no existe en el informe")
    if estado not in EstadoHallazgo.__args__:
        raise ValueError(f"Estado desconocido: {estado}")
    states = dict(states or {})
    if estado == "pendiente":
        states.pop(str(index), None)
    else:
        states[str(index)] = {"estado": estado, "por": user, "en": now.isoformat(timespec="seconds")}
    return states


def pending_findings(report: dict | None, states: dict | None) -> int:
    """Hallazgos que nadie ha aplicado, revisado ni descartado."""
    states = states or {}
    return sum(1 for i in range(len((report or {}).get("hallazgos", []))) if str(i) not in states)
