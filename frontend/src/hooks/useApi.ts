// Hooks de React Query — centralizan todas las llamadas al backend.
// Cada hook devuelve { data, isLoading, isError } y gestiona la caché
// automáticamente. Si dos componentes usan el mismo hook, solo se hace
// una petición real al backend.

import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import { apiClient } from "@/lib/api";
import type {
  Device, Alert, FirewallRule, DeviceSummary, SystemStatus,
} from "@/lib/types";

interface HealthResponse {
  status: string;
  version: string;
}

// ─── Estado del backend ──────────────────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await axios.get<HealthResponse>("/health");
      if (!data || typeof data !== "object" || data.status !== "ok") {
        throw new Error("Respuesta inválida del backend");
      }
      return data;
    },
    refetchInterval: 10000,
  });
}

// ─── Estado del sistema (monitor/security/firewall) ──────────────────────────

export function useSystemStatus() {
  return useQuery({
    queryKey: ["system", "status"],
    queryFn: async () => {
      const { data } = await apiClient.get<SystemStatus>("/system/status");
      return data;
    },
    refetchInterval: 10000,
  });
}

// ─── Dispositivos ────────────────────────────────────────────────────────────

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    queryFn: async () => {
      const { data } = await apiClient.get<Device[]>("/devices/");
      return data;
    },
    refetchInterval: 15000,
  });
}

export function useDevicesSummary() {
  return useQuery({
    queryKey: ["devices", "summary"],
    queryFn: async () => {
      const { data } = await apiClient.get<DeviceSummary>("/devices/summary");
      return data;
    },
    refetchInterval: 15000,
  });
}

// ─── Alertas ─────────────────────────────────────────────────────────────────

export function useAlerts(limit = 50) {
  return useQuery({
    queryKey: ["alerts", limit],
    queryFn: async () => {
      const { data } = await apiClient.get<Alert[]>("/alerts/", {
        params: { limit },
      });
      return data;
    },
    refetchInterval: 10000,
  });
}

// ─── Firewall ────────────────────────────────────────────────────────────────

export function useFirewallRules(onlyActive = true) {
  return useQuery({
    queryKey: ["firewall", "rules", onlyActive],
    queryFn: async () => {
      const { data } = await apiClient.get<FirewallRule[]>("/firewall/rules", {
        params: { only_active: onlyActive },
      });
      return data;
    },
    refetchInterval: 15000,
  });
}
