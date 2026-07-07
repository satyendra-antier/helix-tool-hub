import { Badge } from "@tool-hub/ui";
import { getModuleTheme } from "@tool-hub/ui";

export function ModulePageHeader({
  title,
  description,
  moduleId,
  category,
}: {
  title: string;
  description?: string;
  moduleId: string;
  category?: string;
}) {
  const theme = getModuleTheme(moduleId);

  return (
    <div className="mb-8">
      <div
        className={`h-1 w-full rounded-full bg-gradient-to-r ${theme.gradient} mb-6`}
        aria-hidden
      />
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={theme.badgeVariant}>{theme.label}</Badge>
            {category && (
              <span className="text-xs text-text-muted capitalize">{category}</span>
            )}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{title}</h1>
          {description && (
            <p className="text-sm text-text-secondary max-w-2xl leading-relaxed">{description}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function ModuleAccentShell({
  moduleId,
  children,
}: {
  moduleId: string;
  children: React.ReactNode;
}) {
  const theme = getModuleTheme(moduleId);
  return (
    <div
      data-module={moduleId}
      style={
        {
          "--primary": theme.accent,
          "--primary-hover": theme.accentHover,
          "--module-accent": theme.accent,
          "--module-accent-muted": theme.accentMuted,
          "--module-accent-border": theme.accentBorder,
        } as React.CSSProperties
      }
      className="module-accent-scope"
    >
      {children}
    </div>
  );
}
