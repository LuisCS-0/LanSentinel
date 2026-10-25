// Tema del panel: oscuro (predeterminado), claro o el del sistema. Se guarda
// en este navegador y se aplica con la clase "dark" en <html>; index.html lo
// aplica ya antes de pintar para que no parpadee.

import { useSyncExternalStore } from "react";

export type Theme = "dark" | "light" | "system";

const KEY = "lansentinel-theme";
const listeners = new Set<() => void>();
const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

function read(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "system" ? value : "dark";
  } catch {
    return "dark";
  }
}

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && systemDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Sin almacenamiento (modo privado): se aplica solo en esta visita
  }
  apply(theme);
  listeners.forEach(l => l());
}

// Si el tema es "system", sigue los cambios del sistema operativo
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (read() === "system") apply("system");
  listeners.forEach(l => l());
});

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, read);
}

// ¿Se está viendo en oscuro ahora? (para colores que no van por CSS)
export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, () => document.documentElement.classList.contains("dark"));
}
