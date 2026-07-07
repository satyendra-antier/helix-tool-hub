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
import { Play, Save } from "lucide-react";

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  hiring: { x: 0, y: 40 },
  capital: { x: 0, y: 120 },
  github: { x: 0, y: 200 },
  "market-depth": { x: 280, y: 120 },
  "build-readiness": { x: 560, y: 120 },
  "lead-intelligence": { x: 840, y: 120 },
  "video-scraper": { x: 560, y: 280 },
};

function ModuleNode({ data }: { data: { label: string; moduleId: string; selected: boolean } }) {
  const theme = getModuleTheme(data.moduleId);
  return (
    <div
      className="rounded-lg border-2 bg-surface px-4 py-3 min-w-[140px] shadow-sm"
      style={{ borderColor: data.selected ? theme.accent : "var(--border)" }}
    >
      <Handle type="target" position={Position.Left} />
      <p className="text-xs text-text-muted uppercase">{data.moduleId}</p>
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
    { id: "hiring", type: "source", position: NODE_POSITIONS.hiring, data: { label: "Hiring APIs" } },
    { id: "capital", type: "source", position: NODE_POSITIONS.capital, data: { label: "DefiLlama" } },
    { id: "github", type: "source", position: NODE_POSITIONS.github, data: { label: "GitHub" } },
    {
      id: "market-depth",
      type: "module",
      position: NODE_POSITIONS["market-depth"],
      data: { label: "Market Depth", moduleId: "market-depth-analyzer", selected: selectedId === "market-depth" },
    },
    {
      id: "build-readiness",
      type: "module",
      position: NODE_POSITIONS["build-readiness"],
      data: { label: "Build Readiness", moduleId: "build-readiness", selected: selectedId === "build-readiness" },
    },
    {
      id: "lead-intelligence",
      type: "module",
      position: NODE_POSITIONS["lead-intelligence"],
      data: { label: "Lead Intelligence", moduleId: "lead-intelligence", selected: selectedId === "lead-intelligence" },
    },
    {
      id: "video-scraper",
      type: "module",
      position: NODE_POSITIONS["video-scraper"],
      data: { label: "Video Scraper", moduleId: "video-scraper", selected: selectedId === "video-scraper" },
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
        title="Pipeline Studio"
        description="Configure the revenue flywheel template — topology is fixed; tune weights, domains, and thresholds."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={saveConfig} disabled={saving}>
              <Save className="h-4 w-4 mr-1" />
              Save
            </Button>
            <Button size="sm" onClick={runPipeline}>
              <Play className="h-4 w-4 mr-1" />
              Run flywheel
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
            <SheetTitle>Configure {selectedNode}</SheetTitle>
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
          {selectedNode && !["market-depth", "lead-intelligence"].includes(selectedNode) ? (
            <p className="text-sm text-text-secondary mt-4">
              Select Market Depth or Lead Intelligence to edit template parameters. Other nodes use module defaults.
            </p>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
