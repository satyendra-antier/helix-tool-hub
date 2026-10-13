"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  chartColors,
  useToast,
} from "@tool-hub/ui";
import { errorMessage, fmtDate, useApi } from "../api";

type Query = { id: string; query: string; domain?: string };
type Check = {
  id: string;
  query_id: string;
  query: string;
  provider: string;
  mentioned: boolean;
  rank?: number | null;
  competitors: string[];
  citations: string[];
  answer_excerpt?: string;
  checked_at: string;
};
type Summary = {
  company: string;
  providers: string[];
  share: number | null;
  avg_rank: number | null;
  by_provider: Record<string, { checks: number; mentioned: number }>;
  top_competitors: { name: string; mentions: number }[];
  latest: Check[];
};
type TrendPoint = { date: string; provider: string; share: number };
type Recommendation = { title: string; why: string; target_queries?: string[]; format?: string };

const PROVIDER_COLORS: Record<string, string> = { openai: chartColors.primary, perplexity: chartColors.success };

export default function VisibilityTab({ onChange }: { onChange: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [queries, setQueries] = useState<Query[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [newQuery, setNewQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [q, s, t] = await Promise.all([
        api.get<{ queries: Query[] }>("/visibility/queries"),
        api.get<Summary>("/visibility/summary"),
        api.get<{ points: TrendPoint[] }>("/visibility/trend"),
      ]);
      setQueries(q.queries);
      setSummary(s);
      setTrend(t.points);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const chartData = useMemo(() => {
    const byDate: Record<string, Record<string, number | string>> = {};
    for (const p of trend) {
      byDate[p.date] = { ...(byDate[p.date] || { date: p.date }), [p.provider]: Math.round(p.share * 100) };
    }
    return Object.values(byDate);
  }, [trend]);
  const trendProviders = useMemo(() => Array.from(new Set(trend.map((p) => p.provider))), [trend]);

  const addQuery = async () => {
    if (!newQuery.trim()) return;
    await api.post("/visibility/queries", { query: newQuery.trim() });
    setNewQuery("");
    load();
    onChange();
  };

  const suggest = async () => {
    setBusy("suggest");
    try {
      const r = await api.post<{ added: string[] }>("/visibility/queries/suggest", { per_domain: 2 });
      toast(r.added.length ? `Added ${r.added.length} queries` : "No new queries. Do you have market domains yet?", r.added.length ? "success" : "default");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const removeQuery = async (id: string) => {
    await api.del(`/visibility/queries/${id}`);
    load();
    onChange();
  };

  const runCheck = async () => {
    setBusy("check");
    try {
      const { job_id } = await api.post<{ job_id: string }>("/visibility/check");
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Check failed");
      else if (job.result.note) toast(String(job.result.note));
      else toast(`Mentioned in ${job.result.mentioned ?? 0} of ${job.result.checks ?? 0} answers`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const loadRecs = async () => {
    setBusy("recs");
    try {
      const r = await api.post<{ recommendations: Recommendation[] }>("/visibility/recommendations");
      setRecs(r.recommendations);
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger" title="Failed to load visibility data">{error}</Alert>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-text-muted uppercase">AI answer share</p>
            <p className="text-2xl font-semibold">{summary?.share != null ? `${Math.round(summary.share * 100)}%` : "—"}</p>
            <p className="text-xs text-text-muted">of latest answers mention {summary?.company}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-text-muted uppercase">Average rank when listed</p>
            <p className="text-2xl font-semibold">{summary?.avg_rank ?? "—"}</p>
            <p className="text-xs text-text-muted">1 = recommended first</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-xs text-text-muted uppercase">Engines checked</p>
            <p className="text-2xl font-semibold">{summary?.providers.length || 0}</p>
            <p className="text-xs text-text-muted">{summary?.providers.join(", ") || "add an OpenAI key"}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Buyer queries</CardTitle>
          <CardDescription>The questions prospects ask AI assistants when choosing a vendor.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Input
              className="flex-1 min-w-[240px]"
              placeholder="e.g. best smart contract audit firms for DeFi protocols"
              value={newQuery}
              onChange={(e) => setNewQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addQuery()}
            />
            <Button size="sm" onClick={addQuery} disabled={!newQuery.trim()}>
              Add
            </Button>
            <Button size="sm" variant="outline" onClick={suggest} disabled={!!busy}>
              {busy === "suggest" ? "Suggesting…" : "Suggest from my domains"}
            </Button>
            <Button size="sm" onClick={runCheck} disabled={!!busy || queries.length === 0}>
              {busy === "check" ? "Asking AI engines…" : "Run check"}
            </Button>
          </div>
          {queries.length === 0 ? (
            <EmptyState title="No queries yet" description="Add buyer questions or generate them from your winnable domains." />
          ) : (
            <div className="flex flex-wrap gap-2">
              {queries.map((q) => (
                <span key={q.id} className="inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs">
                  {q.query}
                  <button className="text-text-muted hover:text-danger" onClick={() => removeQuery(q.id)} aria-label="Remove query">
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {chartData.length > 1 && (
        <Card>
          <CardHeader>
            <CardTitle>AI search rank over time</CardTitle>
            <CardDescription>% of answers that mention you, per day and engine</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Legend />
                {trendProviders.map((p) => (
                  <Line key={p} type="monotone" dataKey={p} stroke={PROVIDER_COLORS[p] || chartColors.violet} strokeWidth={2} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {summary && summary.latest.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Latest answers</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {summary.latest.map((c) => (
                <div key={c.id} className="rounded-lg border border-border p-3 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={c.mentioned ? "success" : "danger"}>{c.mentioned ? (c.rank ? `#${c.rank}` : "mentioned") : "missing"}</Badge>
                    <Badge variant="outline">{c.provider}</Badge>
                    <span className="text-sm font-medium">{c.query}</span>
                    <span className="text-xs text-text-muted ml-auto">{fmtDate(c.checked_at)}</span>
                  </div>
                  {c.competitors.length > 0 && <p className="text-xs text-text-secondary">Named instead: {c.competitors.slice(0, 6).join(", ")}</p>}
                  <button className="text-xs text-primary" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                    {expanded === c.id ? "Hide answer" : "Show answer"}
                  </button>
                  {expanded === c.id && (
                    <div className="text-xs whitespace-pre-wrap bg-surface-muted rounded p-2">
                      {c.answer_excerpt}
                      {c.citations.length > 0 && (
                        <div className="mt-2 space-y-0.5">
                          {c.citations.map((u) => (
                            <a key={u} href={u} target="_blank" rel="noreferrer" className="block text-primary truncate">
                              {u}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Who AI recommends</CardTitle>
              <CardDescription>Competitors named most often</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1">
              {summary.top_competitors.map((c) => (
                <div key={c.name} className="flex justify-between text-sm">
                  <span className="truncate">{c.name}</span>
                  <span className="text-text-muted">{c.mentions}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {summary && summary.latest.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle>How to close the gap</CardTitle>
                <CardDescription>Content and PR moves that make assistants more likely to cite you</CardDescription>
              </div>
              <Button size="sm" variant="outline" onClick={loadRecs} disabled={!!busy}>
                {busy === "recs" ? "Thinking…" : "Get recommendations"}
              </Button>
            </div>
          </CardHeader>
          {recs.length > 0 && (
            <CardContent className="space-y-3">
              {recs.map((r, i) => (
                <div key={i} className="rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{r.title}</p>
                    {r.format && <Badge variant="muted">{r.format}</Badge>}
                  </div>
                  <p className="text-xs text-text-secondary mt-1">{r.why}</p>
                  {r.target_queries && r.target_queries.length > 0 && (
                    <p className="text-xs text-text-muted mt-1">For: {r.target_queries.join(" · ")}</p>
                  )}
                </div>
              ))}
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
