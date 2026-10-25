import { CheckCircle2, X } from "lucide-react";
import { SeverityBadge } from "@/components/SeverityBadge";
import { dismissToast, useToasts } from "@/lib/toast";
import { SEVERITY } from "@/lib/severity";
import { cn } from "@/lib/utils";

export function Toaster() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2 px-4 sm:px-0">
      {toasts.map(t => (
        <div
          key={t.id}
          role="status"
          className="relative flex animate-zoom-in gap-3 overflow-hidden rounded-xl border bg-card/95 p-4 pr-9 shadow-2xl backdrop-blur"
        >
          <span className={cn("absolute inset-y-0 left-0 w-1", t.severity ? SEVERITY[t.severity].bar : "bg-success")} />
          {t.severity
            ? <SeverityBadge severity={t.severity} className="mt-0.5 h-fit" />
            : <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />}
          <div className="min-w-0">
            <p className="text-sm font-medium">{t.title}</p>
            {t.description && <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{t.description}</p>}
          </div>
          <button
            onClick={() => dismissToast(t.id)}
            className="absolute right-3 top-3 rounded-sm text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Cerrar aviso"
          >
            <X className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
