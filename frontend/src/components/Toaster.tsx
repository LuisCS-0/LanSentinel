import { X } from "lucide-react";
import { SeverityBadge } from "@/components/SeverityBadge";
import { dismissToast, useToasts } from "@/lib/toast";

export function Toaster() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2 px-4 sm:px-0">
      {toasts.map(t => (
        <div
          key={t.id}
          role="status"
          className="relative rounded-lg border bg-card p-4 pr-9 shadow-lg"
        >
          <button
            onClick={() => dismissToast(t.id)}
            className="absolute top-3 right-3 rounded-sm opacity-60 hover:opacity-100"
            aria-label="Cerrar aviso"
          >
            <X className="h-4 w-4" />
          </button>
          <div className="flex items-start gap-2">
            {t.severity && <SeverityBadge severity={t.severity} className="mt-0.5 flex-shrink-0" />}
            <div className="min-w-0">
              <p className="text-sm font-medium">{t.title}</p>
              {t.description && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-3">{t.description}</p>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
