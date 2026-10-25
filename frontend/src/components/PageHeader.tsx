// Cabecera de página y tarjeta de indicador (KPI), comunes a todas las vistas.

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageHeader({
  title, description, actions,
}: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES = {
  primary: "bg-primary/10 text-primary ring-primary/20",
  success: "bg-success/10 text-success ring-success/20",
  warning: "bg-warning/10 text-warning ring-warning/20",
  destructive: "bg-destructive/10 text-destructive ring-destructive/20",
  info: "bg-info/10 text-info ring-info/20",
  upload: "bg-upload/10 text-upload ring-upload/20",
  muted: "bg-muted text-muted-foreground ring-border",
};

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon: LucideIcon;
  hint?: ReactNode;
  tone?: keyof typeof TONES;
  to?: string;               // si se indica, la tarjeta lleva a esa página
  onClick?: () => void;
  children?: ReactNode;      // contenido extra debajo (p. ej. una mini gráfica)
  className?: string;
}

export function StatCard({ label, value, icon: Icon, hint, tone = "primary", to, onClick, children, className }: StatCardProps) {
  const interactive = Boolean(to || onClick);
  const body = (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground sm:text-xs">{label}</p>
          <p className="tabular mt-2 whitespace-nowrap text-xl font-semibold tracking-tight sm:text-2xl xl:text-3xl">{value}</p>
        </div>
        <div className={cn("shrink-0 rounded-xl p-2 ring-1 ring-inset sm:p-2.5", TONES[tone])}>
          <Icon className="size-4 sm:size-5" />
        </div>
      </div>
      {hint && <div className="mt-1.5 text-xs text-muted-foreground">{hint}</div>}
      {children}
      {interactive && (
        <ArrowUpRight className="absolute bottom-3 right-3 size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      )}
    </>
  );
  const classes = cn(
    "group relative block overflow-hidden rounded-xl border bg-card/80 p-4 text-left shadow-card backdrop-blur-sm sm:p-5",
    interactive && "transition-all hover:-translate-y-0.5 hover:border-primary/40",
    className,
  );
  if (to) return <Link to={to} className={classes}>{body}</Link>;
  if (onClick) return <button onClick={onClick} className={cn(classes, "w-full")}>{body}</button>;
  return <div className={classes}>{body}</div>;
}
