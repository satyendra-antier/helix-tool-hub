import * as React from "react";
import { cn } from "../lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between mb-8", className)}>
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{title}</h1>
        {description && (
          <p className="text-sm text-text-secondary max-w-2xl leading-relaxed">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
