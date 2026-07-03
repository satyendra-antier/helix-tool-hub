import fs from "fs";
import path from "path";
import { ToolManifest, ToolManifestSchema } from "@tool-hub/shared-types";

function resolveModulesDir(): string {
  const candidates = [
    path.join(process.cwd(), "modules"),
    path.join(process.cwd(), "..", "..", "modules"),
    path.join(__dirname, "..", "..", "..", "modules"),
  ];
  for (const dir of candidates) {
    if (fs.existsSync(dir)) return dir;
  }
  return path.join(process.cwd(), "modules");
}

const MODULES_DIR = resolveModulesDir();

export function loadToolRegistry(): ToolManifest[] {
  const modulesPath = MODULES_DIR;
  if (!fs.existsSync(modulesPath)) {
    return [];
  }

  const tools: ToolManifest[] = [];
  const entries = fs.readdirSync(modulesPath, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const manifestPath = path.join(modulesPath, entry.name, "manifest.json");
    if (!fs.existsSync(manifestPath)) continue;

    try {
      const raw = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
      const manifest = ToolManifestSchema.parse(raw);
      if (manifest.status !== "deprecated") {
        tools.push(manifest);
      }
    } catch {
      // skip invalid manifests
    }
  }

  return tools.sort((a, b) => a.name.localeCompare(b.name));
}

export function getToolBySlug(slug: string): ToolManifest | undefined {
  return loadToolRegistry().find((t) => t.id === slug);
}

export function resolveBackendUrl(manifest: ToolManifest): string {
  const publicMap: Record<string, string | undefined> = {
    "video-scraper": process.env.VIDEO_SCRAPER_PUBLIC_URL,
    "market-depth-analyzer": process.env.MARKET_DEPTH_PUBLIC_URL,
    "lead-intelligence": process.env.LEAD_INTELLIGENCE_PUBLIC_URL,
    "build-readiness": process.env.BUILD_READINESS_PUBLIC_URL,
  };
  if (publicMap[manifest.id]) return publicMap[manifest.id]!;

  const portMap: Record<string, string> = {
    "video-scraper": process.env.VIDEO_SCRAPER_HOST_PORT || "8101",
    "market-depth-analyzer": process.env.MARKET_DEPTH_HOST_PORT || "8102",
    "lead-intelligence": process.env.LEAD_INTELLIGENCE_HOST_PORT || "8103",
    "build-readiness": process.env.BUILD_READINESS_HOST_PORT || "8104",
  };
  return `http://localhost:${portMap[manifest.id] || "8100"}`;
}
