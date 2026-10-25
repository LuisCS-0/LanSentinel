// Menú desplegable sencillo: se abre con su botón y se cierra al elegir una
// opción, al pulsar fuera o con Escape.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useEscape } from "@/components/ui/overlay";

export function Menu({
  trigger, children, align = "right", className,
}: { trigger: (open: boolean) => ReactNode; children: ReactNode; align?: "left" | "right"; className?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEscape(open, () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <div onClick={() => setOpen(o => !o)}>{trigger(open)}</div>
      {open && (
        <div
          role="menu"
          onClick={() => setOpen(false)}
          className={cn(
            "absolute z-50 mt-2 min-w-56 animate-zoom-in rounded-xl border bg-card p-1.5 shadow-2xl",
            align === "right" ? "right-0" : "left-0",
            className,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

export function MenuItem({
  icon, children, onClick, danger, active,
}: { icon?: ReactNode; children: ReactNode; onClick?: () => void; danger?: boolean; active?: boolean }) {
  return (
    <button
      role="menuitem"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors [&_svg]:size-4",
        danger ? "text-destructive hover:bg-destructive/10" : "hover:bg-accent",
        active && "bg-accent",
      )}
    >
      {icon}
      <span className="flex-1">{children}</span>
    </button>
  );
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return <p className="px-2.5 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{children}</p>;
}

export function MenuSeparator() {
  return <div className="my-1.5 h-px bg-border" />;
}
