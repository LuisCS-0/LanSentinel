// Modo del panel: "experto" (todo, con el detalle técnico) o "basico" (lo
// esencial, en lenguaje sencillo, para quien no sabe de redes). Se guarda en
// este navegador, como el tema. No cambia lo que se puede hacer: los
// permisos los pone el backend; solo cambia lo que se enseña.

import { useSyncExternalStore } from "react";

export type ViewMode = "basico" | "experto";

const KEY = "lansentinel-modo";
const listeners = new Set<() => void>();

function read(): ViewMode {
  try {
    return localStorage.getItem(KEY) === "basico" ? "basico" : "experto";
  } catch {
    return "experto";
  }
}

export function setViewMode(mode: ViewMode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // Sin almacenamiento (modo privado): vale solo para esta visita
  }
  listeners.forEach(l => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useViewMode(): ViewMode {
  return useSyncExternalStore(subscribe, read);
}

export function useIsBasic(): boolean {
  return useViewMode() === "basico";
}
