// Auditoría con IA (solo administradores).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { AiAuditDetail, AiAuditPreview, AiAuditStatus, AiAuditSummary } from "@/lib/types";

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

export function useAiAuditStatus() {
  return useQuery({
    queryKey: ["ai-audit", "status"],
    queryFn: async () => (await apiClient.get<AiAuditStatus>("/ai-audit/status")).data,
  });
}

// Mientras haya una en marcha se consulta cada pocos segundos
export function useAiAuditReports() {
  return useQuery({
    queryKey: ["ai-audit", "reports"],
    queryFn: async () => (await apiClient.get<AiAuditSummary[]>("/ai-audit/reports", { params: { limit: 5 } })).data,
    refetchInterval: q => (q.state.data?.some(r => r.status === "running") ? 3000 : false),
  });
}

export function useAiAuditReport(id: number | null) {
  return useQuery({
    queryKey: ["ai-audit", "report", id],
    queryFn: async () => (await apiClient.get<AiAuditDetail>(`/ai-audit/reports/${id}`)).data,
    enabled: id !== null,
  });
}

export function useRunAiAudit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await apiClient.post<{ id: number }>("/ai-audit/run")).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-audit"] }),
  });
}

export function useCheckAiProvider() {
  return useMutation({
    mutationFn: async () => (await apiClient.post<{ ok: boolean; detail: string }>("/ai-audit/check")).data,
  });
}
