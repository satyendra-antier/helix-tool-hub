"use client";

import dynamic from "next/dynamic";
import { ModuleLoaderSkeleton } from "@tool-hub/ui";

const MODULE_COMPONENTS: Record<string, React.ComponentType> = {
  "video-scraper": dynamic(
    () => import("@tool-hub/video-scraper-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoaderSkeleton /> }
  ),
  "market-depth-analyzer": dynamic(
    () => import("@tool-hub/market-depth-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoaderSkeleton /> }
  ),
  "lead-intelligence": dynamic(
    () => import("@tool-hub/lead-intelligence-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoaderSkeleton /> }
  ),
  "build-readiness": dynamic(
    () => import("@tool-hub/build-readiness-frontend").then((m) => m.default),
    { ssr: false, loading: () => <ModuleLoaderSkeleton /> }
  ),
};

export function ToolHost({ slug }: { slug: string }) {
  const Component = MODULE_COMPONENTS[slug];
  if (!Component) {
    return (
      <div className="text-center py-20 text-text-muted text-sm">
        Module &quot;{slug}&quot; has no frontend registered.
      </div>
    );
  }
  return <Component />;
}
