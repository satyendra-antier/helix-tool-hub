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
  Card,
  CardContent,
} from "@tool-hub/ui";

type OutreachReport = {
  totals: Record<string, number>;
  by_step: { step: number; sent: number; replies: number; positive: number; reply_rate: number }[];
  by_subject: { subject: string; sent: number; replies: number; reply_rate: number }[];
  reply_types: Record<string, number>;
  daily: { date: string; sent: number; replies: number }[];
  learnings: string[];
};

const REPLY_LABELS: Record<string, string> = {
  interested: "Interested",
  question: "Question",
  not_now: "Not now",
  not_interested: "Not interested",
  unsubscribe: "Unsubscribe",
  out_of_office: "Out of office",
  referral: "Referral",
};

export default function AnalyticsPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchHub>> | null>(null);
  const [outreach, setOutreach] = useState<OutreachReport | null>(null);
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
    fetch("/api/modules/outreach-autopilot/reports/summary?days=30")
      .then((r) => (r.ok ? r.json() : null))
      .then(setOutreach)
      .catch(() => {});
  }, []);

  if (loading) return <Skeleton className="h-96" />;
  if (!data) return <EmptyState title="Reports unavailable" description="Start module services and refresh." />;

  const history = data.charts.domainRankings.map((d: { domain: string; score: number }, i: number) => ({
    label: d.domain.slice(0, 12),
    value: d.score,
    rank: i + 1,
  }));

  const pct = (n?: number) => `${Math.round((n || 0) * 100)}%`;

  return (
    <div className="space-y-6 pb-8">
      <PageHeader
        title="Reports"
        description="Deeper drill-down across market demand, verdicts, pipeline and outreach results."
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

      {outreach ? (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-text-primary">Outreach results (last 30 days)</h2>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {[
              ["Emails sent", outreach.totals.emails_sent],
              ["People replied", `${outreach.totals.people_replied} (${pct(outreach.totals.reply_rate)})`],
              ["Interested", outreach.totals.interested],
              ["Bounced", outreach.totals.bounced],
              ["AI calls", outreach.totals.calls],
            ].map(([label, value]) => (
              <Card key={label as string}>
                <CardContent className="pt-5">
                  <p className="text-xs text-text-muted uppercase tracking-wide">{label}</p>
                  <p className="text-2xl font-semibold mt-1">{value}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <LineTrendChartCard
              title="Emails sent per day"
              description="From all connected mailboxes"
              data={outreach.daily.length ? outreach.daily.map((d) => ({ label: d.date.slice(5), value: d.sent })) : [{ label: "—", value: 0 }]}
              nameKey="label"
            />
            <DonutChartCard
              title="Reply types"
              description={
                Object.entries(outreach.reply_types)
                  .map(([k, v]) => `${REPLY_LABELS[k] || k} ${v}`)
                  .join(" · ") || undefined
              }
              data={
                Object.keys(outreach.reply_types).length
                  ? Object.entries(outreach.reply_types).map(([k, v]) => ({ name: REPLY_LABELS[k] || k, value: v }))
                  : [{ name: "No replies yet", value: 1 }]
              }
            />
            <Card>
              <CardContent className="pt-5">
                <p className="font-semibold mb-3">Which email gets replies</p>
                <table className="w-full text-sm">
                  <thead className="text-text-muted text-xs">
                    <tr><th className="text-left">Email</th><th>Sent</th><th>Replies</th><th>Rate</th></tr>
                  </thead>
                  <tbody>
                    {outreach.by_step.map((s) => (
                      <tr key={s.step} className="border-t border-border text-center">
                        <td className="text-left py-1.5">Email {s.step}</td><td>{s.sent}</td><td>{s.replies}</td><td>{pct(s.reply_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-5 space-y-2">
                <p className="font-semibold">What the AI writer learned</p>
                {outreach.learnings.length ? (
                  outreach.learnings.map((l) => <p key={l} className="text-sm text-text-secondary">• {l}</p>)
                ) : (
                  <p className="text-sm text-text-secondary">
                    Not enough results yet. After a few dozen emails, the best subject lines and styles show here and are fed back into the writer.
                  </p>
                )}
                {outreach.by_subject.slice(0, 5).map((s) => (
                  <p key={s.subject} className="text-xs text-text-muted truncate">
                    “{s.subject}” · {s.sent} sent · {pct(s.reply_rate)} replied
                  </p>
                ))}
              </CardContent>
            </Card>
          </div>
        </section>
      ) : null}
    </div>
  );
}
