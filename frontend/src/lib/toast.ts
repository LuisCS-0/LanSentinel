// Avisos flotantes ("toasts") sin dependencias: un pequeño almacén global
// al que cualquier parte de la app puede añadir avisos con toast(), y que
// <Toaster /> muestra en una esquina.

import { useSyncExternalStore } from "react";
import type { AlertSeverity } from "@/lib/types";

export interface Toast {
  id: number;
  title: string;
  description?: string | null;
  severity?: AlertSeverity;
}

const DURATION_MS = 8000;
const MAX_VISIBLE = 4;

let toasts: Toast[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach(l => l());
}

export function dismissToast(id: number) {
  toasts = toasts.filter(t => t.id !== id);
  emit();
}

export function toast(input: Omit<Toast, "id">) {
  const id = nextId++;
  // Los más recientes arriba; si hay muchos, se descartan los más antiguos
  toasts = [{ ...input, id }, ...toasts].slice(0, MAX_VISIBLE);
  emit();
  window.setTimeout(() => dismissToast(id), DURATION_MS);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(subscribe, () => toasts);
}
