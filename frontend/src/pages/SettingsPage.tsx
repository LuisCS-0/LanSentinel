// Ajustes: apariencia, cuenta, avisos externos (Telegram, ntfy, correo),
// notificaciones del navegador e información del sistema. Los
// administradores ven además los usuarios, el registro de acciones y los
// ajustes que antes iban en .env (proveedor de IA, avisos, detección...).

import { useState, type ReactNode } from "react";
import {
  AlertCircle, Bell, Check, Info, KeyRound, Loader2, Mail, MessageCircle, Monitor, Moon, Palette,
  Radar, Send, Settings2, Smartphone, Sun, User, Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { ConfigDialog } from "@/components/ConfigDialog";
import { PageHeader } from "@/components/PageHeader";
import { RouterCard } from "@/components/RouterCard";
import { TlsCard } from "@/components/TlsCard";
import { BackupsCard } from "@/components/BackupsCard";
import { UsersCard } from "@/components/UsersCard";
import { AuditCard } from "@/components/AuditCard";
import { AiAuditCard } from "@/components/AiAuditCard";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useHealth, useSystemStatus } from "@/hooks/useApi";
import { useCurrentUser, useIsAdmin, ROLE_LABEL } from "@/hooks/useAuth";
import { useConfig } from "@/hooks/useConfig";
import { browserNotificationsSupported } from "@/hooks/useLiveEvents";
import { useNotificationStatus, useTestNotification } from "@/hooks/useNotifications";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { setTheme, useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { setViewMode, useIsBasic } from "@/lib/viewMode";
import type { NotificationChannel } from "@/lib/types";

// Ajustes de cada canal (se cambian en el diálogo de configuración) y una pista para empezar
const CHANNEL_HELP: Record<NotificationChannel["name"], { names: string[]; hint: string; icon: typeof Send }> = {
  telegram: {
    icon: MessageCircle,
    names: ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    hint: "Crea un bot con @BotFather para obtener el token y escríbele un mensaje; tu chat aparece en https://api.telegram.org/bot<token>/getUpdates.",
  },
  ntfy: {
    icon: Smartphone,
    names: ["NTFY_SERVER", "NTFY_TOPIC", "NTFY_TOKEN"],
    hint: "Instala la app ntfy en el móvil y suscríbete al mismo tema. En ntfy.sh cualquiera que conozca el tema puede leerlo: usa un nombre difícil de adivinar.",
  },
  email: {
    icon: Mail,
    names: ["SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO"],
    hint: "Con Gmail u Outlook necesitas una contraseña de aplicación, no la de la cuenta.",
  },
};

export default function SettingsPage() {
  const isAdmin = useIsAdmin();
  const basic = useIsBasic();
  if (basic) {
    // Lo justo: avisos, la IA, el aspecto y la cuenta. Lo de instalación y red, en el modo experto
    return (
      <div className="space-y-6">
        <PageHeader title="Ajustes" description="Cómo te avisa LanSentinel, la revisión con IA y tu cuenta" />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="min-w-0 space-y-4 xl:col-span-2">
            <NotificationsCard />
            <BrowserNotificationsCard />
            {isAdmin && <AiAuditCard />}
          </div>
          <div className="min-w-0 space-y-4">
            <AppearanceCard />
            <AccountCard />
            <p className="flex items-start gap-2 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">
              <Wrench className="mt-0.5 size-4 shrink-0" />
              <span>
                El modo router, HTTPS, las copias de seguridad, la detección y los usuarios están en el modo experto.
                {" "}<button className="font-medium text-primary hover:underline" onClick={() => setViewMode("experto")}>Cambiar</button>
              </span>
            </p>
            <AboutCard />
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <PageHeader title="Ajustes" description="Modo router, HTTPS, copias de seguridad, avisos, usuarios y cuenta" />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="min-w-0 space-y-4 xl:col-span-2">
          <RouterCard />
          <TlsCard />
          <BackupsCard />
          <NotificationsCard />
          {isAdmin && <DetectionCard />}
          <BrowserNotificationsCard />
          {isAdmin && <AiAuditCard />}
          {isAdmin && <AuditCard />}
        </div>
        <div className="min-w-0 space-y-4">
          <AppearanceCard />
          <AccountCard />
          {isAdmin && <UsersCard />}
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
              {me.data ? ROLE_LABEL[me.data.role] : ""}
              {me.data?.last_login_at && ` · último acceso ${relativeTime(me.data.last_login_at)}`}
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

// ─── Detección y sistema ─────────────────────────────────────────────────────

function DetectionCard() {
  const config = useConfig();
  const [open, setOpen] = useState<"deteccion" | "sistema" | null>(null);
  const fields = (config.data ?? []).filter(f => f.group === "deteccion");
  return (
    <Card>
      <CardHeaderRow
        title={<><Radar />Detección y sistema</>}
        description="Qué vigila LanSentinel y cómo reacciona, la zona horaria y cuánto se guarda el registro."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setOpen("deteccion")}><Settings2 />Detección</Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen("sistema")}>Sistema</Button>
          </div>
        }
      />
      <CardContent>
        {config.isLoading ? (
          <Skeleton className="h-24" />
        ) : (
          <ul className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {fields.map(f => (
              <li key={f.name} className="flex items-center justify-between gap-3">
                <span className="min-w-0 truncate text-muted-foreground">{f.label}</span>
                <span className="shrink-0 font-medium">
                  {f.kind === "bool" ? (f.value ? <Badge variant="success">Sí</Badge> : <Badge variant="secondary">No</Badge>) : String(f.value)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <ConfigDialog
        open={open !== null}
        onClose={() => setOpen(null)}
        group={open ?? "deteccion"}
        title={open === "sistema" ? "Sistema" : "Detección y protección"}
      />
    </Card>
  );
}

// ─── Avisos externos ─────────────────────────────────────────────────────────

function NotificationsCard() {
  const status = useNotificationStatus();
  const isAdmin = useIsAdmin();
  const [configuring, setConfiguring] = useState(false);
  return (
    <Card>
      <CardHeaderRow
        title={<><Send />Avisos externos</>}
        description="Las alertas nuevas se envían por los canales que configures aquí: Telegram, ntfy o correo."
        actions={isAdmin && <Button size="sm" variant="outline" onClick={() => setConfiguring(true)}><Settings2 />Configurar</Button>}
      />
      <ConfigDialog
        open={configuring}
        onClose={() => setConfiguring(false)}
        names={["NOTIFY_MIN_SEVERITY", "NOTIFY_MAX_PER_HOUR", "PANEL_URL"]}
        title="Avisos externos"
        description="De qué alertas se avisa y con qué enlace. Cada canal se configura en su fila."
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
              </div>
              <div>
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Máximo por hora</p>
                <p className="font-medium">{status.data.max_per_hour} avisos</p>
              </div>
              <div className="min-w-0">
                <p className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground">Enlace al panel</p>
                <p className="truncate font-mono text-xs">{status.data.panel_url ?? "Sin dirección"}</p>
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
  const isAdmin = useIsAdmin();
  const [configuring, setConfiguring] = useState(false);
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
          {isAdmin && (
            <Button variant={channel.configured ? "ghost" : "outline"} size="sm" onClick={() => setConfiguring(true)}>
              <Settings2 />{channel.configured ? "Configurar" : "Activar"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={() => test.mutate(channel.name)} disabled={!isAdmin || !channel.configured || test.isPending}>
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
      <ConfigDialog
        open={configuring}
        onClose={() => { setConfiguring(false); test.reset(); }}
        names={help.names}
        title={channel.label}
        description={help.hint}
        icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><help.icon className="size-4" /></div>}
      />
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
