// Tipos que reflejan los schemas Pydantic del backend.
// Mantener sincronizado con backend/app/schemas/*.py

// ─── Dispositivos ─────────────────────────────────────────────────────────────

export interface Device {
  id: string;                   // UUID
  mac: string;
  ip: string | null;
  hostname: string | null;
  vendor: string | null;
  device_type: string | null;
  is_trusted: boolean;
  is_blocked: boolean;
  last_seen: string;            // ISO timestamp
}

export interface DeviceSummary {
  total: number;
  trusted: number;
  blocked: number;
}

// ─── Alertas ──────────────────────────────────────────────────────────────────

export type AlertSeverity = "info" | "low" | "medium" | "high" | "critical";
export type AlertSource = "monitor" | "suricata" | "firewall" | "system";
export type AlertStatus = "new" | "acknowledged" | "resolved" | "ignored";

export interface Alert {
  id: number;
  device_id: string | null;
  severity: AlertSeverity;
  source: AlertSource;
  status: AlertStatus;
  title: string;
  description: string | null;
  raw_payload: Record<string, unknown> | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  occurrences: number;          // > 1 si se han agrupado eventos repetidos
  created_at: string;           // primera ocurrencia
  last_seen_at: string;         // última ocurrencia
  updated_at: string;
}

// ─── Puertos ──────────────────────────────────────────────────────────────────

export interface PortScan {
  id: number;
  device_id: string;
  port: number;
  protocol: string;
  state: string;
  service: string | null;
  version: string | null;
  scanned_at: string;
}

export interface ScanResultResponse {
  ip: string;
  ports_found: number;
  scanned_at: string;
}

// ─── Firewall ─────────────────────────────────────────────────────────────────

export interface FirewallRule {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  src_ip: string | null;
  src_mac: string | null;       // presente en los bloqueos de dispositivos
  action: string;
  direction: string;
  protocol: string;
  device_id: string | null;
  auto_generated: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Sesión ───────────────────────────────────────────────────────────────────

export interface CurrentUser {
  username: string;
  last_login_at: string | null;
}

// ─── Sistema ──────────────────────────────────────────────────────────────────

export interface SystemStatus {
  monitor: {
    running: boolean;
    interface: string;
    interval_seconds: number;
    last_scan_at: string | null;
    devices_online: number;
  };
  security?: {
    running: boolean;
    eve_path: string;
    events_processed: number;
    alerts_generated: number;
    last_event_at: string | null;
  };
  firewall?: {
    running: boolean;
    iptables_available: boolean;
    ipv6_enabled?: boolean;
    rules_applied: number;
    last_action_at: string | null;
  };
}

// ─── Histórico de tráfico ─────────────────────────────────────────────────────

export type TrafficRange = "24h" | "7d" | "30d" | "1y";
export type UsageUnit = "hour" | "day" | "month";

export interface UsageBucket {
  start: string;                // inicio del tramo (ISO con zona horaria)
  bytes_sent: number;           // subida
  bytes_recv: number;           // descarga
}

export interface UsageSeries {
  range: TrafficRange;
  unit: UsageUnit;
  buckets: UsageBucket[];
  total_sent: number;
  total_recv: number;
}

export interface DeviceUsage {
  device_id: string;
  mac: string;
  ip: string | null;
  hostname: string | null;
  vendor: string | null;
  bytes_sent: number;
  bytes_recv: number;
  total_bytes: number;
}

export interface TopDevices {
  range: TrafficRange;
  devices: DeviceUsage[];
}
