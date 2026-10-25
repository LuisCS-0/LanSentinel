import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  // Icono dentro del campo, a la izquierda (p. ej. la lupa del buscador)
  icon?: LucideIcon;
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, icon: Icon, ...props }, ref) => {
    const input = (
      <input
        type={type}
        ref={ref}
        className={cn(
          "flex h-10 w-full rounded-lg border border-input bg-surface px-3 py-2 text-sm",
          "placeholder:text-muted-foreground/70 transition-colors",
          "focus-visible:outline-none focus-visible:border-primary/60 focus-visible:ring-2 focus-visible:ring-primary/20",
          "disabled:cursor-not-allowed disabled:opacity-50",
          Icon && "pl-9",
          className,
        )}
        {...props}
      />
    );
    if (!Icon) return input;
    return (
      <div className="relative w-full">
        <Icon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        {input}
      </div>
    );
  },
);
Input.displayName = "Input";

export { Input };
