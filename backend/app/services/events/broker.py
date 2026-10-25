"""
Bus de eventos en memoria para notificar al panel en tiempo real.

Cada conexión SSE del frontend se suscribe con su propia cola. Cuando algo
cambia (p. ej. se crea una alerta), el código llama a publish() y el evento
llega a todas las colas. Si un cliente lento acumula demasiados eventos, se
descartan los suyos en lugar de bloquear a quien publica: el panel sigue
teniendo el sondeo periódico como respaldo.

Vive en el proceso del backend (un único worker de uvicorn), así que no
necesita Redis ni nada externo.
"""

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import structlog

log = structlog.get_logger(__name__)

_QUEUE_SIZE = 100


class EventBroker:

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event_type: str, data: dict) -> None:
        """Envía un evento a todos los suscriptores. Nunca bloquea."""
        event = {
            "type": event_type,
            "data": data,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("event_broker.subscriber_queue_full", type=event_type)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)


event_broker = EventBroker()
