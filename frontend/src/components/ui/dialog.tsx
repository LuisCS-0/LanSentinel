// Modal sencillo sin dependencias externas.
// Si en el futuro necesitamos comportamiento más avanzado (focus trap,
// teclas de escape, animaciones), reemplazaríamos por @radix-ui/react-dialog.

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}

export function Dialog({
  open, onClose, title, description, children, className,
}: DialogProps) {
  // Cierra con tecla ESC
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className={cn(
          "relative bg-card rounded-lg shadow-lg max-w-lg w-full mx-4 p-6",
          className
        )}
        onClick={e => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 rounded-sm opacity-70 hover:opacity-100"
        >
          <X className="h-4 w-4" />
        </button>

        {title && <h2 className="text-lg font-semibold">{title}</h2>}
        {description && (
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        )}

        <div className={cn(title || description ? "mt-4" : "")}>
          {children}
        </div>
      </div>
    </div>
  );
}
