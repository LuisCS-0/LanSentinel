import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info";
  // Punto de color delante del texto
  dot?: boolean;
}

const VARIANTS = {
  default: "bg-primary/15 text-primary ring-primary/25",
  secondary: "bg-secondary text-secondary-foreground ring-border",
  destructive: "bg-destructive/15 text-destructive ring-destructive/30",
  outline: "text-muted-foreground ring-border",
  success: "bg-success/15 text-success ring-success/30",
  warning: "bg-warning/15 text-warning ring-warning/30",
  info: "bg-info/15 text-info ring-info/30",
};

function Badge({ className, variant = "default", dot, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        "[&_svg]:size-3 [&_svg]:shrink-0",
        VARIANTS[variant],
        className,
      )}
      {...props}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export { Badge };
