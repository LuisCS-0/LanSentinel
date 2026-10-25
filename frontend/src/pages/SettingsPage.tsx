import { useState } from "react";
import { AlertCircle, Bell, Check, Loader2, Send } from "lucide-react";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SeverityBadge } from "@/components/SeverityBadge";
import { useNotificationStatus, useTestNotification } from "@/hooks/useNotifications";
import { browserNotificationsSupported } from "@/hooks/useLiveEvents";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import type { NotificationChannel } from "@/lib/types";

// Variables de .env de cada canal, para la guía de configuración
const CHANNEL_HELP: Record<NotificationChannel["name"], { vars: string; hint: string }> = {
  telegram: {
    vars: "TELEGRAM_BOT_TOKEN=123456:ABC...\nTELEGRAM_CHAT_ID=987654321",
    hint: "Crea un bot con @BotFather para obtener el token y escríbele un mensaje; tu chat_id aparece en https://api.telegram.org/bot<token>/getUpdates.",
  },
  ntfy: {
    vars: "NTFY_SERVER=https://ntfy.sh\nNTFY_TOPIC=lansentinel-un-nombre-largo-y-dificil\n# NTFY_TOKEN=tk_... (servidor propio con autenticación)",
    hint: "Instala la app ntfy en el móvil y suscríbete al mismo tema. En ntfy.sh cualquiera que conozca el tema puede leerlo: usa un nombre difícil de adivinar.",
  },
  email: {
    vars: "SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_SECURITY=starttls\nSMTP_USER=tu@gmail.com\nSMTP_PASSWORD=contraseña-de-aplicación\nSMTP_FROM=tu@gmail.com\nSMTP_TO=tu@gmail.com",
    hint: "Con Gmail u Outlook necesitas una contraseña de aplicación, no la de la cuenta.",
  },
};

export default function SettingsPage() {
  const status = useNotificationStatus();

  return (
    <div className="container py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Ajustes</h1>
        <p className="text-muted-foreground mt-1">Avisos de alertas fuera del panel</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Avisos externos</CardTitle>
          <CardDescription>
            LanSentinel avisa de las alertas nuevas por los canales configurados en el fichero
            <code className="font-mono mx-1">.env</code>
            del servidor. Tras cambiarlo, reinicia el backend.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {status.isLoading || !status.data ? (
            <p className="text-sm text-muted-foreground">Cargando…</p>
          ) : (
            <>
              <div className="grid gap-3 sm:grid-cols-3 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Se avisa desde</p>
                  <SeverityBadge severity={status.data.min_severity} />
                  <span className="text-xs text-muted-foreground ml-1">(NOTIFY_MIN_SEVERITY)</span>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Máximo por hora</p>
                  <p>{status.data.max_per_hour} avisos <span className="text-xs text-muted-foreground">(NOTIFY_MAX_PER_HOUR)</span></p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Enlace al panel</p>
                  {status.data.panel_url ? (
                    <p className="font-mono text-xs break-all">{status.data.panel_url}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">Sin PANEL_URL: los avisos no incluirán enlace</p>
                  )}
                </div>
              </div>

              <div className="space-y-3">
                {status.data.channels.map(channel => (
                  <ChannelRow key={channel.name} channel={channel} />
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <BrowserNotificationsCard />
    </div>
  );
}

// ─── Un canal ────────────────────────────────────────────────────────────────

function ChannelRow({ channel }: { channel: NotificationChannel }) {
  const test = useTestNotification();
  const [showHelp, setShowHelp] = useState(false);
  const help = CHANNEL_HELP[channel.name];

  return (
    <div className="rounded-md border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <p className="font-medium">{channel.label}</p>
          {channel.configured ? (
            <Badge variant="success">Configurado</Badge>
          ) : (
            <Badge variant="outline">No configurado</Badge>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => setShowHelp(h => !h)}>
            {showHelp ? "Ocultar ayuda" : "Cómo configurarlo"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => test.mutate(channel.name)}
            disabled={!channel.configured || test.isPending}
          >
            {test.isPending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
            Enviar prueba
          </Button>
        </div>
      </div>

      <div className="mt-2 space-y-1 text-xs text-muted-foreground">
        {channel.last_sent_at && <p>Último envío correcto {relativeTime(channel.last_sent_at)}</p>}
        {test.isSuccess && (
          <p className="flex items-center gap-1 text-emerald-700">
            <Check className="h-3 w-3" /> Prueba enviada. Comprueba que te ha llegado.
          </p>
        )}
        {(test.isError || channel.last_error) && (
          <p className="flex items-start gap-1 text-destructive">
            <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
            {test.isError ? extractErrorMessage(test.error) : channel.last_error}
          </p>
        )}
      </div>

      {showHelp && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">{help.hint}</p>
          <pre className="text-xs bg-muted p-3 rounded-md overflow-auto font-mono">{help.vars}</pre>
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

  const request = async () => {
    setPermission(await Notification.requestPermission());
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="h-4 w-4" />
          Notificaciones del navegador
        </CardTitle>
        <CardDescription>
          Con el panel abierto, las alertas nuevas aparecen al instante. Si además lo
          permites, las altas y críticas se notifican aunque la pestaña esté en segundo plano.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm">
        {permission === "unsupported" && (
          <p className="text-muted-foreground">
            No disponible: los navegadores solo permiten notificaciones en páginas servidas por
            HTTPS o desde localhost. Los avisos dentro del panel siguen funcionando.
          </p>
        )}
        {permission === "granted" && (
          <p className="flex items-center gap-1 text-emerald-700">
            <Check className="h-4 w-4" /> Activadas en este navegador.
          </p>
        )}
        {permission === "denied" && (
          <p className="text-muted-foreground">
            Bloqueadas. Para activarlas, cambia el permiso de notificaciones de este sitio en la
            configuración del navegador.
          </p>
        )}
        {permission === "default" && (
          <Button onClick={request}>
            <Bell className="h-4 w-4 mr-2" />
            Activar notificaciones
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
