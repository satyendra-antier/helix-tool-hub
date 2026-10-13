"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Loader2,
  RefreshCw,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Skeleton,
  HorizontalBarChartCard,
  DonutChartCard,
  FunnelBarChartCard,
  RadarChartCard,
  cn,
  getModuleTheme,
} from "@tool-hub/ui";
import { BRAND, JOURNEY, firstPendingStep, type JourneyStep } from "@/lib/journey";

type HubStatus = {
  generatedAt: string;
  dataAsOf?: string | null;
  freshness?: {
    marketAt?: string | null;
    companyDepthAt?: string | null;
    fitVerdictAt?: string | null;
    staleWarning?: string | null;
    fitAgeDays?: number | null;
  };
  kpis: {
    topDomain: { name: string; score: number } | null;
    goVerdicts: { go: number; conditional: number; noGo: number; total: number; asOf?: string | null };
    leadsInPipeline: number;
    proofAssets: { pages: number; chunks: number; capabilities: number; videos: number };
    marketFetchedAt: string | null;
  };
  charts: {
    domainRankings: Array<{ domain: string; score: number }>;
    verdictDistribution: Array<{ name: string; value: number }>;
    leadFunnel: Array<{ stage: string; count: number }>;
    topDomainSignals: Array<{ signal: string; value: number }>;
  };
  flywheel: Record<string, { ready: boolean; route: string; counts?: Record<string, number> }> & {
    reachOut?: ReachOutStatus;
  };
  activity: Array<{ id: string; type: string; label: string; status: string; at?: string }>;
  health: Array<{ slug: string; ok: boolean }>;
};

type ReachOutStatus = {
  ready: boolean;
  route: string;
  online: boolean;
  autopilotEnabled: boolean;
  paused: boolean;
  mailboxes: number;
  sandboxOnly: boolean;
  waitingApproval: number;
  inSequence: number;
  hotLeads: number;
  sentToday: number;
  repliesToday: number;
  unreadReplies: number;
  nextCheck?: string | null;
};

type RunStep = { id: string; label: string; status: string; error?: string };

export function CommandCenter() {
  const [data, setData] = useState<HubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runSteps, setRunSteps] = useState<RunStep[] | null>(null);
  const [runMessage, setRunMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/hub/status");
      if (res.ok) setData(await res.json());
    } catch {
      // Friendly empty state below covers this
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runAll() {
    setRunning(true);
    setRunMessage(null);
    setRunSteps(JOURNEY.map((s) => ({ id: s.id, label: s.name, status: "pending" })));
    try {
      const res = await fetch("/api/hub/pipeline/run", { method: "POST" });
      if (res.status === 403) {
        setRunMessage({ ok: false, text: "Your account can view results but can't start a run. Ask an admin." });
        setRunSteps(null);
        return;
      }
      const { runId } = await res.json();
      if (!runId) throw new Error("no run id");
      for (;;) {
        await new Promise((r) => setTimeout(r, 2000));
        const statusRes = await fetch(`/api/hub/pipeline/run?runId=${runId}`);
        const { run } = await statusRes.json();
        if (run?.steps) setRunSteps(run.steps);
        if (run?.status === "completed") {
          setRunMessage({ ok: true, text: "All steps finished. Your leads are ready and first emails are waiting for your OK in Reach Out." });
          break;
        }
        if (run?.status === "failed" || !run) {
          const failed = (run?.steps as RunStep[] | undefined)?.find((s) => s.status === "error");
          setRunMessage({
            ok: false,
            text: failed
              ? `Stopped at "${failed.label}". ${failed.error || ""} You can open that step and run it by hand.`
              : "The run stopped. Please try again.",
          });
          break;
        }
      }
      await load();
    } catch {
      setRunMessage({ ok: false, text: "Couldn't start the run. Services may still be starting, try again in a minute." });
    } finally {
      setRunning(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full rounded-2xl" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      </div>
    );
  }

  const flywheel = data?.flywheel;
  const next = firstPendingStep(flywheel);
  const doneCount = JOURNEY.filter((s) => flywheel?.[s.statusKey]?.ready).length;
  const pillarCounts = flywheel?.growthPillars?.counts;
  const warmPaths = pillarCounts ? (pillarCounts.intros_pending || 0) + (pillarCounts.partners || 0) : null;

  return (
    <div className="space-y-6 pb-8">
      <section className="ai-gradient ai-glow relative overflow-hidden rounded-2xl p-6 sm:p-8 text-white">
        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-xl">
            <p className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium">
              <Sparkles className="h-3.5 w-3.5" />
              {BRAND.name}
            </p>
            <h1 className="mt-3 text-2xl sm:text-3xl font-semibold tracking-tight">
              Find, reach and win leads with AI in {JOURNEY.length} steps
            </h1>
            <p className="mt-2 text-sm sm:text-base text-white/85">
              Go step by step, or press one button and let AI run them all for you.
              {data ? ` ${doneCount} of ${JOURNEY.length} steps have results.` : ""}
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 shrink-0">
            <Button
              size="lg"
              onClick={runAll}
              disabled={running}
              className="bg-white text-violet-700 hover:bg-white/90"
            >
              {running ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Wand2 className="h-4 w-4 mr-2" />}
              {running ? "AI is working…" : "Run all steps with AI"}
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={load}
              className="border-white/40 bg-transparent text-white hover:bg-white/10"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </div>
        </div>

        {runSteps ? (
          <ol className="relative z-10 mt-6 grid grid-cols-2 lg:grid-cols-5 gap-2">
            {runSteps.map((s, i) => (
              <li
                key={s.id}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-3 py-2 text-sm",
                  s.status === "running" ? "bg-white/25" : "bg-white/10"
                )}
              >
                <RunIcon status={s.status} index={i + 1} />
                <span className="truncate">{JOURNEY[i]?.name ?? s.label}</span>
              </li>
            ))}
          </ol>
        ) : null}
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-white/10 blur-2xl" />
      </section>

      {runMessage ? (
        <Alert variant={runMessage.ok ? "success" : "warning"}>{runMessage.text}</Alert>
      ) : null}

      {!data ? (
        <Alert variant="warning" title="Services are starting up">
          We couldn't load your results yet. Give it a minute, then press Refresh.
        </Alert>
      ) : null}

      {data?.freshness?.staleWarning ? (
        <Alert variant="warning" title="Some steps need attention">
          {data.freshness.staleWarning.replace(/\.+$/, "")}. Press "Run all steps with AI" to bring everything up to date.
        </Alert>
      ) : null}

      {next ? (
        <NextStepCard step={next} />
      ) : data ? (
        <Card className="ai-soft border-primary/20">
          <CardContent className="py-5 flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-success text-white">
              <Check className="h-5 w-5" />
            </span>
            <div>
              <p className="font-semibold">All {JOURNEY.length} steps have results</p>
              <p className="text-sm text-text-secondary">
                Check Reach Out for replies, open Win Leads for your deal coach, or run everything again for fresh data.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {flywheel?.reachOut ? <AutopilotCard s={flywheel.reachOut} /> : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        {JOURNEY.map((step) => (
          <StepCard
            key={step.id}
            step={step}
            done={!!flywheel?.[step.statusKey]?.ready}
            isNext={next?.id === step.id}
          />
        ))}
      </div>

      {data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Kpi
            label="Best market"
            value={data.kpis.topDomain?.name || "—"}
            hint={data.kpis.topDomain ? `Demand score ${data.kpis.topDomain.score.toFixed(0)}/100` : "Run step 1"}
          />
          <Kpi
            label="Markets we can serve"
            value={String(data.kpis.goVerdicts.go)}
            hint={
              data.kpis.goVerdicts.total
                ? `GO out of ${data.kpis.goVerdicts.total} checked · ${data.kpis.goVerdicts.conditional} maybe`
                : "Run step 2"
            }
          />
          <Kpi
            label="Leads found"
            value={String(data.kpis.leadsInPipeline)}
            hint={data.kpis.leadsInPipeline ? "Scored companies" : "Run step 3"}
          />
          {warmPaths != null ? (
            <Kpi
              label="Warm paths"
              value={String(warmPaths)}
              hint={`${pillarCounts?.unread_alerts || 0} new account alerts`}
            />
          ) : (
            <Kpi
              label="Proof ready"
              value={String(data.kpis.proofAssets.capabilities)}
              hint={`${data.kpis.proofAssets.videos} videos in Proof Library`}
            />
          )}
        </div>
      ) : null}

      {data ? (
        <details className="group rounded-xl border border-border bg-surface">
          <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-sm font-medium">
            See the details (charts and recent activity)
            <ChevronDown className="h-4 w-4 text-text-muted transition-transform group-open:rotate-180" />
          </summary>
          <div className="space-y-4 border-t border-border p-5">
            <p className="text-xs text-text-muted">
              Data as of {data.dataAsOf ? new Date(data.dataAsOf).toLocaleString() : "— (nothing run yet)"}
            </p>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <HorizontalBarChartCard
                title="Markets by demand"
                description="Demand score (0–100)"
                data={data.charts.domainRankings}
              />
              <DonutChartCard
                title="Can we deliver?"
                description="GO / maybe (CONDITIONAL) / no (NO_GO)"
                data={data.charts.verdictDistribution.filter((d) => d.value > 0)}
              />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <FunnelBarChartCard
                title="Leads by stage"
                description="Where your leads are right now"
                data={data.charts.leadFunnel.length ? data.charts.leadFunnel : [{ stage: "none", count: 0 }]}
              />
              {data.charts.topDomainSignals.length > 0 ? (
                <RadarChartCard
                  title="Why the best market ranks high"
                  description={data.kpis.topDomain?.name}
                  data={data.charts.topDomainSignals}
                />
              ) : (
                <Card>
                  <CardContent className="py-12 text-center text-sm text-text-secondary">
                    Run step 1 (Find Demand) to see this chart
                  </CardContent>
                </Card>
              )}
            </div>
            <Card>
              <CardContent className="py-4">
                <p className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">Recent activity</p>
                {data.activity.length === 0 ? (
                  <p className="text-sm text-text-secondary">Nothing yet</p>
                ) : (
                  <ul className="divide-y divide-border">
                    {data.activity.map((a) => (
                      <li key={a.id} className="flex items-center justify-between py-2 text-sm">
                        <span className="truncate">{a.label}</span>
                        <span className="text-text-muted capitalize">{a.status}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </details>
      ) : null}
    </div>
  );
}

function RunIcon({ status, index }: { status: string; index: number }) {
  if (status === "done") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white text-violet-700">
        <Check className="h-3 w-3" />
      </span>
    );
  }
  if (status === "running") return <Loader2 className="h-5 w-5 animate-spin" />;
  if (status === "error") {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-red-500">
        <X className="h-3 w-3" />
      </span>
    );
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full border border-white/50 text-[10px]">
      {index}
    </span>
  );
}

function NextStepCard({ step }: { step: JourneyStep }) {
  const theme = getModuleTheme(step.id);
  const Icon = step.icon;
  return (
    <Card className="border-2" style={{ borderColor: theme.accentBorder }}>
      <CardContent className="py-5 flex flex-col sm:flex-row sm:items-center gap-4">
        <span
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-white"
          style={{ backgroundColor: theme.accent }}
        >
          <Icon className="h-6 w-6" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: theme.accent }}>
            Your next step · Step {step.step}
          </p>
          <p className="text-lg font-semibold">{step.name}</p>
          <p className="text-sm text-text-secondary">{step.blurb}</p>
        </div>
        <Button size="lg" asChild>
          <Link href={step.route}>
            {step.action}
            <ArrowRight className="h-4 w-4 ml-1" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function StepCard({ step, done, isNext }: { step: JourneyStep; done: boolean; isNext: boolean }) {
  const theme = getModuleTheme(step.id);
  const Icon = step.icon;
  return (
    <Link
      href={step.route}
      className={cn(
        "group flex flex-col rounded-xl border bg-surface p-5 transition-all hover:-translate-y-0.5 hover:shadow-md",
        isNext ? "border-primary/40 ring-2 ring-primary/20" : "border-border"
      )}
    >
      <div className="flex items-center justify-between">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold text-white"
          style={{ backgroundColor: done ? "var(--success)" : theme.accent }}
        >
          {done ? <Check className="h-4 w-4" /> : step.step}
        </span>
        <Badge variant={done ? "success" : isNext ? "primary" : "muted"}>
          {done ? "Done" : isNext ? "Up next" : "Not started"}
        </Badge>
      </div>
      <div className={`mt-4 flex h-10 w-10 items-center justify-center rounded-lg border ${theme.iconClass}`}>
        <Icon className="h-5 w-5" />
      </div>
      <p className="mt-3 font-semibold">{step.name}</p>
      <p className="mt-1 text-sm text-text-secondary flex-1">{step.blurb}</p>
      <span className="mt-4 inline-flex items-center text-sm font-medium" style={{ color: theme.accent }}>
        {done ? "Open" : step.action}
        <ArrowRight className="h-4 w-4 ml-1 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function AutopilotCard({ s }: { s: ReachOutStatus }) {
  const theme = getModuleTheme("outreach-autopilot");
  const on = s.autopilotEnabled && !s.paused;
  const line = !s.online
    ? "Reach Out service is not running."
    : !s.mailboxes
      ? "Connect a mailbox to start reaching out automatically."
      : !s.autopilotEnabled
        ? "Autopilot is off. Turn it on to send follow-ups and sort replies all day."
        : s.paused
          ? "Paused. Nothing goes out until you resume."
          : `On${s.sandboxOnly ? " (test mode)" : ""}. Next check ${s.nextCheck ? new Date(s.nextCheck).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "soon"}.`;
  return (
    <Card className="border-2" style={{ borderColor: theme.accentBorder }}>
      <CardContent className="py-4 flex flex-col lg:flex-row lg:items-center gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span className={cn("h-3 w-3 rounded-full shrink-0", on ? "bg-success animate-pulse" : s.paused ? "bg-warning" : "bg-border")} />
          <div className="min-w-0">
            <p className="font-semibold">Outreach autopilot</p>
            <p className="text-sm text-text-secondary">{line}</p>
          </div>
        </div>
        <div className="grid grid-cols-4 gap-3 text-center">
          {[
            ["To approve", s.waitingApproval],
            ["Sent today", s.sentToday],
            ["Replies today", s.repliesToday],
            ["Hot leads", s.hotLeads],
          ].map(([label, value]) => (
            <div key={label as string}>
              <p className="text-lg font-semibold">{value}</p>
              <p className="text-[11px] text-text-muted">{label}</p>
            </div>
          ))}
        </div>
        <Button asChild>
          <Link href={s.route}>
            {s.waitingApproval ? `Approve ${s.waitingApproval} email${s.waitingApproval === 1 ? "" : "s"}` : "Open Reach Out"}
            <ArrowRight className="h-4 w-4 ml-1" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs text-text-muted uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-semibold mt-1 truncate">{value}</p>
        <p className="text-sm text-text-secondary">{hint}</p>
      </CardContent>
    </Card>
  );
}
