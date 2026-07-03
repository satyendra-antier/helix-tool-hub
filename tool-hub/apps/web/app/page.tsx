import Link from "next/link";
import { Film, TrendingUp, Radar, Compass, ArrowUpRight } from "lucide-react";
import { loadToolRegistry } from "@/lib/registry";

const ICONS: Record<string, React.ReactNode> = {
  film: <Film className="w-5 h-5" />,
  "trending-up": <TrendingUp className="w-5 h-5" />,
  radar: <Radar className="w-5 h-5" />,
  compass: <Compass className="w-5 h-5" />,
};

const TRACK_CLASS: Record<string, string> = {
  content: "track-content",
  intelligence: "track-intel",
  growth: "track-growth",
};

export default function DashboardPage() {
  const tools = loadToolRegistry();
  const vaultLinked = !!process.env.OPENAI_API_KEY;

  return (
    <div className="wrap max-w-[1180px] mx-auto px-12 py-10 pb-20">
      <div className="boot-line font-mono text-xs text-text-dim mb-6 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-ok shadow-[0_0_8px_#3ED598]" />
        hub://online — {tools.length} modules registered — vault:{" "}
        {vaultLinked ? "openai_api_key linked" : "keys not configured"}
      </div>

      <header className="flex justify-between items-end pb-7 mb-8 border-b border-border">
        <div>
          <h1 className="font-display text-[32px] font-bold tracking-tight">
            Tool<span className="text-accent-a">Hub</span>
          </h1>
          <p className="text-text-secondary text-sm mt-1.5 max-w-lg leading-relaxed">
            One launcher. Every tool plugs into the same registry — new
            capability, no new product.
          </p>
        </div>
        <div className="text-right font-mono text-[11px] text-text-dim leading-relaxed hidden sm:block">
          OPERATOR&nbsp;&nbsp;<b className="text-text-secondary font-medium">local</b>
          <br />
          SESSION&nbsp;&nbsp;<b className="text-text-secondary font-medium">docker · dev</b>
          <br />
          MODULES&nbsp;&nbsp;<b className="text-text-secondary font-medium">{String(tools.length).padStart(2, "0")} / 08 slots</b>
        </div>
      </header>

      <div className="mb-11">
        <div className="font-mono text-[11px] text-text-dim uppercase tracking-widest mb-2.5 flex justify-between">
          <span>MODULE REGISTRY</span>
          <span>8 SLOTS</span>
        </div>
        <div className="grid grid-cols-8 gap-1.5">
          {Array.from({ length: 8 }).map((_, i) => {
            const tool = tools[i];
            const isB = tool?.category === "intelligence";
            const isG = tool?.category === "growth";
            return (
              <div
                key={i}
                className={`h-[34px] rounded flex items-center justify-center font-mono text-[10px] ${
                  tool
                    ? isG
                      ? "bg-gradient-to-b from-ok/14 to-ok/5 border border-ok/40 text-ok"
                      : isB
                      ? "bg-gradient-to-b from-accent-b/14 to-accent-b/5 border border-accent-b/40 text-accent-b"
                      : "bg-gradient-to-b from-accent-a/14 to-accent-a/5 border border-accent-a/40 text-accent-a"
                    : "border border-dashed border-border-bright text-text-dim"
                }`}
              >
                {tool
                  ? `${String(i + 1).padStart(2, "0")} · ${tool.id.slice(0, 3).toUpperCase()}`
                  : String(i + 1).padStart(2, "0")}
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-9">
        {tools.map((tool, idx) => {
          const isIntel = tool.category === "intelligence";
          const isGrowth = tool.category === "growth";
          return (
            <div
              key={tool.id}
              className={`card bg-panel border border-border rounded-[10px] p-6 relative overflow-hidden hover:border-border-bright hover:-translate-y-0.5 transition-all ${
                isGrowth ? "before:bg-ok" : isIntel ? "before:bg-accent-b" : "before:bg-accent-a"
              } before:content-[''] before:absolute before:top-0 before:left-0 before:right-0 before:h-0.5`}
            >
              <div className="flex justify-between items-start mb-4">
                <span className="font-mono text-[11px] text-text-dim">
                  MODULE · {String(idx + 1).padStart(2, "0")}
                </span>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded-full border border-ok/35 text-ok bg-ok/10 uppercase tracking-wider">
                  ● {tool.status}
                </span>
              </div>
              <div
                className={`w-11 h-11 rounded-lg flex items-center justify-center mb-4 ${
                  isGrowth
                    ? "bg-ok/12 border border-ok/30 text-ok"
                    : isIntel
                    ? "bg-accent-b/12 border border-accent-b/30 text-accent-b"
                    : "bg-accent-a/12 border border-accent-a/30 text-accent-a"
                }`}
              >
                {ICONS[tool.icon] || <Film className="w-5 h-5" />}
              </div>
              <h2 className="font-display text-xl font-semibold mb-2">{tool.name}</h2>
              <p className="text-text-secondary text-[13.5px] leading-relaxed mb-5 min-h-[40px]">
                {tool.tagline}
              </p>
              <div className="flex justify-between items-center">
                <div className="flex gap-1.5 flex-wrap">
                  {tool.requiredEnv.slice(0, 2).map((env) => (
                    <span
                      key={env}
                      className="font-mono text-[10px] text-text-dim border border-border-bright px-1.5 py-0.5 rounded"
                    >
                      {env.replace(/_API_KEY|_TOKEN|_APP_ID|_APP_KEY/g, "").toLowerCase()}
                    </span>
                  ))}
                </div>
                <Link
                  href={tool.route}
                  className="font-mono text-xs font-medium bg-text-primary text-bg px-4 py-2 rounded-md flex items-center gap-1.5 hover:bg-accent-a transition-colors"
                >
                  Launch <ArrowUpRight className="w-3 h-3" />
                </Link>
              </div>
            </div>
          );
        })}

        {tools.length < 8 &&
          Array.from({ length: Math.min(2, 8 - tools.length) }).map((_, i) => (
            <div
              key={`ghost-${i}`}
              className="border border-dashed border-border-bright rounded-[10px] min-h-[210px] flex flex-col items-center justify-center text-text-dim opacity-60"
            >
              <span className="text-2xl font-mono mb-2">+</span>
              <span className="font-mono text-[11px] tracking-wide">
                REGISTER MODULE {String(tools.length + i + 1).padStart(2, "0")}
              </span>
            </div>
          ))}
      </div>

      <div className="font-mono text-[11px] text-text-dim flex flex-wrap justify-between gap-2 border-t border-border pt-4">
        <span>tool-hub v1.0.0 — monorepo</span>
        <span>postgres · redis · shared vault</span>
        <span>next module = manifest.json + folder, no shell changes</span>
      </div>
    </div>
  );
}
