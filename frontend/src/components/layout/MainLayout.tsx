// Marco del panel: barra lateral con las secciones (cajón en el móvil),
// barra superior con el buscador global, el estado en directo y la cuarentena,
// y el detalle de dispositivo, que se abre encima de cualquier página.

import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  ChevronDown, KeyRound, LogOut, Menu as MenuIcon, Monitor, Moon, Search, ShieldAlert, Sun, User, Eye,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/misc";
import { Menu, MenuItem, MenuLabel, MenuSeparator } from "@/components/ui/menu";
import { Sheet } from "@/components/ui/sheet";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { Toaster } from "@/components/Toaster";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { NAV_GROUPS, pageFor } from "@/components/layout/nav";
import { DeviceSheet } from "@/components/devices/DeviceSheet";
import { useAlerts, useDevices, useHealth, useSystemStatus } from "@/hooks/useApi";
import { useCurrentUser, useIsAdmin, useLogout, ROLE_LABEL } from "@/hooks/useAuth";
import { useAiAuditReports } from "@/hooks/useAiAudit";
import { useNetworkConnections } from "@/hooks/useConnections";
import { useLiveEvents, type LiveStatus } from "@/hooks/useLiveEvents";
import { useQuarantine } from "@/hooks/useQuarantine";
import { setTheme, useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export default function MainLayout() {
  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const live = useLiveEvents();
  const location = useLocation();

  // Ctrl+K / Cmd+K o "/" (si no se está escribiendo) abren el buscador
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="app-backdrop flex min-h-dvh">
      {/* Barra lateral fija en escritorio */}
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 border-r bg-surface/60 backdrop-blur-xl lg:flex lg:flex-col">
        <SidebarContent onNavigate={() => {}} />
      </aside>

      {/* Cajón en el móvil; se cierra al navegar */}
      <Sheet open={navOpen} onClose={() => setNavOpen(false)} side="left" className="max-w-[17rem]" label="Menú">
        <SidebarContent onNavigate={() => setNavOpen(false)} />
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          live={live}
          onMenu={() => setNavOpen(true)}
          onSearch={() => setSearchOpen(true)}
          onPassword={() => setPasswordOpen(true)}
        />
        <main key={location.pathname} className="mx-auto w-full max-w-[1400px] flex-1 animate-fade-in px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>

      <DeviceSheet />
      <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ChangePasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />
      <Toaster />
    </div>
  );
}

// ─── Barra lateral ───────────────────────────────────────────────────────────

function SidebarContent({ onNavigate }: { onNavigate: () => void }) {
  const alerts = useAlerts(100);
  const devices = useDevices();
  const conns = useNetworkConnections();
  const isAdmin = useIsAdmin();
  const audits = useAiAuditReports(20, isAdmin);
  const lastAudit = audits.data?.find(r => r.status === "done");

  const newAlerts = (alerts.data ?? []).filter(a => a.status === "new").length;
  const urgent = (alerts.data ?? []).some(a => a.status === "new" && (a.severity === "critical" || a.severity === "high"));
  const counts: Record<string, { value: number; tone?: "destructive" | "warning" } | undefined> = {
    "/alerts": newAlerts ? { value: newAlerts, tone: urgent ? "destructive" : "warning" } : undefined,
    "/devices": devices.data ? { value: devices.data.length } : undefined,
    "/audit": lastAudit?.pending ? { value: lastAudit.pending, tone: "warning" } : undefined,
    "/connections": conns.data?.available
      ? { value: conns.data.connections.filter(c => c.status === "open").length }
      : undefined,
  };

  return (
    <div className="flex h-full flex-col">
      <Link to="/" onClick={onNavigate} className="flex h-16 items-center gap-2.5 px-5">
        <img src="/favicon.svg" alt="" className="size-8 drop-shadow-[0_0_12px_hsl(var(--primary)/0.5)]" />
        <div className="leading-tight">
          <p className="font-semibold tracking-tight">LanSentinel</p>
          <p className="text-[11px] text-muted-foreground">Seguridad de tu red</p>
        </div>
      </Link>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-3">
        {NAV_GROUPS.map(group => (
          <div key={group.title ?? "main"}>
            {group.title && (
              <p className="mb-1.5 px-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">{group.title}</p>
            )}
            <div className="space-y-0.5">
              {group.items.filter(item => isAdmin || !item.adminOnly).map(item => {
                const count = counts[item.to];
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    onClick={onNavigate}
                    className={({ isActive }) => cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive ? "bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
                    )}
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" />}
                        <item.icon className={cn("size-4", isActive && "text-primary")} />
                        <span className="flex-1">{item.label}</span>
                        {count && (
                          <span
                            className={cn(
                              "tabular rounded-full px-1.5 text-[11px] leading-5",
                              count.tone === "destructive" ? "bg-destructive text-destructive-foreground"
                                : count.tone === "warning" ? "bg-warning/20 text-warning"
                                : "bg-foreground/5 text-muted-foreground",
                            )}
                          >
                            {count.value}
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <SystemHealth />
    </div>
  );
}

// Estado de los servicios al pie de la barra lateral
function SystemHealth() {
  const status = useSystemStatus();
  const health = useHealth();
  const services = [
    { name: "Monitor", ok: status.data?.monitor?.running },
    { name: "Suricata", ok: status.data?.security?.running },
    { name: "Cortafuegos", ok: status.data?.firewall?.running },
  ];
  const allOk = !status.isError && services.every(s => s.ok);

  return (
    <div className="m-3 rounded-xl border bg-card/60 p-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-xs font-medium">
          <span className={cn("size-2 rounded-full", allOk ? "animate-pulse-ring bg-success" : "bg-warning")} />
          {status.isError ? "Sin conexión con el backend" : allOk ? "Todo en marcha" : "Revisa los servicios"}
        </p>
        {health.data && <span className="text-[11px] text-muted-foreground">v{health.data.version}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {services.map(s => (
          <span
            key={s.name}
            title={`${s.name}: ${s.ok ? "activo" : "detenido"}`}
            className={cn(
              "rounded-md px-1.5 py-0.5 text-[10px] font-medium",
              s.ok ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {s.name}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Barra superior ──────────────────────────────────────────────────────────

const LIVE: Record<LiveStatus, { label: string; dot: string; title: string }> = {
  live: { label: "En directo", dot: "bg-success animate-pulse-ring", title: "Las alertas nuevas llegan al instante" },
  connecting: { label: "Conectando", dot: "bg-warning", title: "Conectando con el canal en directo…" },
  offline: { label: "Sin directo", dot: "bg-muted-foreground", title: "Sin canal en directo: los datos se refrescan cada pocos segundos" },
};

function Topbar({
  live, onMenu, onSearch, onPassword,
}: { live: LiveStatus; onMenu: () => void; onSearch: () => void; onPassword: () => void }) {
  const location = useLocation();
  const page = pageFor(location.pathname);
  const quarantine = useQuarantine();
  const me = useCurrentUser();
  const logout = useLogout();
  const theme = useTheme();
  const status = LIVE[live];

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/70 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
      <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={onMenu} aria-label="Abrir menú">
        <MenuIcon />
      </Button>
      <div className="flex min-w-0 items-center gap-2 lg:hidden">
        <page.icon className="size-4 text-primary" />
        <span className="truncate font-medium">{page.label}</span>
      </div>

      {/* Buscador global */}
      <button
        onClick={onSearch}
        className="ml-auto flex h-9 items-center gap-2 rounded-lg border bg-surface/80 px-3 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground lg:ml-0 lg:w-80"
      >
        <Search className="size-4" />
        <span className="hidden flex-1 text-left sm:inline">Buscar dispositivo, IP…</span>
        <Kbd className="hidden sm:inline-flex">Ctrl K</Kbd>
      </button>

      <div className="flex items-center gap-2 lg:ml-auto">
        {quarantine.data?.enabled && (
          <Link
            to="/firewall"
            className="hidden items-center gap-1.5 rounded-full bg-warning/15 px-3 py-1 text-xs font-medium text-warning ring-1 ring-inset ring-warning/30 transition-colors hover:bg-warning/25 sm:flex"
            title="Solo los dispositivos de confianza salen a Internet"
          >
            <ShieldAlert className="size-3.5" />Cuarentena activa
          </Link>
        )}
        {me.data?.role === "viewer" && (
          <span
            className="hidden items-center gap-1.5 rounded-full bg-info/10 px-3 py-1 text-xs font-medium text-info ring-1 ring-inset ring-info/30 sm:flex"
            title="Puedes consultarlo todo, pero no cambiar nada"
          >
            <Eye className="size-3.5" />Solo lectura
          </span>
        )}
        <span title={status.title} className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground md:flex">
          <span className={cn("size-1.5 rounded-full", status.dot)} />{status.label}
        </span>

        <Menu
          trigger={open => (
            <button className={cn("flex items-center gap-2 rounded-lg p-1 pr-2 transition-colors hover:bg-accent", open && "bg-accent")}>
              <span className="bg-brand flex size-7 items-center justify-center rounded-md text-xs font-semibold uppercase text-white">
                {me.data?.username?.[0] ?? <User className="size-4" />}
              </span>
              <ChevronDown className="size-3.5 text-muted-foreground" />
            </button>
          )}
        >
          <div className="px-2.5 py-2">
            <p className="text-sm font-medium">{me.data?.username}</p>
            <p className="text-xs text-muted-foreground">{me.data ? ROLE_LABEL[me.data.role] : ""}</p>
          </div>
          <MenuSeparator />
          <MenuLabel>Tema</MenuLabel>
          {([["dark", "Oscuro", Moon], ["light", "Claro", Sun], ["system", "Como el sistema", Monitor]] as [Theme, string, typeof Moon][]).map(([value, label, Icon]) => (
            <MenuItem key={value} icon={<Icon />} active={theme === value} onClick={() => setTheme(value)}>{label}</MenuItem>
          ))}
          <MenuSeparator />
          <MenuItem icon={<KeyRound />} onClick={onPassword}>Cambiar contraseña</MenuItem>
          <MenuItem icon={<LogOut />} danger onClick={() => logout.mutate()}>Cerrar sesión</MenuItem>
        </Menu>
      </div>
    </header>
  );
}
