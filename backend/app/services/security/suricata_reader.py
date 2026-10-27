"""
Lector asíncrono del fichero eve.json de Suricata.

Suricata escribe un evento JSON por línea en eve.json a medida que detecta
actividad. Este módulo implementa un "tail -f" asíncrono que lee las líneas
nuevas según se van escribiendo y las entrega al callback proporcionado.

Características:
  - Persiste la posición leída en disco para sobrevivir reinicios sin
    reprocesar eventos antiguos ni perder los nuevos.
  - Detecta rotación del fichero (docker/suricata/arranque.sh lo renombra a
    eve.json.1 cuando crece): termina de leer lo que quedaba en el .1 y sigue
    desde el principio del nuevo, así no se pierden los eventos escritos
    entre la última lectura y la rotación.
  - Tolerante a líneas malformadas: si una línea no es JSON válido se
    descarta y se continúa con la siguiente.
"""

import asyncio
import json
from pathlib import Path
from typing import Callable, Awaitable

import structlog

log = structlog.get_logger(__name__)

# Tipo del callback que recibe cada evento parseado
EventHandler = Callable[[dict], Awaitable[None]]

# Máximo de bytes leídos de eve.json en cada sondeo
_MAX_READ_BYTES = 4 * 1024 * 1024


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
        # Inodo del eve.json leído por última vez, para detectar rotaciones
        self._inode: int | None = None

    # ── Gestión del offset ────────────────────────────────────────────────────

    def _load_offset(self) -> int:
        """
        Lee la posición desde donde continuar leyendo eve.json. Junto a ella va
        el inodo del fichero, para notar una rotación hecha con el backend
        parado (versiones anteriores solo guardaban la posición).
        """
        try:
            parts = self.offset_path.read_text().split()
            if len(parts) > 1:
                self._inode = int(parts[1])
            return int(parts[0])
        except (FileNotFoundError, ValueError, IndexError):
            return 0

    def _save_offset(self, offset: int) -> None:
        """Persiste la posición actual (y el inodo) para el próximo arranque."""
        try:
            text = f"{offset} {self._inode}" if self._inode is not None else str(offset)
            self.offset_path.write_text(text)
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

        stat = self.eve_path.stat()
        size = stat.st_size

        # Rotación: el fichero ha menguado o es otro fichero (otro inodo).
        # Comprobar solo el tamaño no basta si el nuevo eve.json ya ha
        # crecido por encima del offset antes de la siguiente lectura.
        rotated = size < offset or (self._inode is not None and stat.st_ino != self._inode)
        drained: list[str] = []
        if rotated:
            if self._inode is not None and stat.st_ino != self._inode:
                drained = self._drain_rotated(self._inode, offset)
            log.info("suricata_reader.file_rotated", new_size=size, recovered=len(drained))
            offset = 0
        self._inode = stat.st_ino

        lines, new_offset = self._read_from(self.eve_path, offset, size)
        return drained + lines, new_offset

    def _drain_rotated(self, old_inode: int, offset: int) -> list[str]:
        """Lo que quedaba por leer del fichero rotado (eve.json.1), si es el que se leía."""
        rotated = self.eve_path.with_name(self.eve_path.name + ".1")
        try:
            stat = rotated.stat()
        except FileNotFoundError:
            return []
        if stat.st_ino != old_inode:
            return []
        lines: list[str] = []
        while offset < stat.st_size:
            chunk, new_offset = self._read_from(rotated, offset, stat.st_size)
            if new_offset == offset:
                break           # queda una línea sin terminar: se descarta
            lines.extend(chunk)
            offset = new_offset
        return lines

    def _read_from(self, path: Path, offset: int, size: int) -> tuple[list[str], int]:
        """Líneas completas de path desde offset; devuelve también la nueva posición."""
        if size == offset:
            return [], offset  # no hay nada nuevo

        # Leer en binario desde el offset: así el offset son bytes exactos.
        # Se limita cada lectura para no cargar en memoria un eve.json enorme
        # de golpe (p. ej. la primera vez); el resto se lee en las siguientes.
        try:
            with path.open("rb") as f:
                f.seek(offset)
                content = f.read(_MAX_READ_BYTES)
        except Exception as exc:
            log.error("suricata_reader.read_error", error=str(exc))
            return [], offset

        # Solo devolvemos líneas completas (terminadas en \n).
        # Si la última línea está a medio escribir, la dejamos para el próximo tick.
        last_newline = content.rfind(b"\n")
        if last_newline < 0:
            if len(content) == _MAX_READ_BYTES:
                # Una "línea" más larga que el límite no es un evento válido:
                # se descarta para no quedarse atascado en ella
                log.warning("suricata_reader.line_too_long", offset=offset)
                return [], offset + len(content)
            return [], offset
        complete = content[:last_newline + 1]
        new_offset = offset + len(complete)

        lines = complete.decode("utf-8", errors="replace").split("\n")
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
