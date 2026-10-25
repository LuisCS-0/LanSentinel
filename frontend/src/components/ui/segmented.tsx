// Grupo de opciones excluyentes con aspecto de interruptor (filtros, rangos,
// pestañas). Cada opción puede llevar un contador.

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  count?: number;
  // Color del contador cuando hay elementos (p. ej. alertas críticas)
  tone?: "default" | "destructive" | "warning";
}

interface SegmentedProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: SegmentedOption<T>[];
  className?: string;
  size?: "sm" | "default";
}

export function Segmented<T extends string>({ value, onChange, options, className, size = "default" }: SegmentedProps<T>) {
  return (
    <div
      role="tablist"
      className={cn("inline-flex max-w-full shrink-0 items-center gap-0.5 overflow-x-auto rounded-lg border bg-muted/60 p-0.5", className)}
    >
      {options.map(o => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex shrink-0 items-center gap-1.5 rounded-md font-medium transition-all [&_svg]:size-3.5",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
              active ? "bg-card text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {o.label}
            {o.count !== undefined && (
              <span
                className={cn(
                  "tabular rounded-full px-1.5 text-[11px] leading-4",
                  o.count > 0 && o.tone === "destructive" ? "bg-destructive/15 text-destructive"
                    : o.count > 0 && o.tone === "warning" ? "bg-warning/15 text-warning"
                    : "bg-foreground/5 text-muted-foreground",
                )}
              >
                {o.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
