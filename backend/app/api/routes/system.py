from fastapi import APIRouter
import psutil, platform

router = APIRouter()

@router.get("/info")
async def system_info():
    return {
        "os": platform.system(),
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "uptime_seconds": int(psutil.boot_time()),
    }

@router.get("/status")
async def service_status():
    return {
        "monitor": "stopped",
        "suricata": "stopped",
        "firewall": "stopped",
    }
