import * as React from "react";
import { AlertCircle, CheckCircle2, Info, AlertTriangle } from "lucide-react";
import { cn } from "../lib/utils";

export type AlertVariant = "default" | "success" | "warning" | "danger";

const styles: Record<AlertVariant, string> = {
  default: "border-border bg-surface-muted text-text-primary",
  success: "border-success/30 bg-success/5 text-success",
  warning: "border-warning/30 bg-warning/5 text-warning",
  danger: "border-danger/30 bg-danger/5 text-danger",
};

const icons: Record<AlertVariant, React.ReactNode> = {
  default: <Info className="h-4 w-4 shrink-0" />,
  success: <CheckCircle2 className="h-4 w-4 shrink-0" />,
  warning: <AlertTriangle className="h-4 w-4 shrink-0" />,
  danger: <AlertCircle className="h-4 w-4 shrink-0" />,
};

export function Alert({
  className,
  variant = "default",
  title,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  variant?: AlertVariant;
  title?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "relative flex gap-3 rounded-lg border p-4 text-sm",
        styles[variant],
        className
      )}
      {...props}
    >
      {icons[variant]}
      <div className="flex-1 space-y-1">
        {title && <p className="font-medium leading-none">{title}</p>}
        {children && <div className="text-text-secondary [&_p]:leading-relaxed">{children}</div>}
      </div>
    </div>
  );
}
