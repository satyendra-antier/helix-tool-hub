import Link from "next/link";
import { ArrowRight, Compass, Film, Radar, TrendingUp } from "lucide-react";
import { loadToolRegistry } from "@/lib/registry";
import { Button } from "@tool-hub/ui";
import { getModuleTheme } from "@tool-hub/ui";
import { FlywheelDiagram } from "./flywheel-diagram";
import { ComparisonTable } from "./comparison-table";

const ICONS: Record<string, React.ReactNode> = {
  film: <Film className="w-5 h-5" />,
  "trending-up": <TrendingUp className="w-5 h-5" />,
  radar: <Radar className="w-5 h-5" />,
  compass: <Compass className="w-5 h-5" />,
};

const INTEGRATIONS = ["Adzuna", "DefiLlama", "GitHub", "Grants.gov", "Hunter", "RemoteOK", "OpenAI"];

export default function LandingPage() {
  const tools = loadToolRegistry();

  return (
    <div className="bg-surface">
      <section className="border-b border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-4">
              Revenue Intelligence Engine
            </p>
            <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-text-primary leading-tight">
              Know where to sell. Win what you can deliver.
            </h1>
            <p className="mt-5 text-lg text-text-secondary leading-relaxed max-w-xl">
              A deterministic operating system for technical services firms — live market scoring,
              cited build verdicts, and a qualified lead pipeline in one closed loop.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link href="/login">
                  Open platform
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/methodology">See methodology</Link>
              </Button>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-6 shadow-sm">
            <p className="text-xs font-medium text-text-muted uppercase mb-4">Command center preview</p>
            <div className="grid grid-cols-2 gap-3 mb-4">
              {[
                { label: "Top domain", value: "Stablecoin" },
                { label: "GO verdicts", value: "8 / 12" },
                { label: "Pipeline leads", value: "142" },
                { label: "Proof assets", value: "86 caps" },
              ].map((k) => (
                <div key={k.label} className="rounded-lg border border-border bg-surface p-3">
                  <p className="text-[10px] text-text-muted uppercase">{k.label}</p>
                  <p className="text-lg font-semibold mt-1">{k.value}</p>
                </div>
              ))}
            </div>
            <FlywheelDiagram className="w-full h-auto" />
          </div>
        </div>
      </section>

      <section className="border-b border-border bg-surface-muted/40">
        <div className="max-w-6xl mx-auto px-4 py-10 grid grid-cols-2 md:grid-cols-4 gap-6 text-center md:text-left">
          {[
            { v: "12", l: "Scored market domains" },
            { v: "5", l: "Weighted live signals" },
            { v: "4", l: "Intelligence modules" },
            { v: "GO", l: "Cited verdict framework" },
          ].map((s) => (
            <div key={s.l}>
              <p className="text-2xl font-semibold text-text-primary">{s.v}</p>
              <p className="text-sm text-text-secondary mt-1">{s.l}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="product" className="py-20 border-b border-border">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-2xl font-semibold text-text-primary">One platform. Four intelligence engines.</h2>
          <p className="mt-3 text-text-secondary max-w-2xl">
            Market heat and company capability measured in the same system — not separate analyst reports and CRM lists.
          </p>
          <div className="mt-10 grid md:grid-cols-2 gap-5">
            {tools.map((tool) => {
              const theme = getModuleTheme(tool.id);
              return (
                <div
                  key={tool.id}
                  className="rounded-xl border border-border bg-surface p-5"
                  style={{ borderTopWidth: 3, borderTopColor: theme.accent }}
                >
                  <div className="flex gap-3">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-lg border ${theme.iconClass}`}>
                      {ICONS[tool.icon]}
                    </div>
                    <div>
                      <h3 className="font-semibold">{tool.name}</h3>
                      <p className="text-sm text-text-secondary mt-1">{tool.tagline}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section id="compare" className="py-20 border-b border-border bg-surface-muted/30">
        <div className="max-w-6xl mx-auto px-4">
          <h2 className="text-2xl font-semibold text-text-primary">Not an AI agent</h2>
          <p className="mt-3 text-text-secondary max-w-2xl mb-8">
            Agents answer questions. Tool Hub runs your revenue operating cadence — with scored verdicts and cited proof.
          </p>
          <ComparisonTable />
        </div>
      </section>

      <section className="py-16 border-b border-border">
        <div className="max-w-6xl mx-auto px-4 text-center">
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider mb-4">Live data sources</p>
          <p className="font-mono text-sm text-text-secondary">{INTEGRATIONS.join("  ·  ")}</p>
        </div>
      </section>

      <section className="py-20">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <h2 className="text-2xl font-semibold text-text-primary">Run your revenue flywheel</h2>
          <p className="mt-3 text-text-secondary">
            Sign in to configure pipelines, monitor KPIs, and pursue markets you can credibly win.
          </p>
          <Button size="lg" className="mt-6" asChild>
            <Link href="/login">Sign in to platform</Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
