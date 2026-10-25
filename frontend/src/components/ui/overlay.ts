// Comportamiento común de las capas superpuestas (modales, panel lateral,
// buscador): cerrar con Escape y bloquear el scroll de la página de fondo.

import { useEffect } from "react";

export function useEscape(active: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!active) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEscape();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [active, onEscape]);
}

// Varias capas abiertas a la vez comparten el bloqueo
let locks = 0;

export function useBodyScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return;
    locks++;
    document.body.style.overflow = "hidden";
    return () => {
      locks--;
      if (locks === 0) document.body.style.overflow = "";
    };
  }, [active]);
}
