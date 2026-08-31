"use client";

import { useCallback, useEffect, useState } from "react";
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer,
} from "recharts";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  EmptyState,
  chartColors,
  useToast,
} from "@tool-hub/ui";

type MatchedDomain = {
  domain_name: string;
  verdict?: string;
  market_score?: number;
  capability_score?: number;
  matched_terms?: string[];
};

type Lead = {
  id: string;
  name: string;
  track: string;
  domain?: string;
  description?: string;
  source: string;
  signal_type?: string;
  signal_value?: number;
  deadline?: string;
  score: number;
  breakdown: Record<string, number | string>;
  stage: string;
  lead_orientation?: string;
  matched_domains?: MatchedDomain[];
  domain_context?: MatchedDomain;
  portal_link?: string;
  is_portal_lead?: boolean;
  outreach_draft?: { subject?: string; body?: string; cited_signal?: string };
  contacts: {
    full_name?: string;
    role_title?: string;
    email?: string;
    email_verified: boolean;
    consent_basis: string;
  }[];
};

type PipelineStatus = {
  aligned_scoring: boolean;
  can_discover: boolean;
  stale_warning?: string;
  orientations: {
    demand: { label: string; description: string; domain_count: number; top_domains: string[] };
    future: { label: string; description: string; domain_count: number; top_domains: string[] };
  };
  steps: { step: number; name: string; ready: boolean; stats?: Record<string, number> }[];
  sync_keywords_preview?: string[];
};

const STAGES = ["new", "qualified", "contacted", "replied", "won", "lost"];
const TRACKS = ["all", "government", "web3", "web2", "ai"] as const;
const ORIENTATIONS = ["all", "demand", "future", "generic"] as const;

const TRACK_COLORS: Record<string, string> = {
  government: chartColors.success,
  web3: chartColors.warning,
  web2: chartColors.primary,
  ai: chartColors.violet,
  growth: chartColors.success,
};

const ORIENTATION_COLORS: Record<string, string> = {
  demand: chartColors.success,
  future: chartColors.warning,
  generic: chartColors.muted,
};

const WEIGHT_LABELS: Record<string, string> = {
  recency: "Recency",
  budget_indicator: "Budget",
  keyword_fit: "Keyword Fit",
  urgency: "Urgency",
  contact_confidence: "Contact Confidence",
  market_demand_fit: "Market Demand",
  capability_fit: "Capability Fit",
};

function daysRemaining(deadline?: string) {
  if (!deadline) return null;
  return Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000);
}

function stripHtml(text?: string): string {
  if (!text) return "";
  if (!/[<&]/.test(text)) return text.replace(/\s+/g, " ").trim();
  const doc = new DOMParser().parseFromString(text, "text/html");
  return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
}

export default function LeadIntelligencePanel() {
  const { backendUrl } = useToolContext();
  const apiBase = backendUrl;
  const { toast } = useToast();

  const [leads, setLeads] = useState<Lead[]>([]);
  const [govLeads, setGovLeads] = useState<Lead[]>([]);
  const [trackFilter, setTrackFilter] = useState<string>("all");
  const [orientationFilter, setOrientationFilter] = useState<string>("all");
  const [view, setView] = useState<"kanban" | "calendar" | "settings">("kanban");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null);
  const [keywords, setKeywords] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [draftText, setDraftText] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(24);
  const [totalLeads, setTotalLeads] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [leadsError, setLeadsError] = useState<string | null>(null);

  const fetchWithTimeout = async (url: string, ms = 15000) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    try {
      return await fetch(url, { signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  };

  const loadLeads = useCallback(async () => {
    const params = new URLSearchParams();
    if (trackFilter !== "all") params.set("track", trackFilter);
    if (orientationFilter !== "all") params.set("orientation", orientationFilter);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    params.set("sort", "score");
    const qs = `?${params}`;

    setLeadsLoading(true);
    setLeadsError(null);
    try {
      // Do NOT load /leads/government here — it N+1s every gov entity and hangs the Kanban.
      const [leadsRes, profileRes, statusRes] = await Promise.all([
        fetchWithTimeout(`${apiBase}/leads${qs}`),
        fetchWithTimeout(`${apiBase}/fit-profile`, 10000),
        fetchWithTimeout(`${apiBase}/pipeline/status`, 10000),
      ]);
      if (!leadsRes.ok) throw new Error(`Leads API failed (${leadsRes.status})`);
      const leadsData = await leadsRes.json();
      const profile = profileRes.ok ? await profileRes.json() : {};
      const status = statusRes.ok ? await statusRes.json() : null;
      setLeads(leadsData.leads || []);
      setTotalLeads(leadsData.total ?? 0);
      setTotalPages(leadsData.pages ?? 1);
      setKeywords((profile.keywords || []).join(", "));
      setWeights(profile.weights || {});
      setPipelineStatus(status);
    } catch (e) {
      setLeads([]);
      setTotalLeads(0);
      setLeadsError(
        e instanceof Error && e.name === "AbortError"
          ? "Leads API timed out — backend may be overloaded (N+1 queries)."
          : e instanceof Error
            ? e.message
            : "Failed to load leads"
      );
    } finally {
      setLeadsLoading(false);
    }
  }, [apiBase, trackFilter, orientationFilter, page, pageSize]);

  const loadGovLeads = useCallback(async () => {
    try {
      const govRes = await fetchWithTimeout(`${apiBase}/leads/government?limit=50`, 15000);
      if (!govRes.ok) throw new Error(`Government calendar failed (${govRes.status})`);
      const govData = await govRes.json();
      setGovLeads(govData.opportunities || []);
    } catch {
      setGovLeads([]);
    }
  }, [apiBase]);

  useEffect(() => {
    setPage(1);
  }, [trackFilter, orientationFilter]);

  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  useEffect(() => {
    if (view === "calendar") loadGovLeads();
  }, [view, loadGovLeads]);

  useEffect(() => {
    if (selected?.outreach_draft?.body) {
      setDraftText(selected.outreach_draft.body);
    }
  }, [selected]);

  const handleDiscover = async () => {
    setDiscoverError(null);
    setDiscovering(true);
    try {
      const res = await fetch(`${apiBase}/discover`, { method: "POST" });
      if (!res.ok) throw new Error("Discovery failed to start");
      const data = await res.json();
      const poll = setInterval(async () => {
        const job = await (await fetch(`${apiBase}/jobs/${data.job_id}`)).json();
        if (job.status === "done" || job.status === "failed") {
          clearInterval(poll);
          setDiscovering(false);
          if (job.status === "failed") setDiscoverError(job.error || "Discovery failed");
          loadLeads();
        }
      }, 3000);
    } catch (e) {
      setDiscovering(false);
      setDiscoverError(e instanceof Error ? e.message : "Discovery failed");
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    await fetch(`${apiBase}/fit-profile/sync`, { method: "POST" });
    setSyncing(false);
    loadLeads();
  };

  const moveStage = async (leadId: string, stage: string) => {
    await fetch(`${apiBase}/leads/${leadId}/stage`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
    loadLeads();
  };

  const markSent = async (leadId: string) => {
    await fetch(`${apiBase}/leads/${leadId}/mark-sent`, { method: "POST" });
    loadLeads();
    setSelected(null);
  };

  const saveDraft = async (leadId: string) => {
    await fetch(`${apiBase}/leads/${leadId}/outreach`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outreach_draft: JSON.stringify({ body: draftText }) }),
    });
    toast("Draft saved", "success");
  };

  const saveFitProfile = async () => {
    await fetch(`${apiBase}/fit-profile`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
        weights,
      }),
    });
    loadLeads();
  };

  const leadsByStage = (stage: string) =>
    leads.filter((l) => l.stage === stage).sort((a, b) => b.score - a.score);

  const radarData = selected
    ? Object.entries(selected.breakdown)
        .filter(([k, v]) => typeof v === "number")
        .map(([k, v]) => ({
          metric: WEIGHT_LABELS[k] || k,
          value: v as number,
        }))
    : [];

  const showPagination = view === "kanban" && totalLeads > 0;

  return (
    <div className="space-y-6">
      {discoverError && <Alert variant="danger" title="Discovery failed">{discoverError}</Alert>}
      {pipelineStatus && (
        <Card className="accent-strip">
          <CardContent className="py-4 space-y-3">
          <div className="flex justify-between items-start flex-wrap gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase text-text-dim tracking-wider">
                Market-aligned discovery
              </p>
              <p className="font-mono text-xs text-text-secondary mt-1">
                {pipelineStatus.aligned_scoring
                  ? "Demand + future orientation active — scoring uses Market Depth + Build Readiness"
                  : "Partial alignment — refresh Market Depth and run Build Readiness for full scoring"}
              </p>
            </div>
            <Button variant="outline" onClick={handleSync} disabled={syncing} size="sm">
              {syncing ? "Syncing…" : "Sync from Build Readiness"}
            </Button>
          </div>

          {pipelineStatus.stale_warning && (
            <p className="font-mono text-xs text-accent-b border border-accent-b/30 rounded px-3 py-2">
              {pipelineStatus.stale_warning}
            </p>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(["demand", "future"] as const).map((key) => {
              const o = pipelineStatus.orientations[key];
              return (
                <div key={key} className="bg-panel-raised border border-border rounded p-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: ORIENTATION_COLORS[key] }}
                    />
                    <span className="font-mono text-xs text-text-primary">{o.label}</span>
                    <span className="font-mono text-[10px] text-text-dim ml-auto">
                      {o.domain_count} domains
                    </span>
                  </div>
                  <p className="font-mono text-[10px] text-text-dim mt-1">{o.description}</p>
                  {o.top_domains.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {o.top_domains.map((d) => (
                        <span
                          key={d}
                          className="font-mono text-[9px] px-1.5 py-0.5 rounded border"
                          style={{
                            color: ORIENTATION_COLORS[key],
                            borderColor: `${ORIENTATION_COLORS[key]}40`,
                          }}
                        >
                          {d}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          </CardContent>
        </Card>
      )}

      {leadsError && (
        <Alert variant="danger" title="Leads failed to load" className="mb-2">
          {leadsError} This is not an empty pipeline — the request failed.
        </Alert>
      )}
      {leadsLoading && !leadsError && (
        <p className="text-sm text-text-secondary mb-2">Loading leads…</p>
      )}

      <Tabs value={view} onValueChange={(v) => setView(v as typeof view)}>
        <div className="flex justify-between items-center flex-wrap gap-3">
          <TabsList>
            <TabsTrigger value="kanban">Kanban</TabsTrigger>
            <TabsTrigger value="calendar">Gov calendar</TabsTrigger>
            <TabsTrigger value="settings">Settings</TabsTrigger>
          </TabsList>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" asChild>
              <a href={`${apiBase}/export/csv`}>Export CSV</a>
            </Button>
            <Button onClick={handleDiscover} disabled={discovering}>
              {discovering ? "Discovering…" : "Run discovery"}
            </Button>
          </div>
        </div>

      {view !== "settings" && (
        <div className="space-y-2">
          <div className="flex gap-1 flex-wrap">
            {TRACKS.map((t) => (
              <button
                key={t}
                onClick={() => setTrackFilter(t)}
                className={`text-xs uppercase px-3 py-1 rounded-lg border ${
                  trackFilter === t
                    ? "border-primary text-primary bg-primary/10"
                    : "border-border text-text-muted"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="flex gap-1 flex-wrap items-center">
            <span className="font-mono text-[10px] text-text-dim uppercase mr-1">Orientation</span>
            {ORIENTATIONS.map((o) => (
              <button
                key={o}
                onClick={() => setOrientationFilter(o)}
                className={`text-xs uppercase px-3 py-1 rounded-lg border ${
                  orientationFilter === o
                    ? "border-warning text-warning bg-warning/10"
                    : "border-border text-text-muted"
                }`}
              >
                {o}
              </button>
            ))}
          </div>
        </div>
      )}

      <TabsContent value="kanban">
          {!leadsLoading && !leadsError && totalLeads === 0 && (
            <EmptyState
              title="No leads in pipeline"
              description="Run discovery to pull government, hiring, and funding signals — or check filters."
            />
          )}

        <div className="flex gap-3 overflow-x-auto pb-2">
          {STAGES.map((stage) => (
            <div key={stage} className="bg-surface border border-border rounded-xl p-3 min-w-[180px] flex-1">
              <h3 className="text-xs uppercase text-text-muted mb-3 font-medium">{stage}</h3>
              <div className="space-y-2">
                {leadsByStage(stage).map((lead) => (
                  <button
                    key={lead.id}
                    onClick={() => setSelected(lead)}
                    className="w-full text-left bg-panel-raised border border-border rounded p-2 hover:border-border-bright transition-colors"
                  >
                    <p className="font-mono text-xs text-text-primary truncate">{lead.name}</p>
                    <div className="flex justify-between items-center mt-1 gap-1">
                      <span
                        className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded shrink-0"
                        style={{
                          color: TRACK_COLORS[lead.track],
                          border: `1px solid ${TRACK_COLORS[lead.track]}40`,
                        }}
                      >
                        {lead.track}
                      </span>
                      <span className="font-mono text-[10px] text-text-dim">{lead.score.toFixed(0)}</span>
                    </div>
                    {lead.lead_orientation && lead.lead_orientation !== "generic" && (
                      <span
                        className="font-mono text-[8px] uppercase px-1 py-0.5 rounded mt-1 inline-block"
                        style={{
                          color: ORIENTATION_COLORS[lead.lead_orientation],
                          background: `${ORIENTATION_COLORS[lead.lead_orientation]}15`,
                        }}
                      >
                        {lead.lead_orientation}
                      </span>
                    )}
                    {lead.domain_context?.domain_name && (
                      <p className="font-mono text-[8px] text-text-dim mt-0.5 truncate">
                        {lead.domain_context.domain_name}
                        {lead.domain_context.verdict ? ` · ${lead.domain_context.verdict}` : ""}
                      </p>
                    )}
                    <p className="font-mono text-[9px] text-text-dim mt-1 truncate">
                      {lead.signal_type} · {lead.source}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </TabsContent>

      {showPagination && view === "kanban" && (
        <div className="flex flex-wrap justify-between items-center gap-3 border-t border-border pt-4">
          <p className="font-mono text-xs text-text-dim">
            {totalLeads} leads · page {page} of {totalPages}
            <span className="ml-2 text-text-dim/70">(sorted by score)</span>
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="font-mono text-xs border border-border px-3 py-1.5 rounded disabled:opacity-40 hover:border-text-primary"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="font-mono text-xs border border-border px-3 py-1.5 rounded disabled:opacity-40 hover:border-text-primary"
            >
              Next
            </button>
          </div>
        </div>
      )}

      <TabsContent value="calendar">
        <div className="space-y-2">
          {govLeads.length === 0 ? (
            <p className="font-mono text-sm text-text-dim text-center py-12">
              No government opportunities — run discovery first
            </p>
          ) : (
            govLeads.map((lead) => {
              const days = daysRemaining(lead.deadline);
              const urgent = days !== null && days <= 5;
              return (
                <button
                  key={lead.id}
                  onClick={() => setSelected(lead)}
                  className="w-full text-left bg-panel border border-border rounded-lg p-4 hover:border-border-bright flex justify-between items-center gap-4"
                >
                  <div>
                    <p className="font-display text-sm font-medium">{lead.name}</p>
                    <p className="font-mono text-xs text-text-dim mt-1">
                      {lead.source} · score {lead.score.toFixed(0)}
                      {lead.lead_orientation ? ` · ${lead.lead_orientation}` : ""}
                    </p>
                  </div>
                  {days !== null && (
                    <span
                      className={`font-mono text-xs px-3 py-1 rounded shrink-0 ${
                        urgent
                          ? "bg-red-950/40 text-red-400 border border-red-800"
                          : "bg-panel-raised text-text-secondary border border-border"
                      }`}
                    >
                      {days < 0 ? "expired" : `${days}d left`}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </TabsContent>

      <TabsContent value="settings">
        <div className="bg-panel border border-border rounded-lg p-6 space-y-6 max-w-xl">
          <div>
            <label className="font-mono text-xs text-text-dim uppercase block mb-2">
              Fit Profile Keywords
            </label>
            <textarea
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              rows={4}
              className="w-full bg-panel-raised border border-border rounded p-3 font-mono text-sm text-text-primary"
            />
            <p className="font-mono text-[10px] text-text-dim mt-2">
              Use &quot;Sync from Build Readiness&quot; to auto-fill from GO + future domains.
            </p>
          </div>
          <div className="space-y-3">
            <p className="font-mono text-xs text-text-dim uppercase">Scoring Weights</p>
            {Object.entries(weights).map(([k, v]) => (
              <div key={k}>
                <div className="flex justify-between font-mono text-xs mb-1">
                  <span>{WEIGHT_LABELS[k] || k}</span>
                  <span>{v.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={v}
                  onChange={(e) => setWeights({ ...weights, [k]: parseFloat(e.target.value) })}
                  className="w-full accent-primary"
                />
              </div>
            ))}
          </div>
          <Button onClick={saveFitProfile}>Save & re-score</Button>
        </div>
      </TabsContent>
      </Tabs>

      <Sheet open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent>
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>{selected.name}</SheetTitle>
                <div className="flex flex-wrap gap-2 mt-2">
                  <Badge variant="outline" style={{ color: TRACK_COLORS[selected.track], borderColor: TRACK_COLORS[selected.track] }}>
                    {selected.track} · {selected.score.toFixed(1)}
                  </Badge>
                  {selected.lead_orientation && (
                    <Badge variant="outline" style={{ color: ORIENTATION_COLORS[selected.lead_orientation] }}>
                      {selected.lead_orientation}-oriented
                    </Badge>
                  )}
                </div>
              </SheetHeader>

            {selected.domain_context?.domain_name && (
              <div className="mt-4 bg-panel-raised border border-border rounded p-3">
                <p className="font-mono text-[10px] text-text-dim uppercase">Matched Domain</p>
                <p className="font-mono text-sm text-text-primary mt-1">
                  {selected.domain_context.domain_name}
                </p>
                <div className="flex gap-3 mt-2 font-mono text-[10px] text-text-dim">
                  {selected.domain_context.verdict && (
                    <span>Verdict: {selected.domain_context.verdict}</span>
                  )}
                  {selected.domain_context.market_score != null && (
                    <span>Market: {selected.domain_context.market_score}</span>
                  )}
                  {selected.domain_context.capability_score != null && (
                    <span>Capability: {selected.domain_context.capability_score}</span>
                  )}
                </div>
                {selected.domain_context.matched_terms && selected.domain_context.matched_terms.length > 0 && (
                  <p className="font-mono text-[10px] text-text-dim mt-2">
                    Terms: {selected.domain_context.matched_terms.join(", ")}
                  </p>
                )}
              </div>
            )}

            <p className="text-text-secondary text-sm mt-4 leading-relaxed">
              {stripHtml(selected.description)}
            </p>

            <div className="mt-6">
              <h3 className="font-mono text-xs text-text-dim uppercase mb-2">Score Breakdown</h3>
              <ResponsiveContainer width="100%" height={180}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#e4e4e7" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: chartColors.muted, fontSize: 9 }} />
                  <Radar dataKey="value" stroke={chartColors.success} fill={chartColors.success} fillOpacity={0.2} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-4">
              <h3 className="font-mono text-xs text-text-dim uppercase mb-2">Contacts</h3>
              {selected.contacts.length === 0 ? (
                <div className="border border-border rounded p-3 font-mono text-xs text-text-secondary">
                  {selected.is_portal_lead || selected.track === "government" ? (
                    <>
                      <p>No direct email — this is a government portal opportunity.</p>
                      {selected.portal_link && (
                        <a
                          href={selected.portal_link}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent-b underline mt-2 inline-block"
                        >
                          Open on {selected.domain || "portal"} →
                        </a>
                      )}
                    </>
                  ) : (
                    <p>No verified contacts yet. Re-run discovery after adding Apollo/Hunter keys, or qualify manually.</p>
                  )}
                </div>
              ) : (
                selected.contacts.map((c, i) => (
                  <div key={i} className="border border-border rounded p-2 mb-2 font-mono text-xs">
                    <p className="text-text-primary">{c.full_name || "—"} · {c.role_title}</p>
                    <p className="text-text-secondary">{c.email}</p>
                    <div className="flex gap-2 mt-1">
                      {c.email_verified && (
                        <span className="text-ok text-[10px]">verified ✓</span>
                      )}
                      <span className="text-text-dim text-[10px]">{c.consent_basis}</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="mt-6">
              <h3 className="font-mono text-xs text-text-dim uppercase mb-2">
                Outreach Draft (human review)
              </h3>
              {selected.outreach_draft?.cited_signal && (
                <p className="font-mono text-[10px] text-accent-b mb-2">
                  Signal: {selected.outreach_draft.cited_signal}
                </p>
              )}
              <Textarea
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                rows={6}
                className="font-mono text-xs"
              />
              <div className="flex gap-2 mt-3">
                <Button variant="outline" size="sm" onClick={() => saveDraft(selected.id)}>Save draft</Button>
                <Button size="sm" onClick={() => markSent(selected.id)}>Mark as sent</Button>
              </div>
              <p className="font-mono text-[10px] text-text-dim mt-2">
                No auto-send — you must explicitly mark as sent.
              </p>
            </div>

            <div className="mt-4 flex gap-1 flex-wrap">
              {STAGES.filter((s) => s !== selected.stage).map((s) => (
                <Button key={s} variant="outline" size="sm" onClick={() => moveStage(selected.id, s)}>
                  → {s}
                </Button>
              ))}
            </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
