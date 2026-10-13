import Link from "next/link";
import { ArrowLeft, ArrowRight, Home, Puzzle } from "lucide-react";
import { Badge, Button, cn, getModuleTheme } from "@tool-hub/ui";
import { JOURNEY, getExtra, getStep, nextStep, prevStep } from "@/lib/journey";

export function ModulePageHeader({
  title,
  description,
  moduleId,
}: {
  title: string;
  description?: string;
  moduleId: string;
  category?: string;
}) {
  const theme = getModuleTheme(moduleId);
  const step = getStep(moduleId);
  const extra = getExtra(moduleId);
  const Icon = step?.icon ?? extra?.icon ?? Puzzle;

  return (
    <div className="mb-8">
      {step ? (
        <ol className="mb-6 flex items-center gap-2" aria-label="Progress">
          {JOURNEY.map((s) => (
            <li key={s.id} className="flex flex-1 items-center gap-2">
              <Link
                href={s.route}
                title={`Step ${s.step}: ${s.name}`}
                className={cn(
                  "h-1.5 w-full rounded-full transition-colors",
                  s.step <= step.step ? "" : "bg-surface-muted"
                )}
                style={s.step <= step.step ? { backgroundColor: getModuleTheme(s.id).accent } : undefined}
              />
            </li>
          ))}
        </ol>
      ) : (
        <div className={`h-1 w-full rounded-full bg-gradient-to-r ${theme.gradient} mb-6`} aria-hidden />
      )}
      <div className="flex items-start gap-4">
        <span className="ai-gradient ai-glow flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white">
          <Icon className="h-6 w-6" />
        </span>
        <div className="space-y-1.5 min-w-0">
          <Badge variant={theme.badgeVariant}>
            {step ? `Step ${step.step} of ${JOURNEY.length}` : "Extra tool"}
          </Badge>
          <h1 className="text-2xl font-semibold tracking-tight text-text-primary">{step?.name ?? title}</h1>
          {(step?.blurb || description) && (
            <p className="text-sm text-text-secondary max-w-2xl leading-relaxed">{description || step?.blurb}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function ModuleStepFooter({ moduleId }: { moduleId: string }) {
  const step = getStep(moduleId);
  const prev = prevStep(moduleId);
  const next = nextStep(moduleId);

  return (
    <div className="mt-10 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border pt-6">
      {prev ? (
        <Button variant="outline" asChild>
          <Link href={prev.route}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back: {prev.name}
          </Link>
        </Button>
      ) : (
        <Button variant="outline" asChild>
          <Link href="/dashboard">
            <Home className="h-4 w-4 mr-1" />
            Back to Home
          </Link>
        </Button>
      )}
      {next ? (
        <Button asChild>
          <Link href={next.route}>
            Next: Step {next.step} · {next.name}
            <ArrowRight className="h-4 w-4 ml-1" />
          </Link>
        </Button>
      ) : step ? (
        <Button asChild>
          <Link href="/dashboard">
            <Home className="h-4 w-4 mr-1" />
            All done · Back to Home
          </Link>
        </Button>
      ) : null}
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
