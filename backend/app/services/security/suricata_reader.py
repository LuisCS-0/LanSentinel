"""
Lector asíncrono del fichero eve.json de Suricata.

Suricata escribe un evento JSON por línea en eve.json a medida que detecta
actividad. Este módulo implementa un "tail -f" asíncrono que lee las líneas
nuevas según se van escribiendo y las entrega al callback proporcionado.

Características:
  - Persiste la posición leída en disco para sobrevivir reinicios sin
    reprocesar eventos antiguos ni perder los nuevos.
  - Detecta rotación del fichero (Suricata rota eve.json cuando crece) y
    reinicia desde el principio del nuevo fichero.
  - Tolerante a líneas malformadas: si una línea no es JSON válido se
    descarta y se continúa con la siguiente.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import AsyncIterator, Callable, Awaitable

import structlog

log = structlog.get_logger(__name__)

# Tipo del callback que recibe cada evento parseado
EventHandler = Callable[[dict], Awaitable[None]]


class SuricataReader:
    """
    Lee eve.json de forma incremental y entrega cada evento al handler.
    El offset (posición leída) se guarda en un fichero auxiliar.
    """

    def __init__(
        self,
        eve_path: str,
        offset_path: str | None = None,
        poll_interval: float = 1.0,
    ):
        self.eve_path = Path(eve_path)
        self.offset_path = Path(offset_path or f"{eve_path}.offset")
        self.poll_interval = poll_interval
        self._running = False

    # ── Gestión del offset ────────────────────────────────────────────────────

    def _load_offset(self) -> int:
        """Lee la posición desde donde continuar leyendo eve.json."""
        try:
            return int(self.offset_path.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _save_offset(self, offset: int) -> None:
        """Persiste la posición actual para el próximo arranque."""
        try:
            self.offset_path.write_text(str(offset))
        except Exception as exc:
            log.warning("suricata_reader.offset_save_error", error=str(exc))

    # ── Lectura incremental ───────────────────────────────────────────────────

    async def _read_new_lines(self, offset: int) -> tuple[list[str], int]:
        """
        Lee las líneas nuevas desde 'offset' hasta el final del fichero.
        Detecta rotación si el fichero es más pequeño que el offset guardado.
        """
        if not self.eve_path.exists():
            return [], offset

        size = self.eve_path.stat().st_size

        # Si el fichero ha menguado, Suricata lo ha rotado
        if size < offset:
            log.info("suricata_reader.file_rotated", new_size=size)
            offset = 0

        if size == offset:
            return [], offset  # no hay nada nuevo

        # Leer desde el offset hasta el final
        try:
            with self.eve_path.open("r", encoding="utf-8") as f:
                f.seek(offset)
                content = f.read()
                new_offset = f.tell()
        except Exception as exc:
            log.error("suricata_reader.read_error", error=str(exc))
            return [], offset

        # Solo devolvemos líneas completas (terminadas en \n).
        # Si la última línea está a medio escribir, la dejamos para el próximo tick.
        lines = content.split("\n")
        if not content.endswith("\n"):
            # ajustar offset para reintentar la línea incompleta
            incomplete = lines.pop()
            new_offset -= len(incomplete.encode("utf-8"))

        return [l for l in lines if l.strip()], new_offset

    # ── Bucle principal ───────────────────────────────────────────────────────

    async def run(self, handler: EventHandler) -> None:
        """
        Bucle de lectura. Cada poll_interval segundos lee las líneas nuevas,
        las parsea como JSON y se las entrega al handler.
        """
        self._running = True
        offset = self._load_offset()
        log.info("suricata_reader.started", path=str(self.eve_path), offset=offset)

        while self._running:
            try:
                lines, new_offset = await self._read_new_lines(offset)

                for line in lines:
                    try:
                        event = json.loads(line)
                        await handler(event)
                    except json.JSONDecodeError:
                        log.warning("suricata_reader.bad_json", line=line[:200])
                        continue
                    except Exception as exc:
                        log.error("suricata_reader.handler_error", error=str(exc))
                        continue

                if new_offset != offset:
                    offset = new_offset
                    self._save_offset(offset)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("suricata_reader.loop_error", error=str(exc))

            await asyncio.sleep(self.poll_interval)

        log.info("suricata_reader.stopped")

    def stop(self) -> None:
        self._running = False
