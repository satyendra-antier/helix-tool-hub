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
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Textarea,
  useToast,
} from "@tool-hub/ui";
import { errorMessage, useApi } from "../api";

type Partner = {
  id: string;
  name: string;
  website?: string;
  partner_type: string;
  services: string[];
  domains: string[];
  fit_score: number;
  fit_reasons: string[];
  verified: boolean;
  source: string;
  stage: string;
  contact_name?: string;
  contact_email?: string;
  notes?: string;
  referrals_received: number;
};

const STAGES = ["prospect", "talking", "signed", "dropped"];
const EMPTY_PARTNER = { name: "", website: "", partner_type: "consultancy", services: "", domains: "" };
const EMPTY_REFERRAL = { company_name: "", domain: "", description: "", contact_name: "", contact_email: "", track: "web2" };

const splitList = (v: string) => v.split(/[;,]/).map((s) => s.trim()).filter(Boolean);

export default function PartnersTab({ onChange }: { onChange: () => void }) {
  const api = useApi();
  const { toast } = useToast();
  const [partners, setPartners] = useState<Partner[]>([]);
  const [form, setForm] = useState(EMPTY_PARTNER);
  const [discovering, setDiscovering] = useState(false);
  const [referFor, setReferFor] = useState<Partner | null>(null);
  const [referral, setReferral] = useState(EMPTY_REFERRAL);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ partners: Partner[] }>("/partners");
      setPartners(r.partners);
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const discover = async () => {
    setDiscovering(true);
    try {
      const { job_id } = await api.post<{ job_id: string }>("/partners/discover", { per_domain: 4 });
      const job = await api.pollJob(job_id);
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Discovery failed");
      else if (job.result.note) toast(String(job.result.note));
      else toast(`Added ${job.result.added ?? 0} partner prospects`, "success");
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    } finally {
      setDiscovering(false);
    }
  };

  const addPartner = async () => {
    try {
      await api.post("/partners", {
        name: form.name.trim(),
        website: form.website || null,
        partner_type: form.partner_type,
        services: splitList(form.services),
        domains: splitList(form.domains),
      });
      setForm(EMPTY_PARTNER);
      load();
      onChange();
    } catch (err) {
      toast(errorMessage(err));
    }
  };

  const setStage = async (id: string, stage: string) => {
    await api.patch(`/partners/${id}`, { stage });
    load();
    onChange();
  };

  const submitReferral = async () => {
    if (!referFor) return;
    try {
      await api.post(`/partners/${referFor.id}/referrals`, {
        ...referral,
        domain: referral.domain || null,
        contact_name: referral.contact_name || null,
        contact_email: referral.contact_email || null,
      });
      toast(`Referral from ${referFor.name} added to your leads`, "success");
      setReferFor(null);
      setReferral(EMPTY_REFERRAL);
      load();
    } catch (err) {
      toast(errorMessage(err));
    }
  };

  return (
    <div className="space-y-6">
      {error && <Alert variant="danger" title="Failed to load partners">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Referral partners</CardTitle>
          <CardDescription>
            Firms that already sell to your buyers but don&apos;t build what you build. AI suggestions are scoped to the
            domains you can win (GO and CONDITIONAL verdicts). Check each one before reaching out.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
            <div>
              <Label>Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>Website</Label>
              <Input value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
            </div>
            <div>
              <Label>Type</Label>
              <select
                className="h-9 w-full rounded-lg border border-border bg-surface px-2 text-sm"
                value={form.partner_type}
                onChange={(e) => setForm({ ...form, partner_type: e.target.value })}
              >
                {["consultancy", "integrator", "agency", "vc_platform", "accelerator", "other"].map((t) => (
                  <option key={t} value={t}>
                    {t.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>Services (; separated)</Label>
              <Input value={form.services} onChange={(e) => setForm({ ...form, services: e.target.value })} />
            </div>
            <div>
              <Label>Domains (; separated)</Label>
              <Input value={form.domains} onChange={(e) => setForm({ ...form, domains: e.target.value })} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={addPartner} disabled={!form.name.trim()}>
              Add partner
            </Button>
            <Button size="sm" variant="outline" onClick={discover} disabled={discovering}>
              {discovering ? "Finding partners…" : "Suggest partners with AI"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {partners.length === 0 ? (
        <EmptyState title="No partners yet" description="Add partners you know, or let AI suggest candidates for your winnable domains." />
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2">
          {STAGES.map((stage) => (
            <div key={stage} className="min-w-[260px] flex-1 rounded-xl border border-border bg-surface p-3">
              <h3 className="text-xs uppercase text-text-muted mb-3 font-medium">
                {stage} ({partners.filter((p) => p.stage === stage).length})
              </h3>
              <div className="space-y-2">
                {partners
                  .filter((p) => p.stage === stage)
                  .map((p) => (
                    <div key={p.id} className="rounded-lg border border-border bg-panel-raised p-3 space-y-2">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{p.name}</p>
                          {p.website && (
                            <a href={p.website.startsWith("http") ? p.website : `https://${p.website}`} target="_blank" rel="noreferrer" className="text-xs text-primary truncate block">
                              {p.website}
                            </a>
                          )}
                        </div>
                        <Badge variant="outline">{p.fit_score.toFixed(0)}</Badge>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        <Badge variant="muted">{p.partner_type.replace("_", " ")}</Badge>
                        {p.source === "ai_suggested" && <Badge variant={p.verified ? "success" : "warning"}>{p.verified ? "AI · site verified" : "AI · unverified"}</Badge>}
                        {p.referrals_received > 0 && <Badge variant="success">{p.referrals_received} referrals</Badge>}
                      </div>
                      {p.domains.length > 0 && <p className="text-xs text-text-muted">{p.domains.join(", ")}</p>}
                      {p.fit_reasons.length > 0 && <p className="text-xs text-text-secondary">{p.fit_reasons.join(" · ")}</p>}
                      {p.notes && <p className="text-xs text-text-secondary italic">{p.notes}</p>}
                      <div className="flex flex-wrap gap-1">
                        {STAGES.filter((s) => s !== stage).map((s) => (
                          <Button key={s} size="sm" variant="ghost" onClick={() => setStage(p.id, s)}>
                            → {s}
                          </Button>
                        ))}
                        {stage !== "dropped" && (
                          <Button size="sm" variant="secondary" onClick={() => setReferFor(p)}>
                            Log referral
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <Sheet open={!!referFor} onOpenChange={(o) => !o && setReferFor(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Referral from {referFor?.name}</SheetTitle>
          </SheetHeader>
          <div className="space-y-3 mt-4">
            <p className="text-xs text-text-secondary">
              This adds the company to your leads (step 3), tagged as a partner referral. It gets scored like every other lead.
            </p>
            <div>
              <Label>Company *</Label>
              <Input value={referral.company_name} onChange={(e) => setReferral({ ...referral, company_name: e.target.value })} />
            </div>
            <div>
              <Label>Company website / domain</Label>
              <Input value={referral.domain} onChange={(e) => setReferral({ ...referral, domain: e.target.value })} />
            </div>
            <div>
              <Label>Track</Label>
              <select
                className="h-9 w-full rounded-lg border border-border bg-surface px-2 text-sm"
                value={referral.track}
                onChange={(e) => setReferral({ ...referral, track: e.target.value })}
              >
                {["web2", "web3", "ai", "government"].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label>What do they need?</Label>
              <Textarea rows={4} value={referral.description} onChange={(e) => setReferral({ ...referral, description: e.target.value })} />
            </div>
            <div>
              <Label>Contact name</Label>
              <Input value={referral.contact_name} onChange={(e) => setReferral({ ...referral, contact_name: e.target.value })} />
            </div>
            <div>
              <Label>Contact email</Label>
              <Input value={referral.contact_email} onChange={(e) => setReferral({ ...referral, contact_email: e.target.value })} />
            </div>
            <Button onClick={submitReferral} disabled={!referral.company_name.trim()}>
              Add referral as lead
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
