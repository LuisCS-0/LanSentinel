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
  last_port_scan_at?: string | null;  // último escaneo de puertos completo
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
  risk_severity: AlertSeverity | null;   // si es un servicio inseguro
  risk_reason: string | null;
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
    quarantine_enabled?: boolean;
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

// ─── Avisos ───────────────────────────────────────────────────────────────────

export interface NotificationChannel {
  name: "telegram" | "ntfy" | "email";
  label: string;
  configured: boolean;
  last_sent_at: string | null;
  last_error: string | null;
}

export interface NotificationStatus {
  min_severity: AlertSeverity;
  max_per_hour: number;
  panel_url: string | null;
  live_clients: number;
  channels: NotificationChannel[];
}

// ─── Modo router ──────────────────────────────────────────────────────────────

export interface RouterStatus {
  enabled: boolean;             // estado elegido (panel o .env)
  active: boolean;              // reglas de NAT y reenvío aplicadas
  available: boolean;           // WAN configurada y válida
  problem: string | null;       // por qué no se puede activar
  wan_interface: string | null;
  lan_interface: string;
  ip_forward: boolean;          // reenvío activado en el sistema
  dhcp_enabled: boolean;        // LanSentinel da DHCP/DNS (ROUTER_DHCP)
  dhcp: {
    running: boolean;
    lan_ip: string | null;
    range_start: string | null;
    range_end: string | null;
    active_leases: number;
    error: string | null;
  };
}

// ─── Cuarentena ───────────────────────────────────────────────────────────────

export interface QuarantineStatus {
  enabled: boolean;
  interface: string;
  trusted_count: number;
  quarantined: Device[];        // sin confianza, vistos en las últimas 24 h
}

// ─── Conexiones de un dispositivo ─────────────────────────────────────────────

// open: en uso · idle: TCP sin tráfico hace rato · pending: sin respuesta ·
// done: intercambio suelto terminado (DNS, NTP) · closing: TCP cerrándose
export type ConnectionStatus = "open" | "idle" | "pending" | "done" | "closing";

export interface DeviceConnection {
  protocol: string;             // tcp | udp | icmp...
  direction: "outgoing" | "incoming";
  local_port: number | null;    // puerto del dispositivo
  remote_ip: string;
  remote_port: number | null;
  remote_is_lan: boolean;       // el otro extremo es una IP privada
  service: string | null;       // HTTPS, DNS... según el puerto
  state: string | null;         // estado TCP según el kernel
  status: ConnectionStatus;
  idle_seconds: number | null;  // tiempo sin tráfico, si se puede deducir
  expires_in: number;
}

export interface DeviceConnections {
  available: boolean;           // false si el backend no pudo leer conntrack
  connections: DeviceConnection[];
}

// Conexión de la red vista desde un dispositivo (GET /network/connections)
export interface NetworkConnection extends DeviceConnection {
  device_id: string;
}

export interface NetworkConnections {
  available: boolean;
  connections: NetworkConnection[];
}

// ─── HTTPS ───────────────────────────────────────────────────────────────────

export interface TlsStatus {
  available: boolean;
  /** "lansentinel": firmado por la CA propia · "custom": certificado puesto a mano */
  issuer: "lansentinel" | "custom" | null;
  dns_names: string[];
  ip_addresses: string[];
  valid_until: string | null;
  server_fingerprint: string | null;
  ca_fingerprint: string | null;
  ca_valid_until: string | null;
  error: string | null;
}

// ─── Copias de seguridad ─────────────────────────────────────────────────────

export type BackupMotivo = "inicial" | "diaria" | "manual" | "actualizacion" | "restauracion";

export interface BackupFile {
  name: string;
  created_at: string;
  motivo: BackupMotivo;
  size: number;
}

export interface BackupStatus {
  enabled: boolean;
  hour: number;
  keep_daily: number;
  keep_weekly: number;
  location: string;
  running: boolean;
  next_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  backups: BackupFile[];
}
