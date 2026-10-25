"""
Canal de eventos en tiempo real (Server-Sent Events).

El panel abre GET /api/v1/events/stream con EventSource; el navegador envía
sola la cookie de sesión, así que la autenticación es la misma que en el
resto de la API. Cada evento se envía como:

    event: alert.created
    data: {"type": "alert.created", "data": {...}, "at": "..."}

Cada pocos segundos se manda un comentario (": ping") para que ni nginx ni
el navegador den la conexión por muerta. La conexión se cierra a los 15
minutos y EventSource reconecta solo: así se vuelve a comprobar la sesión.
"""

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.events.broker import event_broker

router = APIRouter()

_HEARTBEAT_SECONDS = 20
_MAX_STREAM_SECONDS = 15 * 60


@router.get("/stream")
async def stream(request: Request):
    async def event_source():
        started = time.monotonic()
        with event_broker.subscribe() as queue:
            # Indica al navegador cuánto esperar antes de reconectar
            yield "retry: 5000\n\n"
            while time.monotonic() - started < _MAX_STREAM_SECONDS:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                payload = json.dumps(event, default=str)
                yield f"event: {event['type']}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Desactiva el buffer de nginx para esta respuesta
            "X-Accel-Buffering": "no",
        },
    )
