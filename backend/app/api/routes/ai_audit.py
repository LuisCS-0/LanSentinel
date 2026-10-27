"""
Auditoría con IA (solo administradores). De momento, la vista previa: la
instantánea exacta que se enviaría al modelo, su tamaño y la equivalencia
de seudónimos (esta no se envía nunca).
"""

from fastapi import APIRouter

from app.services.ai_audit import collect

router = APIRouter()


@router.get("/preview")
async def preview():
    snapshot = await collect.build()
    text = snapshot.to_json()
    return {
        "snapshot": snapshot.data,
        "characters": len(text),
        "approx_tokens": snapshot.approx_tokens(),
        "mapping": snapshot.mapping,
    }
