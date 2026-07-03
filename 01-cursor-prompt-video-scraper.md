# Cursor Build Prompt — Module: Video Scraper

Paste this whole thing into Cursor (Composer / Agent mode) as the task. It assumes the `tool-hub` monorepo from `00-tool-hub-architecture.md` already exists — if it doesn't yet, tell Cursor to scaffold that shell first using the layout in that doc, then run this prompt.

---

## ROLE

You are building a production-grade module called **Video Scraper** inside the `modules/video-scraper/` folder of an existing Next.js + FastAPI monorepo ("Tool Hub"). This module must register itself into the Hub via `manifest.json` and be fully self-contained (own backend, own DB tables, own frontend panel) per the architecture in `00-tool-hub-architecture.md`. Do not modify the Hub shell except to confirm the module appears in the registry.

## OBJECTIVE

User pastes **any URL** into a single input. The system detects what kind of video content lives at that URL, extracts it, transcribes it if no captions exist, summarizes it, and renders everything in a clean, tabbed "nice format" view — not a raw JSON dump.

## SUPPORTED SOURCE TYPES (in priority order)

1. **Platform videos** (YouTube, Vimeo, Twitter/X, TikTok, Reddit, Facebook, SoundCloud-style audio) — via `yt-dlp` as the extraction engine (supports 1800+ sites out of the box, actively maintained, this is the right tool — do not hand-roll platform-specific scrapers).
2. **Generic web pages with embedded `<video>` or HLS/DASH streams** — fallback using Playwright (headless Chromium) to render the page, detect `<video src>`, `<source>`, and network requests matching `.m3u8` / `.mpd`, then extract via `yt-dlp` or `ffmpeg` against the resolved stream URL.
3. **Direct file links** (`.mp4`, `.webm`, `.mov` ending URLs) — pull metadata via `ffprobe` directly, no scraping needed.

## PIPELINE

```
URL in
  → 1. Classify (regex/domain match → platform | generic-page | direct-file)
  → 2. Extract (yt-dlp | Playwright+yt-dlp | ffprobe)
  → 3. Captions: use yt-dlp's native subtitle extraction if available
  → 4. If no captions: download audio only, transcribe via a
       pluggable transcription provider (default: Gemini's audio
       understanding via the same API key the user provides —
       do not hardcode a different STT vendor, keep this configurable
       via TRANSCRIPTION_PROVIDER env var)
  → 5. Summarize transcript via Gemini (structured prompt, see below)
  → 6. Persist job + results to Postgres
  → 7. Push result to frontend (poll job status or SSE)
```

## BACKEND — FastAPI (`modules/video-scraper/backend/`)

### Endpoints

- `POST /jobs` — body `{ "url": string }` → creates a job row, status `queued`, kicks off background task (Celery or FastAPI `BackgroundTasks` + Redis-backed status), returns `{ "job_id": uuid }`.
- `GET /jobs/{job_id}` — returns current status (`queued | extracting | transcribing | summarizing | done | failed`) and, when `done`, the full result payload.
- `GET /jobs` — paginated history of past scrapes for the "Recent" panel.
- `DELETE /jobs/{job_id}` — remove a job + its stored media/transcript.

### DB schema (Postgres, table prefix `video_scraper_`)

```sql
CREATE TABLE video_scraper_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url TEXT NOT NULL,
  source_type TEXT,              -- platform | generic-page | direct-file
  status TEXT NOT NULL DEFAULT 'queued',
  error TEXT,
  title TEXT,
  channel_or_author TEXT,
  duration_seconds INT,
  thumbnail_url TEXT,
  transcript TEXT,
  transcript_source TEXT,        -- 'native-captions' | 'transcribed'
  summary_json JSONB,            -- structured summary, see prompt below
  created_at TIMESTAMPTZ DEFAULT now(),
  completed_at TIMESTAMPTZ
);
```

### Gemini summarization prompt (use this exact structure, output must be valid JSON)

```
You are summarizing a video transcript. Return ONLY valid JSON, no markdown fences, no preamble.

Schema:
{
  "one_line_summary": string,
  "key_points": string[],        // 3-7 bullets, each a full sentence
  "chapters": [{ "timestamp_hint": string, "title": string }],
  "notable_quotes": string[],    // max 3, only if genuinely load-bearing
  "topics": string[]             // for tagging/search later
}

Transcript:
{{transcript}}
```

### Legal / operational guardrails (build these in, don't skip)

- Respect `robots.txt` on generic-page fallback scraping.
- Rate-limit outbound requests per domain (default: 1 req/sec/domain) — configurable.
- Never attempt to defeat DRM-protected streams (Widevine/FairPlay) — if `yt-dlp` reports the stream is DRM-protected, fail the job with a clear `error: "DRM-protected source, cannot extract"` rather than trying workarounds.
- Store a `source_url` audit trail on every job so usage is always traceable.
- Add a configurable `MAX_VIDEO_DURATION_SECONDS` guard to avoid accidentally processing a 10-hour livestream VOD.

## FRONTEND — `modules/video-scraper/frontend/`

Single-page module UI, mounted into the Hub's `/tools/video-scraper` host route.

**Layout:**
1. **Input bar** (top, sticky) — URL field + "Scrape" button. Inline validation (must be a valid URL).
2. **Job status strip** — shows live progress through the pipeline stages (`Extracting → Transcribing → Summarizing → Done`) as a horizontal stepper, not a spinner — the user should always know which stage it's in.
3. **Result view** (tabbed, appears once `status = done`):
   - **Overview** tab — thumbnail, title, author, duration, `one_line_summary`, `topics` as chips.
   - **Summary** tab — `key_points` as a clean bulleted list, `chapters` as a scannable timeline, `notable_quotes` in blockquote style.
   - **Full Transcript** tab — scrollable, monospace-adjacent, with a copy-to-clipboard button and a "transcript source" badge (native captions vs. transcribed).
   - **Raw / Export** tab — download as `.md` (nicely formatted) or `.json`.
4. **Recent Scrapes** sidebar — last 10 jobs, click to reopen without re-scraping.
5. Empty state, loading state, and error state must all be explicitly designed — don't leave any of these as a bare "undefined" or blank screen.

**Design direction:** match the Hub's shared design tokens (dark console aesthetic, see the Hub mockup) — this is a workspace tool, not a marketing page. Prioritize information density and scan-ability over decoration.

## `manifest.json` for this module

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

## ENV VARS

```
GEMINI_API_KEY=            # user-provided, read from Hub's shared vault
TRANSCRIPTION_PROVIDER=gemini   # pluggable, default gemini
MAX_VIDEO_DURATION_SECONDS=7200
RATE_LIMIT_PER_DOMAIN_SECONDS=1
DATABASE_URL=              # shared Hub Postgres instance
REDIS_URL=                 # shared Hub Redis instance
```

## DEPENDENCIES (backend)

```
fastapi, uvicorn, yt-dlp, playwright, ffmpeg-python, sqlalchemy, alembic,
celery[redis] (or arq), google-genai, pydantic-settings
```

## ACCEPTANCE CRITERIA

- [ ] Paste a YouTube URL → get transcript + summary within pipeline, no manual intervention.
- [ ] Paste a random blog post with an embedded `<video>` tag → correctly falls back to Playwright detection.
- [ ] Paste a `.mp4` direct link → skips scraping, goes straight to metadata + transcription.
- [ ] Paste a DRM-protected stream → fails gracefully with a clear message, does not hang.
- [ ] Module appears on the Hub dashboard automatically once `manifest.json` is added — no Hub code changes required.
- [ ] All four UI states (empty/loading/error/done) are implemented, not placeholder text.

Build this end-to-end, then run it against 3 real URLs (one YouTube video, one generic article with an embedded video, one direct `.mp4`) and report the actual output for each before declaring done.
