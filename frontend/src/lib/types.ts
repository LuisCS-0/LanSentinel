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
  first_seen?: string;          // primera vez que se vio en la red
  last_port_scan_at?: string | null;  // último escaneo de puertos completo
  ipv6_addresses?: string[];    // IPv6 en uso, según la tabla de vecinos
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

export type UserRole = "admin" | "viewer";

export interface CurrentUser {
  username: string;
  role: UserRole;
  last_login_at: string | null;
}

// Usuario del panel (Ajustes → Usuarios, solo administradores)
export interface UserAccount {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

// Entrada del registro de acciones
export interface AuditEntry {
  id: number;
  created_at: string;
  username: string | null;
  ip: string | null;
  method: string;
  path: string;
  action: string;
  target: string | null;
  status_code: number;
  details: { params?: Record<string, string>; body?: unknown } | null;
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
    ipv6_ra?: boolean;          // anuncia también IPv6
    error: string | null;
  };
  ipv6_forward?: boolean;       // reenvío IPv6 activado en el sistema
  ipv6?: {
    enabled: boolean;           // IPV6_LAN
    active: boolean;            // la LAN tiene prefijo
    source: "static" | "pd" | "ula" | null;
    prefix: string | null;
    lan_address: string | null;
    nat: boolean;               // NAT66 con la ULA de reserva
    pd_client: boolean;         // pidiendo prefijo a la operadora
    error: string | null;
  } | null;
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
  remote_name?: string | null;  // dominio de la IP remota (DNS o SNI que vio Suricata)
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

// ─── Inteligencia de amenazas ────────────────────────────────────────────────

export interface ThreatList {
  name: string;
  url: string | null;
  entries: number;
  updated_at: string | null;
  error: string | null;
}

export interface ThreatIntelStatus {
  enabled: boolean;
  lists: ThreatList[];
  addresses: number;
  removed_unsafe: number;
  applied_at: string | null;
  update_hours: number;
  blocked_outgoing: number;
  blocked_incoming: number;
  error: string | null;
  suricata: {
    rules: number | null;
    last_success_at: string | null;
    error: string | null;
    loaded: number | null;
    failed: number | null;
  };
}

// ─── Patrón de consumo (anomalías) ───────────────────────────────────────────

export interface UsageProfileDirection {
  median: number;      // bytes por hora habituales
  p95: number;
  threshold: number;   // a partir de aquí se avisa
}

export interface UsageProfile {
  enabled: boolean;
  days: number;
  active_hours: number;
  min_hours: number;
  upload: UsageProfileDirection | null;
  download: UsageProfileDirection | null;
}

// ─── Dominios y huellas TLS por dispositivo ──────────────────────────────────

export interface DeviceDomain {
  domain: string;
  hits: number;
  via_dns: boolean;
  via_tls: boolean;
  first_seen: string;
  last_seen: string;
}

export interface DeviceTlsFingerprint {
  fingerprint: string;      // JA4 (o JA3 si no la hay)
  ja3: string | null;
  last_sni: string | null;
  hits: number;
  first_seen: string;
  last_seen: string;
}

export interface DeviceDomains {
  enabled: boolean;
  history_days: number;
  domains: DeviceDomain[];
  fingerprints: DeviceTlsFingerprint[];
}

// ─── Auditoría con IA ─────────────────────────────────────────────────────────

// Vista previa: la instantánea que se enviaría al modelo y, aparte, la
// equivalencia de seudónimos (esta no se envía nunca)
export interface AiAuditPreview {
  snapshot: Record<string, unknown> & {
    incluye: { nombres_de_red: boolean; dominios: boolean };
    dispositivos: unknown[];
    alertas: unknown[];
    compacta?: boolean;
    omitido?: { alertas: number; dispositivos: number };
  };
  characters: number;
  approx_tokens: number;
  mapping: { id: string; device_id: string; nombre: string | null; ip: string | null; mac: string }[];
}

export interface AiAuditStatus {
  configured: boolean;
  problem: string | null;       // por qué no se puede auditar
  provider: string | null;
  model: string | null;
  local: boolean;               // los datos no salen de la red de casa
  endpoint: string | null;      // equipo del servidor compatible
  compact: boolean;             // se envía la instantánea compacta
  running: boolean;
}

export type AiGravedad = "critica" | "alta" | "media" | "baja" | "info";

export interface AiHallazgo {
  gravedad: AiGravedad;
  categoria: string;
  titulo: string;
  detalle: string;
  dispositivos: string[];       // seudónimos disp-NN
  recomendacion: string;
}

export type AiTipoAccion =
  | "bloquear_dispositivo" | "desbloquear_dispositivo" | "marcar_confianza" | "quitar_confianza" | "escanear_puertos"
  | "bloquear_ip" | "desbloquear_ip"
  | "activar_cuarentena" | "desactivar_cuarentena" | "actualizar_listas" | "escanear_red" | "hacer_copia";

// Una acción del plan: la propone el modelo, la elige y aplica el dueño
export interface AiAccion {
  tipo: AiTipoAccion;
  objetivo: string;             // seudónimo disp-NN, IP de Internet o "" si es de todo LanSentinel
  motivo: string;
  hallazgo: number;             // índice del hallazgo que la justifica, -1 si ninguno
}

export interface AiAuditSummary {
  id: number;
  created_at: string;
  finished_at: string | null;
  status: "running" | "done" | "error";
  provider: string;
  model: string;
  local: boolean;
  requested_by: string | null;
  cost_usd: number | null;
  score: number | null;
  findings: Partial<Record<AiGravedad, number>>;
  pending: number;              // hallazgos sin aplicar ni descartar
  error: string | null;
}

export type AiFindingStatus = "pendiente" | "aplicado" | "descartado";

export interface AiFindingState {
  estado: Exclude<AiFindingStatus, "pendiente">;
  por: string | null;
  en: string;
}

export interface AiAuditDetail extends AiAuditSummary {
  report: { puntuacion: number; resumen: string; hallazgos: AiHallazgo[]; positivos: string[]; acciones?: AiAccion[] } | null;
  discarded: { hallazgo?: AiHallazgo; accion?: AiAccion; motivo: string }[];
  input_tokens: number | null;
  output_tokens: number | null;
  mapping: AiAuditPreview["mapping"];
  snapshot: AiAuditPreview["snapshot"] | null;   // lo que se envió
  finding_states: Record<string, AiFindingState>;  // por índice del hallazgo
  action_states: Record<string, AiFindingState>;   // por índice de la acción
}

// Ajuste que se cambia desde el panel (encima de .env)
export interface ConfigField {
  name: string;
  group: "ia" | "avisos" | "deteccion" | "copias" | "sistema";
  label: string;
  kind: "bool" | "int" | "float" | "text" | "select" | "secret" | "url" | "emails";
  help: string;
  options: { value: string; label: string }[];
  min: number | null;
  max: number | null;
  sensitive: boolean;           // cambiarlo pide la contraseña
  restart: boolean;             // solo se aplica al reiniciar
  placeholder: string;
  source: "panel" | "env" | "default";
  value: string | number | boolean | null;   // null en los secretos
  is_set?: boolean;             // solo los secretos: si hay uno puesto
}
