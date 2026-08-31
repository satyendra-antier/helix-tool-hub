import { loadToolRegistry } from "./registry";

const MODULE_API_URLS: Record<string, string | undefined> = {
  "video-scraper": process.env.VIDEO_SCRAPER_API_URL,
  "market-depth-analyzer": process.env.MARKET_DEPTH_API_URL,
  "lead-intelligence": process.env.LEAD_INTELLIGENCE_API_URL,
  "build-readiness": process.env.BUILD_READINESS_API_URL,
};

const MODULE_HOST_PORTS: Record<string, string> = {
  "video-scraper": process.env.VIDEO_SCRAPER_HOST_PORT || "8101",
  "market-depth-analyzer": process.env.MARKET_DEPTH_HOST_PORT || "8102",
  "lead-intelligence": process.env.LEAD_INTELLIGENCE_HOST_PORT || "8103",
  "build-readiness": process.env.BUILD_READINESS_HOST_PORT || "8104",
};

const DEFAULT_TIMEOUT_MS = 12_000;

export function getModuleApiBase(slug: string): string {
  if (MODULE_API_URLS[slug]) return MODULE_API_URLS[slug]!;
  const port = MODULE_HOST_PORTS[slug] || "8100";
  return `http://localhost:${port}`;
}

export async function fetchModule(
  slug: string,
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const base = getModuleApiBase(slug);
  const url = `${base.replace(/\/$/, "")}/${path.replace(/^\//, "")}`;
  const headers = new Headers(init?.headers);
  const serviceKey = process.env.HUB_SERVICE_KEY;
  if (serviceKey) headers.set("X-Hub-Service-Key", serviceKey);

  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const { timeoutMs: _t, signal: _s, ...rest } = init || {};
    return await fetch(url, {
      ...rest,
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchModuleJson<T>(
  slug: string,
  path: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<T | null> {
  try {
    const res = await fetchModule(slug, path, init);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function getAllModuleSlugs(): string[] {
  return loadToolRegistry().map((t) => t.id);
}
