# Build Readiness Engine — Complete Product One-Pager

**Product:** Build Readiness Engine  
**Part of:** Tool Hub — Revenue Intelligence Platform  
**Tagline:** Index your company depth, cross-market demand, and get a GO / NO-GO verdict with a build plan.  
**Audience:** CEO, practice heads, sales leadership, delivery leads, investors, technical stakeholders  
**Status:** Working POC (v1.0.0)  
**Default port:** `8104` (API) · Dashboard route: `/tools/build-readiness`

---

## One Sentence

Build Readiness Engine indexes your company website (and video transcripts) into a searchable knowledge base, cross-references **live Market Depth demand data**, and produces per-domain **GO / CONDITIONAL / NO_GO** verdicts with cited evidence and phased build plans.

---

## The Problem It Solves

Hot markets are useless if you cannot credibly deliver. Services firms routinely pursue opportunities where they lack published proof, case studies, or technical depth — eroding win rate, margins, and brand trust. Manual website audits and capability matrices are slow, subjective, and disconnected from live market signals.

**This product answers:** *Can we credibly win in those markets today — and if not, what should we build?*

---

## What It Does

| Capability | Detail |
|------------|--------|
| **Website crawler** | Same-origin BFS from company URL; extracts text for RAG indexing |
| **RAG knowledge base** | Chunked, embedded company content stored in Postgres |
| **Capability taxonomy** | 8 categories, ~85 keywords — deterministic depth scoring |
| **Market cross-reference** | Reads latest Market Depth snapshots from shared database |
| **Algorithmic scoring** | `capability_score` + `opportunity_score` per domain |
| **LLM verdicts** | Grounded GO/CONDITIONAL/NO_GO with cited evidence and build plans |
| **Video enrichment** | Indexes completed Video Scraper transcripts into RAG |
| **Versioned history** | Index runs and analysis batches preserved for accountability |

---

## The Three-Step Pipeline

```
Market Depth  →  Company Depth  →  Fit Verdict
(live signals)   (RAG index)      (GO / CONDITIONAL / NO_GO)
```

| Step | Requirement | Stored In |
|------|-------------|-----------|
| 1. Market Depth | Latest snapshots exist | `market_depth_snapshots` (read via bridge) |
| 2. Company Depth | Website indexed (`chunks > 0`, `last_indexed_at` set) | `build_readiness_chunks`, `build_readiness_capabilities` |
| 3. Fit Verdict | Analysis run completed | `build_readiness_verdicts` |

`can_analyze = market_ready AND company_ready`

**Check status:** `GET /pipeline/status`

---

## How It Works — Website Indexing

### Crawler

| Setting | Value |
|---------|-------|
| Algorithm | Same-origin BFS from configured company URL |
| Max pages | 50 (local) / 120 (Docker) via `MAX_CRAWL_PAGES` |
| Skips | `.pdf`, images, `.mp4`, fonts, etc. |
| Min text per page | 80 characters |
| Timeout | 15 seconds per page |
| Progress | Reported every 5 pages |

**Trigger:** `POST /index/website`

### RAG Indexing

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

---

## Capability Taxonomy (Company Depth)

Deterministic keyword extraction across all crawled pages. **8 categories**, ~85 keywords:

| Category | Example Keywords |
|----------|------------------|
| `blockchain_core` | solidity, smart contract, defi, layer 2, nft, dao |
| `blockchain_security` | audit, formal verification, penetration, exploit |
| `stablecoins_payments` | stablecoin, usdc, usdt, payment rail, remittance, cbdc, mint, redeem |
| `rwa_tokenization` | rwa, tokenization, real world asset, security token, asset-backed |
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

---

## Scoring Algorithms

### Capability Match Score

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

### Opportunity Score

```
opportunity_score = market_score × 0.55 + capability_score × 0.45
```

Where `market_score` = `composite_score` from latest Market Depth snapshot.

### Algorithmic Verdict Thresholds

| Verdict | Condition |
|---------|-----------|
| **GO** | `opportunity ≥ 65` AND `capability_score ≥ 45` |
| **CONDITIONAL** | `opportunity ≥ 45` AND `capability_score ≥ 30` |
| **NO_GO** | otherwise |

---

## LLM Verdict Layer

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

**Trigger:** `POST /analyze`

---

## Video Transcript Indexing

Pulls up to **50** completed `video_scraper_jobs` with transcript length > 100 characters. Chunks and embeds as `source_type = "video"`. Enriches RAG retrieval without replacing website capabilities.

**Trigger:** `POST /index/videos`

---

## Stablecoins & RWA — First-Class Domains

Stablecoins and RWA are tracked as **standalone market domains**, not sub-topics of DeFi:

| Layer | What Happens |
|-------|--------------|
| **Market Depth** | Domains scored on hiring, capital, GitHub, funding, and search trends |
| **Product landscape** | Detects `Stablecoins & Payment Rails` and `RWA & Asset Tokenization` product types |
| **Build Readiness** | `stablecoins_payments` and `rwa_tokenization` capability categories match website evidence |
| **Fit Verdict** | Cross-scores market demand vs company depth with strengthen suggestions for gaps |

**After updates:** Run Market Depth → Refresh Data, then Build Readiness → Re-index Website → Run Fit Analysis.

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health |
| GET | `/config` | Company profile, key status |
| GET | `/pipeline/status` | 3-step readiness (market / company / verdict) |
| GET | `/profile` | Current company profile |
| PUT | `/profile` | Update company URL and name |
| POST | `/index/website` | Crawl and index company website |
| POST | `/index/videos` | Index Video Scraper transcripts |
| POST | `/analyze` | Run fit analysis across all domains |
| GET | `/jobs/{job_id}` | Index or analysis job status |
| GET | `/history/index-runs` | Past website index runs |
| GET | `/history/analysis-runs` | Past analysis batches |
| GET | `/capabilities` | Detected company capabilities |
| GET | `/domains/status` | Per-domain market + verdict status |
| GET | `/verdicts/latest` | Latest verdict batch |

---

## Configuration & API Keys

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Embeddings + verdicts |
| `BUILD_READINESS_OPENAI_API_KEY` | Optional override | Verdicts only |
| `DEFAULT_COMPANY_URL` | `https://www.antier.com/` | Crawl start URL |
| `DEFAULT_COMPANY_NAME` | `Antier` | Profile name |
| `MAX_CRAWL_PAGES` | 120 (Docker) | Crawl depth limit |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | RAG embeddings |

---

## Integration With Other Tool Hub Modules

```
┌────────────────────┐
│ Market Depth       │─── market_depth_snapshots (market_score, product_landscape)
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐     ┌────────────────────┐
│ Build Readiness    │◄────│ Video Scraper      │
│                    │     │ (transcripts)      │
└─────────┬──────────┘     └────────────────────┘
          │
          │  build_readiness_verdicts
          ▼
┌────────────────────┐
│ Lead Intelligence│
│ (demand/future   │
│  domain sync)    │
└────────────────────┘
```

**Prerequisites for analysis:**
1. Refresh **Market Depth Analyzer** first
2. Index website (`POST /index/website`)
3. Optionally index videos (`POST /index/videos`)
4. Run Fit Analysis (`POST /analyze`)

---

## Two Commercial Modes (From Verdicts)

| Mode | Verdict | GTM Action |
|------|---------|------------|
| **Demand-oriented** | GO, or CONDITIONAL + capability ≥ 35 | Sales, proposals, outbound now |
| **Future-oriented** | Hot market + NO_GO or weak capability | Hire, productize, publish thought leadership |

This prevents overselling into markets where delivery risk erodes margin.

---

## Business Value

| Outcome | How |
|---------|-----|
| **Higher win rate** | Pursue only domains with cited proof from your own content |
| **Honest capability gaps** | NO_GO verdicts with strengthen suggestions guide investment |
| **Faster positioning** | New service pages flow into verdicts on re-index |
| **Accountability** | Versioned batches create decision history for board retrospectives |
| **Sales enablement** | Verdict JSON includes `our_strengths`, `revenue_path`, and `cited_evidence` |

---

## Operational Best Practices

| Practice | Why |
|----------|-----|
| Re-index after major website launches | New pages (stablecoin, RWA, agents) must enter RAG |
| Run Fit Analysis after every market refresh | Verdicts must reflect current demand |
| Review CONDITIONAL verdicts monthly | These are your deliberate build investments |
| Index video transcripts from talks/demos | Strengthens evidence for domains with thin website copy |

**Recommended cadence:** Weekly — refresh Market Depth → re-index if site changed → Run Fit Analysis.

---

## Known Limitations

| Area | Limitation |
|------|------------|
| **RAG retrieval** | Embeddings in JSONB; in-memory cosine similarity (no pgvector). Fine for <10k chunks. |
| **Capability taxonomy** | Keyword-based — misses capabilities not in ~85 keyword list |
| **Website re-index** | Clears capabilities; video-only index does not update `last_indexed_at` |
| **Jobs** | BackgroundTasks in-process — jobs lost on container restart |
| **LLM dependency** | Full verdicts require OpenAI key; fallback is algorithmic only |

---

## Quick Reference — Key Formulas

```
# Opportunity score
opportunity = market_score × 0.55 + capability_score × 0.45

# Capability match
cap_score = min(100, keyword×0.35 + semantic×45 + chunk_hits×1.6)

# Verdict thresholds
GO:          opportunity ≥ 65 AND cap_score ≥ 45
CONDITIONAL: opportunity ≥ 45 AND cap_score ≥ 30
NO_GO:       else

# Company capability depth
depth_score = min(100, evidence_count × 8 + urls × 5)
```

---

## Architecture Notes

- **Backend:** FastAPI (`modules/build-readiness/backend/`)
- **Frontend:** React panel loaded by Tool Hub web shell
- **Database tables:** `build_readiness_profiles`, `build_readiness_chunks`, `build_readiness_capabilities`, `build_readiness_verdicts`, `build_readiness_index_runs`, `build_readiness_analysis_runs`
- **Key files:** `crawler.py`, `rag.py`, `capabilities.py`, `pipeline.py`, `verdict.py`, `market_bridge.py`

---

*Standalone product brief — Tool Hub Build Readiness Engine v1.0 · July 2026*
