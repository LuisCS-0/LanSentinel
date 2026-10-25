// Hooks del histórico de tráfico. El backend agrega los datos cada 5
// minutos, así que basta con refrescar cada minuto.

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { TopDevices, TrafficRange, UsageSeries } from "@/lib/types";

const REFRESH_MS = 60_000;

// Consumo de toda la red
export function useNetworkUsage(range: TrafficRange) {
  return useQuery({
    queryKey: ["traffic-usage", "network", range],
    queryFn: async () => {
      const { data } = await apiClient.get<UsageSeries>("/network/traffic/usage", {
        params: { range },
      });
      return data;
    },
    refetchInterval: REFRESH_MS,
  });
}

// Consumo de un dispositivo
export function useDeviceUsage(deviceId: string | null, range: TrafficRange) {
  return useQuery({
    queryKey: ["traffic-usage", "device", deviceId, range],
    queryFn: async () => {
      const { data } = await apiClient.get<UsageSeries>(`/devices/${deviceId}/traffic/usage`, {
        params: { range },
      });
      return data;
    },
    enabled: !!deviceId,
    refetchInterval: REFRESH_MS,
  });
}

// Consumo total por dispositivo, de mayor a menor
export function useTopDevices(range: TrafficRange) {
  return useQuery({
    queryKey: ["traffic-usage", "top", range],
    queryFn: async () => {
      const { data } = await apiClient.get<TopDevices>("/network/traffic/top", {
        params: { range },
      });
      return data.devices;
    },
    refetchInterval: REFRESH_MS,
  });
}
