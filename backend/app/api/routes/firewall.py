from fastapi import APIRouter

router = APIRouter()

@router.get("/rules")
async def list_rules():
    return {"message": "TODO: reglas de firewall"}

@router.get("/status")
async def firewall_status():
    return {"active": False, "rules_count": 0}
