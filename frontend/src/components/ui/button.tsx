import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "soft" | "success";
  size?: "default" | "sm" | "xs" | "lg" | "icon" | "icon-sm";
}

const VARIANTS = {
  default: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 hover:shadow-glow",
  destructive: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
  outline: "border border-input bg-card/50 hover:bg-accent hover:text-accent-foreground",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  ghost: "hover:bg-accent hover:text-accent-foreground",
  soft: "bg-primary/10 text-primary hover:bg-primary/20",
  success: "bg-success/15 text-success hover:bg-success/25",
};

const SIZES = {
  default: "h-10 px-4 gap-2",
  sm: "h-9 px-3 gap-2",
  xs: "h-7 px-2.5 gap-1.5 text-xs",
  lg: "h-11 px-6 gap-2 text-base",
  icon: "h-10 w-10",
  "icon-sm": "h-8 w-8",
};

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium",
        "transition-all duration-150 active:scale-[0.98]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button };
