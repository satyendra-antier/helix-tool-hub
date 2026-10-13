"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  useToast,
} from "@tool-hub/ui";
import { BellRing, Handshake, Lightbulb, Search, Users, Wand2 } from "lucide-react";
import { errorMessage, useApi } from "./api";
import ExpertsTab from "./tabs/experts";
import InsiderTab from "./tabs/insider";
import PartnersTab from "./tabs/partners";
import VisibilityTab from "./tabs/visibility";
import AdvisoryTab from "./tabs/advisory";

type Status = {
  upstream: Record<string, boolean>;
  llm_available: boolean;
  counts: Record<string, number>;
  visibility_share: number | null;
};

const PILLARS = [
  {
    value: "experts",
    label: "Warm Intros",
    icon: Users,
    help: "Add people you know. AI matches them to your best leads and drafts an intro email for you to approve.",
  },
  {
    value: "insider",
    label: "Account Watch",
    icon: BellRing,
    help: "AI watches your top leads and alerts you when something changes: funding, hiring, news or a tender deadline.",
  },
  {
    value: "partners",
    label: "Partners",
    icon: Handshake,
    help: "Find agencies and consultancies that can refer clients to you, and track each one from first talk to signed.",
  },
  {
    value: "visibility",
    label: "AI Search Rank",
    icon: Search,
    help: "See whether ChatGPT and Perplexity recommend your company when buyers ask, and who they recommend instead.",
  },
  {
    value: "advisory",
    label: "Deal Coach",
    icon: Lightbulb,
    help: "For each lead, AI tells you the best next move, what to say, likely objections and how risky the deal is.",
  },
] as const;

export default function GrowthPillarsPanel() {
  const api = useApi();
  const { toast } = useToast();
  const [tab, setTab] = useState<string>("experts");
  const [status, setStatus] = useState<Status | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await api.get<Status>("/status"));
      setStatusError(null);
    } catch (e) {
      setStatusError(errorMessage(e));
    }
  }, [api]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const runAll = async () => {
    setRunning("starting");
    try {
      const { job_id } = await api.post<{ job_id: string }>("/run", {});
      const job = await api.pollJob(job_id, (j) => setRunning(String(j.progress?.step || j.status)));
      if (job.status === "failed") toast(job.error?.split("\n")[0] || "Run failed");
      else toast("Your leads are warmed up", "success");
    } catch (e) {
      toast(errorMessage(e));
    } finally {
      setRunning(null);
      loadStatus();
    }
  };

  const leadsUp = status?.upstream?.["lead-intelligence"];
  const c = status?.counts || {};

  return (
    <div className="space-y-6">
      {statusError && (
        <Alert variant="danger" title="Win Leads service isn't reachable">
          It may still be starting up. Try again in a minute. ({statusError})
        </Alert>
      )}
      {status && !leadsUp && (
        <Alert variant="warning" title="Find Leads (step 3) is offline">
          This step works on the leads from step 3. Start it and find leads first.
        </Alert>
      )}
      {status && !status.llm_available && (
        <Alert variant="warning" title="AI key missing">
          Without an OpenAI key, matching, partner ideas, AI search checks and coaching use simple rules. Add
          OPENAI_API_KEY in Settings for full AI results.
        </Alert>
      )}

      <Card className="accent-strip">
        <CardContent className="py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge variant="outline">{c.experts ?? 0} people you know</Badge>
            <Badge variant={c.intros_pending ? "primary" : "outline"}>{c.intros_pending ?? 0} intros to review</Badge>
            <Badge variant="outline">{c.watched_accounts ?? 0} accounts watched</Badge>
            <Badge variant={c.unread_alerts ? "warning" : "outline"}>{c.unread_alerts ?? 0} new alerts</Badge>
            <Badge variant="outline">{c.partners ?? 0} partners</Badge>
            <Badge variant="outline">
              AI search rank{" "}
              {status?.visibility_share != null ? `${Math.round(status.visibility_share * 100)}%` : "—"}
            </Badge>
            <Badge variant="outline">{c.advice ?? 0} deal plans</Badge>
          </div>
          <Button onClick={runAll} disabled={!!running}>
            <Wand2 className="h-4 w-4 mr-1.5" />
            {running ? `AI is working: ${running.replace(/_/g, " ")}…` : "Warm up my leads with AI"}
          </Button>
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex-wrap h-auto">
          {PILLARS.map((p) => (
            <TabsTrigger key={p.value} value={p.value} className="gap-1.5">
              <p.icon className="h-4 w-4" />
              {p.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <p className="mt-3 text-sm text-text-secondary">
          {PILLARS.find((p) => p.value === tab)?.help}
        </p>
        <TabsContent value="experts">
          <ExpertsTab onChange={loadStatus} />
        </TabsContent>
        <TabsContent value="insider">
          <InsiderTab onChange={loadStatus} />
        </TabsContent>
        <TabsContent value="partners">
          <PartnersTab onChange={loadStatus} />
        </TabsContent>
        <TabsContent value="visibility">
          <VisibilityTab onChange={loadStatus} />
        </TabsContent>
        <TabsContent value="advisory">
          <AdvisoryTab onChange={loadStatus} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
