// Ajustes: apariencia, cuenta, avisos externos (Telegram, ntfy, correo),
// notificaciones del navegador e información del sistema.

import { useState, type ReactNode } from "react";
import {
  AlertCircle, Bell, Check, Info, KeyRound, Loader2, Mail, MessageCircle, Monitor, Moon, Palette,
  Send, Smartphone, Sun, User,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { PageHeader } from "@/components/PageHeader";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useHealth, useSystemStatus } from "@/hooks/useApi";
import { useCurrentUser } from "@/hooks/useAuth";
import { browserNotificationsSupported } from "@/hooks/useLiveEvents";
import { useNotificationStatus, useTestNotification } from "@/hooks/useNotifications";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { setTheme, useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import type { NotificationChannel, SystemStatus } from "@/lib/types";

// Variables de .env de cada canal, para la guía de configuración
const CHANNEL_HELP: Record<NotificationChannel["name"], { vars: string; hint: string; icon: typeof Send }> = {
  telegram: {
    icon: MessageCircle,
    vars: "TELEGRAM_BOT_TOKEN=123456:ABC...\nTELEGRAM_CHAT_ID=987654321",
    hint: "Crea un bot con @BotFather para obtener el token y escríbele un mensaje; tu chat_id aparece en https://api.telegram.org/bot<token>/getUpdates.",
  },
  ntfy: {
    icon: Smartphone,
    vars: "NTFY_SERVER=https://ntfy.sh\nNTFY_TOPIC=lansentinel-un-nombre-largo-y-dificil\n# NTFY_TOKEN=tk_... (servidor propio con autenticación)",
    hint: "Instala la app ntfy en el móvil y suscríbete al mismo tema. En ntfy.sh cualquiera que conozca el tema puede leerlo: usa un nombre difícil de adivinar.",
  },
  email: {
    icon: Mail,
    vars: "SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_SECURITY=starttls\nSMTP_USER=tu@gmail.com\nSMTP_PASSWORD=contraseña-de-aplicación\nSMTP_FROM=tu@gmail.com\nSMTP_TO=tu@gmail.com",
    hint: "Con Gmail u Outlook necesitas una contraseña de aplicación, no la de la cuenta.",
  },
};

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Ajustes" description="Apariencia, cuenta y avisos de LanSentinel" />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <NotificationsCard />
          <BrowserNotificationsCard />
        </div>
        <div className="space-y-4">
          <AppearanceCard />
          <AccountCard />
          <AboutCard />
        </div>
      </div>
    </div>
  );
}

// ─── Apariencia ──────────────────────────────────────────────────────────────

function AppearanceCard() {
  const theme = useTheme();
  const options: [Theme, string, typeof Moon][] = [["dark", "Oscuro", Moon], ["light", "Claro", Sun], ["system", "Sistema", Monitor]];
  return (
    <Card>
      <CardHeaderRow title={<><Palette />Apariencia</>} description="Se guarda en este navegador" />
      <CardContent className="grid grid-cols-3 gap-2">
        {options.map(([value, label, Icon]) => (
          <button
            key={value}
            onClick={() => setTheme(value)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-xl border p-3 text-xs font-medium transition-all",
              theme === value ? "border-primary bg-primary/10 text-foreground shadow-glow" : "text-muted-foreground hover:border-primary/40",
            )}
          >
            <Icon className="size-5" />{label}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

// ─── Cuenta ──────────────────────────────────────────────────────────────────

function AccountCard() {
  const me = useCurrentUser();
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <CardHeaderRow title={<><User />Cuenta</>} />
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="bg-brand flex size-10 items-center justify-center rounded-xl text-sm font-semibold uppercase text-white">
            {me.data?.username?.[0]}
          </span>
          <div>
            <p className="font-medium">{me.data?.username}</p>
            <p className="text-xs text-muted-foreground">
              {me.data?.last_login_at ? `Último acceso ${relativeTime(me.data.last_login_at)}` : "Administrador"}
            </p>
          </div>
        </div>
        <Button variant="outline" className="w-full" onClick={() => setOpen(true)}><KeyRound />Cambiar contraseña</Button>
      </CardContent>
      <ChangePasswordDialog open={open} onClose={() => setOpen(false)} />
    </Card>
  );
}

// ─── Sistema ─────────────────────────────────────────────────────────────────

function AboutCard() {
  const health = useHealth();
  const status = useSystemStatus();
  const rows: [string, ReactNode][] = [
    ["Versión", health.data ? `LanSentinel ${health.data.version}` : "—"],
    ["Interfaz vigilada", status.data?.monitor?.interface ?? "—"],
    ["Escaneo ARP", status.data?.monitor ? `cada ${status.data.monitor.interval_seconds} s` : "—"],
    ["Eventos de Suricata", status.data?.security?.events_processed?.toLocaleString("es-ES") ?? "—"],
    ["IPv6 en el cortafuegos", status.data?.firewall ? (status.data.firewall.ipv6_enabled ? "Sí" : "No") : "—"],
    ["Modo router", <RouterState key="router" router={status.data?.firewall?.router} />],
  ];
  return (
    <Card>
      <CardHeaderRow title={<><Info />Sistema</>} />
      <CardContent>
        <dl className="divide-y text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 py-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-right font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

// Estado del modo router: activo, mal configurado o desactivado
function RouterState({ router }: { router?: NonNullable<SystemStatus["firewall"]>["router"] }) {
  if (!router) return <>—</>;
  if (!router.configured) return <span className="text-muted-foreground">Desactivado</span>;
  if (!router.active) {
    return <span className="text-destructive" title="Revisa WAN_INTERFACE y MONITOR_INTERFACE en .env y los logs del backend">Con errores</span>;
  }
  if (!router.ip_forward) {
    return <span className="text-warning" title="Ejecuta scripts/instalar.sh o activa net.ipv4.ip_forward">Activo, sin reenvío</span>;
  }
  return <span className="text-success">Activo · {router.wan_interface} → {router.lan_interface}</span>;
}

// ─── Avisos externos ─────────────────────────────────────────────────────────

function NotificationsCard() {
  const status = useNotificationStatus();
  return (
    <Card>
      <CardHeaderRow
        title={<><Send />Avisos externos</>}
        description={<>Las alertas nuevas se envían por los canales configurados en el <code className="font-mono">.env</code> del servidor. Tras cambiarlo, reinicia el backend.</>}
      />
      <CardContent className="space-y-4">
        {status.isLoading || !status.data ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <div className="grid gap-3 rounded-xl border bg-muted/30 p-4 text-sm sm:grid-cols-3">
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Se avisa desde</p>
                <SeverityBadge severity={status.data.min_severity} />
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">NOTIFY_MIN_SEVERITY</p>
              </div>
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Máximo por hora</p>
                <p className="font-medium">{status.data.max_per_hour} avisos</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">NOTIFY_MAX_PER_HOUR</p>
              </div>
              <div className="min-w-0">
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Enlace al panel</p>
                <p className="truncate font-mono text-xs">{status.data.panel_url ?? "Sin PANEL_URL"}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">{status.data.panel_url ? "Se incluye en los avisos" : "Los avisos no llevarán enlace"}</p>
              </div>
            </div>
            <div className="space-y-3">
              {status.data.channels.map(channel => <ChannelRow key={channel.name} channel={channel} />)}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ChannelRow({ channel }: { channel: NotificationChannel }) {
  const test = useTestNotification();
  const [showHelp, setShowHelp] = useState(false);
  const help = CHANNEL_HELP[channel.name];

  return (
    <div className="rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className={cn("rounded-lg p-2", channel.configured ? "bg-success/10 text-success" : "bg-muted text-muted-foreground")}>
            <help.icon className="size-4" />
          </div>
          <div>
            <p className="font-medium">{channel.label}</p>
            <p className="text-xs text-muted-foreground">
              {channel.last_sent_at ? `Último envío ${relativeTime(channel.last_sent_at)}` : channel.configured ? "Sin envíos todavía" : "No configurado"}
            </p>
          </div>
          {channel.configured && <Badge variant="success" dot>Activo</Badge>}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => setShowHelp(h => !h)}>{showHelp ? "Ocultar ayuda" : "Cómo configurarlo"}</Button>
          <Button variant="outline" size="sm" onClick={() => test.mutate(channel.name)} disabled={!channel.configured || test.isPending}>
            {test.isPending ? <Loader2 className="animate-spin" /> : <Send />}Enviar prueba
          </Button>
        </div>
      </div>
      {test.isSuccess && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-success"><Check className="size-3.5" />Prueba enviada. Comprueba que te ha llegado.</p>
      )}
      {(test.isError || channel.last_error) && (
        <p className="mt-3 flex items-start gap-1.5 text-xs text-destructive">
          <AlertCircle className="mt-px size-3.5 shrink-0" />{test.isError ? extractErrorMessage(test.error) : channel.last_error}
        </p>
      )}
      {showHelp && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">{help.hint}</p>
          <pre className="overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-xs">{help.vars}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Notificaciones del navegador ────────────────────────────────────────────

function BrowserNotificationsCard() {
  const supported = browserNotificationsSupported();
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    supported ? Notification.permission : "unsupported",
  );

  return (
    <Card>
      <CardHeaderRow
        title={<><Bell />Notificaciones del navegador</>}
        description="Con el panel abierto, las alertas nuevas aparecen al instante. Si además lo permites, las altas y críticas se notifican aunque la pestaña esté en segundo plano."
      />
      <CardContent className="text-sm">
        {permission === "unsupported" && (
          <p className="rounded-lg bg-muted/50 p-3 text-muted-foreground">
            No disponible: los navegadores solo permiten notificaciones en páginas servidas por HTTPS o desde
            localhost. Los avisos dentro del panel siguen funcionando.
          </p>
        )}
        {permission === "granted" && <p className="flex items-center gap-1.5 text-success"><Check className="size-4" />Activadas en este navegador.</p>}
        {permission === "denied" && (
          <p className="text-muted-foreground">Bloqueadas. Para activarlas, cambia el permiso de notificaciones de este sitio en la configuración del navegador.</p>
        )}
        {permission === "default" && (
          <Button onClick={async () => setPermission(await Notification.requestPermission())}><Bell />Activar notificaciones</Button>
        )}
      </CardContent>
    </Card>
  );
}
