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
  Input,
  Label,
  Textarea,
  useToast,
} from "@tool-hub/ui";
import { errorMessage, useApi } from "../api";

type Expert = {
  id: string;
  full_name: string;
  title?: string;
  organization?: string;
  email?: string;
  linkedin_url?: string;
  domains: string[];
  companies: string[];
  relationship_strength: number;
};

type Intro = {
  id: string;
  lead_id: string;
  lead_name?: string;
  expert_name?: string;
  expert_email?: string;
  expert_linkedin?: string;
  match_score: number;
  rationale?: string;
  subject?: string;
  body?: string;
  status: string;
};

const STATUS_VARIANT: Record<string, "default" | "primary" | "success" | "warning" | "danger"> = {
  draft: "warning",
  approved: "primary",
  requested: "primary",
  introduced: "success",
  declined: "danger",
};

const EMPTY_FORM = { full_name: "", title: "", organization: "", email: "", linkedin_url: "", domains: "", companies: "", relationship_strength: "3" };

const CSV_HINT = "full_name,title,organization,email,linkedin_url,domains,companies,relationship_strength,notes\nJane Doe,Partner,Acme VC,jane@acme.vc,,DeFi;Stablecoin & Payments Engineering,Circle;Fireblocks,4,Met at Token2049";

const splitList = (v: string) => v.split(/[;,]/).map((s) => s.trim()).filter(Boolean);

export default function ExpertsTab({ onChange }: { onChange: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [experts, setExperts] = useState<Expert[]>([]);
  const [intros, setIntros] = useState<Intro[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [csv, setCsv] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [matching, setMatching] = useState(false);
  const [editing, setEditing] = useState<Record<string, { subject: string; body: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [e, i] = await Promise.all([
        api.get<{ experts: Expert[] }>("/experts"),
        api.get<{ intros: Intro[] }>("/intros"),
      ]);
      setExperts(e.experts);
      setIntros(i.intros);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const addExpert = async () => {
    if (!form.full_name.trim()) return;
    try {
      await api.post("/experts", {
        full_name: form.full_name.trim(),
        title: form.title || null,
        organization: form.organization || null,
        email: form.email || null,
        linkedin_url: form.linkedin_url || null,
        domains: splitList(form.domains),
        companies: splitList(form.companies),
        relationship_strength: Math.min(5, Math.max(1, parseInt(form.relationship_strength, 10) || 3)),
      });
      setForm(EMPTY_FORM);
      toast("Expert added", "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    }
  };

  const importCsv = async () => {
    try {
      const r = await api.post<{ added: number; skipped: number }>("/experts/import-csv", { csv });
      toast(`Imported ${r.added} experts${r.skipped ? `, skipped ${r.skipped}` : ""}`, "success");
      setCsv("");
      setShowImport(false);
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    }
  };

  const removeExpert = async (id: string) => {
    await api.del(`/experts/${id}`);
    load();
    onChange();
  };

  const findIntros = async () => {
    setMatching(true);
    try {
      const { job_id } = await api.post<{ job_id: string }>("/experts/match", { lead_limit: 50 });
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Matching failed");
      else toast(`${job.result.intros_created ?? 0} new intro drafts from ${job.result.leads_checked ?? 0} leads`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setMatching(false);
    }
  };

  const updateIntro = async (id: string, patch: Partial<Intro>) => {
    try {
      await api.patch(`/intros/${id}`, patch);
      setEditing((e) => {
        const next = { ...e };
        delete next[id];
        return next;
      });
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger" title="Failed to load experts">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>People who can introduce you</CardTitle>
          <CardDescription>
            Advisors, investors, ex-colleagues and clients who can open doors. List the companies they know and the
            domains they work in. Matching uses both.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div>
              <Label>Full name *</Label>
              <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </div>
            <div>
              <Label>Title</Label>
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <Label>Organization</Label>
              <Input value={form.organization} onChange={(e) => setForm({ ...form, organization: e.target.value })} />
            </div>
            <div>
              <Label>Relationship (1-5)</Label>
              <Input
                type="number"
                min="1"
                max="5"
                value={form.relationship_strength}
                onChange={(e) => setForm({ ...form, relationship_strength: e.target.value })}
              />
            </div>
            <div>
              <Label>Email</Label>
              <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <Label>LinkedIn URL</Label>
              <Input value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} />
            </div>
            <div>
              <Label>Domains (; separated)</Label>
              <Input value={form.domains} onChange={(e) => setForm({ ...form, domains: e.target.value })} />
            </div>
            <div>
              <Label>Companies they know (; separated)</Label>
              <Input value={form.companies} onChange={(e) => setForm({ ...form, companies: e.target.value })} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={addExpert} disabled={!form.full_name.trim()}>
              Add expert
            </Button>
            <Button size="sm" variant="outline" onClick={() => setShowImport((s) => !s)}>
              {showImport ? "Hide CSV import" : "Import CSV"}
            </Button>
          </div>
          {showImport && (
            <div className="space-y-2">
              <Textarea rows={5} value={csv} placeholder={CSV_HINT} onChange={(e) => setCsv(e.target.value)} />
              <Button size="sm" onClick={importCsv} disabled={!csv.trim()}>
                Import
              </Button>
            </div>
          )}

          {experts.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-text-muted text-left">
                  <tr>
                    <th className="py-2 pr-3">Name</th>
                    <th className="py-2 pr-3">Domains</th>
                    <th className="py-2 pr-3">Knows</th>
                    <th className="py-2 pr-3">Strength</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {experts.map((e) => (
                    <tr key={e.id} className="border-t border-border align-top">
                      <td className="py-2 pr-3">
                        <p className="font-medium">{e.full_name}</p>
                        <p className="text-xs text-text-muted">{[e.title, e.organization].filter(Boolean).join(" · ")}</p>
                      </td>
                      <td className="py-2 pr-3 text-xs">{e.domains.join(", ") || "—"}</td>
                      <td className="py-2 pr-3 text-xs">{e.companies.join(", ") || "—"}</td>
                      <td className="py-2 pr-3 text-xs">{e.relationship_strength}/5</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => removeExpert(e.id)}>
                          Remove
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Intro requests</h3>
          <p className="text-xs text-text-muted">
            Drafts addressed to your expert, asking for the intro. Review, edit and approve each one. Nothing is sent
            automatically.
          </p>
        </div>
        <Button onClick={findIntros} disabled={matching || experts.length === 0}>
          {matching ? "Matching…" : "Find intro paths for top leads"}
        </Button>
      </div>

      {intros.length === 0 ? (
        <EmptyState
          title="No intro paths yet"
          description={
            experts.length === 0
              ? "Add experts first, then match them against your scored leads."
              : "Run matching to find which experts can introduce you to your top leads."
          }
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {intros.map((intro) => {
            const draft = editing[intro.id];
            return (
              <Card key={intro.id}>
                <CardContent className="py-4 space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">{intro.lead_name}</p>
                      <p className="text-xs text-text-muted">
                        via {intro.expert_name}
                        {intro.expert_email ? ` · ${intro.expert_email}` : ""}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Badge variant="outline">{intro.match_score.toFixed(0)}</Badge>
                      <Badge variant={STATUS_VARIANT[intro.status] || "default"}>{intro.status}</Badge>
                    </div>
                  </div>
                  {intro.rationale && <p className="text-xs text-text-secondary">Why: {intro.rationale}</p>}
                  {draft ? (
                    <div className="space-y-2">
                      <Input value={draft.subject} onChange={(e) => setEditing({ ...editing, [intro.id]: { ...draft, subject: e.target.value } })} />
                      <Textarea rows={6} value={draft.body} onChange={(e) => setEditing({ ...editing, [intro.id]: { ...draft, body: e.target.value } })} />
                    </div>
                  ) : (
                    <div className="rounded-lg bg-surface-muted p-3 text-xs whitespace-pre-wrap">
                      <p className="font-medium mb-1">{intro.subject}</p>
                      {intro.body}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {draft ? (
                      <Button size="sm" onClick={() => updateIntro(intro.id, draft)}>
                        Save
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setEditing({ ...editing, [intro.id]: { subject: intro.subject || "", body: intro.body || "" } })}
                      >
                        Edit
                      </Button>
                    )}
                    {intro.status === "draft" && (
                      <Button size="sm" onClick={() => updateIntro(intro.id, { status: "approved" })}>
                        Approve
                      </Button>
                    )}
                    {intro.status === "approved" && (
                      <Button size="sm" variant="secondary" onClick={() => updateIntro(intro.id, { status: "requested" })}>
                        Mark requested
                      </Button>
                    )}
                    {intro.status === "requested" && (
                      <Button size="sm" variant="secondary" onClick={() => updateIntro(intro.id, { status: "introduced" })}>
                        Mark introduced
                      </Button>
                    )}
                    {intro.status !== "declined" && intro.status !== "introduced" && (
                      <Button size="sm" variant="ghost" onClick={() => updateIntro(intro.id, { status: "declined" })}>
                        Decline
                      </Button>
                    )}
                    {intro.expert_email && (
                      <Button size="sm" variant="ghost" asChild>
                        <a href={`mailto:${intro.expert_email}?subject=${encodeURIComponent(intro.subject || "")}&body=${encodeURIComponent(intro.body || "")}`}>
                          Open in email
                        </a>
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
