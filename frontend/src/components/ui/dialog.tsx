// Modal sin dependencias externas. El contenido largo hace scroll dentro del
// modal (nunca se sale de la pantalla); se cierra con Escape o pulsando fuera,
// salvo con dismissible={false} (hay que terminar lo que pide).

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useBodyScrollLock, useEscape } from "@/components/ui/overlay";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  dismissible?: boolean;
}

export function Dialog({
  open, onClose, title, description, icon, children, footer, className, dismissible = true,
}: DialogProps) {
  useEscape(open && dismissible, onClose);
  useBodyScrollLock(open);
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 animate-fade-in bg-background/70 backdrop-blur-sm" onClick={dismissible ? onClose : undefined} />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative flex max-h-[92dvh] w-full max-w-lg animate-zoom-in flex-col overflow-hidden",
          "rounded-t-2xl border bg-card shadow-2xl sm:rounded-2xl",
          className,
        )}
      >
        <div className="flex items-start gap-3 border-b px-5 py-4">
          {icon && <div className="mt-0.5 shrink-0">{icon}</div>}
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-base font-semibold leading-tight">{title}</h2>}
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
          {dismissible && (
            <button
              onClick={onClose}
              className="-mr-1 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              aria-label="Cerrar"
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t bg-muted/30 px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
