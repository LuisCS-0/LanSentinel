// Piezas para mostrar un dispositivo: icono con indicador de conexión,
// estado (confianza, bloqueo, cuarentena) y nombre con su IP.

import { createElement } from "react";
import { Ban, ShieldAlert, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { deviceIcon, deviceName, isOnline } from "@/lib/devices";
import { cn } from "@/lib/utils";
import type { Device } from "@/lib/types";

export function DeviceAvatar({ device, size = "md" }: { device: Device; size?: "sm" | "md" | "lg" }) {
  const online = isOnline(device);
  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center rounded-xl border",
        device.is_blocked ? "border-destructive/30 bg-destructive/10 text-destructive"
          : device.is_trusted ? "border-primary/25 bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground",
        size === "sm" && "size-8 [&_svg]:size-4",
        size === "md" && "size-10 [&_svg]:size-5",
        size === "lg" && "size-14 rounded-2xl [&_svg]:size-7",
      )}
    >
      {/* Icono elegido de una tabla fija según el tipo de aparato */}
      {createElement(deviceIcon(device))}
      <span
        title={online ? "En línea" : "Desconectado"}
        className={cn(
          "absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-card",
          online ? "bg-success" : "bg-muted-foreground/40",
        )}
      />
    </div>
  );
}

export function DeviceStatusBadge({ device, quarantine }: { device: Device; quarantine: boolean }) {
  if (device.is_blocked) return <Badge variant="destructive"><Ban />Bloqueado</Badge>;
  if (device.is_trusted) return <Badge variant="success"><ShieldCheck />De confianza</Badge>;
  if (quarantine) {
    return (
      <Badge variant="warning" title="Sin acceso a Internet hasta que lo marques como de confianza">
        <ShieldAlert />En cuarentena
      </Badge>
    );
  }
  return <Badge variant="outline">Sin revisar</Badge>;
}

// Nombre con la IP debajo; con onClick se comporta como enlace al detalle
export function DeviceLabel({
  device, onClick, className,
}: { device: Device; onClick?: () => void; className?: string }) {
  const content = (
    <>
      <DeviceAvatar device={device} size="sm" />
      <div className="min-w-0 text-left">
        <p className={cn("truncate text-sm font-medium", onClick && "group-hover:text-primary")}>{deviceName(device)}</p>
        <p className="truncate font-mono text-[11px] text-muted-foreground">{device.ip ?? "sin IP"}</p>
      </div>
    </>
  );
  if (!onClick) return <div className={cn("flex min-w-0 items-center gap-2.5", className)}>{content}</div>;
  return (
    <button onClick={onClick} className={cn("group flex min-w-0 items-center gap-2.5", className)}>
      {content}
    </button>
  );
}
