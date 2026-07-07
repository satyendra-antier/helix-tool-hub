# Tool Hub — Product & Algorithm Documentation

Complete technical reference for scoring, depth analysis, pipelines, and data flow across all Tool Hub modules.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Architecture](#2-architecture)
3. [Market Depth Analyzer](#3-market-depth-analyzer)
4. [Build Readiness Engine](#4-build-readiness-engine)
5. [Video Scraper](#5-video-scraper)
6. [Lead Intelligence Engine](#6-lead-intelligence-engine)
7. [Cross-Module Data Flow](#7-cross-module-data-flow)
8. [Configuration & API Keys](#8-configuration--api-keys)
9. [Known Limitations](#9-known-limitations)

---

## 1. Product Overview

**Tool Hub** is a modular intelligence platform for a services company (default profile: Antier) to answer:

| Question | Module |
|----------|--------|
| Which market domains have the strongest demand? | Market Depth Analyzer |
| Does our company have depth to build in those domains? | Build Readiness Engine |
| Can we scrape and understand video content? | Video Scraper |
| Where are qualified leads coming from? | Lead Intelligence Engine |

### Directional Fit Pipeline (Build Readiness)

```
Market Demand  →  Company Depth  →  Fit Verdict
(live signals)    (RAG index)       (GO / CONDITIONAL / NO_GO)
```

All modules share **PostgreSQL** for persistence. Jobs run in-process (FastAPI BackgroundTasks) or via Redis-backed queues where configured.

---

## 2. Architecture

### Monorepo Layout

```
tool-hub/
├── apps/web/                  # Next.js dashboard + tool host
├── packages/shared-types/     # Shared TypeScript types
├── modules/
│   ├── market-depth-analyzer/
│   ├── build-readiness/
│   ├── video-scraper/
│   └── lead-intelligence/
└── infra/
    ├── docker-compose.yml
    └── init-db.sql
```

Each module has:
- `manifest.json` — registry entry (id, route, required env)
- `backend/` — FastAPI service
- `frontend/` — React panel loaded by the web shell

### Services & Ports (default host mapping)

| Service | Internal | Host | Purpose |
|---------|----------|------|---------|
| `web` | 3000 | **3200** | Dashboard UI |
| `video-scraper-api` | 8001 | **8101** | Video extraction & transcription |
| `market-depth-api` | 8002 | **8102** | Market scoring & narratives |
| `lead-intelligence-api` | 8003 | **8103** | Lead discovery & pipeline |
| `build-readiness-api` | 8004 | **8104** | Company depth & fit verdicts |
| `postgres` | 5432 | — | Shared database |
| `redis` | 6379 | — | Cache / job backing |
| `minio` | 9000 | **9100** | Temp video staging |

### Database Tables (by prefix)

| Prefix | Examples |
|--------|----------|
| `market_depth_*` | domains, snapshots, reports, jobs, weights |
| `build_readiness_*` | profiles, chunks, capabilities, verdicts, index_runs |
| `video_scraper_*` | jobs |
| `leads_*` | leads, contacts, fit_profile |

---

## 3. Market Depth Analyzer

**Purpose:** Rank blockchain and AI market domains by live demand signals. Produce algorithmic scores plus LLM-grounded narratives.

**Key files:** `modules/market-depth-analyzer/backend/scoring/engine.py`, `sources/__init__.py`, `intelligence/product_landscape.py`, `narrative.py`, `pipeline.py`

### 3.1 Seed Domains (11)

| Domain | Track | Example Keywords |
|--------|-------|------------------|
| Smart Contract Engineering | blockchain | solidity, smart contract, ethereum |
| DeFi Protocol Engineering | blockchain | defi, amm, liquidity protocol |
| **Stablecoin & Payments Engineering** | blockchain | stablecoin, usdc, usdt, payment rail, fiat-backed token |
| Blockchain Security / Auditing | blockchain | blockchain audit, smart contract security |
| L2 / Infra Engineering | blockchain | layer 2, rollup, blockchain infrastructure |
| Web3 Growth/Tokenomics | blockchain | tokenomics, web3 growth, crypto marketing |
| LLM Application Engineering | ai | llm, langchain, rag application |
| AI Agent Orchestration | ai | ai agent, agent orchestration, autonomous agent |
| LLMOps / Inference Infra | ai | llmops, inference, model serving |
| AI Security / Red-teaming | ai | ai security, llm red team, prompt injection |
| Applied ML / Data Engineering | ai | machine learning, data engineering, mlops |

### 3.2 Signal Sources

Five independent signals are fetched per domain on each refresh:

| Signal | Weight | Source | Raw Value |
|--------|--------|--------|-----------|
| **hiring_demand** | 0.30 | Adzuna API + RemoteOK | `max(adzuna_job_counts) + remoteok_keyword_matches` |
| **capital_flow** | 0.25 | DefiLlama (blockchain) or CoinGecko (ai) | Sum of TVL or market cap for keyword-matched protocols/coins |
| **developer_momentum** | 0.20 | GitHub Search API | `total_count` of repos matching domain keywords (90-day filter, falls back to all-time on 403) |
| **funding_signal** | 0.15 | TechCrunch AI + Crypto RSS | `mention_count + log10(disclosed_usd + 1)` |
| **public_interest** | 0.10 | Google Trends (pytrends) | Mean 12-month interest index across up to 3 keywords |

**Important:** If an API key is missing or a source returns no data, that signal is marked `available=False` and is **excluded from scoring** — missing data does not penalize a domain.

### 3.3 Normalization (Min-Max)

For each signal, raw values are normalized across all 11 domains in the current batch:

```
normalized = ((value - min) / (max - min)) × 100
```

Rules:
- Clamped to `[0, 100]`
- If `max == min` (all domains equal): returns **50.0**
- Unavailable signals: normalized to **0.0** but excluded from composite weight sum

### 3.4 Composite Score

```
weight_sum = Σ weights[k]  for k in available_signals only

composite_score = Σ (normalized[k] × weights[k]) / weight_sum
```

Default weights (adjustable via UI sliders, stored in `market_depth_weights`):

```python
DEFAULT_WEIGHTS = {
    "hiring_demand":       0.30,
    "capital_flow":        0.25,
    "developer_momentum":  0.20,
    "funding_signal":      0.15,
    "public_interest":     0.10,
}
```

Domains are ranked by `composite_score` descending.

### 3.5 Product Landscape (Deterministic)

Built from raw signals — **not LLM-generated**.

**Product type detection:** 13 patterns (e.g. "AI Agents & Copilots", "DeFi Protocols (DEX/Lending)", **"Stablecoins & Payment Rails"**) matched by keyword frequency in combined signal text blobs. Top **6** types by hit count become `product_types_in_demand`.

**Signal strength** = keyword hit count per product type.

**Revenue model fit** (derived from product types, not hardcoded per domain):

| signal_strength | fit label |
|-----------------|-----------|
| ≥ 3 | high |
| ≥ 2 | medium |
| else | low |

Up to **5** revenue models per domain; padded from defaults if fewer than 3 detected.

**Stablecoin-specific revenue models** (when "Stablecoins & Payment Rails" is detected):
- Payment API fees (per-transaction B2B rails)
- Reserve yield / issuance spread
- Cross-border remittance fees
- Compliance & attestation SaaS (reserve proof, KYC/AML)

**Builders** extracted from: GitHub top repos (8), job top companies (8), protocols/coins (6), funding headlines (6) — max **12** total.

**Market indicators** stored per snapshot: job counts, TVL/market cap, funding mentions, `signals_available` / `signals_total` (out of 5).

### 3.6 AI Narrative (LLM Layer)

After algorithmic scoring, an LLM (`gpt-5-mini` by default) generates:

- `executive_summary`
- `domain_narratives` for top 3 domains
- `confidence_flags` for thin evidence

**Validation rules** (rejects hallucinated numbers):
- Output numbers > 5 must exist in input JSON
- Top-3 narrative domains must match top 3 by `composite_score`
- No duplicate domains
- One automatic retry on validation failure

**Fallback without API key:** Deterministic summary citing top domain and score only.

### 3.7 Refresh Pipeline

```
fetching → scoring → narrating → done
```

Each refresh creates a `snapshot_batch_id`. Per domain stores:
- `MarketDepthSnapshot` — raw evidence, normalized components, composite score, product_landscape
- `MarketDepthReport` — narrative JSON + validation status

---

## 4. Build Readiness Engine

**Purpose:** Index a company's website (and video transcripts) into a RAG store, cross-reference Market Depth demand data, and produce per-domain **GO / CONDITIONAL / NO_GO** verdicts with build plans.

**Key files:** `crawler.py`, `rag.py`, `capabilities.py`, `pipeline.py`, `verdict.py`, `market_bridge.py`

### 4.1 Three-Step Pipeline

| Step | Requirement | Stored In |
|------|-------------|-----------|
| 1. Market Depth | Latest snapshots exist | `market_depth_snapshots` (read via bridge) |
| 2. Company Depth | Website indexed (`chunks > 0`, `last_indexed_at` set) | `build_readiness_chunks`, `build_readiness_capabilities` |
| 3. Fit Verdict | Analysis run completed | `build_readiness_verdicts` |

`can_analyze = market_ready AND company_ready`

### 4.2 Website Crawler

- **Algorithm:** Same-origin BFS from configured company URL
- **Max pages:** `MAX_CRAWL_PAGES` (default 50 local / 120 in Docker)
- **Skips:** `.pdf`, images, `.mp4`, fonts, etc.
- **Min text per page:** 80 characters
- **Timeout:** 15 seconds per page
- **Progress:** Reported every 5 pages

### 4.3 RAG Indexing

| Setting | Value |
|---------|-------|
| Chunk size | 900 characters |
| Chunk overlap | 120 characters |
| Min chunk length | > 60 characters |
| Embedding model | `text-embedding-3-small` |
| Embed batch size | 40 chunks |
| Storage | JSONB vectors in Postgres (cosine similarity in-memory) |

**Retrieval at analysis time:** Top **k = 8** chunks by cosine similarity to domain query embedding.

**Query construction per domain:**
```
domain_name + keywords + product_types_from_market_landscape
```

### 4.4 Capability Taxonomy (Company Depth)

Deterministic keyword extraction across all crawled pages. **8 categories**, ~85 keywords:

| Category | Example Keywords |
|----------|------------------|
| `blockchain_core` | solidity, smart contract, defi, layer 2, nft, dao |
| `blockchain_security` | audit, formal verification, penetration, exploit |
| `stablecoins_payments` | **stablecoin, usdc, usdt, payment rail, remittance, cbdc, mint, redeem, reserve attestation** |
| `ai_ml` | llm, langchain, rag, mlops, fine-tuning, agent |
| `ai_governance` | ai governance, guardrail, prompt injection |
| `gaming_metaverse` | game development, metaverse, p2e, unity |
| `enterprise` | enterprise, supply chain, healthcare, fintech, saas |
| `infrastructure` | wallet, exchange, custody, rpc, oracle, bridge |

**Depth score per capability:**
```
depth_score = min(100, evidence_count × 8 + len(sample_urls) × 5)
```

Top **80** capabilities stored; up to **5** sample URLs each.

### 4.5 Capability Match Score

For each market domain at analysis time:

```
keyword_score = Σ (depth_score × 0.15)   for each matching capability

chunk_hits = count of retrieved chunks containing query terms

semantic_avg = mean(cosine_similarity) of top-8 retrieved chunks

capability_score = min(100,
    keyword_score × 0.35
  + semantic_avg × 100 × 0.45
  + chunk_hits × 8 × 0.20
)
```

Returns up to **12** matched capability names for citations.

### 4.6 Opportunity Score & Algorithmic Verdict

```
opportunity_score = market_score × 0.55 + capability_score × 0.45
```

Where `market_score` = `composite_score` from latest Market Depth snapshot.

**Thresholds:**

| Verdict | Condition |
|---------|-----------|
| **GO** | `opportunity ≥ 65` AND `capability_score ≥ 45` |
| **CONDITIONAL** | `opportunity ≥ 45` AND `capability_score ≥ 30` |
| **NO_GO** | otherwise |

### 4.7 LLM Verdict Layer

After algorithmic scoring, an LLM synthesizes a grounded verdict JSON:

- `headline`, `market_need`, `our_strengths`, `gaps`
- `how_to_build` (phase_1, phase_2, phase_3)
- `revenue_path`, `depth_assessment`
- `strengthen_suggestions` (required for NO_GO / CONDITIONAL)
- `cited_evidence` from RAG chunks

**Rules enforced in prompt:**
- Never invent numbers not in input
- Never claim capabilities unsupported by retrieved evidence
- Verdict must be GO, CONDITIONAL, or NO_GO

**Validation:** Rejects output numbers > 5 not present in input; one retry.

**Fallback without API key:** Algorithmic verdict only; `can_build = capability_score ≥ 50`.

LLM verdict may override algorithmic label if `verdict_json.verdict` is set.

### 4.8 Market Depth Bridge

Build Readiness reads market data **directly from shared Postgres** (not HTTP):

```sql
DISTINCT ON (domain_id) ... ORDER BY fetched_at DESC
```

Returns per domain: `market_score`, `product_landscape`, `components`, `raw_evidence`, `fetched_at`.

### 4.9 Video Transcript Indexing

Pulls up to **50** completed `video_scraper_jobs` with transcript length > 100 characters. Chunks and embeds as `source_type = "video"`. Does not replace website capabilities but enriches RAG retrieval.

### 4.10 Stablecoins in the Fit Pipeline

Stablecoins are a **first-class market domain**, not a sub-topic of DeFi:

| Layer | What happens |
|-------|----------------|
| **Market Depth** | Domain `Stablecoin & Payments Engineering` scored on hiring, capital, GitHub repos, funding, and search trends for stablecoin/payment-rail keywords |
| **Product landscape** | Detects `Stablecoins & Payment Rails` product type; maps payment API, reserve yield, remittance, and compliance revenue models |
| **Build Readiness** | `stablecoins_payments` capability category matches company website evidence (USDC integrations, payment rails, CBDC, treasury, etc.) |
| **Fit Verdict** | Cross-scores market demand vs Antier depth — e.g. if site mentions stablecoin development but market score is low, verdict may be CONDITIONAL with strengthen suggestions |

After deploying this update, run **Market Depth → Refresh Data** then **Build Readiness → Re-index Website → Run Fit Analysis** to include stablecoin verdicts.

### 4.11 Versioning

- Re-index website: replaces website chunks + capabilities; history kept in `build_readiness_index_runs`
- Each analysis run gets a `analysis_batch_id`; prior verdicts preserved
- `/verdicts/latest` returns most recent batch only

---

## 5. Video Scraper

**Purpose:** Extract video metadata and transcripts from platform URLs, generic pages, or direct files; summarize with LLM.

**Key files:** `extractor.py`, `browser_discovery.py`, `ytdlp_utils.py`, `pipeline.py`, `local_transcription.py`, `openai_service.py`

### 5.1 URL Classification

| Type | Detection |
|------|-----------|
| `platform` | YouTube, Vimeo, TikTok, Twitter/X, etc. (16 domains) |
| `direct-file` | `.mp4`, `.webm`, `.m3u8`, `.mpd`, etc. |
| `generic-page` | Marketing sites, portfolio pages, etc. |

### 5.2 Extraction Pipeline

```
extracting → downloading → transcribing → summarizing → done
```

**Order of attempts:**

1. **yt-dlp** on submitted URL (metadata + optional native captions)
2. **Playwright browser discovery** (page + iframes + network requests)
3. **Subpath probes:** `/video-testimonials`, `/videos`, `/portfolio`, `/work`

### 5.3 yt-dlp Configuration

- **YouTube player clients rotated:** android, ios, web, mweb, tv_embedded
- **Download format chain:** `ba/b` → `bestaudio/best` → `best[height<=720]/best` → `worst`
- **Caption languages tried:** en, en-US, en-GB, fuzzy `en*`
- **Caption fetch failures are non-fatal** — falls back to download + transcribe
- **Max duration:** 7200 seconds (2 hours)

### 5.4 Browser Discovery (Playwright)

- Chromium, 90 second page timeout
- Scrolls 6 viewport heights; clicks video-related selectors
- Scans: `og:video` meta, iframes, `<video>` elements, network responses
- **Candidate scoring:**

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

### 5.5 Transcription

**Default: local faster-whisper** (no OpenAI Audio API required)

| Setting | Default |
|---------|---------|
| `TRANSCRIPTION_PROVIDER` | `local` |
| `LOCAL_WHISPER_MODEL` | `small` |
| Device | CPU, int8 |
| Whisper params | `beam_size=5`, `vad_filter=True` |
| Audio extract (ffmpeg) | max 600 seconds, MP3 |

**OpenAI fallback** (`TRANSCRIPTION_PROVIDER=openai`): uses Audio API (`whisper-1` or configured `TRANSCRIPTION_MODEL`). Requires project with Audio API access.

> **Note:** `gpt-5-mini` cannot transcribe audio. It is used only for **summarization** after transcription.

### 5.6 Summarization (gpt-5-mini)

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

### 5.7 Media Staging

Downloads staged to local disk + optional MinIO mirror. **Always deleted** after job completes (success or failure).

---

## 6. Lead Intelligence Engine

**Purpose:** Discover leads from government tenders, Web3 funding, AI launches; score and enrich using **Market Depth demand signals** and **Build Readiness company strengths**. Finds leads in two orientations:

| Orientation | When | Strategy |
|-------------|------|----------|
| **Demand-oriented** | Hot market + proven depth (GO or CONDITIONAL with capability ≥ 35) | Pursue now — we can deliver |
| **Future-oriented** | Hot market (score ≥ 40) + capability gap (NO_GO or capability < 35) | Growth opportunity — build depth while market heats up |

**Key files:** `intelligence_bridge.py`, `scoring/domain_match.py`, `scoring/lead_score.py`, `pipeline.py`, `pipeline_status.py`

### 6.1 Cross-Module Flow

```
Market Depth (snapshots) ──┐
                           ├── intelligence_bridge → demand_domains / future_domains
Build Readiness (verdicts) ┘
                           │
                           ▼
              domain_match → lead_orientation per entity
                           │
                           ▼
              lead_score (market_demand_fit + capability_fit)
```

**Prerequisites for aligned scoring:**
1. Refresh **Market Depth Analyzer** (domain snapshots)
2. Index website + **Run Fit Analysis** in Build Readiness

Discovery auto-syncs fit keywords from GO domains + future opportunity domains + top capabilities.

### 6.2 Discovery Sources

| Source | Track | Type |
|--------|-------|------|
| SAM.gov | government | tender |
| Grants.gov | government | grant |
| World Bank procurement | government | tender |
| TED EU | government | tender |
| GeM (India) | government | tender |
| CPPP (India) | government | tender |
| DefiLlama raises | web3 | funding |
| Web3.career | web3 | hiring |
| Product Hunt | ai/web2 | launch |
| YC AI directory | ai | funding |
| Crunchbase RSS | web2 | funding |

Rate limit: **1.0 second** per domain.

### 6.3 Lead Scoring

**Default weights:**

| Component | Weight | Role |
|-----------|--------|------|
| `market_demand_fit` | 0.22 | Market heat + opportunity score (orientation-aware) |
| `capability_fit` | 0.20 | Our depth vs gap (high for demand, inverted for future) |
| `keyword_fit` | 0.14 | Synced keywords from GO + future domains |
| `budget_indicator` | 0.14 | Signal value (funding, contract size) |
| `recency` | 0.12 | Signal freshness |
| `urgency` | 0.10 | Deadline proximity (government) |
| `contact_confidence` | 0.08 | Email verification |

**Orientation classification** (`domain_match.classify_orientation`):

```
demand:  verdict GO, or CONDITIONAL + capability ≥ 35
future:  market_score ≥ 40 and (NO_GO or capability < 35 or no verdict)
generic: weak domain match or low market signal
```

**Component formulas:**

```
recency_decay:
  ≤7 days  → 1.0
  ≤30 days → 0.8
  ≤90 days → 0.5
  else     → 0.2
  no date  → 0.3

normalize_budget(value, max=50_000_000):
  no value → 0.2
  else     → min(1.0, value / 50_000_000)

keyword_fit:
  matches / max(len(keywords) × 0.3, 1), capped at 1.0

deadline_proximity (government only; else 0.5):
  past deadline → 0
  ≤5 days       → 1.0
  ≤14 days      → 0.8
  ≤30 days      → 0.6
  else          → 0.4
  no deadline   → 0.3

contact_confidence:
  verified email   → 1.0
  unverified email → 0.5
  none             → 0.0

market_demand_fit (orientation-aware):
  demand → market_score/100 × 0.5 + opportunity_score/100 × 0.5
  future → market_score/100 × 0.7 + 0.15
  generic → market_score/100 × 0.4

capability_fit (orientation-aware):
  demand + GO         → min(1, capability/100 + 0.2)
  demand + CONDITIONAL → min(1, capability/100)
  future              → min(1, max(0.3, market×0.6 − capability×0.3 + 0.2))

composite_score = (weighted_sum / weight_sum) × 100
```

**API endpoints:**
- `GET /pipeline/status` — readiness + demand/future domain counts
- `POST /fit-profile/sync` — rebuild keywords from Market Depth + Build Readiness; re-score all leads
- `GET /leads?orientation=demand|future|generic` — filter by orientation

### 6.4 Enrichment

Contact lookup priority: **Apollo** → **Hunter** → **Clearbit** (up to 3 contacts each). Fallback: `info@{domain}` (unverified).

### 6.5 Pipeline Stages

`new` → `qualified` → `contacted` → `replied` → `won` / `lost`

Outreach drafts are LLM-generated for **human review only** — no auto-send.

---

## 7. Cross-Module Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     External APIs                                │
│  GitHub · Adzuna · RemoteOK · DefiLlama · CoinGecko · Trends    │
│  TechCrunch RSS · SAM.gov · Apollo · Hunter · YouTube · etc.     │
└────────────┬───────────────────────────────┬────────────────────┘
             │                               │
             ▼                               ▼
    ┌────────────────┐              ┌────────────────┐
    │ Market Depth   │              │ Video Scraper  │
    │ API :8102      │              │ API :8101      │
    └───────┬────────┘              └───────┬────────┘
            │                               │
            │  market_depth_snapshots       │  video_scraper_jobs
            │                               │  (transcripts)
            ▼                               ▼
    ┌─────────────────────────────────────────────────┐
    │              PostgreSQL (toolhub)                │
    └───────────────────────┬─────────────────────────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │ Build Readiness      │
                 │ API :8104            │
                 │                      │
                 │ 1. Read market snaps │
                 │ 2. RAG company index │
                 │ 3. Fit verdicts      │
                 └──────────┬───────────┘
                            │
                            │  build_readiness_verdicts
                            │  + market_depth_snapshots
                            ▼
                 ┌────────────────────┐
                 │ Lead Intelligence    │
                 │ API :8103            │
                 │                      │
                 │ demand + future      │
                 │ domain-matched leads │
                 └────────────────────┘
```

**Build Readiness analysis per domain:**
1. Load latest market snapshot → `market_score`, `product_landscape`
2. Embed domain query → retrieve top-8 company chunks
3. Compute `capability_score` + `opportunity_score`
4. LLM verdict with RAG citations
5. Store in `build_readiness_verdicts` (versioned batch)

---

## 8. Configuration & API Keys

### Shared vs Per-Tool Keys

| Variable | Used By |
|----------|---------|
| `OPENAI_API_KEY` | All modules (fallback) |
| `VIDEO_SCRAPER_OPENAI_API_KEY` | Video summarization only |
| `MARKET_DEPTH_OPENAI_API_KEY` | Market narratives |
| `BUILD_READINESS_OPENAI_API_KEY` | RAG embeddings + verdicts |
| `LEAD_INTELLIGENCE_OPENAI_API_KEY` | Outreach drafts |
| `GITHUB_TOKEN` | Market Depth developer momentum |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Market Depth hiring demand |
| `APOLLO_API_KEY` / `HUNTER_API_KEY` | Lead enrichment |

### Video Scraper Transcription

```env
TRANSCRIPTION_PROVIDER=local        # default — no Whisper API needed
LOCAL_WHISPER_MODEL=small           # base | small | medium
# TRANSCRIPTION_PROVIDER=openai     # requires Audio API access
# TRANSCRIPTION_MODEL=whisper-1
```

### Build Readiness

```env
DEFAULT_COMPANY_URL=https://www.antier.com/
DEFAULT_COMPANY_NAME=Antier
MAX_CRAWL_PAGES=120
EMBEDDING_MODEL=text-embedding-3-small
```

### Health / Config Endpoints

| API | Endpoint |
|-----|----------|
| Market Depth | `GET /config` — key status, chat model |
| Video Scraper | `GET /config` — transcription provider, whisper model |
| Build Readiness | `GET /pipeline/status` — 3-step readiness |
| All | `GET /health` |

---

## 9. Known Limitations

| Area | Limitation |
|------|------------|
| **RAG retrieval** | Embeddings in JSONB; in-memory cosine similarity (no pgvector). Fine for <10k chunks. |
| **Market Depth** | Min-max normalization is batch-relative — scores shift when domain set changes. |
| **Market Depth** | Google Trends can rate-limit; signal marked unavailable, not penalized. |
| **Build Readiness** | Capability taxonomy is keyword-based — misses capabilities not in ~70 keyword list. |
| **Build Readiness** | Website re-index clears capabilities; video-only index does not update `last_indexed_at`. |
| **Video Scraper** | Local Whisper extracts max **10 minutes** of audio per video. |
| **Video Scraper** | Hindi/Sanskrit/low-quality audio may produce short transcripts on `small` model. |
| **Video Scraper** | JS-heavy sites may need direct video URL or channel URL. |
| **Lead Intelligence** | Government portal scraping is brittle; some sources return empty without keys. |
| **Jobs** | BackgroundTasks are in-process — jobs lost on container restart. |

---

## Quick Reference — Key Formulas

```
# Market Depth composite
composite = Σ(normalized[k] × weight[k]) / Σ(weight[k])   # available signals only

# Build Readiness opportunity
opportunity = market_score × 0.55 + capability_score × 0.45

# Build Readiness capability match
cap_score = min(100, keyword×0.35 + semantic×45 + chunk_hits×1.6)

# Build Readiness verdict thresholds
GO:          opportunity ≥ 65 AND cap_score ≥ 45
CONDITIONAL: opportunity ≥ 45 AND cap_score ≥ 30
NO_GO:       else

# Company capability depth
depth_score = min(100, evidence_count × 8 + urls × 5)

# Lead composite
lead_score = (Σ component[k] × weight[k]) / Σ(weight[k]) × 100
```

---

*Document version: 1.0 — reflects Tool Hub codebase as of July 2026.*
