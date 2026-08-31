"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from "recharts";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import { DEFAULT_WEIGHTS, type WeightKey } from "@tool-hub/shared-types";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Label,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  chartColors,
  trackColors,
} from "@tool-hub/ui";

const FIT_COLORS: Record<string, string> = {
  high: chartColors.success,
  medium: chartColors.warning,
  low: chartColors.muted,
};

type ProductLandscape = {
  demand_summary?: string;
  product_types_in_demand?: { product_type: string; signal_strength: number; matched_keywords: string[] }[];
  builders?: { name: string; type: string; source: string; metric: string; url?: string }[];
  revenue_models?: { model: string; fit: string; note: string; derived_from?: string }[];
  market_indicators?: Record<string, unknown>;
  sample_products?: { name: string; description: string; category: string; url?: string }[];
};

type Score = {
  domain: string;
  domain_id: string;
  track: string;
  composite_score: number;
  components: Record<string, number>;
  raw_evidence: Record<string, {
    value: number;
    unit: string;
    available: boolean;
    raw_data?: Record<string, unknown>;
    note?: string;
  }>;
  product_landscape?: ProductLandscape;
};

type Report = {
  executive_summary?: string;
  domain_narratives?: {
    domain: string;
    narrative: string;
    product_focus?: string;
    cited_metrics: string[];
  }[];
  confidence_flags?: { domain: string; reason: string }[];
};

const WEIGHT_LABELS: Record<WeightKey, string> = {
  hiring_demand: "Hiring Demand",
  capital_flow: "Capital Flow",
  developer_momentum: "Developer Momentum",
  funding_signal: "Funding Signal",
  public_interest: "Public Interest",
};

const TRACK_COLORS = trackColors;

function formatUsd(n: unknown): string {
  const v = Number(n);
  if (!v || isNaN(v)) return "—";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function MarketIndicators({ indicators }: { indicators?: Record<string, unknown> }) {
  if (!indicators) return null;
  const items = [
    indicators.job_postings != null && { label: "Job postings", value: String(indicators.job_postings) },
    indicators.adzuna_count != null && { label: "Adzuna (max kw)", value: String(indicators.adzuna_count) },
    indicators.remoteok_count != null && { label: "RemoteOK matches", value: String(indicators.remoteok_count) },
    indicators.new_repos_90d != null && { label: "GitHub repos", value: String(indicators.new_repos_90d) },
    indicators.total_tvl_usd != null && { label: "Protocol TVL", value: formatUsd(indicators.total_tvl_usd) },
    indicators.market_cap_usd != null && { label: "Market cap", value: formatUsd(indicators.market_cap_usd) },
    indicators.funding_mentions != null && { label: "Funding mentions", value: String(indicators.funding_mentions) },
    indicators.disclosed_capital_usd != null && Number(indicators.disclosed_capital_usd) > 0 && {
      label: "Disclosed funding",
      value: formatUsd(indicators.disclosed_capital_usd),
    },
    indicators.search_interest_index != null && { label: "Search interest", value: String(indicators.search_interest_index) },
    indicators.signals_available != null && {
      label: "Live sources",
      value: `${indicators.signals_available}/${indicators.signals_total ?? 5}`,
    },
  ].filter(Boolean) as { label: string; value: string }[];

  if (!items.length) return <p className="font-mono text-xs text-text-dim">No market data yet — refresh to pull signals</p>;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
      {items.map((item) => (
        <div key={item.label} className="bg-surface-muted border border-border rounded-lg p-3">
          <p className="text-xs text-text-muted">{item.label}</p>
          <p className="text-lg font-semibold mt-1 text-text-primary">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

export default function MarketDepthPanel() {
  const { backendUrl } = useToolContext();
  const apiBase = backendUrl;

  const [scores, setScores] = useState<Score[]>([]);
  const [weights, setWeights] = useState<Record<string, number>>({ ...DEFAULT_WEIGHTS });
  const [report, setReport] = useState<Report | null>(null);
  const [validationPassed, setValidationPassed] = useState<boolean | null>(null);
  const [validationNotes, setValidationNotes] = useState("");
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [selected, setSelected] = useState<Score | null>(null);
  const [detailTab, setDetailTab] = useState<"products" | "builders" | "revenue" | "market">("products");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshJobId, setRefreshJobId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const weightDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [keyStatus, setKeyStatus] = useState<{
    openai_configured?: boolean;
    github_configured?: boolean;
    adzuna_configured?: boolean;
  }>({});

  const staleApiKeyReport = Boolean(
    keyStatus.openai_configured &&
    report?.confidence_flags?.some((f) =>
      /missing API key|OPENAI_API_KEY not set/i.test(f.reason)
    )
  );

  const loadData = useCallback(async () => {
    try {
      const [snapRes, reportRes, weightsRes, configRes] = await Promise.all([
        fetch(`${apiBase}/snapshots/latest`),
        fetch(`${apiBase}/reports/latest`),
        fetch(`${apiBase}/weights`),
        fetch(`${apiBase}/config`),
      ]);
      const snap = await snapRes.json();
      const rep = await reportRes.json();
      const w = await weightsRes.json();
      const cfg = await configRes.json();
      setKeyStatus(cfg);
      setScores(snap.scores || []);
      setWeights(w.weights || { ...DEFAULT_WEIGHTS });
      setFetchedAt(snap.fetched_at);
      if (rep.report) {
        setReport(rep.report);
        setValidationPassed(rep.validation_passed);
        setValidationNotes(rep.validation_notes || "");
      }
    } catch {
      setLoadError("Could not load market data.");
    }
  }, [apiBase]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (!refreshJobId) return;
    const interval = setInterval(async () => {
      const res = await fetch(`${apiBase}/jobs/${refreshJobId}`);
      const job = await res.json();
      if (job.status === "done" || job.status === "failed") {
        setRefreshing(false);
        setRefreshJobId(null);
        loadData();
        clearInterval(interval);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [refreshJobId, apiBase, loadData]);

  const handleWeightChange = (key: string, value: number) => {
    const updated = { ...weights, [key]: value };
    setWeights(updated);
    if (weightDebounceRef.current) clearTimeout(weightDebounceRef.current);
    weightDebounceRef.current = setTimeout(async () => {
      const res = await fetch(`${apiBase}/weights`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weights: updated }),
      });
      const data = await res.json();
      if (data.scores) setScores(data.scores);
    }, 400);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    const res = await fetch(`${apiBase}/refresh`, { method: "POST" });
    const data = await res.json();
    setRefreshJobId(data.job_id);
  };

  const topThree = [...scores].sort((a, b) => b.composite_score - a.composite_score).slice(0, 3);

  const chartData = scores.map((s) => ({
    name: s.domain.length > 22 ? s.domain.slice(0, 20) + "…" : s.domain,
    fullName: s.domain,
    score: s.composite_score,
    track: s.track,
  }));

  const radarData = selected
    ? Object.entries(selected.components).map(([k, v]) => ({
        metric: WEIGHT_LABELS[k as WeightKey] || k,
        value: v,
      }))
    : [];

  const landscape = selected?.product_landscape;
  const narrative = report?.domain_narratives?.find((n) => n.domain === selected?.domain);

  return (
    <div className="space-y-6">
      {loadError && <Alert variant="danger" title="Load error">{loadError}</Alert>}
      {staleApiKeyReport && (
        <Alert variant="warning" title="Report may be stale">
          API keys are configured but the stored report predates them. Refresh to regenerate narratives.
          <div className="mt-3">
            <Button size="sm" onClick={handleRefresh} disabled={refreshing}>Refresh data</Button>
          </div>
        </Alert>
      )}

      <div className="flex justify-between items-start gap-4 flex-wrap">
        <div className="flex-1 min-w-[300px]">
          {report?.executive_summary ? (
            <Card className="accent-strip">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <CardTitle>Executive summary</CardTitle>
                  {validationPassed !== null && (
                    <Badge variant={validationPassed ? "success" : "warning"}>
                      {validationPassed ? "Validated" : "AI narrative suppressed"}
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {validationPassed === false ? (
                  <>
                    <Alert variant="warning" title="Not published as validated signal" className="mb-3">
                      {validationNotes || "Invented or uncited numbers detected. Showing score-only fallback."}
                    </Alert>
                    <p className="text-sm text-text-secondary leading-relaxed">{report.executive_summary}</p>
                  </>
                ) : (
                  <p className="text-sm text-text-secondary leading-relaxed">{report.executive_summary}</p>
                )}
              </CardContent>
            </Card>
          ) : (
            <EmptyState title="No report yet" description="Click Refresh Data to pull live market signals." />
          )}
        </div>
        <div className="text-right">
          <Button onClick={handleRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh data"}
          </Button>
          {fetchedAt && (
            <p className="text-xs text-text-muted mt-2">Last updated: {new Date(fetchedAt).toLocaleString()}</p>
          )}
        </div>
      </div>

      {/* Top 3 product opportunity cards */}
      {topThree.length > 0 && (
        <div>
          <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-3">
            Top Product Opportunities
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {topThree.map((s, i) => {
              const pl = s.product_landscape;
              const topProduct = pl?.product_types_in_demand?.[0];
              return (
                <button
                  key={s.domain_id}
                  onClick={() => { setSelected(s); setDetailTab("products"); }}
                  className="text-left bg-panel border border-border rounded-lg p-4 hover:border-border-bright transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="font-mono text-[10px] text-text-dim">#{i + 1}</span>
                    <span className="font-mono text-xs font-medium" style={{ color: TRACK_COLORS[s.track as keyof typeof TRACK_COLORS] }}>
                      {s.composite_score.toFixed(0)}
                    </span>
                  </div>
                  <h4 className="font-display font-semibold text-sm mb-1">{s.domain}</h4>
                  {topProduct ? (
                    <p className="font-mono text-[11px] text-accent-b mb-2">{topProduct.product_type}</p>
                  ) : null}
                  <p className="text-text-dim text-xs leading-relaxed line-clamp-2">
                    {pl?.demand_summary || "Refresh data for product intelligence"}
                  </p>
                  {pl?.builders && pl.builders.length > 0 && (
                    <p className="font-mono text-[10px] text-text-dim mt-2">
                      {pl.builders.length} builders · {pl.revenue_models?.length || 0} revenue paths
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {report?.confidence_flags && report.confidence_flags.length > 0 && (
        <Alert variant="warning" title="Confidence Flags" className="mb-2">
          <div className="space-y-2 mt-1">
            {report.confidence_flags.map((f, i) => (
              <p key={i} className="font-mono text-xs leading-relaxed text-zinc-800">
                <span className="font-semibold text-amber-700">{f.domain}:</span>{" "}
                {f.reason}
              </p>
            ))}
          </div>
        </Alert>
      )}

      {/* Chart + weights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-panel border border-border rounded-lg p-5">
          <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-4">Domain Rankings</h3>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={360}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 20 }}>
                <XAxis type="number" domain={[0, 100]} tick={{ fill: chartColors.muted, fontSize: 10 }} />
                <YAxis type="category" dataKey="name" width={140} tick={{ fill: chartColors.muted, fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: "#ffffff", border: "1px solid #e4e4e7", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [v.toFixed(1), "Score"]}
                  labelFormatter={(_, payload) => payload?.[0]?.payload?.fullName || ""}
                />
                <Bar dataKey="score" radius={[0, 4, 4, 0]} cursor="pointer"
                  onClick={(bar) => {
                    const name = (bar as { payload?: { fullName?: string } })?.payload?.fullName;
                    const match = scores.find((s) => s.domain === name);
                    if (match) { setSelected(match); setDetailTab("products"); }
                  }}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={TRACK_COLORS[entry.track as keyof typeof TRACK_COLORS] || chartColors.primary} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="font-mono text-sm text-text-dim text-center py-16">No scores yet</p>
          )}
        </div>

        <div className="bg-panel border border-border rounded-lg p-5">
          <h3 className="font-mono text-xs text-text-dim uppercase tracking-wider mb-4">Weight Sliders</h3>
          <div className="space-y-4">
            {(Object.keys(DEFAULT_WEIGHTS) as WeightKey[]).map((key) => (
              <div key={key}>
                <div className="flex justify-between font-mono text-xs mb-1">
                  <span className="text-text-secondary">{WEIGHT_LABELS[key]}</span>
                  <span className="text-text-dim">{(weights[key] ?? 0).toFixed(2)}</span>
                </div>
                <input type="range" min={0} max={1} step={0.05} value={weights[key] ?? 0}
                  onChange={(e) => handleWeightChange(key, parseFloat(e.target.value))}
                  className="w-full accent-primary" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Domain detail — sheet */}
      <Sheet open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent className="overflow-y-auto">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>{selected.domain}</SheetTitle>
                <Badge variant="outline" style={{ color: TRACK_COLORS[selected.track as keyof typeof TRACK_COLORS] }}>
                  {selected.track} · score {selected.composite_score.toFixed(1)}
                </Badge>
                {landscape?.demand_summary && (
                  <p className="text-sm text-text-secondary mt-2">{landscape.demand_summary}</p>
                )}
              </SheetHeader>

              <Tabs value={detailTab} onValueChange={(v) => setDetailTab(v as typeof detailTab)} className="mt-6">
                <TabsList>
                  <TabsTrigger value="products">Products</TabsTrigger>
                  <TabsTrigger value="builders">Builders</TabsTrigger>
                  <TabsTrigger value="revenue">Revenue</TabsTrigger>
                  <TabsTrigger value="market">Market</TabsTrigger>
                </TabsList>

                <TabsContent value="products">
            <div className="space-y-5">
              <div>
                <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Product Types In Demand</h4>
                {landscape?.product_types_in_demand?.length ? (
                  <div className="space-y-2">
                    {landscape.product_types_in_demand.map((pt, i) => (
                      <div key={i} className="flex items-center gap-3 bg-panel-raised border border-border rounded-lg p-3">
                        <div className="w-8 h-8 rounded bg-accent-b/10 border border-accent-b/30 flex items-center justify-center font-mono text-xs text-accent-b">
                          {pt.signal_strength}
                        </div>
                        <div>
                          <p className="font-medium text-sm">{pt.product_type}</p>
                          <p className="font-mono text-[10px] text-text-dim">signals: {pt.matched_keywords.join(", ")}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="font-mono text-xs text-text-dim">Run Refresh Data to populate product types</p>
                )}
              </div>

              {landscape?.sample_products && landscape.sample_products.length > 0 && (
                <div>
                  <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Live Products & Projects</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {landscape.sample_products.map((p, i) => (
                      <div key={i} className="border border-border rounded-lg p-3">
                        <div className="flex justify-between items-start gap-2">
                          <p className="font-mono text-xs text-text-primary font-medium">{p.name}</p>
                          <span className="font-mono text-[9px] text-text-dim border border-border px-1.5 py-0.5 rounded shrink-0">{p.category}</span>
                        </div>
                        <p className="text-text-secondary text-xs mt-1 leading-relaxed">{p.description}</p>
                        {p.url && (
                          <a href={p.url} target="_blank" rel="noopener noreferrer"
                            className="font-mono text-[10px] text-accent-b mt-1 inline-block hover:underline">view →</a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {narrative && (
                <div className="border-t border-border pt-4">
                  <h4 className="font-mono text-xs text-text-dim uppercase mb-2">AI Analysis (grounded)</h4>
                  {narrative.product_focus && (
                    <p className="font-mono text-xs text-accent-b mb-2">{narrative.product_focus}</p>
                  )}
                  <p className="text-text-secondary text-sm leading-relaxed">{narrative.narrative}</p>
                </div>
              )}
            </div>
                </TabsContent>

                <TabsContent value="builders">
            <div>
              <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Who Is Building</h4>
              {landscape?.builders?.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-xs">
                    <thead>
                      <tr className="text-text-dim border-b border-border">
                        <th className="text-left py-2 pr-4">Name</th>
                        <th className="text-left py-2 pr-4">Type</th>
                        <th className="text-left py-2 pr-4">Source</th>
                        <th className="text-left py-2">Signal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {landscape.builders.map((b, i) => (
                        <tr key={i} className="border-b border-border/50 hover:bg-panel-raised">
                          <td className="py-2.5 pr-4 text-text-primary">
                            {b.url ? (
                              <a href={b.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent-b">{b.name}</a>
                            ) : b.name}
                          </td>
                          <td className="py-2.5 pr-4 text-text-secondary">{b.type}</td>
                          <td className="py-2.5 pr-4 text-text-dim">{b.source}</td>
                          <td className="py-2.5 text-accent-a">{b.metric}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="font-mono text-xs text-text-dim">No builders identified — refresh with GITHUB_TOKEN and job API keys configured</p>
              )}
            </div>
                </TabsContent>

                <TabsContent value="revenue">
            <div>
              <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Revenue Options For This Domain</h4>
              {landscape?.revenue_models?.length ? (
                <div className="space-y-3">
                  {landscape.revenue_models.map((rm, i) => (
                    <div key={i} className="flex gap-4 items-start border border-border rounded-lg p-4">
                      <span className="font-mono text-[10px] uppercase px-2 py-1 rounded shrink-0"
                        style={{ color: FIT_COLORS[rm.fit] || "#8A91A3", border: `1px solid ${FIT_COLORS[rm.fit] || "#8A91A3"}40` }}>
                        {rm.fit} fit
                      </span>
                      <div>
                        <p className="font-medium text-sm">{rm.model}</p>
                        <p className="text-text-secondary text-xs mt-1 leading-relaxed">{rm.note}</p>
                        {rm.derived_from && (
                          <p className="font-mono text-[10px] text-text-dim mt-1">derived from: {rm.derived_from}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="font-mono text-xs text-text-dim">Revenue models load after refresh</p>
              )}
            </div>
                </TabsContent>

                <TabsContent value="market">
            <div className="space-y-5">
              <div>
                <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Market Indicators</h4>
                <MarketIndicators indicators={landscape?.market_indicators} />
              </div>
              <div>
                <h4 className="font-mono text-xs text-text-dim uppercase mb-3">Signal Breakdown</h4>
                <ResponsiveContainer width="100%" height={200}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#e4e4e7" />
                    <PolarAngleAxis dataKey="metric" tick={{ fill: chartColors.muted, fontSize: 9 }} />
                    <Radar dataKey="value" stroke={chartColors.primary} fill={chartColors.primary} fillOpacity={0.2} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div>
                <h4 className="font-mono text-xs text-text-dim uppercase mb-2">Raw Evidence</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {Object.entries(selected.raw_evidence).map(([k, v]) => (
                    <div key={k} className={`font-mono text-xs border rounded p-3 ${v.available ? "border-border" : "border-border/50 opacity-60"}`}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-text-dim">{WEIGHT_LABELS[k as WeightKey] || k}</span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded ${v.available ? "bg-ok/10 text-ok" : "bg-panel-raised text-text-dim"}`}>
                          {v.available ? "live" : "unavailable"}
                        </span>
                      </div>
                      <p className="text-text-primary">{v.value} {v.unit}</p>
                      {typeof v.raw_data?.methodology === "string" && (
                        <p className="text-text-dim text-[10px] mt-1 leading-relaxed">{v.raw_data.methodology}</p>
                      )}
                      {v.note && <p className="text-warning text-[10px] mt-1 leading-relaxed">{v.note}</p>}
                    </div>
                  ))}
                </div>
              </div>
            </div>
                </TabsContent>
              </Tabs>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
