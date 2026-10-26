// Dominios (DNS y SNI) y huellas TLS de un dispositivo.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { DeviceDomains } from "@/lib/types";

export function useDeviceDomains(deviceId: string, days: number) {
  return useQuery({
    queryKey: ["devices", deviceId, "domains", days],
    queryFn: async () => {
      const { data } = await apiClient.get<DeviceDomains>(`/devices/${deviceId}/domains`, { params: { days } });
      return data;
    },
    refetchInterval: 60_000,
  });
}
