# Video Scraper — Complete Product One-Pager

**Product:** Video Scraper  
**Part of:** Tool Hub — Revenue Intelligence Platform  
**Tagline:** Any URL in, structured transcript + summary out.  
**Audience:** Marketing, sales enablement, knowledge teams, delivery leads, technical stakeholders  
**Status:** Working POC (v1.0.0)  
**Default port:** `8101` (API) · Dashboard route: `/tools/video-scraper`

---

## One Sentence

Video Scraper extracts video metadata and transcripts from platform URLs, generic pages, or direct files — then produces structured LLM summaries — turning talks, demos, and webinars into searchable company knowledge that feeds Build Readiness.

---

## The Problem It Solves

Technical services firms accumulate expertise in videos (conference talks, client demos, webinars, portfolio pages) that never enters CRM, proposals, or capability audits. Manual transcription is slow and expensive; platform-specific tools only cover YouTube.

**This product answers:** *What proof and expertise do we already have on record — and can we make it searchable?*

---

## What It Does

| Capability | Detail |
|------------|--------|
| **Universal URL input** | YouTube, Vimeo, TikTok, Twitter/X, direct files, generic marketing pages |
| **Multi-strategy extraction** | yt-dlp → Playwright browser discovery → subpath probes |
| **Local transcription** | faster-whisper on CPU (no OpenAI Audio API required by default) |
| **LLM summarization** | Structured JSON: summary, key points, chapters, quotes, topics |
| **Job history** | All jobs stored in Postgres with status tracking |
| **Build Readiness feed** | Completed transcripts indexed into company RAG via Build Readiness |

---

## How It Works (Pipeline)

```
extracting → downloading → transcribing → summarizing → done
```

1. **Classify URL** — Platform, direct file, or generic page.
2. **Extract** — Try yt-dlp, then browser discovery, then subpath probes.
3. **Download** — Stage audio/video to local disk (+ optional MinIO mirror).
4. **Transcribe** — Local Whisper (default) or OpenAI Audio API.
5. **Summarize** — LLM produces structured JSON from transcript.
6. **Cleanup** — Media files always deleted after job completes.

**Trigger:** `POST /jobs` with `{ "url": "..." }`

---

## URL Classification

| Type | Detection |
|------|-----------|
| `platform` | YouTube, Vimeo, TikTok, Twitter/X, etc. (16 domains) |
| `direct-file` | `.mp4`, `.webm`, `.m3u8`, `.mpd`, etc. |
| `generic-page` | Marketing sites, portfolio pages, testimonial pages |

---

## Extraction Strategy (Order of Attempts)

1. **yt-dlp** on submitted URL (metadata + optional native captions)
2. **Playwright browser discovery** (page + iframes + network requests)
3. **Subpath probes:** `/video-testimonials`, `/videos`, `/portfolio`, `/work`

### yt-dlp Configuration

- **YouTube player clients rotated:** android, ios, web, mweb, tv_embedded
- **Download format chain:** `ba/b` → `bestaudio/best` → `best[height<=720]/best` → `worst`
- **Caption languages tried:** en, en-US, en-GB, fuzzy `en*`
- **Caption fetch failures are non-fatal** — falls back to download + transcribe
- **Max duration:** 7200 seconds (2 hours)

### Browser Discovery (Playwright)

- Chromium, 90 second page timeout
- Scrolls 6 viewport heights; clicks video-related selectors
- Scans: `og:video` meta, iframes, `<video>` elements, network responses

**Candidate scoring:**

| Signal | Points |
|--------|--------|
| Base | +10 |
| Direct file (.mp4, etc.) | +40 |
| Known platform URL | +35 |
| HLS (.m3u8) | +25 |
| DASH (.mpd) | +20 |
| Video element | +15 |
| Iframe embed | +10 |
| Network capture | +12 |
| Blob URL | −50 (filtered) |

Top **12** candidates tried in score order.

---

## Transcription

**Default: local faster-whisper** (no OpenAI Audio API required)

| Setting | Default |
|---------|---------|
| `TRANSCRIPTION_PROVIDER` | `local` |
| `LOCAL_WHISPER_MODEL` | `small` (options: base, small, medium) |
| Device | CPU, int8 |
| Whisper params | `beam_size=5`, `vad_filter=True` |
| Audio extract (ffmpeg) | max 600 seconds, MP3 |

**OpenAI fallback** (`TRANSCRIPTION_PROVIDER=openai`): uses Audio API (`whisper-1` or configured `TRANSCRIPTION_MODEL`). Requires project with Audio API access.

> **Note:** `gpt-5-mini` cannot transcribe audio. It is used only for **summarization** after transcription.

---

## Summarization (LLM)

Output JSON schema:

```json
{
  "one_line_summary": "string",
  "key_points": ["string"],
  "chapters": [{ "timestamp_hint": "string", "title": "string" }],
  "notable_quotes": ["string"],
  "topics": ["string"]
}
```

Transcript truncated to **50,000** characters for the prompt.

---

## Media Staging

- Downloads staged to local disk + optional MinIO mirror (port `9100`)
- **Always deleted** after job completes (success or failure)
- No long-term video storage — transcripts and summaries persist in Postgres

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health |
| GET | `/config` | Transcription provider, whisper model, key status |
| POST | `/jobs` | Submit URL for extraction |
| GET | `/jobs/{job_id}` | Job status and result |
| GET | `/jobs/{job_id}/items` | Individual video items in multi-video job |
| GET | `/jobs` | List recent jobs |
| DELETE | `/jobs/{job_id}` | Delete job record |

### Example Request

```bash
curl -X POST http://localhost:8101/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=EXAMPLE"}'
```

---

## Configuration & API Keys

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | For summarization | LLM summary generation |
| `VIDEO_SCRAPER_OPENAI_API_KEY` | Optional override | Summarization only |

### Transcription Settings

```env
TRANSCRIPTION_PROVIDER=local        # default — no Whisper API needed
LOCAL_WHISPER_MODEL=small           # base | small | medium
# TRANSCRIPTION_PROVIDER=openai     # requires Audio API access
# TRANSCRIPTION_MODEL=whisper-1
```

---

## Integration With Other Tool Hub Modules

```
Video Scraper
     │
     │  video_scraper_jobs (transcript, summary, metadata)
     ▼
┌────────────────────┐
│ Build Readiness    │
│ POST /index/videos │
│                    │
│ source_type=video  │
│ enriches RAG       │
└────────────────────┘
```

**Workflow:**
1. Scrape company talks, demos, and webinar URLs in Video Scraper
2. In Build Readiness, run **Index Videos** (`POST /index/videos`)
3. Run **Fit Analysis** — video evidence strengthens capability scores and verdict citations

Video transcripts do **not** replace website capabilities but enrich retrieval for domains with thin website copy.

---

## Use Cases

| Use Case | Value |
|----------|-------|
| **Conference talks** | Capture technical depth not on the company website |
| **Client demo recordings** | Proof points for proposals and case studies |
| **Webinar archives** | Searchable knowledge for sales and delivery teams |
| **Portfolio pages** | Extract embedded videos from JS-heavy marketing sites |
| **Capability audit** | Feed Build Readiness RAG with spoken expertise |

---

## Business Value

| Outcome | How |
|---------|-----|
| **Stronger win rate** | Verdicts cite video evidence alongside website content |
| **Faster sales enablement** | Structured summaries with key points and quotes |
| **Lower transcription cost** | Local Whisper avoids per-minute API fees |
| **Universal input** | One tool for YouTube, Vimeo, portfolio pages, and direct files |
| **Compounding knowledge** | Every scraped video becomes permanent searchable evidence |

---

## Operational Best Practices

| Practice | Why |
|----------|-----|
| Scrape after major events | New talks should enter RAG before next Fit Analysis |
| Use direct video URLs when possible | JS-heavy sites may need explicit video links |
| Review summaries before sharing externally | LLM summaries are for internal use; verify quotes |
| Batch portfolio URLs | Subpath probes help discover hidden video pages |

---

## Known Limitations

| Area | Limitation |
|------|------------|
| **Audio length** | Local Whisper extracts max **10 minutes** of audio per video |
| **Language/quality** | Hindi/Sanskrit/low-quality audio may produce short transcripts on `small` model |
| **JS-heavy sites** | May need direct video URL or channel URL instead of marketing page |
| **Jobs** | BackgroundTasks in-process — jobs lost on container restart |
| **Storage** | Media deleted after job; only transcript/summary persist |
| **Summarization** | Requires OpenAI key; transcription works without it |

---

## Architecture Notes

- **Backend:** FastAPI (`modules/video-scraper/backend/`)
- **Frontend:** React panel loaded by Tool Hub web shell
- **Database table:** `video_scraper_jobs`
- **Key files:** `extractor.py`, `browser_discovery.py`, `ytdlp_utils.py`, `pipeline.py`, `local_transcription.py`, `openai_service.py`
- **Infrastructure:** Optional MinIO for temp staging (`infra/docker-compose.yml`, port `9100`)

---

## Quick Reference

```
Pipeline:  extracting → downloading → transcribing → summarizing → done

Transcription default:  local faster-whisper (small model, CPU)
Summarization model:    gpt-5-mini (text only, post-transcription)
Max video duration:     7200 seconds (2 hours)
Max audio extract:      600 seconds for local Whisper
Transcript limit:       50,000 chars for summarization prompt
```

---

*Standalone product brief — Tool Hub Video Scraper v1.0 · July 2026*
