from fastapi import APIRouter
router = APIRouter()

@router.get("/stats")
async def network_stats():
    return {"message": "TODO: estadísticas globales de red"}

@router.post("/scan")
async def trigger_scan():
    return {"message": "TODO: lanzar escaneo ARP"}
