// Auditoría con IA (solo administradores).

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { AiAuditPreview } from "@/lib/types";

// Se pide al abrir la vista previa, siempre fresca: es lo que se enviaría ahora
export function useAiAuditPreview(enabled: boolean) {
  return useQuery({
    queryKey: ["ai-audit", "preview"],
    queryFn: async () => (await apiClient.get<AiAuditPreview>("/ai-audit/preview")).data,
    enabled,
    staleTime: 0,
    gcTime: 0,
  });
}
