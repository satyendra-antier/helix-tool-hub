"use client";

import { useEffect, useState } from "react";
import {
  PageHeader,
  HorizontalBarChartCard,
  DonutChartCard,
  FunnelBarChartCard,
  LineTrendChartCard,
  Skeleton,
  EmptyState,
  Button,
} from "@tool-hub/ui";

export default function AnalyticsPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchHub>> | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchHub() {
    const res = await fetch("/api/hub/status");
    if (!res.ok) return null;
    return res.json();
  }

  useEffect(() => {
    fetchHub().then((d) => {
      setData(d);
      setLoading(false);
    });
  }, []);

  if (loading) return <Skeleton className="h-96" />;
  if (!data) return <EmptyState title="Analytics unavailable" description="Start module services and refresh." />;

  const history = data.charts.domainRankings.map((d: { domain: string; score: number }, i: number) => ({
    label: d.domain.slice(0, 12),
    value: d.score,
    rank: i + 1,
  }));

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        title="Analytics"
        description="Deeper drill-down across market demand, verdicts, and pipeline velocity."
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href="/api/modules/lead-intelligence/export/csv" download>
              Export leads CSV
            </a>
          </Button>
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <HorizontalBarChartCard title="Domain demand rankings" data={data.charts.domainRankings} />
        <DonutChartCard title="Verdict mix" data={data.charts.verdictDistribution.filter((d: { value: number }) => d.value > 0)} />
        <FunnelBarChartCard title="Lead stages" data={data.charts.leadFunnel.length ? data.charts.leadFunnel : [{ stage: "empty", count: 0 }]} />
        <LineTrendChartCard title="Domain score index" description="Current snapshot ranking" data={history} nameKey="label" />
      </div>
    </div>
  );
}
