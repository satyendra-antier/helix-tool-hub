import Link from "next/link";
import { ArrowRight, Compass, Film, Handshake, Radar, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import { loadToolRegistry } from "@/lib/registry";
import { BRAND, getStep } from "@/lib/journey";
import { Button } from "@tool-hub/ui";
import { getModuleTheme } from "@tool-hub/ui";
import { FlywheelDiagram } from "./flywheel-diagram";
import { ComparisonTable } from "./comparison-table";

const ICONS: Record<string, React.ReactNode> = {
  film: <Film className="w-5 h-5" />,
  "trending-up": <TrendingUp className="w-5 h-5" />,
  radar: <Radar className="w-5 h-5" />,
  compass: <Compass className="w-5 h-5" />,
  "shield-check": <ShieldCheck className="w-5 h-5" />,
  handshake: <Handshake className="w-5 h-5" />,
};

const INTEGRATIONS = ["Adzuna", "DefiLlama", "GitHub", "Grants.gov", "Hunter", "RemoteOK", "OpenAI"];

export default function LandingPage() {
  const tools = loadToolRegistry();
  const rank = (id: string) => getStep(id)?.step ?? 99;
  const orderedTools = [...tools].sort((a, b) => rank(a.id) - rank(b.id));

  return (
    <div className="bg-surface">
      <section className="border-b border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-20 md:py-28 grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <p className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary mb-4">
              <Sparkles className="h-3.5 w-3.5" />
              {BRAND.name}
            </p>
            <h1 className="text-4xl md:text-5xl font-semibold tracking-tight text-text-primary leading-tight">
              Find and win leads <span className="ai-text">with AI</span>, in 4 simple steps.
            </h1>
            <p className="mt-5 text-lg text-text-secondary leading-relaxed max-w-xl">
              Find where buyers are spending, check what you can deliver, get a scored list of companies
              that need you, then warm them up with intros, alerts, partners and a deal coach.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" asChild>
                <Link href="/login">
                  Start finding leads
                  <ArrowRight className="w-4 h-4 ml-1" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/methodology">How it works</Link>
              </Button>
            </div>
          </div>
          <div className="rounded-xl border border-border bg-surface-muted p-6 shadow-sm">
            <p className="text-xs font-medium text-text-muted uppercase mb-4">Home preview</p>
            <div className="grid grid-cols-2 gap-3 mb-4">
              {[
                { label: "Best market", value: "Stablecoin" },
                { label: "Markets we can serve", value: "8 / 12" },
                { label: "Leads found", value: "142" },
                { label: "Warm paths", value: "23" },
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
            { v: "4", l: "Simple steps" },
            { v: "1 click", l: "Run everything with AI" },
            { v: "12", l: "Markets scored live" },
            { v: "5", l: "Ways to win a lead" },
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
          <h2 className="text-2xl font-semibold text-text-primary">How it works</h2>
          <p className="mt-3 text-text-secondary max-w-2xl">
            Go step by step, or press one button and let AI run all four for you.
          </p>
          <div className="mt-10 grid md:grid-cols-2 gap-5">
            {orderedTools.map((tool) => {
              const theme = getModuleTheme(tool.id);
              const step = getStep(tool.id);
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
                      <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                        {step ? `Step ${step.step}` : "Extra"}
                      </p>
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
            Agents answer questions. {BRAND.name} runs your lead generation every week, with scores you can check and proof you can cite.
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
          <h2 className="text-2xl font-semibold text-text-primary">Ready to find your next client?</h2>
          <p className="mt-3 text-text-secondary">
            Sign in and follow the 4 steps. AI does the heavy lifting.
          </p>
          <Button size="lg" className="mt-6" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
