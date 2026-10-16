import { clsx } from "clsx";
import type { ReactNode } from "react";

const VARIANTS = {
  neutral: "bg-muted text-muted-foreground",
  outline: "border border-border text-foreground",
  destructive: "bg-destructive/10 text-destructive",
  blue: "bg-status-blue/10 text-status-blue",
  violet: "bg-status-violet/10 text-status-violet",
  amber: "bg-status-amber/10 text-status-amber",
} as const;

export type BadgeVariant = keyof typeof VARIANTS;

// Stable per-source-system assignment so the same vendor always reads the
// same color everywhere it appears (result rows, detail chips, the graph
// legend) — an arbitrary but fixed mapping onto the three status hues plus
// neutral/outline, not a semantic meaning owned by any one hue.
const SOURCE_SYSTEM_VARIANT: Record<string, BadgeVariant> = {
  azure_devops: "blue",
  github: "violet",
  jira: "amber",
  confluence: "outline",
  teams: "blue",
};

export function sourceSystemBadgeVariant(sourceSystem: string | null | undefined): BadgeVariant {
  if (!sourceSystem) return "neutral";
  return SOURCE_SYSTEM_VARIANT[sourceSystem] ?? "neutral";
}

export function Badge({
  children,
  variant = "neutral",
  className,
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium leading-none",
        VARIANTS[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
