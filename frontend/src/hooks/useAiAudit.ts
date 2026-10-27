// Auditoría con IA (solo administradores).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { AiAuditDetail, AiAuditPreview, AiAuditStatus, AiAuditSummary, AiFindingStatus } from "@/lib/types";

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
export function useAiAuditReports(limit = 20, enabled = true) {
  return useQuery({
    queryKey: ["ai-audit", "reports", limit],
    queryFn: async () => (await apiClient.get<AiAuditSummary[]>("/ai-audit/reports", { params: { limit } })).data,
    enabled,
    refetchInterval: q => (q.state.data?.some(r => r.status === "running") ? 3000 : false),
  });
}

export function useAiAuditReport(id: number | null) {
  return useQuery({
    queryKey: ["ai-audit", "report", id],
    queryFn: async () => (await apiClient.get<AiAuditDetail>(`/ai-audit/reports/${id}`)).data,
    enabled: id !== null,
    refetchInterval: q => (q.state.data?.status === "running" ? 3000 : false),
  });
}

// Aplicado, descartado o de vuelta a pendiente
export function useSetFindingState() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, index, estado }: { id: number; index: number; estado: AiFindingStatus }) =>
      (await apiClient.put(`/ai-audit/reports/${id}/findings/${index}`, { estado })).data,
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["ai-audit", "report", vars.id] });
      queryClient.invalidateQueries({ queryKey: ["ai-audit", "reports"] });
    },
  });
}

export function useDeleteAiAudit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/ai-audit/reports/${id}`);
    },
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: ["ai-audit", "report", id] });
      queryClient.invalidateQueries({ queryKey: ["ai-audit", "reports"] });
    },
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
