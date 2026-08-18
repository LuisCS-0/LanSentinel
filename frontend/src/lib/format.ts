// Utilidad para formatear tasas de tráfico de forma legible.
// 1024 → "1.0 KB/s", 1500000 → "1.4 MB/s", etc.

export function formatBps(bps: number): string {
  if (bps <= 0) return "—";
  if (bps < 1024) return `${bps.toFixed(0)} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  if (bps < 1024 * 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
  return `${(bps / 1024 / 1024 / 1024).toFixed(2)} GB/s`;
}
