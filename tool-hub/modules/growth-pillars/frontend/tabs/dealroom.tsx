"use client";

import { useCallback, useEffect, useState } from "react";
import { useToolContext } from "@tool-hub/shared-types/src/tool-context";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  useToast,
} from "@tool-hub/ui";
import { errorMessage, fmtDate, useApi } from "../api";

type Doc = { id: string; kind: string; lead_id: string; lead_name?: string; content: Record<string, unknown>; generated_by?: string; created_at?: string };

type Recipe = {
  id: string;
  name: string;
  description?: string;
  signal_types: string[];
  alert_types: string[];
  keywords: string[];
  min_score: number;
  auto_enroll: boolean;
  active: boolean;
  matched_total: number;
  enrolled_total: number;
  last_run_at?: string | null;
};

type Match = { id: string; recipe?: string; lead_name?: string; reason?: string; enrolled: boolean; note?: string; created_at?: string };

const DOC_BUTTONS = [
  { kind: "meeting_prep", path: "meeting-prep", label: "Meeting prep" },
  { kind: "playbook", path: "playbook", label: "Objection playbook" },
  { kind: "proposal", path: "proposal", label: "Proposal draft" },
] as const;

function List({ items }: { items?: unknown }) {
  if (!Array.isArray(items) || !items.length) return null;
  return (
    <ul className="list-disc pl-5 space-y-0.5 text-sm">
      {items.map((x, i) => (
        <li key={i}>{typeof x === "string" ? x : JSON.stringify(x)}</li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs uppercase text-text-muted mb-1">{title}</p>
      {children}
    </div>
  );
}

function DocView({ doc }: { doc: Doc }) {
  const c = doc.content as Record<string, unknown>;
  if (doc.kind === "meeting_prep") {
    return (
      <div className="space-y-3">
        <p className="text-sm font-semibold">{String(c.headline || "")}</p>
        <Section title="Company"><p className="text-sm">{String(c.company_snapshot || "")}</p></Section>
        <Section title="Why now"><p className="text-sm">{String(c.why_now || "")}</p></Section>
        {c.their_words ? <Section title="What they said"><p className="text-sm italic">&ldquo;{String(c.their_words)}&rdquo;</p></Section> : null}
        <Section title="Who you meet"><List items={c.who_you_meet} /></Section>
        <Section title="Goals for the call"><List items={c.goals} /></Section>
        <Section title="Agenda"><List items={c.agenda} /></Section>
        <Section title="Questions to ask"><List items={c.questions} /></Section>
        <Section title="Talking points"><List items={c.talking_points} /></Section>
        <Section title="Proof to bring"><List items={c.proof_to_bring} /></Section>
        <Section title="Watch out for"><List items={c.risks} /></Section>
        <Section title="Next step to propose"><p className="text-sm font-medium">{String(c.next_step || "")}</p></Section>
      </div>
    );
  }
  if (doc.kind === "playbook") {
    const objections = (c.objections as { objection: string; response: string; proof?: string }[]) || [];
    return (
      <div className="space-y-2">
        {objections.map((o, i) => (
          <div key={i} className="rounded-lg bg-surface-muted p-2 text-sm">
            <p className="font-medium">&ldquo;{o.objection}&rdquo;</p>
            <p className="text-text-secondary text-xs mt-0.5">Say: {o.response}</p>
            {o.proof ? <p className="text-text-muted text-xs">Show: {o.proof}</p> : null}
          </div>
        ))}
        <Section title="Golden rules"><List items={c.golden_rules} /></Section>
      </div>
    );
  }
  const approach = (c.approach as { phase: string; detail: string }[]) || [];
  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold">{String(c.title || "")}</p>
      <Section title="Summary"><p className="text-sm">{String(c.summary || "")}</p></Section>
      <Section title="Our understanding"><List items={c.our_understanding} /></Section>
      <Section title="Approach">
        <div className="space-y-1">
          {approach.map((a, i) => (
            <p key={i} className="text-sm"><span className="font-medium">{a.phase}:</span> {a.detail}</p>
          ))}
        </div>
      </Section>
      <Section title="Why us"><List items={c.why_us} /></Section>
      <Section title="Investment"><p className="text-sm">{String(c.investment || "")}</p></Section>
      <Section title="Next steps"><List items={c.next_steps} /></Section>
    </div>
  );
}

export function DealDocs({ leadId }: { leadId: string }) {
  const api = useApi();
  const { backendUrl } = useToolContext();
  const { toast } = useToast();
  const [docs, setDocs] = useState<Record<string, Doc>>({});
  const [open, setOpen] = useState<string>("meeting_prep");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ docs: Record<string, Doc> }>(`/deal/${leadId}`);
      setDocs(r.docs);
    } catch {
      setDocs({});
    }
  }, [api, leadId]);

  useEffect(() => {
    load();
  }, [load]);

  const make = async (path: string, kind: string) => {
    setBusy(kind);
    try {
      await api.post(`/deal/${leadId}/${path}`);
      setOpen(kind);
      await load();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const doc = docs[open];
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs uppercase text-text-muted mr-2">Deal room</p>
        {DOC_BUTTONS.map((b) => (
          <Button
            key={b.kind}
            size="sm"
            variant={open === b.kind ? "primary" : "outline"}
            disabled={busy === b.kind}
            onClick={() => (docs[b.kind] && open !== b.kind ? setOpen(b.kind) : make(b.path, b.kind))}
          >
            {busy === b.kind ? "Writing…" : docs[b.kind] ? b.label : `Write ${b.label.toLowerCase()}`}
          </Button>
        ))}
        {docs.proposal && (
          <Button size="sm" variant="ghost" asChild>
            <a href={`${backendUrl}/deal/${leadId}/proposal.pdf`} download>
              Download proposal PDF
            </a>
          </Button>
        )}
      </div>
      {docs.handoff && (
        <div className="rounded-lg border border-success/40 bg-success/5 p-3 text-sm space-y-1">
          <p className="font-medium">Hot reply hand-off</p>
          <p>{String(docs.handoff.content.summary || "")}</p>
          {docs.handoff.content.what_they_said ? (
            <p className="italic text-text-secondary">&ldquo;{String(docs.handoff.content.what_they_said)}&rdquo;</p>
          ) : null}
          <p className="text-xs">Next: {String(docs.handoff.content.recommended_next_step || "")}</p>
        </div>
      )}
      {doc ? (
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs text-text-muted">
            <span>{fmtDate(doc.created_at)} · {doc.generated_by === "llm" ? "AI" : "template"}</span>
            <button className="underline" onClick={() => make(DOC_BUTTONS.find((b) => b.kind === open)!.path, open)}>Rewrite</button>
          </div>
          <DocView doc={doc} />
        </div>
      ) : (
        <p className="text-xs text-text-muted">Pick a document to write it for this lead.</p>
      )}
    </div>
  );
}

export function HandoffList({ onPick }: { onPick: (leadId: string) => void }) {
  const api = useApi();
  const [items, setItems] = useState<Doc[]>([]);

  useEffect(() => {
    api.get<{ handoffs: Doc[] }>("/deal-handoffs?limit=10").then((r) => setItems(r.handoffs)).catch(() => setItems([]));
  }, [api]);

  if (!items.length) return null;
  return (
    <Card className="border-success/40">
      <CardHeader>
        <CardTitle>Hot replies handed to you</CardTitle>
        <CardDescription>Leads that replied interested in Reach Out. A meeting prep is already written for each.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((h) => (
          <button key={h.id} onClick={() => onPick(h.lead_id)} className="w-full text-left rounded-lg border border-border p-2 hover:border-primary">
            <div className="flex justify-between gap-2">
              <p className="text-sm font-medium">{h.lead_name}</p>
              <span className="text-xs text-text-muted">{fmtDate(h.created_at)}</span>
            </div>
            <p className="text-xs text-text-secondary">{String(h.content.summary || "")}</p>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

export function RecipesCard({ onChange }: { onChange?: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", keywords: "", signal_types: "", min_score: "50" });

  const load = useCallback(async () => {
    try {
      const [r, m] = await Promise.all([
        api.get<{ recipes: Recipe[] }>("/recipes"),
        api.get<{ matches: Match[] }>("/recipes/matches?limit=15"),
      ]);
      setRecipes(r.recipes);
      setMatches(m.matches);
    } catch (err) {
      toast(errorMessage(err));
    }
  }, [api, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async () => {
    setBusy("run");
    try {
      const { job_id } = await api.post<{ job_id: string }>("/recipes/run");
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Recipes failed");
      else toast(`${job.result.matched ?? 0} new matches, ${job.result.enrolled ?? 0} sent to Reach Out for approval.`, "success");
      load();
      onChange?.();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const update = async (r: Recipe, values: Partial<Recipe>) => {
    await api.patch(`/recipes/${r.id}`, values);
    load();
  };

  const add = async () => {
    if (!form.name) return;
    const split = (s: string) => s.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
    await api.post("/recipes", {
      name: form.name,
      keywords: split(form.keywords),
      signal_types: split(form.signal_types),
      alert_types: split(form.signal_types),
      min_score: parseFloat(form.min_score) || 0,
      auto_enroll: true,
    });
    setForm({ name: "", keywords: "", signal_types: "", min_score: "50" });
    toast("Recipe added.", "success");
    load();
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle>Signal recipes</CardTitle>
            <CardDescription>
              Saved rules like &ldquo;raised funding&rdquo; or &ldquo;hiring a CTO&rdquo;. When a lead matches, its first email is drafted in Reach Out
              and waits for your approval. Runs after every account scan.
            </CardDescription>
          </div>
          <Button onClick={run} disabled={!!busy}>{busy === "run" ? "Checking…" : "Run recipes now"}</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {recipes.map((r) => (
            <div key={r.id} className={`rounded-lg border border-border p-3 flex flex-wrap justify-between gap-2 ${r.active ? "" : "opacity-60"}`}>
              <div className="min-w-0">
                <p className="text-sm font-medium">{r.name}</p>
                {r.description && <p className="text-xs text-text-secondary">{r.description}</p>}
                <div className="flex flex-wrap gap-1 mt-1">
                  {[...r.signal_types, ...r.keywords].slice(0, 6).map((t) => <Badge key={t} variant="muted">{t}</Badge>)}
                  <Badge variant="outline">score ≥ {r.min_score}</Badge>
                </div>
                <p className="text-xs text-text-muted mt-1">
                  {r.matched_total} matched · {r.enrolled_total} sent to Reach Out · last run {fmtDate(r.last_run_at)}
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={r.auto_enroll} onChange={(e) => update(r, { auto_enroll: e.target.checked })} />
                  Send to Reach Out
                </label>
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={r.active} onChange={(e) => update(r, { active: e.target.checked })} />
                  On
                </label>
              </div>
            </div>
          ))}
        </div>
        <div className="grid md:grid-cols-4 gap-2 items-end">
          <div><Label>New recipe name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Hiring a CTO" /></div>
          <div><Label>Keywords (comma separated)</Label><Input value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="cto, head of engineering" /></div>
          <div><Label>Signal types</Label><Input value={form.signal_types} onChange={(e) => setForm({ ...form, signal_types: e.target.value })} placeholder="hiring, funding" /></div>
          <div className="flex gap-2 items-end">
            <div className="w-20"><Label>Min score</Label><Input type="number" value={form.min_score} onChange={(e) => setForm({ ...form, min_score: e.target.value })} /></div>
            <Button variant="outline" disabled={!form.name} onClick={add}>Add</Button>
          </div>
        </div>
        {matches.length > 0 && (
          <div>
            <p className="text-xs uppercase text-text-muted mb-1">Latest matches</p>
            <div className="space-y-1">
              {matches.map((m) => (
                <div key={m.id} className="flex flex-wrap justify-between gap-2 text-xs border-b border-border/60 py-1">
                  <span><span className="font-medium">{m.lead_name}</span> · {m.recipe} · {m.reason}</span>
                  <span className={m.enrolled ? "text-success" : "text-text-muted"}>{m.enrolled ? "In Reach Out" : m.note || "Matched"}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
