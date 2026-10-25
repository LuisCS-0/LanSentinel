// Panel lateral que entra por la derecha (o por la izquierda, para el menú
// en el móvil). Ocupa toda la altura y su contenido hace scroll dentro.

import * as React from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { useBodyScrollLock, useEscape } from "@/components/ui/overlay";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  side?: "right" | "left";
  children: React.ReactNode;
  className?: string;
  label?: string;
}

export function Sheet({ open, onClose, side = "right", children, className, label }: SheetProps) {
  useEscape(open, onClose);
  useBodyScrollLock(open);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 animate-fade-in bg-background/60 backdrop-blur-[2px]" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className={cn(
          "absolute inset-y-0 flex w-full flex-col border-l bg-card shadow-2xl",
          side === "right" ? "right-0 animate-slide-in-right sm:max-w-xl" : "left-0 animate-slide-in-left border-l-0 border-r",
          className,
        )}
      >
        {children}
      </aside>
    </div>,
    document.body,
  );
}
