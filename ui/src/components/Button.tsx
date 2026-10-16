import { clsx } from "clsx";
import type { ButtonHTMLAttributes } from "react";

const VARIANTS = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/90",
  outline:
    "border border-input bg-background text-foreground hover:bg-accent hover:text-accent-foreground",
  ghost: "text-foreground hover:bg-accent hover:text-accent-foreground",
} as const;

const SIZES = {
  sm: "h-7 px-2.5 text-xs",
  default: "h-9 px-3.5 text-sm",
} as const;

type ButtonVariant = keyof typeof VARIANTS;

export function Button({
  variant = "outline",
  size = "default",
  active = false,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: keyof typeof SIZES;
  /** Segmented-control / toggle look (layout picker, color-by switch, nav
   * item) — overrides the chosen variant's resting state with the pressed
   * one, independent of hover. */
  active?: boolean;
}) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:pointer-events-none disabled:opacity-50",
        active ? "bg-secondary text-secondary-foreground" : VARIANTS[variant],
        SIZES[size],
        className
      )}
      {...props}
    />
  );
}
