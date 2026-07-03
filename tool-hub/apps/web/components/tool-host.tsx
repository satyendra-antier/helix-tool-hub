"use client";

import dynamic from "next/dynamic";

const MODULE_COMPONENTS: Record<string, React.ComponentType> = {
  "video-scraper": dynamic(
    () => import("@tool-hub/video-scraper-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoader name="Video Scraper" /> }
  ),
  "market-depth-analyzer": dynamic(
    () => import("@tool-hub/market-depth-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoader name="Market Depth Analyzer" /> }
  ),
  "lead-intelligence": dynamic(
    () => import("@tool-hub/lead-intelligence-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoader name="Lead Intelligence Engine" /> }
  ),
};

function ModuleLoader({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center min-h-[400px] font-mono text-text-secondary">
      <span className="animate-pulse">Loading {name}…</span>
    </div>
  );
}

export function ToolHost({ slug }: { slug: string }) {
  const Component = MODULE_COMPONENTS[slug];
  if (!Component) {
    return (
      <div className="text-center py-20 font-mono text-text-dim">
        Module &quot;{slug}&quot; has no frontend registered.
      </div>
    );
  }
  return <Component />;
}
