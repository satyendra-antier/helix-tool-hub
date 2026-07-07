"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Play,
  RefreshCw,
  Workflow,
} from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  PageHeader,
  StatusDot,
  Skeleton,
  HorizontalBarChartCard,
  DonutChartCard,
  FunnelBarChartCard,
  RadarChartCard,
  EmptyState,
} from "@tool-hub/ui";

type HubStatus = {
  generatedAt: string;
  kpis: {
    topDomain: { name: string; score: number } | null;
    goVerdicts: { go: number; conditional: number; noGo: number; total: number };
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
  flywheel: Record<string, { ready: boolean; route: string }>;
  activity: Array<{ id: string; type: string; label: string; status: string; at?: string }>;
  health: Array<{ slug: string; ok: boolean }>;
};

export function CommandCenter() {
  const [data, setData] = useState<HubStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/hub/status");
      if (res.ok) setData(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runFlywheel() {
    setRunning(true);
    try {
      const res = await fetch("/api/hub/pipeline/run", { method: "POST" });
      const { runId } = await res.json();
      if (!runId) return;
      let done = false;
      while (!done) {
        await new Promise((r) => setTimeout(r, 2000));
        const statusRes = await fetch(`/api/hub/pipeline/run?runId=${runId}`);
        const { run } = await statusRes.json();
        if (run?.status === "completed" || run?.status === "failed") {
          done = true;
        }
      }
      await load();
    } finally {
      setRunning(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!data) {
    return <EmptyState title="Unable to load command center" description="Check that module APIs are running." />;
  }

  const flywheelSteps = [
    { key: "marketDepth", label: "Market Depth" },
    { key: "buildReadiness", label: "Build Readiness" },
    { key: "leadIntelligence", label: "Lead Intelligence" },
    { key: "videoScraper", label: "Video Scraper" },
  ];

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        title="Command Center"
        description="Live revenue intelligence across market demand, capability proof, and qualified pipeline."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="h-4 w-4 mr-1" />
              Refresh
            </Button>
            <Button size="sm" onClick={runFlywheel} disabled={running}>
              <Play className="h-4 w-4 mr-1" />
              {running ? "Running flywheel…" : "Run flywheel"}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href="/studio">
                <Workflow className="h-4 w-4 mr-1" />
                Pipeline Studio
              </Link>
            </Button>
          </div>
        }
      />

      <p className="text-xs text-text-muted">
        Last updated {new Date(data.generatedAt).toLocaleString()}
        {data.kpis.marketFetchedAt ? ` · Market data ${new Date(data.kpis.marketFetchedAt).toLocaleDateString()}` : ""}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-text-muted uppercase tracking-wide">Top domain</p>
            <p className="text-2xl font-semibold mt-1">{data.kpis.topDomain?.name || "—"}</p>
            <p className="text-sm text-text-secondary">{data.kpis.topDomain ? `${data.kpis.topDomain.score.toFixed(1)} score` : "Run market refresh"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-text-muted uppercase tracking-wide">GO verdicts</p>
            <p className="text-2xl font-semibold mt-1">{data.kpis.goVerdicts.go}</p>
            <p className="text-sm text-text-secondary">of {data.kpis.goVerdicts.total || 12} domains analyzed</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-text-muted uppercase tracking-wide">Pipeline leads</p>
            <p className="text-2xl font-semibold mt-1">{data.kpis.leadsInPipeline}</p>
            <p className="text-sm text-text-secondary">scored entities</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-5">
            <p className="text-xs text-text-muted uppercase tracking-wide">Proof assets</p>
            <p className="text-2xl font-semibold mt-1">{data.kpis.proofAssets.capabilities}</p>
            <p className="text-sm text-text-secondary">{data.kpis.proofAssets.pages} pages · {data.kpis.proofAssets.videos} videos</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="py-4">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">Revenue flywheel</p>
          <div className="flex flex-wrap gap-4">
            {flywheelSteps.map((step) => {
              const fw = data.flywheel[step.key];
              return (
                <Link
                  key={step.key}
                  href={fw?.route || "/dashboard"}
                  className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 hover:bg-surface-muted transition-colors"
                >
                  <StatusDot variant={fw?.ready ? "success" : "warning"} />
                  <span className="text-sm font-medium">{step.label}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-text-muted" />
                </Link>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <HorizontalBarChartCard
          title="Domain rankings"
          description="Composite demand scores (0–100)"
          data={data.charts.domainRankings}
        />
        <DonutChartCard
          title="Verdict distribution"
          description="GO / CONDITIONAL / NO_GO across analyzed domains"
          data={data.charts.verdictDistribution.filter((d) => d.value > 0)}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <FunnelBarChartCard
          title="Lead pipeline"
          description="Entities by stage"
          data={data.charts.leadFunnel.length ? data.charts.leadFunnel : [{ stage: "none", count: 0 }]}
        />
        {data.charts.topDomainSignals.length > 0 ? (
          <RadarChartCard
            title="Top domain signals"
            description={data.kpis.topDomain?.name}
            data={data.charts.topDomainSignals}
          />
        ) : (
          <Card>
            <CardContent className="py-12 text-center text-sm text-text-secondary">
              Refresh market depth to see signal breakdown
            </CardContent>
          </Card>
        )}
      </div>

      <Card>
        <CardContent className="py-4">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wide mb-3">Recent activity</p>
          {data.activity.length === 0 ? (
            <p className="text-sm text-text-secondary">No recent jobs</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.activity.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2 text-sm">
                  <span>{a.label}</span>
                  <span className="text-text-muted capitalize">{a.status}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
