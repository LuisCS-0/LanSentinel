// Auditoría con IA en Ajustes (solo administradores): el proveedor, lanzar
// una auditoría y el último informe. Los informes y sus hallazgos están en
// la página Auditoría IA.

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Eye, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { ProviderBar } from "@/components/ai-audit/ProviderBar";
import { PreviewDialog } from "@/components/ai-audit/SnapshotDialogs";
import { ScoreBadge } from "@/components/ai-audit/shared";
import { summaryText } from "@/lib/aiAudit";
import { useAiAuditReports } from "@/hooks/useAiAudit";
import { relativeTime } from "@/lib/dates";

export function AiAuditCard() {
  const reports = useAiAuditReports();
  const navigate = useNavigate();
  const [preview, setPreview] = useState(false);
  const last = reports.data?.[0];

  return (
    <Card>
      <CardHeaderRow
        title={<><Sparkles />Auditoría con IA</>}
        description="Un modelo de IA revisa el estado de la red y de LanSentinel y propone mejoras. Solo recibe la instantánea seudonimizada que puedes ver aquí."
        actions={<Button size="sm" variant="outline" onClick={() => setPreview(true)}><Eye />Ver lo que se enviará</Button>}
      />
      <CardContent className="space-y-3 text-sm">
        <ProviderBar onStarted={id => navigate(`/audit?report=${id}`)} />
        {last && (
          <Link to={`/audit?report=${last.id}`} className="flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors hover:bg-muted/40">
            <ScoreBadge score={last.status === "done" ? last.score : null} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">Última: {summaryText(last)}</p>
              <p className="truncate text-xs text-muted-foreground">{relativeTime(last.created_at)} · {last.model}</p>
            </div>
            {last.status === "done" && last.pending > 0 && <Badge variant="warning">{last.pending} pendientes</Badge>}
            <span className="flex shrink-0 items-center gap-1 text-xs text-primary">Ver informes<ArrowRight className="size-3.5" /></span>
          </Link>
        )}
      </CardContent>
      <PreviewDialog open={preview} onClose={() => setPreview(false)} />
    </Card>
  );
}
