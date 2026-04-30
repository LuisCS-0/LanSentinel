from fastapi import APIRouter

# ─── Alerts ──────────────────────────────────────────────────────────────────
router = APIRouter()

@router.get("/")
async def list_alerts():
    return {"message": "TODO: listar alertas"}

@router.get("/summary")
async def alert_summary():
    return {"new": 0, "high": 0, "critical": 0}
