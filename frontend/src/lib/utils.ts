import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// Utilidad estándar de shadcn/ui: combina clases de Tailwind resolviendo conflictos.
// Ej: cn("p-2", "p-4") => "p-4"
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
