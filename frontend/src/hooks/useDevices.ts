// Hooks de mutación para acciones que modifican el estado del backend.
// Cada mutación invalida automáticamente las queries afectadas para que
// la UI se actualice sin necesidad de pedir un refresh manual.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { DeviceConnections, ScanResultResponse, PortScan } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";

// ─── Dispositivos: trust / block ─────────────────────────────────────────────

export function useTrustDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, trusted }: { id: string; trusted: boolean }) => {
      // Si trusted=true → POST /trust, si false → DELETE /trust
      if (trusted) {
        await apiClient.post(`/devices/${id}/trust`);
      } else {
        await apiClient.delete(`/devices/${id}/trust`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      // Cambia quién está en cuarentena
      queryClient.invalidateQueries({ queryKey: ["firewall", "quarantine"] });
    },
  });
}

export function useBlockDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, blocked }: { id: string; blocked: boolean }) => {
      if (blocked) {
        await apiClient.post(`/devices/${id}/block`);
      } else {
        await apiClient.delete(`/devices/${id}/block`);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.invalidateQueries({ queryKey: ["firewall", "rules"] });
      queryClient.invalidateQueries({ queryKey: ["system", "status"] });
    },
  });
}

// ─── Escaneo de puertos ──────────────────────────────────────────────────────

export function useScanPorts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ports }: { id: string; ports?: string }) => {
      const { data } = await apiClient.post<ScanResultResponse>(
        `/security/devices/${id}/scan`,
        null,
        // Sin "ports" el backend hace el escaneo completo, que es el que
        // detecta servicios inseguros; puede tardar un par de minutos
        { params: ports ? { ports } : undefined, timeout: 300000 },
      );
      return data;
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["ports", vars.id] });
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// ─── Forzar escaneo de red ───────────────────────────────────────────────────

export function useForceNetworkScan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post("/network/scan");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devices"] });
    },
  });
}

// ─── Lista de puertos detectados de un dispositivo ───────────────────────────

export function useDevicePorts(deviceId: string | null) {
  return useQuery({
    queryKey: ["ports", deviceId],
    queryFn: async () => {
      if (!deviceId) return [];
      const { data } = await apiClient.get<PortScan[]>(
        `/security/devices/${deviceId}/ports`,
      );
      return data;
    },
    enabled: !!deviceId,
  });
}

// ─── Conexiones abiertas de un dispositivo ───────────────────────────────────

// Cambian a cada segundo, así que se refrescan a menudo mientras el detalle
// del dispositivo está abierto
export function useDeviceConnections(deviceId: string | null) {
  return useQuery({
    queryKey: ["connections", deviceId],
    queryFn: async () => {
      const { data } = await apiClient.get<DeviceConnections>(
        `/devices/${deviceId}/connections`,
      );
      return data;
    },
    enabled: !!deviceId,
    refetchInterval: 5000,
  });
}
