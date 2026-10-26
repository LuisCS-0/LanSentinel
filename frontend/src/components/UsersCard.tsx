// Usuarios del panel (solo administradores): alta con rol, cambio de rol,
// activar o desactivar, poner contraseña y borrar. El backend impide dejar el
// sistema sin ningún administrador activo.

import { useState, type ReactNode } from "react";
import {
  AlertCircle, Eye, KeyRound, Loader2, MoreHorizontal, Power, ShieldCheck, Trash2, UserPlus, Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeaderRow } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Menu, MenuItem, MenuSeparator } from "@/components/ui/menu";
import { Select, Skeleton } from "@/components/ui/misc";
import { ROLE_LABEL, useCurrentUser } from "@/hooks/useAuth";
import { useCreateUser, useDeleteUser, useSetUserPassword, useUpdateUser, useUsers } from "@/hooks/useUsers";
import { extractErrorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/dates";
import { toast } from "@/lib/toast";
import { cn } from "@/lib/utils";
import type { UserAccount, UserRole } from "@/lib/types";

const MIN_LENGTH = 10;

export function UsersCard() {
  const users = useUsers();
  const me = useCurrentUser();
  const update = useUpdateUser();
  const [creating, setCreating] = useState(false);
  const [passwordFor, setPasswordFor] = useState<UserAccount | null>(null);
  const [toDelete, setToDelete] = useState<UserAccount | null>(null);

  const change = async (user: UserAccount, changes: { role?: UserRole; is_active?: boolean }, done: string) => {
    try {
      await update.mutateAsync({ id: user.id, ...changes });
      toast({ title: done, description: user.username });
    } catch (err) {
      toast({ title: "No se pudo cambiar", description: extractErrorMessage(err), severity: "medium" });
    }
  };

  return (
    // relative z-10: el menú de cada usuario tiene que quedar por encima de
    // la tarjeta siguiente (backdrop-blur crea un contexto de apilamiento)
    <Card className="relative z-10">
      <CardHeaderRow
        title={<><Users />Usuarios</>}
        description="Los de solo lectura ven todo el panel, pero no pueden cambiar nada ni ver el historial de dominios ni descargar copias."
        actions={<Button size="sm" onClick={() => setCreating(true)}><UserPlus />Añadir</Button>}
      />
      <CardContent className="p-0">
        {users.isLoading ? <div className="p-5"><Skeleton className="h-24" /></div> : (
          <ul className="divide-y border-t">
            {(users.data ?? []).map(u => {
              const isMe = u.username === me.data?.username;
              return (
                <li key={u.id} className={cn("flex items-center gap-3 px-5 py-3", !u.is_active && "opacity-60")}>
                  <span className={cn(
                    "flex size-9 shrink-0 items-center justify-center rounded-lg text-sm font-semibold uppercase",
                    u.role === "admin" ? "bg-brand text-white" : "bg-muted text-muted-foreground",
                  )}>
                    {u.username[0]}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      <span className="truncate">{u.username}</span>
                      {isMe && <Badge variant="outline">tú</Badge>}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-muted-foreground">
                      <Badge variant={u.role === "admin" ? "info" : "secondary"}>{ROLE_LABEL[u.role]}</Badge>
                      {!u.is_active && <Badge variant="outline">Desactivado</Badge>}
                      <span>{u.last_login_at ? `Último acceso ${relativeTime(u.last_login_at)}` : "Nunca ha entrado"}</span>
                    </div>
                  </div>
                  <div className="shrink-0">
                    {!isMe && (
                      <Menu trigger={() => (
                        <Button variant="ghost" size="icon-sm" aria-label={`Acciones de ${u.username}`}><MoreHorizontal /></Button>
                      )}>
                        {u.role === "admin" ? (
                          <MenuItem icon={<Eye />} onClick={() => change(u, { role: "viewer" }, "Ahora es de solo lectura")}>Pasar a solo lectura</MenuItem>
                        ) : (
                          <MenuItem icon={<ShieldCheck />} onClick={() => change(u, { role: "admin" }, "Ahora es administrador")}>Hacer administrador</MenuItem>
                        )}
                        <MenuItem icon={<Power />} onClick={() => change(u, { is_active: !u.is_active }, u.is_active ? "Usuario desactivado" : "Usuario activado")}>
                          {u.is_active ? "Desactivar" : "Activar"}
                        </MenuItem>
                        <MenuItem icon={<KeyRound />} onClick={() => setPasswordFor(u)}>Poner contraseña…</MenuItem>
                        <MenuSeparator />
                        <MenuItem icon={<Trash2 />} danger onClick={() => setToDelete(u)}>Borrar…</MenuItem>
                      </Menu>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
      <CreateUserDialog open={creating} onClose={() => setCreating(false)} />
      <SetPasswordDialog user={passwordFor} onClose={() => setPasswordFor(null)} />
      <DeleteUserDialog user={toDelete} onClose={() => setToDelete(null)} />
    </Card>
  );
}

// ─── Diálogos ────────────────────────────────────────────────────────────────

function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateUser();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setUsername(""); setPassword(""); setRole("viewer"); setError(null);
    create.reset();
    onClose();
  };

  const submit = async () => {
    setError(null);
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(username)) {
      setError("El nombre solo puede llevar letras sin tilde, números, punto, guion y guion bajo");
      return;
    }
    if (password.length < MIN_LENGTH) {
      setError(`La contraseña debe tener al menos ${MIN_LENGTH} caracteres`);
      return;
    }
    try {
      await create.mutateAsync({ username, password, role });
      toast({ title: "Usuario creado", description: `${username} · ${ROLE_LABEL[role]}` });
      close();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Añadir usuario"
      description="Dale la contraseña por un canal seguro; podrá cambiarla desde su cuenta."
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><UserPlus className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={create.isPending}>Cancelar</Button>
          <Button onClick={submit} disabled={create.isPending || !username || !password}>
            {create.isPending && <Loader2 className="animate-spin" />}Crear
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={e => { e.preventDefault(); submit(); }}>
        <Field label="Nombre de usuario">
          <Input value={username} onChange={e => setUsername(e.target.value.trim())} autoComplete="off" autoFocus />
        </Field>
        <Field label="Contraseña" hint={`Al menos ${MIN_LENGTH} caracteres`}>
          <Input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" />
        </Field>
        <Field label="Rol">
          <Select value={role} onChange={e => setRole(e.target.value as UserRole)} className="w-full">
            <option value="viewer">Solo lectura: lo ve todo, no cambia nada</option>
            <option value="admin">Administrador: puede cambiarlo todo</option>
          </Select>
        </Field>
        <ErrorBox error={error} />
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  );
}

function SetPasswordDialog({ user, onClose }: { user: UserAccount | null; onClose: () => void }) {
  const setPassword = useSetUserPassword();
  const [password, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setValue(""); setError(null);
    setPassword.reset();
    onClose();
  };

  const submit = async () => {
    if (!user) return;
    if (password.length < MIN_LENGTH) {
      setError(`La contraseña debe tener al menos ${MIN_LENGTH} caracteres`);
      return;
    }
    try {
      await setPassword.mutateAsync({ id: user.id, new_password: password });
      toast({ title: "Contraseña cambiada", description: `${user.username}: sus sesiones abiertas se han cerrado` });
      close();
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  };

  return (
    <Dialog
      open={user !== null}
      onClose={close}
      title={`Poner contraseña a ${user?.username ?? ""}`}
      description="Se cerrarán todas sus sesiones abiertas."
      icon={<div className="rounded-lg bg-primary/15 p-2 text-primary"><KeyRound className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={setPassword.isPending}>Cancelar</Button>
          <Button onClick={submit} disabled={setPassword.isPending || !password}>
            {setPassword.isPending && <Loader2 className="animate-spin" />}Cambiar
          </Button>
        </>
      }
    >
      <form className="space-y-4" onSubmit={e => { e.preventDefault(); submit(); }}>
        <Field label="Nueva contraseña" hint={`Al menos ${MIN_LENGTH} caracteres`}>
          <Input type="password" value={password} onChange={e => setValue(e.target.value)} autoComplete="new-password" autoFocus />
        </Field>
        <ErrorBox error={error} />
        <button type="submit" className="hidden" />
      </form>
    </Dialog>
  );
}

function DeleteUserDialog({ user, onClose }: { user: UserAccount | null; onClose: () => void }) {
  const remove = useDeleteUser();

  const close = () => {
    remove.reset();
    onClose();
  };

  const confirm = async () => {
    if (!user) return;
    try {
      await remove.mutateAsync(user.id);
      toast({ title: "Usuario borrado", description: user.username });
      close();
    } catch {
      // El error se muestra en el diálogo
    }
  };

  return (
    <Dialog
      open={user !== null}
      onClose={close}
      title={`Borrar a ${user?.username ?? ""}`}
      description="No podrá volver a entrar. Lo que hizo sigue en el registro de acciones. Si solo quieres cortarle el acceso un tiempo, desactívalo."
      icon={<div className="rounded-lg bg-destructive/15 p-2 text-destructive"><Trash2 className="size-4" /></div>}
      footer={
        <>
          <Button variant="outline" onClick={close} disabled={remove.isPending}>Cancelar</Button>
          <Button variant="destructive" onClick={confirm} disabled={remove.isPending}>
            {remove.isPending && <Loader2 className="animate-spin" />}Borrar
          </Button>
        </>
      }
    >
      <ErrorBox error={remove.isError ? extractErrorMessage(remove.error) : null} />
    </Dialog>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between text-sm font-medium">
        {label}
        {hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p className="flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />{error}
    </p>
  );
}
