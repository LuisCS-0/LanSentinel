// Fila compacta con el estado de un servicio (monitor, security, firewall).
// Muestra el nombre, un punto verde/rojo y la información adicional.

import { cn } from "@/lib/utils";

interface ServiceStatusProps {
  name: string;
  running: boolean;
  info?: string;
}

export function ServiceStatus({ name, running, info }: ServiceStatusProps) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b last:border-0">
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "h-2.5 w-2.5 rounded-full",
            running ? "bg-emerald-500" : "bg-red-500"
          )}
        />
        <div>
          <p className="text-sm font-medium">{name}</p>
          {info && <p className="text-xs text-muted-foreground">{info}</p>}
        </div>
      </div>
      <span
        className={cn(
          "text-xs font-medium",
          running ? "text-emerald-600" : "text-red-600"
        )}
      >
        {running ? "Activo" : "Detenido"}
      </span>
    </div>
  );
}
