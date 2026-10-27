"""
Informe de auditoría: el esquema que se pide al modelo y su validación.

El esquema está escrito a mano en JSON Schema (no generado por un SDK) para
que sirva igual a cualquier proveedor con salida estructurada. Después,
Pydantic valida la respuesta y validate() descarta lo que no se sostiene:
un hallazgo que cita un dispositivo que no está en la instantánea es una
invención del modelo y no llega al panel.

El informe tiene dos partes: los hallazgos (qué pasa) y un plan de acciones
(qué hacer dentro de LanSentinel), cada acción enlazada a su hallazgo. Las
acciones nunca se ejecutan solas: el dueño elige cuáles en el panel, que
las aplica por las rutas de siempre.
"""

import ipaddress
import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

Gravedad = Literal["critica", "alta", "media", "baja", "info"]
Categoria = Literal[
    "dispositivo", "servicio_expuesto", "alertas", "cortafuegos", "configuracion", "privacidad", "otro",
]
TipoAccion = Literal[
    # sobre un dispositivo (objetivo: su seudónimo)
    "bloquear_dispositivo", "desbloquear_dispositivo", "marcar_confianza", "quitar_confianza", "escanear_puertos",
    # sobre una IP de Internet (objetivo: la IP)
    "bloquear_ip", "desbloquear_ip",
    # de todo LanSentinel (sin objetivo)
    "activar_cuarentena", "desactivar_cuarentena", "actualizar_listas", "escanear_red", "hacer_copia",
]
DEVICE_ACTIONS = {"bloquear_dispositivo", "desbloquear_dispositivo", "marcar_confianza", "quitar_confianza",
                  "escanear_puertos"}
IP_ACTIONS = {"bloquear_ip", "desbloquear_ip"}
# Pares que se contradicen sobre el mismo objetivo: gana la primera
_OPPOSITES = [
    {"bloquear_dispositivo", "desbloquear_dispositivo"}, {"bloquear_dispositivo", "marcar_confianza"},
    {"marcar_confianza", "quitar_confianza"}, {"bloquear_ip", "desbloquear_ip"},
    {"activar_cuarentena", "desactivar_cuarentena"},
]
MAX_ACTIONS = 20

# Lo que el dueño hace con un hallazgo o una acción; "pendiente" es no haber hecho nada
EstadoHallazgo = Literal["pendiente", "aplicado", "descartado"]


class Hallazgo(BaseModel):
    gravedad: Gravedad
    categoria: Categoria
    titulo: str = Field(max_length=200)
    detalle: str = Field(max_length=2000)
    dispositivos: list[str]
    recomendacion: str = Field(max_length=1500)


class Accion(BaseModel):
    tipo: TipoAccion
    objetivo: str = Field(max_length=64)          # seudónimo, IP o "" si no tiene
    motivo: str = Field(max_length=500)
    hallazgo: int                                 # índice en hallazgos, -1 si ninguno


class Informe(BaseModel):
    puntuacion: int
    resumen: str = Field(max_length=3000)
    hallazgos: list[Hallazgo]
    positivos: list[str]
    acciones: list[Accion] = []


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
    })},
    "positivos": {"type": "array", "items": {"type": "string"}},
    "acciones": {"type": "array", "items": _strict({
        "tipo": _enum(TipoAccion),
        "objetivo": {"type": "string", "description": "seudónimo disp-NN, IP de Internet o vacío"},
        "motivo": {"type": "string"},
        "hallazgo": {"type": "integer", "description": "índice del hallazgo que la justifica, o -1"},
    })},
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
    "informativa": "info", "informacion": "info",
    "bloquear": "bloquear_dispositivo", "desbloquear": "desbloquear_dispositivo",
    "confianza": "marcar_confianza", "cuarentena": "activar_cuarentena", "copia": "hacer_copia",
}


class ReportError(ValueError):
    """La respuesta del modelo no es un informe válido."""


def validate(raw: dict, known_devices: set[str], known_ips: set[str] = frozenset()) -> tuple[Informe, list[dict]]:
    """
    Informe validado y lo descartado (con el motivo):
      - hallazgos que citan dispositivos que no existen;
      - acciones sobre dispositivos que no existen, sobre IPs que no son de
        Internet o que no aparecen en la instantánea, enlazadas a un
        hallazgo descartado, repetidas o que contradicen otra anterior.
    Los hallazgos se ordenan por gravedad y las acciones siguen apuntando al
    suyo.
    """
    try:
        report = Informe.model_validate(_lenient(raw))
    except ValidationError as exc:
        raise ReportError(f"El modelo devolvió un informe que no cumple el esquema: {exc.error_count()} errores") from exc

    discarded: list[dict] = []
    kept: list[tuple[int, Hallazgo]] = []
    for i, h in enumerate(report.hallazgos):
        unknown = [d for d in h.dispositivos if d not in known_devices]
        if unknown:
            discarded.append({"hallazgo": h.model_dump(), "motivo": f"Cita dispositivos inexistentes: {', '.join(unknown)}"})
            continue
        h.dispositivos = list(dict.fromkeys(h.dispositivos))
        kept.append((i, h))
    kept.sort(key=lambda x: _ORDER[x[1].gravedad])
    new_index = {old: new for new, (old, _) in enumerate(kept)}

    actions: list[Accion] = []
    for a in report.acciones:
        problem = _action_problem(a, known_devices, known_ips, report, new_index, actions)
        if problem:
            discarded.append({"accion": a.model_dump(), "motivo": problem})
            continue
        if a.tipo not in DEVICE_ACTIONS | IP_ACTIONS:
            a.objetivo = ""
        a.hallazgo = new_index.get(a.hallazgo, -1)
        actions.append(a)

    report.hallazgos = [h for _, h in kept]
    report.acciones = actions[:MAX_ACTIONS]
    report.puntuacion = max(0, min(100, report.puntuacion))
    return report, discarded


def _action_problem(a: Accion, known_devices, known_ips, report: Informe, new_index: dict, accepted) -> str | None:
    if a.tipo in DEVICE_ACTIONS and a.objetivo not in known_devices:
        return f"Dispositivo inexistente: {a.objetivo or '(ninguno)'}"
    if a.tipo in IP_ACTIONS:
        try:
            addr = ipaddress.ip_address(a.objetivo)
            public = addr.is_global and not addr.is_multicast
        except ValueError:
            return f"No es una IP: {a.objetivo or '(ninguna)'}"
        if not public:
            return f"{a.objetivo} no es una IP de Internet"
        if a.objetivo not in known_ips:
            return f"{a.objetivo} no aparece en la instantánea"
    if 0 <= a.hallazgo < len(report.hallazgos) and a.hallazgo not in new_index:
        return "Su hallazgo se descartó"
    target = a.objetivo if a.tipo in DEVICE_ACTIONS | IP_ACTIONS else ""
    for b in accepted:
        if b.objetivo == target and (b.tipo == a.tipo or {a.tipo, b.tipo} in _OPPOSITES):
            return "Repetida o contraria a otra acción del plan"
    return None


def _word(value) -> str:
    """"Crítica " → "critica"; "Escanear puertos" → "escanear_puertos"."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().strip().lower()
    text = text.replace(" ", "_").replace("-", "_")
    return _SYNONYMS.get(text, text)


def _lenient(raw):
    """
    Arregla lo que no cambia el sentido (mayúsculas, tildes, sinónimos en
    inglés, una lista que llega como texto, una puntuación decimal, un
    objetivo vacío como null) antes de validar. Una categoría desconocida
    pasa a "otro"; una acción de tipo desconocido se quita (no se puede
    aplicar). Lo que no se entienda sigue fallando.
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
                for key in ("gravedad", "categoria"):
                    if isinstance(h.get(key), str):
                        h[key] = _word(h[key])
                if h.get("categoria") not in Categoria.__args__:
                    h["categoria"] = "otro"
                if isinstance(h.get("dispositivos"), str):
                    h["dispositivos"] = [h["dispositivos"]] if h["dispositivos"] else []
                h.setdefault("dispositivos", [])
            fixed.append(h)
        raw["hallazgos"] = fixed
    actions = raw.get("acciones")
    if isinstance(actions, list):
        fixed = []
        for a in actions:
            if isinstance(a, dict):
                a = dict(a)
                if isinstance(a.get("tipo"), str):
                    a["tipo"] = _word(a["tipo"])
                if a.get("tipo") not in TipoAccion.__args__:
                    continue
                a["objetivo"] = str(a.get("objetivo") or "").strip()
                a.setdefault("motivo", "")
                if a.get("hallazgo") is None:
                    a["hallazgo"] = -1
            fixed.append(a)
        raw["acciones"] = fixed
    elif actions is None:
        raw["acciones"] = []
    return raw


# ── Seguimiento de hallazgos y acciones ──────────────────────────────────────

def with_state(states: dict | None, items: list, index: int, estado: str, user: str | None, now,
               what: str = "Ese hallazgo") -> dict:
    """
    Estados de los hallazgos (o de las acciones) con el de `index` cambiado:
    un dict nuevo, para que SQLAlchemy vea el cambio en la columna JSONB.
    "pendiente" lo quita.
    """
    if not 0 <= index < len(items):
        raise ValueError(f"{what} no existe en el informe")
    if estado not in EstadoHallazgo.__args__:
        raise ValueError(f"Estado desconocido: {estado}")
    states = dict(states or {})
    if estado == "pendiente":
        states.pop(str(index), None)
    else:
        states[str(index)] = {"estado": estado, "por": user, "en": now.isoformat(timespec="seconds")}
    return states


def with_finding_state(states: dict | None, report: dict | None, index: int, estado: str,
                       user: str | None, now) -> dict:
    return with_state(states, (report or {}).get("hallazgos", []), index, estado, user, now)


def with_action_state(states: dict | None, report: dict | None, index: int, estado: str,
                      user: str | None, now) -> dict:
    return with_state(states, (report or {}).get("acciones", []), index, estado, user, now, what="Esa acción")


def pending_findings(report: dict | None, states: dict | None) -> int:
    """Hallazgos que nadie ha aplicado, revisado ni descartado."""
    states = states or {}
    return sum(1 for i in range(len((report or {}).get("hallazgos", []))) if str(i) not in states)
