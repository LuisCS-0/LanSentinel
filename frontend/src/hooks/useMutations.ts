// Hooks de mutación para acciones sobre alertas y reglas de firewall.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { Alert, AlertStatus, FirewallRule } from "@/lib/types";

// ─── Alertas ─────────────────────────────────────────────────────────────────

export function useUpdateAlertStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, status }: { id: number; status: AlertStatus }) => {
      // PATCH /api/v1/alerts/{id} con el nuevo status
      const { data } = await apiClient.patch<Alert>(`/alerts/${id}`, { status });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// ─── Firewall ────────────────────────────────────────────────────────────────

export function useBlockIp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ ip, reason }: { ip: string; reason?: string }) => {
      const { data } = await apiClient.post<FirewallRule>("/firewall/block", {
        ip,
        reason: reason || "Bloqueo manual desde el panel",
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["firewall", "rules"] });
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}

export function useUnblockRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ruleId: number) => {
      await apiClient.delete(`/firewall/rules/${ruleId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["firewall", "rules"] });
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}