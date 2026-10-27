// Ajustes que se cambian desde el panel (solo administradores).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { ConfigField } from "@/lib/types";

export function useConfig(enabled = true) {
  return useQuery({
    queryKey: ["config"],
    queryFn: async () => (await apiClient.get<{ fields: ConfigField[] }>("/config")).data.fields,
    enabled,
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { values: Record<string, unknown>; password?: string }) =>
      (await apiClient.put<{ fields: ConfigField[]; changed: string[] }>("/config", body)).data,
    onSuccess: data => {
      queryClient.setQueryData(["config"], data.fields);
      // Lo que enseñan otras tarjetas depende de estos ajustes (avisos, IA, copias...)
      queryClient.invalidateQueries({ predicate: q => q.queryKey[0] !== "config" });
    },
  });
}
