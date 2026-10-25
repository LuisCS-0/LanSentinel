import { formatDistanceToNow, parseISO } from "date-fns";
import { es } from "date-fns/locale";

// Formatea una fecha ISO del backend como "hace 5 minutos", "hace 2 horas", etc.
// Devuelve "—" si la fecha es null o inválida.
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true, locale: es });
  } catch {
    return "—";
  }
}

// Versión corta para tablas: "ahora", "hace 5 min", "hace 2 h", "hace 3 d"
export function shortRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(seconds)) return "—";
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`;
  if (seconds < 86400 * 30) return `hace ${Math.floor(seconds / 86400)} d`;
  return relativeTime(iso);
}
