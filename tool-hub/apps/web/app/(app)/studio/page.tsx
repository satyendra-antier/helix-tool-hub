"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { DEFAULT_PIPELINE_CONFIG, type PipelineConfig } from "@tool-hub/shared-types";
import {
  Button,
  PageHeader,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Input,
  Label,
  StatusDot,
  Card,
  CardContent,
} from "@tool-hub/ui";
import { getModuleTheme } from "@tool-hub/ui";
import { Save, Wand2 } from "lucide-react";
import { getStep } from "@/lib/journey";

const NODE_NAMES: Record<string, string> = {
  "market-depth": "Find Demand",
  "build-readiness": "Check Fit",
  "lead-intelligence": "Find Leads",
  "growth-pillars": "Win Leads",
  "outreach-autopilot": "Reach Out",
  "video-scraper": "Proof Library",
  hiring: "Hiring data",
  capital: "Funding data",
  github: "GitHub data",
};

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  hiring: { x: 0, y: 40 },
  capital: { x: 0, y: 120 },
  github: { x: 0, y: 200 },
  "market-depth": { x: 280, y: 120 },
  "build-readiness": { x: 560, y: 120 },
  "lead-intelligence": { x: 840, y: 120 },
  "video-scraper": { x: 560, y: 280 },
  "growth-pillars": { x: 1120, y: 120 },
  "outreach-autopilot": { x: 1400, y: 120 },
};

function ModuleNode({ data }: { data: { label: string; moduleId: string; selected: boolean } }) {
  const theme = getModuleTheme(data.moduleId);
  return (
    <div
      className="rounded-lg border-2 bg-surface px-4 py-3 min-w-[140px] shadow-sm"
      style={{ borderColor: data.selected ? theme.accent : "var(--border)" }}
    >
      <Handle type="target" position={Position.Left} />
      <p className="text-xs text-text-muted uppercase">{getStep(data.moduleId) ? "AI step" : "Extra"}</p>
      <p className="text-sm font-semibold">{data.label}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function SourceNode({ data }: { data: { label: string } }) {
  return (
    <div className="rounded-md border border-border bg-surface-muted px-3 py-2 text-xs font-medium">
      <Handle type="source" position={Position.Right} />
      {data.label}
    </div>
  );
}

const nodeTypes = { module: ModuleNode, source: SourceNode };

function buildGraph(selectedId: string | null): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [
    { id: "hiring", type: "source", position: NODE_POSITIONS.hiring, data: { label: "Hiring data" } },
    { id: "capital", type: "source", position: NODE_POSITIONS.capital, data: { label: "Funding data" } },
    { id: "github", type: "source", position: NODE_POSITIONS.github, data: { label: "GitHub" } },
    {
      id: "market-depth",
      type: "module",
      position: NODE_POSITIONS["market-depth"],
      data: { label: "1 · Find Demand", moduleId: "market-depth-analyzer", selected: selectedId === "market-depth" },
    },
    {
      id: "build-readiness",
      type: "module",
      position: NODE_POSITIONS["build-readiness"],
      data: { label: "2 · Check Fit", moduleId: "build-readiness", selected: selectedId === "build-readiness" },
    },
    {
      id: "lead-intelligence",
      type: "module",
      position: NODE_POSITIONS["lead-intelligence"],
      data: { label: "3 · Find Leads", moduleId: "lead-intelligence", selected: selectedId === "lead-intelligence" },
    },
    {
      id: "video-scraper",
      type: "module",
      position: NODE_POSITIONS["video-scraper"],
      data: { label: "Proof Library", moduleId: "video-scraper", selected: selectedId === "video-scraper" },
    },
    {
      id: "growth-pillars",
      type: "module",
      position: NODE_POSITIONS["growth-pillars"],
      data: { label: "4 · Win Leads", moduleId: "growth-pillars", selected: selectedId === "growth-pillars" },
    },
    {
      id: "outreach-autopilot",
      type: "module",
      position: NODE_POSITIONS["outreach-autopilot"],
      data: { label: "5 · Reach Out", moduleId: "outreach-autopilot", selected: selectedId === "outreach-autopilot" },
    },
  ];
  const edges: Edge[] = [
    { id: "e1", source: "hiring", target: "market-depth", animated: true },
    { id: "e2", source: "capital", target: "market-depth", animated: true },
    { id: "e3", source: "github", target: "market-depth", animated: true },
    { id: "e4", source: "market-depth", target: "build-readiness", animated: true },
    { id: "e5", source: "build-readiness", target: "lead-intelligence", animated: true },
    { id: "e6", source: "video-scraper", target: "build-readiness", animated: true },
    { id: "e7", source: "market-depth", target: "lead-intelligence", animated: true },
    { id: "e8", source: "lead-intelligence", target: "growth-pillars", animated: true },
    { id: "e9", source: "growth-pillars", target: "outreach-autopilot", animated: true },
  ];
  return { nodes, edges };
}

export default function StudioPage() {
  const [config, setConfig] = useState<PipelineConfig>(DEFAULT_PIPELINE_CONFIG);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [runSteps, setRunSteps] = useState<Array<{ id: string; label: string; status: string }>>([]);
  const [saving, setSaving] = useState(false);

  const loadConfig = useCallback(async () => {
    const res = await fetch("/api/hub/pipeline/config");
    if (res.ok) {
      const { config: c } = await res.json();
      setConfig(c);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const { nodes, edges } = buildGraph(selectedNode);

  async function saveConfig() {
    setSaving(true);
    await fetch("/api/hub/pipeline/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    });
    setSaving(false);
  }

  async function runPipeline() {
    const res = await fetch("/api/hub/pipeline/run", { method: "POST" });
    const { runId } = await res.json();
    if (!runId) return;
    let done = false;
    while (!done) {
      await new Promise((r) => setTimeout(r, 1500));
      const s = await fetch(`/api/hub/pipeline/run?runId=${runId}`);
      const { run } = await s.json();
      setRunSteps(run?.steps || []);
      if (run?.status === "completed" || run?.status === "failed") done = true;
    }
  }

  const nodeConfig = selectedNode ? (config.nodes[selectedNode] as Record<string, unknown>) : null;

  return (
    <div className="space-y-4 pb-8">
      <PageHeader
        title="Automation"
        description="See how the 4 steps connect and tune the settings AI uses when it runs them all. Click a step to change it."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={saveConfig} disabled={saving}>
              <Save className="h-4 w-4 mr-1" />
              Save
            </Button>
            <Button size="sm" onClick={runPipeline}>
              <Wand2 className="h-4 w-4 mr-1" />
              Run all steps with AI
            </Button>
          </div>
        }
      />

      {runSteps.length > 0 ? (
        <Card>
          <CardContent className="py-3 flex flex-wrap gap-4">
            {runSteps.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-sm">
                <StatusDot
                  variant={s.status === "done" ? "success" : s.status === "error" ? "danger" : "warning"}
                />
                {s.label}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="h-[480px] rounded-xl border border-border bg-surface overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, n) => setSelectedNode(n.id)}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      <Sheet open={!!selectedNode} onOpenChange={(o) => !o && setSelectedNode(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Settings: {(selectedNode && NODE_NAMES[selectedNode]) || selectedNode}</SheetTitle>
          </SheetHeader>
          {selectedNode === "market-depth" && nodeConfig ? (
            <div className="space-y-4 mt-4">
              {Object.entries((nodeConfig.weights as Record<string, number>) || {}).map(([k, v]) => (
                <div key={k}>
                  <Label>{k.replace(/_/g, " ")}</Label>
                  <Input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={v}
                    onChange={(e) => {
                      const weights = { ...(nodeConfig.weights as Record<string, number>), [k]: parseFloat(e.target.value) };
                      setConfig({
                        ...config,
                        nodes: { ...config.nodes, "market-depth": { ...nodeConfig, weights } },
                      });
                    }}
                  />
                </div>
              ))}
            </div>
          ) : null}
          {selectedNode === "lead-intelligence" && nodeConfig ? (
            <div className="space-y-4 mt-4">
              <div>
                <Label>Min market score</Label>
                <Input
                  type="number"
                  value={(nodeConfig.minMarketScore as number) || 40}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      nodes: {
                        ...config.nodes,
                        "lead-intelligence": { ...nodeConfig, minMarketScore: parseInt(e.target.value, 10) },
                      },
                    })
                  }
                />
              </div>
            </div>
          ) : null}
          {selectedNode === "growth-pillars" ? (
            <div className="space-y-4 mt-4">
              {(
                [
                  ["watchlistSize", "Accounts to watch", 25],
                  ["minLeadScore", "Min lead score", 40],
                  ["advisoryTopN", "Leads to coach per run", 10],
                ] as const
              ).map(([key, label, fallback]) => {
                const gp = (nodeConfig || DEFAULT_PIPELINE_CONFIG.nodes["growth-pillars"]) as Record<string, unknown>;
                return (
                  <div key={key}>
                    <Label>{label}</Label>
                    <Input
                      type="number"
                      min="0"
                      value={(gp[key] as number | undefined) ?? fallback}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          nodes: {
                            ...config.nodes,
                            "growth-pillars": { ...gp, [key]: parseInt(e.target.value, 10) || 0 },
                          },
                        })
                      }
                    />
                  </div>
                );
              })}
            </div>
          ) : null}
          {selectedNode === "outreach-autopilot" ? (
            <div className="space-y-4 mt-4">
              <p className="text-sm text-text-secondary">
                A full run only drafts first emails. They wait for your approval in Reach Out before anything is sent.
              </p>
              {(
                [
                  ["draftForTopN", "First emails to draft per run", 10],
                  ["minLeadScore", "Min lead score", 60],
                ] as const
              ).map(([key, label, fallback]) => {
                const oc = (nodeConfig || DEFAULT_PIPELINE_CONFIG.nodes["outreach-autopilot"]) as Record<string, unknown>;
                return (
                  <div key={key}>
                    <Label>{label}</Label>
                    <Input
                      type="number"
                      min="0"
                      value={(oc[key] as number | undefined) ?? fallback}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          nodes: {
                            ...config.nodes,
                            "outreach-autopilot": { ...oc, [key]: parseInt(e.target.value, 10) || 0 },
                          },
                        })
                      }
                    />
                  </div>
                );
              })}
            </div>
          ) : null}
          {selectedNode && !["market-depth", "lead-intelligence", "growth-pillars", "outreach-autopilot"].includes(selectedNode) ? (
            <p className="text-sm text-text-secondary mt-4">
              Find Demand, Find Leads, Win Leads and Reach Out have settings you can change here. This step uses its own defaults.
            </p>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
