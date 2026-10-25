// Páginas del panel, agrupadas como en la barra lateral. El buscador global
// también las usa.

import {
  Activity, Bell, Cable, Flame, LayoutDashboard, MonitorSmartphone, Settings, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  description: string;
  keywords?: string;
}

export const NAV_GROUPS: { title: string | null; items: NavItem[] }[] = [
  {
    title: null,
    items: [
      { to: "/", label: "Panel", icon: LayoutDashboard, description: "Resumen de la red y de la seguridad" },
    ],
  },
  {
    title: "Red",
    items: [
      { to: "/devices", label: "Dispositivos", icon: MonitorSmartphone, description: "Equipos detectados en la red", keywords: "equipos lista" },
      { to: "/connections", label: "Conexiones", icon: Cable, description: "Todo lo que está abierto ahora mismo", keywords: "conntrack destinos ip" },
      { to: "/traffic", label: "Tráfico", icon: Activity, description: "Consumo histórico y ranking", keywords: "consumo datos ancho de banda" },
    ],
  },
  {
    title: "Seguridad",
    items: [
      { to: "/alerts", label: "Alertas", icon: Bell, description: "Eventos detectados", keywords: "suricata avisos" },
      { to: "/firewall", label: "Cortafuegos", icon: Flame, description: "Bloqueos y modo cuarentena", keywords: "firewall bloquear cuarentena iptables" },
    ],
  },
  {
    title: "Sistema",
    items: [
      { to: "/settings", label: "Ajustes", icon: Settings, description: "Avisos, tema y cuenta", keywords: "telegram ntfy correo contraseña tema" },
    ],
  },
];

export const NAV_ITEMS = NAV_GROUPS.flatMap(g => g.items);

export function pageFor(pathname: string): NavItem {
  return NAV_ITEMS.find(i => (i.to === "/" ? pathname === "/" : pathname.startsWith(i.to))) ?? NAV_ITEMS[0];
}
