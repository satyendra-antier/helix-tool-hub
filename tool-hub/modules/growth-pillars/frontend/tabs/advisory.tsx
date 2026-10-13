"use client";

import { useCallback, useEffect, useState } from "react";
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
  useToast,
} from "@tool-hub/ui";
import { errorMessage, fmtDate, useApi } from "../api";
import { DealDocs, HandoffList } from "./dealroom";

type Advice = {
  id: string;
  lead_id: string;
  lead_name: string;
  next_best_action: string;
  recommended_path: "direct" | "expert_intro" | "partner" | "nurture";
  talking_points: string[];
  objections: { objection: string; response: string }[];
  deal_risk: "low" | "medium" | "high";
  risk_reasons: string[];
  generated_by: string;
  created_at: string;
};

type LeadRow = {
  id: string;
  name: string;
  track?: string;
  score: number;
  stage?: string;
  signal_type?: string;
  matched_domain?: string;
  verdict?: string;
  advice: Advice | null;
};

const RISK_VARIANT = { low: "success", medium: "warning", high: "danger" } as const;
const PATH_LABEL: Record<Advice["recommended_path"], string> = {
  direct: "Direct outreach",
  expert_intro: "Expert intro",
  partner: "Via partner",
  nurture: "Nurture first",
};

export default function AdvisoryTab({ onChange }: { onChange: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<{ leads: LeadRow[] }>("/advice/leads?limit=40");
      setLeads(r.leads);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const adviseOne = async (leadId: string) => {
    setBusy(leadId);
    try {
      await api.post(`/advice/${leadId}`);
      setSelected(leadId);
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const adviseTop = async () => {
    setBusy("batch");
    try {
      const { job_id } = await api.post<{ job_id: string }>("/advice/batch", { top_n: 10 });
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Advisory failed");
      else toast(`Advised ${job.result.advised ?? 0} leads`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const current = leads.find((l) => l.id === selected)?.advice || null;

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger" title="Failed to load leads">{error}</Alert>}

      <HandoffList onPick={setSelected} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Deal plans for your top leads</h3>
          <p className="text-xs text-text-muted">
            Combines lead score, fit verdict, contacts, insider alerts, expert and partner paths into one next step.
          </p>
        </div>
        <Button onClick={adviseTop} disabled={!!busy || leads.length === 0}>
          {busy === "batch" ? "Advising…" : "Advise top 10"}
        </Button>
      </div>

      {!loading && leads.length === 0 && !error ? (
        <EmptyState title="No leads yet" description="Find leads in step 3 (Find Leads) first." />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <div className="lg:col-span-2 space-y-2">
            {leads.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelected(l.id)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  selected === l.id ? "border-primary bg-primary/5" : "border-border hover:bg-surface-muted"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium truncate">{l.name}</p>
                  <span className="text-xs text-text-muted shrink-0">{Number(l.score || 0).toFixed(0)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1 mt-1">
                  {l.track && <Badge variant="muted">{l.track}</Badge>}
                  {l.verdict && <Badge variant="outline">{l.verdict}</Badge>}
                  {l.advice ? (
                    <>
                      <Badge variant={RISK_VARIANT[l.advice.deal_risk]}>{l.advice.deal_risk} risk</Badge>
                      <Badge variant="primary">{PATH_LABEL[l.advice.recommended_path]}</Badge>
                    </>
                  ) : (
                    <span className="text-xs text-text-muted">no plan yet</span>
                  )}
                </div>
              </button>
            ))}
          </div>

          <div className="lg:col-span-3">
            {!selected ? (
              <EmptyState title="Pick a lead" description="Select a lead on the left to see or generate its deal plan." />
            ) : (
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <CardTitle>{leads.find((l) => l.id === selected)?.name}</CardTitle>
                      <CardDescription>
                        {current ? `Generated ${fmtDate(current.created_at)} · ${current.generated_by === "llm" ? "AI" : "rules"}` : "No plan yet"}
                      </CardDescription>
                    </div>
                    <Button size="sm" onClick={() => adviseOne(selected)} disabled={!!busy}>
                      {busy === selected ? "Thinking…" : current ? "Refresh plan" : "Generate plan"}
                    </Button>
                  </div>
                </CardHeader>
                {current && (
                  <CardContent className="space-y-4">
                    <div className="flex flex-wrap gap-2">
                      <Badge variant={RISK_VARIANT[current.deal_risk]}>{current.deal_risk} deal risk</Badge>
                      <Badge variant="primary">{PATH_LABEL[current.recommended_path]}</Badge>
                    </div>
                    <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                      <p className="text-xs uppercase text-text-muted mb-1">Next best action</p>
                      <p className="text-sm font-medium">{current.next_best_action}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-muted mb-1">Talking points</p>
                      <ul className="list-disc pl-5 space-y-1 text-sm">
                        {current.talking_points.map((t, i) => (
                          <li key={i}>{t}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-muted mb-1">Likely objections</p>
                      <div className="space-y-2">
                        {current.objections.map((o, i) => (
                          <div key={i} className="rounded-lg bg-surface-muted p-2 text-sm">
                            <p className="font-medium">&ldquo;{o.objection}&rdquo;</p>
                            <p className="text-text-secondary text-xs mt-0.5">{o.response}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-muted mb-1">Why this risk level</p>
                      <ul className="list-disc pl-5 space-y-1 text-xs text-text-secondary">
                        {current.risk_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  </CardContent>
                )}
                <CardContent className={current ? "pt-0" : undefined}>
                  <DealDocs key={selected} leadId={selected} />
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
