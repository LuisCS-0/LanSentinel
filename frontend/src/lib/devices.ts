// Utilidades para mostrar dispositivos de forma coherente en todo el panel:
// nombre, icono según el tipo de aparato y si está en línea.

import {
  Cast, Cctv, Cpu, Gamepad2, Laptop, Monitor, Printer, Router, Smartphone, Speaker, Tablet, Tv,
  type LucideIcon,
} from "lucide-react";
import type { Device } from "@/lib/types";

// Se considera "en línea" si el escaneo ARP lo ha visto hace poco
const ONLINE_MS = 5 * 60 * 1000;

export function deviceName(d: Pick<Device, "hostname" | "vendor" | "mac">): string {
  return d.hostname || d.vendor || d.mac;
}

export function isOnline(d: Pick<Device, "last_seen">): boolean {
  return Date.now() - new Date(d.last_seen).getTime() < ONLINE_MS;
}

// Icono aproximado a partir del nombre y del fabricante. Es solo orientativo:
// el fabricante de la tarjeta de red no siempre dice qué aparato es
const ICON_RULES: [RegExp, LucideIcon][] = [
  [/router|gateway|fritz|tp-?link|netgear|mikrotik|ubiquiti|asus.*rt|livebox|movistar/i, Router],
  [/cam|cctv|hikvision|dahua|reolink|ezviz|wyze|arlo/i, Cctv],
  [/tv|bravia|roku|lg electronics|vizio|hisense|tcl/i, Tv],
  [/chromecast|cast|fire.?stick|apple tv/i, Cast],
  [/echo|alexa|sonos|speaker|altavoz|homepod|nest audio|amazon/i, Speaker],
  [/printer|impresora|epson|canon|brother|hp inc|hewlett/i, Printer],
  [/ipad|tablet|tab-/i, Tablet],
  [/iphone|android|pixel|galaxy|xiaomi|oneplus|huawei|oppo|motorola|phone|movil/i, Smartphone],
  [/playstation|xbox|nintendo|switch|ps[45]/i, Gamepad2],
  [/raspberry|esp32|espressif|arduino|shelly|tuya|sonoff/i, Cpu],
  [/laptop|portatil|macbook|thinkpad|dell|lenovo|asus|acer|msi/i, Laptop],
  [/apple/i, Smartphone],
  [/samsung/i, Tv],
  [/google/i, Cast],
];

export function deviceIcon(d: Pick<Device, "hostname" | "vendor" | "ip">): LucideIcon {
  if (d.ip && /\.1$/.test(d.ip) && !d.hostname) return Router;
  const text = `${d.hostname ?? ""} ${d.vendor ?? ""}`;
  for (const [pattern, icon] of ICON_RULES) {
    if (pattern.test(text)) return icon;
  }
  return Monitor;
}

// Orden natural de IPs (192.168.1.9 antes que 192.168.1.10)
export function compareIp(a: string | null, b: string | null): number {
  if (!a) return 1;
  if (!b) return -1;
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff) return diff;
  }
  return 0;
}
