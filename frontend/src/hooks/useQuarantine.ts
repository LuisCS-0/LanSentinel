// Modo cuarentena: solo los dispositivos de confianza salen a Internet.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { QuarantineStatus } from "@/lib/types";

const KEY = ["firewall", "quarantine"];

export function useQuarantine() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<QuarantineStatus>("/firewall/quarantine");
      return data;
    },
    refetchInterval: 15_000,
  });
}

export function useSetQuarantine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (enabled: boolean) => {
      const { data } = await apiClient.put<QuarantineStatus>("/firewall/quarantine", { enabled });
      return data;
    },
    onSuccess: data => {
      queryClient.setQueryData(KEY, data);
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}
