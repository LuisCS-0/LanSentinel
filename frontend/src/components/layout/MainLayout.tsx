import { NavLink, Outlet } from "react-router-dom";
import { Shield, LayoutDashboard, HardDrive, Bell, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Dispositivos", icon: HardDrive },
  { to: "/alerts", label: "Alertas", icon: Bell },
  { to: "/firewall", label: "Firewall", icon: Lock },
];

export default function MainLayout() {
  return (
    <div className="flex min-h-screen">
      {/* Barra lateral */}
      <aside className="w-64 border-r bg-card">
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <Shield className="h-6 w-6 text-primary" />
          <span className="font-semibold text-lg">LanSentinel</span>
        </div>

        <nav className="p-3">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  "transition-colors mb-1",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Contenido principal */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
