# Tool Hub — Platform Architecture

## The core idea

Instead of building "Product 1" and "Product 2" as separate apps, you build **one shell** (the Hub) that knows how to discover, launch, and host **tool modules**. Video Scraper and Market Depth Analyzer are the first two modules. Every future tool is just a new folder + a manifest file — it shows up on the dashboard automatically, with zero changes to the shell.

This is the same pattern used internally by things like Retool, Raycast extensions, and VS Code — a thin host + a registry + isolated modules.

```
┌─────────────────────────────────────────────────────┐
│                      TOOL HUB (Shell)                 │
│  - Auth, layout, nav, theme, API key vault             │
│  - Tool Registry (reads manifests, renders launcher)   │
│  - Shared job queue / notifications / billing (future) │
└───────────────┬─────────────────────┬─────────────────┘
                 │                     │
        ┌────────▼────────┐   ┌────────▼─────────┐
        │  Module: Video   │   │  Module: Market   │
        │  Scraper         │   │  Depth Analyzer   │
        │  (own routes,    │   │  (own routes,     │
        │  own API, own    │   │  own API, own     │
        │  DB tables)      │   │  DB tables)        │
        └──────────────────┘   └────────────────────┘
                 │                     │
        ┌────────▼─────────────────────▼────────┐
        │        Shared Postgres + Redis          │
        │   (namespaced per module by prefix)      │
        └──────────────────────────────────────────┘
```

## Monorepo layout

```
tool-hub/
├── apps/
│   └── web/                     # Next.js 14 App Router — the Shell
│       ├── app/
│       │   ├── (dashboard)/page.tsx        # Launcher grid — reads registry
│       │   ├── tools/[slug]/page.tsx       # Generic tool host page
│       │   └── api/registry/route.ts       # Serves tools.registry.json
│       ├── lib/registry.ts                 # Loads + validates manifests
│       └── components/ui/...               # Shared design system (shadcn)
├── modules/
│   ├── video-scraper/
│   │   ├── manifest.json        # See schema below
│   │   ├── frontend/            # UI injected into /tools/video-scraper
│   │   └── backend/             # FastAPI service (own OpenAPI spec)
│   └── market-depth-analyzer/
│       ├── manifest.json
│       ├── frontend/
│       └── backend/
├── packages/
│   └── shared-types/            # Zod schemas shared across modules
└── infra/
    └── docker-compose.yml       # Postgres, Redis, both backends, web
```

## The Manifest — this is what makes it extensible

Every module ships a `manifest.json`. The Hub reads all manifests at build/boot time and renders the launcher grid from them. **Adding tool #3 later = drop a folder + this file. Nothing else changes.**

```json
{
  "id": "video-scraper",
  "name": "Video Scraper",
  "tagline": "Any URL in, structured transcript + summary out.",
  "icon": "film",
  "route": "/tools/video-scraper",
  "backendBaseUrl": "http://video-scraper-api:8001",
  "status": "active",
  "requiredEnv": ["GEMINI_API_KEY"],
  "category": "content",
  "version": "1.0.0"
}
```

## Launch flow (what "launching a tool" actually means)

1. User lands on `/` (the Hub dashboard) — sees a grid of module cards rendered from the registry.
2. Click "Launch" on a card → client-side nav to `/tools/[slug]`.
3. `/tools/[slug]/page.tsx` is a **generic host** — it dynamically imports that module's `frontend/index.tsx` export and renders it inside the shared shell layout (nav stays, only the workspace panel swaps).
4. The module's frontend talks only to its own backend (`backendBaseUrl` from the manifest) — full isolation, no shared state leakage between tools.
5. Shared concerns (auth token, active API keys, theme) are passed down via a `ToolContext` provider — modules read from it, never duplicate it.

## Why this beats "two separate products"

- **One design system, one login, one place to manage API keys** — you paste your Gemini key once, in Hub Settings, and any module that lists it in `requiredEnv` can use it.
- **New tool = new folder.** No re-architecting the dashboard, no new deploy pipeline.
- **Isolation without duplication** — each module owns its DB tables (prefixed `video_scraper_*`, `market_depth_*`) and its own backend process, so a bug in one can't take down another, but they still share infra.
- **You can retire tools too** — set `"status": "beta"` or remove the manifest and the card disappears. No dead code shipped to users.

## Stack decision (applies to both modules)

| Layer | Choice | Why |
|---|---|---|
| Shell frontend | Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui | Fast dashboard iteration, server components for the registry read |
| Module backends | FastAPI (Python) | Both modules need heavy Python libs (yt-dlp, pandas, httpx to Gemini) |
| DB | Postgres (shared instance, namespaced tables) | Relational + jsonb is enough here, no need for two DBs |
| Queue | Redis + BullMQ (or Celery on the Python side) | Both tools are long-running jobs — scrape/analyze happens async, UI polls or gets a websocket push |
| Auth | Clerk or Auth.js (single sign-on across the Hub) | You're the only user today, but build it so a teammate can be added later without rework |

Give the two Cursor prompts below to Cursor **in the same repo**, one after another — each one references this architecture doc so Cursor builds the module inside the registry pattern instead of a standalone app.
