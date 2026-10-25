import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Shield, LayoutDashboard, HardDrive, Bell, Lock, LogOut, KeyRound, User,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { useCurrentUser, useLogout } from "@/hooks/useAuth";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/devices", label: "Dispositivos", icon: HardDrive },
  { to: "/alerts", label: "Alertas", icon: Bell },
  { to: "/firewall", label: "Firewall", icon: Lock },
];

export default function MainLayout() {
  const me = useCurrentUser();
  const logout = useLogout();
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div className="flex min-h-screen">
      {/* Barra lateral */}
      <aside className="w-64 border-r bg-card flex flex-col">
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <Shield className="h-6 w-6 text-primary" />
          <span className="font-semibold text-lg">LanSentinel</span>
        </div>

        <nav className="p-3 flex-1">
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

        {/* Sesión */}
        <div className="border-t p-3 space-y-1">
          <div className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
            <User className="h-4 w-4" />
            <span className="truncate">{me.data?.username}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            onClick={() => setShowPassword(true)}
          >
            <KeyRound className="h-4 w-4 mr-2" />
            Cambiar contraseña
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Cerrar sesión
          </Button>
        </div>
      </aside>

      {/* Contenido principal */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>

      <ChangePasswordDialog open={showPassword} onClose={() => setShowPassword(false)} />
    </div>
  );
}
