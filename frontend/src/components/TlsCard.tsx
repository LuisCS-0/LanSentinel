// Conexión segura: si el panel va cifrado, con qué certificado, y la CA de
// LanSentinel para importarla en los dispositivos y que el navegador deje de
// avisar.

import { useState } from "react";
import { AlertTriangle, Check, ChevronDown, Copy, Download, Lock, LockOpen, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { CA_DOWNLOAD_URL, useTlsStatus } from "@/hooks/useTls";
import { copyText } from "@/lib/clipboard";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";

const GUIDES: { name: string; steps: string[] }[] = [
  {
    name: "Windows (Chrome, Edge)",
    steps: [
      "Abre el fichero descargado y pulsa «Instalar certificado…».",
      "Elige «Usuario actual» y luego «Colocar todos los certificados en el siguiente almacén».",
      "Examinar → «Entidades de certificación raíz de confianza» → Aceptar → Finalizar.",
      "Cierra y vuelve a abrir el navegador.",
    ],
  },
  {
    name: "macOS (Safari, Chrome)",
    steps: [
      "Abre el fichero: se añade a Acceso a Llaveros.",
      "Haz doble clic en «LanSentinel CA», despliega «Confiar» y elige «Confiar siempre».",
    ],
  },
  {
    name: "iPhone y iPad",
    steps: [
      "Descárgalo con Safari y acepta descargar el perfil.",
      "Ajustes → Perfil descargado → Instalar.",
      "Ajustes → General → Información → Ajustes de confianza de certificados → activa «LanSentinel CA».",
    ],
  },
  {
    name: "Android",
    steps: [
      "Ajustes → Seguridad → Más ajustes → Cifrado y credenciales → Instalar un certificado → Certificado de CA (el nombre exacto cambia según el fabricante).",
      "Elige el fichero descargado. Chrome lo acepta; algunas apps solo confían en las CA del sistema.",
    ],
  },
  {
    name: "Firefox (cualquier sistema)",
    steps: [
      "Firefox usa su propio almacén: Ajustes → Privacidad y seguridad → Certificados → Ver certificados.",
      "Pestaña «Autoridades» → Importar → marca «Confiar en esta CA para identificar sitios web».",
    ],
  },
  {
    name: "Linux",
    steps: [
      "Debian/Ubuntu: sudo cp lansentinel-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates",
      "Fedora: sudo trust anchor lansentinel-ca.crt",
      "Chrome en Linux: Ajustes → Privacidad y seguridad → Seguridad → Gestionar certificados → Autoridades → Importar.",
    ],
  },
];

function dateOnly(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" }) : "—";
}

export function TlsCard() {
  const tls = useTlsStatus();
  const [guide, setGuide] = useState<string | null>(null);
  const secure = window.location.protocol === "https:";
  const t = tls.data;
  const own = t?.issuer === "lansentinel";

  const copyFingerprint = async () => {
    if (t?.ca_fingerprint && await copyText(t.ca_fingerprint)) toast({ title: "Huella copiada" });
  };

  return (
    <Card>
      <CardHeaderRow
        title={<><ShieldCheck />Conexión segura (HTTPS)</>}
        description="El panel va cifrado: la contraseña y la cookie de sesión no viajan en claro por la red."
        actions={secure
          ? <Badge variant="success" dot>Cifrada</Badge>
          : <Badge variant="warning" dot>Sin cifrar</Badge>}
      />
      <CardContent className="space-y-4 text-sm">
        {!secure && (
          <p className="flex items-start gap-2 rounded-lg bg-warning/10 p-3 text-warning">
            <LockOpen className="mt-0.5 size-4 shrink-0" />
            Estás entrando por HTTP. Abre el panel con https:// para que la conexión vaya cifrada.
          </p>
        )}

        {tls.isLoading ? <Skeleton className="h-24" /> : !t?.available ? (
          <p className="flex items-start gap-2 rounded-lg bg-muted/60 p-3 text-muted-foreground">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            {t?.error ? `No se pudo generar el certificado: ${t.error}` : "Todavía no hay certificado."}
          </p>
        ) : (
          <>
            <dl className="grid gap-3 rounded-xl border bg-muted/30 p-4 sm:grid-cols-3">
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Certificado</dt>
                <dd className="mt-1 flex items-center gap-1.5 font-medium">
                  <Lock className="size-3.5 text-success" />{own ? "CA de LanSentinel" : "Propio"}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Válido hasta</dt>
                <dd className="mt-1 font-medium">{dateOnly(t.valid_until)}</dd>
                {own && <dd className="text-xs text-muted-foreground">Se renueva solo</dd>}
              </div>
              <div className="min-w-0">
                <dt className="text-[11px] uppercase tracking-wider text-muted-foreground">Direcciones</dt>
                <dd className="mt-1 flex flex-wrap gap-1">
                  {[...t.dns_names, ...t.ip_addresses].filter(n => n !== "localhost" && n !== "127.0.0.1").map(n => (
                    <span key={n} className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px] ring-1 ring-inset ring-border">{n}</span>
                  ))}
                </dd>
              </div>
            </dl>

            {own && (
              <div className="space-y-3">
                <p className="text-muted-foreground">
                  Hasta que importes la CA de LanSentinel, el navegador avisará de que el certificado no es de
                  confianza. Se hace una vez por dispositivo y sirve aunque cambie la IP del equipo. La CA solo
                  puede firmar nombres e IPs de tu red local: aunque alguien la robara, no le serviría para
                  suplantar webs de Internet.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  {/* Navegar a la descarga (Content-Disposition: attachment) no cambia de página,
                      y en iPhone es lo que hace que Safari ofrezca instalar el perfil */}
                  <Button onClick={() => { window.location.href = CA_DOWNLOAD_URL; }}><Download />Descargar la CA</Button>
                  <span className="text-xs text-muted-foreground">Válida hasta {dateOnly(t.ca_valid_until)}</span>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-muted-foreground">Huella SHA-256 (debe coincidir con la que muestra el instalador)</p>
                    <Button variant="ghost" size="icon" className="size-7" onClick={copyFingerprint} aria-label="Copiar huella">
                      <Copy className="size-3.5" />
                    </Button>
                  </div>
                  <p className="mt-1 break-all font-mono text-[11px] leading-relaxed">{t.ca_fingerprint}</p>
                </div>

                <div className="divide-y rounded-lg border">
                  {GUIDES.map(g => (
                    <div key={g.name}>
                      <button
                        className="flex w-full items-center justify-between px-3 py-2 text-left font-medium hover:bg-muted/40"
                        onClick={() => setGuide(guide === g.name ? null : g.name)}
                        aria-expanded={guide === g.name}
                      >
                        {g.name}
                        <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", guide === g.name && "rotate-180")} />
                      </button>
                      {guide === g.name && (
                        <ol className="space-y-1.5 px-3 pb-3 text-muted-foreground">
                          {g.steps.map((s, i) => (
                            <li key={i} className="flex gap-2">
                              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-medium text-foreground">{i + 1}</span>
                              <span className={cn(s.includes("sudo ") && "font-mono text-xs")}>{s}</span>
                            </li>
                          ))}
                        </ol>
                      )}
                    </div>
                  ))}
                </div>
                {secure && (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Check className="size-3.5" />Al terminar, recarga el panel: el candado debe salir sin avisos.
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
