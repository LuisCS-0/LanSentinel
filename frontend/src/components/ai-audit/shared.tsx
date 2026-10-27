// Piezas comunes de la auditoría con IA: la puntuación y el visor del JSON
// enviado (las etiquetas y los nombres de los dispositivos, en lib/aiAudit).

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { copyText } from "@/lib/clipboard";
import { cn } from "@/lib/utils";

export function ScoreBadge({ score, size = "md" }: { score: number | null; size?: "sm" | "md" | "lg" }) {
  const tone = score == null ? "bg-muted text-muted-foreground"
    : score >= 80 ? "bg-success/15 text-success" : score >= 50 ? "bg-warning/15 text-warning" : "bg-destructive/15 text-destructive";
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-lg font-semibold tabular-nums", tone,
        size === "lg" ? "size-16 text-2xl" : size === "md" ? "size-10 text-sm" : "size-8 text-xs",
      )}
    >
      {score ?? "–"}
    </span>
  );
}

export function JsonViewer({ value, className }: { value: unknown; className?: string }) {
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(value, null, 2);
  const copy = async () => {
    if (await copyText(text)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };
  return (
    <div className="relative">
      <pre className={cn("max-h-[45dvh] overflow-auto rounded-lg border bg-muted/50 p-3 pr-10 font-mono text-[11px] leading-relaxed", className)}>
        {text}
      </pre>
      <Button variant="ghost" size="icon-sm" className="absolute right-1.5 top-1.5" onClick={copy} aria-label="Copiar">
        {copied ? <Check className="text-success" /> : <Copy />}
      </Button>
    </div>
  );
}
