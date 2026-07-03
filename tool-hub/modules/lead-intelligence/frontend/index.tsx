"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from "recharts";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";

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
  breakdown: Record<string, number>;
  stage: string;
  outreach_draft?: { subject?: string; body?: string; cited_signal?: string };
  contacts: {
    full_name?: string;
    role_title?: string;
    email?: string;
    email_verified: boolean;
    consent_basis: string;
  }[];
};

const STAGES = ["new", "qualified", "contacted", "replied", "won", "lost"];
const TRACKS = ["all", "government", "web3", "web2", "ai"] as const;
const TRACK_COLORS: Record<string, string> = {
  government: "#3ED598",
  web3: "#FF8A34",
  web2: "#6E86FF",
  ai: "#C084FC",
  growth: "#3ED598",
};

const WEIGHT_LABELS: Record<string, string> = {
  recency: "Recency",
  budget_indicator: "Budget",
  keyword_fit: "Keyword Fit",
  urgency: "Urgency",
  contact_confidence: "Contact Confidence",
};

function daysRemaining(deadline?: string) {
  if (!deadline) return null;
  const diff = Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000);
  return diff;
}

export default function LeadIntelligencePanel() {
  const { backendUrl } = useToolContext();
  const apiBase =
    typeof window !== "undefined"
      ? backendUrl.replace("lead-intelligence-api", "localhost")
      : backendUrl;

  const [leads, setLeads] = useState<Lead[]>([]);
  const [govLeads, setGovLeads] = useState<Lead[]>([]);
  const [trackFilter, setTrackFilter] = useState<string>("all");
  const [view, setView] = useState<"kanban" | "calendar" | "settings">("kanban");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [draftText, setDraftText] = useState("");

  const loadLeads = useCallback(async () => {
    const track = trackFilter === "all" ? "" : `?track=${trackFilter}`;
    const [leadsRes, govRes, profileRes] = await Promise.all([
      fetch(`${apiBase}/leads${track}`),
      fetch(`${apiBase}/leads/government`),
      fetch(`${apiBase}/fit-profile`),
    ]);
    const leadsData = await leadsRes.json();
    const govData = await govRes.json();
    const profile = await profileRes.json();
    setLeads(leadsData.leads || []);
    setGovLeads(govData.opportunities || []);
    setKeywords((profile.keywords || []).join(", "));
    setWeights(profile.weights || {});
  }, [apiBase, trackFilter]);

  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  useEffect(() => {
    if (selected?.outreach_draft?.body) {
      setDraftText(selected.outreach_draft.body);
    }
  }, [selected]);

  const handleDiscover = async () => {
    setDiscovering(true);
    const res = await fetch(`${apiBase}/discover`, { method: "POST" });
    const data = await res.json();
    const poll = setInterval(async () => {
      const job = await (await fetch(`${apiBase}/jobs/${data.job_id}`)).json();
      if (job.status === "done" || job.status === "failed") {
        clearInterval(poll);
        setDiscovering(false);
        loadLeads();
      }
    }, 3000);
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
    ? Object.entries(selected.breakdown).map(([k, v]) => ({
        metric: WEIGHT_LABELS[k] || k,
        value: v,
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div className="flex gap-1 border-b border-border">
          {(["kanban", "calendar", "settings"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`font-mono text-xs px-4 py-2 capitalize border-b-2 -mb-px ${
                view === v
                  ? "border-[#3ED598] text-[#3ED598]"
                  : "border-transparent text-text-dim hover:text-text-secondary"
              }`}
            >
              {v === "calendar" ? "Gov Calendar" : v}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <a
            href={`${apiBase}/export/csv`}
            className="font-mono text-xs border border-border px-3 py-2 rounded hover:border-text-primary"
          >
            Export CSV
          </a>
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="font-mono text-sm bg-[#3ED598] text-bg px-5 py-2 rounded-lg disabled:opacity-40"
          >
            {discovering ? "Discovering…" : "Run Discovery"}
          </button>
        </div>
      </div>

      {view !== "settings" && (
        <div className="flex gap-1 flex-wrap">
          {TRACKS.map((t) => (
            <button
              key={t}
              onClick={() => setTrackFilter(t)}
              className={`font-mono text-[10px] uppercase px-3 py-1 rounded border ${
                trackFilter === t
                  ? "border-[#3ED598] text-[#3ED598] bg-[#3ED598]/10"
                  : "border-border text-text-dim"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {view === "kanban" && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 overflow-x-auto">
          {STAGES.map((stage) => (
            <div key={stage} className="bg-panel border border-border rounded-lg p-3 min-w-[160px]">
              <h3 className="font-mono text-[10px] uppercase text-text-dim mb-3 tracking-wider">
                {stage}
              </h3>
              <div className="space-y-2">
                {leadsByStage(stage).map((lead) => (
                  <button
                    key={lead.id}
                    onClick={() => setSelected(lead)}
                    draggable
                    onDragEnd={() => {}}
                    className="w-full text-left bg-panel-raised border border-border rounded p-2 hover:border-border-bright transition-colors"
                  >
                    <p className="font-mono text-xs text-text-primary truncate">{lead.name}</p>
                    <div className="flex justify-between items-center mt-1">
                      <span
                        className="font-mono text-[9px] uppercase px-1.5 py-0.5 rounded"
                        style={{
                          color: TRACK_COLORS[lead.track],
                          border: `1px solid ${TRACK_COLORS[lead.track]}40`,
                        }}
                      >
                        {lead.track}
                      </span>
                      <span className="font-mono text-[10px] text-text-dim">{lead.score.toFixed(0)}</span>
                    </div>
                    <p className="font-mono text-[9px] text-text-dim mt-1 truncate">
                      {lead.signal_type} · {lead.source}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {view === "calendar" && (
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
                    <p className="font-mono text-xs text-text-dim mt-1">{lead.source} · score {lead.score.toFixed(0)}</p>
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
      )}

      {view === "settings" && (
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
                  className="w-full accent-[#3ED598]"
                />
              </div>
            ))}
          </div>
          <button
            onClick={saveFitProfile}
            className="font-mono text-sm bg-[#3ED598] text-bg px-5 py-2 rounded-lg"
          >
            Save & Re-score
          </button>
        </div>
      )}

      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSelected(null)} />
          <div className="relative w-full max-w-lg bg-panel border-l border-border h-full overflow-y-auto p-6">
            <button
              onClick={() => setSelected(null)}
              className="font-mono text-xs text-text-dim hover:text-text-primary mb-4"
            >
              Close
            </button>
            <h2 className="font-display text-xl font-semibold">{selected.name}</h2>
            <span
              className="font-mono text-[10px] uppercase px-2 py-0.5 rounded border mt-2 inline-block"
              style={{ color: TRACK_COLORS[selected.track], borderColor: `${TRACK_COLORS[selected.track]}40` }}
            >
              {selected.track} · {selected.score.toFixed(1)}
            </span>
            <p className="text-text-secondary text-sm mt-4 leading-relaxed">{selected.description}</p>

            <div className="mt-6">
              <h3 className="font-mono text-xs text-text-dim uppercase mb-2">Score Breakdown</h3>
              <ResponsiveContainer width="100%" height={180}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="#232833" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: "#8A91A3", fontSize: 9 }} />
                  <Radar dataKey="value" stroke="#3ED598" fill="#3ED598" fillOpacity={0.2} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="mt-4">
              <h3 className="font-mono text-xs text-text-dim uppercase mb-2">Contacts</h3>
              {selected.contacts.map((c, i) => (
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
              ))}
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
              <textarea
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                rows={6}
                className="w-full bg-panel-raised border border-border rounded p-3 font-mono text-xs text-text-secondary"
              />
              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => saveDraft(selected.id)}
                  className="font-mono text-xs border border-border px-3 py-1.5 rounded"
                >
                  Save Draft
                </button>
                <button
                  onClick={() => markSent(selected.id)}
                  className="font-mono text-xs bg-text-primary text-bg px-3 py-1.5 rounded"
                >
                  Mark as Sent
                </button>
              </div>
              <p className="font-mono text-[10px] text-text-dim mt-2">
                No auto-send — you must explicitly mark as sent.
              </p>
            </div>

            <div className="mt-4 flex gap-1 flex-wrap">
              {STAGES.filter((s) => s !== selected.stage).map((s) => (
                <button
                  key={s}
                  onClick={() => moveStage(selected.id, s)}
                  className="font-mono text-[10px] border border-border px-2 py-1 rounded hover:border-text-primary"
                >
                  → {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
