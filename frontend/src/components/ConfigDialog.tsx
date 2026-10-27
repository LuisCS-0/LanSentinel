// Diálogo para cambiar ajustes desde el panel (los de services/panel_config).
// Se le pasan los nombres que enseña; agrupa por la parte del nombre antes
// de ":" ("Telegram: token" → sección Telegram). Los secretos no se ven
// nunca: solo si hay uno puesto, y se pueden cambiar o quitar. Si se toca
// algo sensible (un secreto o adónde salen los datos) pide la contraseña.

import { useMemo, useState, type ReactNode } from "react";
import { AlertCircle, KeyRound, Loader2, RotateCcw, Settings2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, Skeleton, Switch } from "@/components/ui/misc";
import { useCurrentUser } from "@/hooks/useAuth";
import { useConfig, useUpdateConfig } from "@/hooks/useConfig";
import { extractErrorMessage } from "@/lib/api";
import { toast } from "@/lib/toast";
import type { ConfigField } from "@/lib/types";

type Value = string | number | boolean | null;

// Para los gestores de contraseñas (1Password, LastPass, Bitwarden, Dashlane):
// estos campos no son de inicio de sesión
const NO_AUTOFILL = {
  "data-1p-ignore": true, "data-lpignore": "true", "data-bwignore": true, "data-form-type": "other",
} as const;

const SOURCE: Record<ConfigField["source"], string> = { panel: "panel", env: ".env", default: "por defecto" };

export function ConfigDialog({
  open, onClose, names, group, title, description, icon,
}: {
  open: boolean;
  onClose: () => void;
  names?: string[];                 // estos ajustes, en este orden
  group?: ConfigField["group"];     // o todos los de un grupo
  title: string;
  description?: ReactNode;
  icon?: ReactNode;
}) {
  const config = useConfig(open);
  const update = useUpdateConfig();
  const me = useCurrentUser().data?.username;
  // Solo lo que se cambia: nombre → valor nuevo (null: volver a .env)
  const [changes, setChanges] = useState<Record<string, Value>>({});
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fields = useMemo(
    () => names
      ? names.map(n => config.data?.find(f => f.name === n)).filter((f): f is ConfigField => !!f)
      : (config.data ?? []).filter(f => f.group === group),
    [names, group, config.data],
  );
  const sections = useMemo(() => {
    const map = new Map<string, ConfigField[]>();
    for (const f of fields) {
      const section = f.label.includes(": ") ? f.label.split(": ")[0] : "";
      map.set(section, [...(map.get(section) ?? []), f]);
    }
    return [...map.entries()];
  }, [fields]);

  const dirty = Object.keys(changes);
  const sensitive = fields.some(f => f.sensitive && f.name in changes);

  const close = () => {
    setChanges({});
    setPassword("");
    setError(null);
    update.reset();
    onClose();
  };

  const set = (name: string, value: Value) => setChanges(prev => ({ ...prev, [name]: value }));
  const unset = (name: string) => setChanges(prev => {
    const next = { ...prev };
    delete next[name];
    return next;
  });

  const save = async () => {
    setError(null);
    try {
      const result = await update.mutateAsync({ values: changes, password: sensitive ? password : undefined });
      const restart = fields.filter(f => f.restart && result.changed.includes(f.name));
      toast({
        title: result.changed.length ? "Ajustes guardados" : "Sin cambios",
        description: restart.length ? "Algunos se aplicarán al reiniciar LanSentinel." : undefined,
      });
      close();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      className="sm:max-w-xl"
      title={title}
      description={description}
      icon={icon ?? <div className="rounded-lg bg-primary/15 p-2 text-primary"><Settings2 className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={update.isPending}>Cancelar</Button>
          <Button onClick={save} disabled={!dirty.length || update.isPending || (sensitive && !password)}>
            {update.isPending && <Loader2 className="animate-spin" />}Guardar
          </Button>
        </>
      }
    >
      {config.isLoading ? (
        <Skeleton className="h-60" />
      ) : config.isError ? (
        <p className="text-sm text-destructive">{extractErrorMessage(config.error)}</p>
      ) : (
        <div className="space-y-5">
          {/* Formulario aparte de la contraseña: el gestor de contraseñas del
              navegador no debe tomar el primer campo de texto por el usuario */}
          <form autoComplete="off" className="space-y-5" onSubmit={e => e.preventDefault()}>
          {sections.map(([section, items]) => (
            <div key={section || "general"} className="space-y-3">
              {section && <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{section}</p>}
              {items.map(f => (
                <FieldRow
                  key={f.name}
                  field={f}
                  label={section ? capitalize(f.label.slice(section.length + 2)) : f.label}
                  value={f.name in changes ? changes[f.name] : f.value}
                  changed={f.name in changes}
                  onChange={v => set(f.name, v)}
                  onUndo={() => unset(f.name)}
                />
              ))}
            </div>
          ))}
          </form>

          {sensitive && (
            <form
              className="rounded-lg border border-warning/40 bg-warning/5 p-3"
              onSubmit={e => { e.preventDefault(); if (password) void save(); }}
            >
              {/* El usuario, para que el navegador rellene aquí (y no en "Modelo") */}
              <input type="text" name="username" autoComplete="username" value={me ?? ""} readOnly
                     tabIndex={-1} aria-hidden className="sr-only" />
              <label className="flex items-center gap-1.5 text-sm font-medium" htmlFor="config-password">
                <KeyRound className="size-4 text-warning" />Confirma con tu contraseña
              </label>
              <p className="mb-2 mt-0.5 text-xs text-muted-foreground">
                Cambias una clave o adónde salen los datos de tu red: hace falta tu contraseña, no basta con la sesión.
              </p>
              <Input id="config-password" name="password" type="password" autoComplete="current-password"
                     value={password} onChange={e => setPassword(e.target.value)} />
            </form>
          )}
          {error && (
            <p className="flex items-start gap-1.5 text-sm text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</p>
          )}
        </div>
      )}
    </Dialog>
  );
}

function capitalize(text: string) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function FieldRow({
  field: f, label, value, changed, onChange, onUndo,
}: {
  field: ConfigField;
  label: string;
  value: Value;
  changed: boolean;
  onChange: (value: Value) => void;
  onUndo: () => void;
}) {
  const id = `config-${f.name}`;
  const toEnv = changed && value === null;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={id} className="text-sm font-medium">{label}</label>
        {!changed && f.source !== "default" && (
          <Badge variant="outline" className="text-[10px]">{SOURCE[f.source]}</Badge>
        )}
        {f.restart && <Badge variant="secondary" className="text-[10px]">al reiniciar</Badge>}
        <span className="ml-auto flex gap-1">
          {changed && (
            <Button size="xs" variant="ghost" onClick={onUndo}><RotateCcw />Deshacer</Button>
          )}
          {!changed && f.source === "panel" && (
            <Button size="xs" variant="ghost" onClick={() => onChange(null)} title="Quitar el valor del panel y usar el de .env">
              Usar el de .env
            </Button>
          )}
        </span>
      </div>

      {toEnv ? (
        <p className="rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">Se usará el valor de .env</p>
      ) : f.kind === "bool" ? (
        <Switch checked={!!value} onChange={onChange} label={label} tone="success" />
      ) : f.kind === "select" ? (
        <Select id={id} value={String(value ?? "")} onChange={e => onChange(e.target.value)}>
          {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
      ) : f.kind === "secret" ? (
        <SecretInput id={id} field={f} value={changed ? (value as string) : null} onChange={onChange} />
      ) : (
        <Input
          id={id}
          name={`cfg-${f.name}`}
          autoComplete="off"
          {...NO_AUTOFILL}
          type={f.kind === "int" || f.kind === "float" ? "number" : "text"}
          step={f.kind === "float" ? "any" : undefined}
          min={f.min ?? undefined}
          max={f.max ?? undefined}
          placeholder={f.placeholder || undefined}
          value={value === null || value === undefined ? "" : String(value)}
          onChange={e => onChange(f.kind === "int" || f.kind === "float"
            ? (e.target.value === "" ? "" : Number(e.target.value))
            : e.target.value)}
        />
      )}
      {f.help && <p className="text-xs text-muted-foreground">{f.help}</p>}
    </div>
  );
}

function SecretInput({
  id, field, value, onChange,
}: { id: string; field: ConfigField; value: string | null; onChange: (value: Value) => void }) {
  // value null: sin tocar (se enseña si hay uno puesto, nunca cuál)
  if (value === null) {
    return (
      <div className="flex items-center gap-2">
        <p className="flex-1 rounded-lg border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          {field.is_set ? "•••••••• (puesta)" : "Sin poner"}
        </p>
        <Button size="sm" variant="outline" onClick={() => onChange("")}>{field.is_set ? "Cambiar" : "Poner"}</Button>
      </div>
    );
  }
  return (
    <Input id={id} name={`cfg-${field.name}`} type="password" autoComplete="new-password" {...NO_AUTOFILL}
           placeholder={field.is_set ? "Nueva (vacía para quitarla)" : ""}
           value={value} onChange={e => onChange(e.target.value)} autoFocus />
  );
}
