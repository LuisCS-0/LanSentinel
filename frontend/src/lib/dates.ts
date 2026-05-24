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
