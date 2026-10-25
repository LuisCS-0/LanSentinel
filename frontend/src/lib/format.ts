// Utilidad para formatear tasas de tráfico de forma legible.
// 1024 → "1.0 KB/s", 1500000 → "1.4 MB/s", etc.

export function formatBps(bps: number): string {
  if (bps <= 0) return "—";
  if (bps < 1024) return `${bps.toFixed(0)} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  if (bps < 1024 * 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
  return `${(bps / 1024 / 1024 / 1024).toFixed(2)} GB/s`;
}

// Cantidades de datos: 1536 → "1.5 KB", 3_000_000_000 → "2.79 GB".
export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value.toFixed(unit === 0 ? 0 : value < 10 ? 2 : 1)} ${units[unit]}`;
}
