import { cn } from "../lib/utils";

export type StatusDotVariant = "success" | "warning" | "danger" | "muted";

const colors: Record<StatusDotVariant, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-text-muted",
};

export function StatusDot({
  variant = "muted",
  className,
  label,
}: {
  variant?: StatusDotVariant;
  className?: string;
  label?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className={cn("h-2 w-2 rounded-full", colors[variant])} aria-hidden />
      {label && <span className="text-xs text-text-secondary">{label}</span>}
    </span>
  );
}
