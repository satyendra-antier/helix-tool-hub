# Market Depth Analyzer — Complete Product One-Pager

**Product:** Market Depth Analyzer  
**Part of:** Tool Hub — Revenue Intelligence Platform  
**Tagline:** Real signal, not AI opinion — where the revenue actually is.  
**Audience:** CEO, GTM leadership, strategy teams, investors, technical stakeholders  
**Status:** Working POC (v1.0.0)  
**Default port:** `8102` (API) · Dashboard route: `/tools/market-depth-analyzer`

---

## One Sentence

Market Depth Analyzer ranks **12 blockchain and AI market domains** using live hiring, capital, developer, funding, and search-trend signals — then layers LLM-grounded narratives on top of algorithmic scores so leadership knows **where demand is actually growing**.

---

## The Problem It Solves

Services firms waste BD and marketing spend chasing domains that *sound* hot but lack measurable demand — or they miss emerging categories (stablecoins, RWA, AI agents) until competitors consolidate. Manual market research is expensive, stale, and opinion-driven.

**This product answers:** *Where is demand actually growing right now, and what product types and revenue models is the market paying for?*

---

## What It Does

| Capability | Detail |
|------------|--------|
| **Live domain scoring** | Composite score (0–100) per domain from 5 independent signals |
| **12 seed domains** | 7 blockchain + 5 AI tracks, configurable |
| **Product landscape** | Deterministic detection of product types in demand (e.g. Stablecoins, RWA, AI Agents) |
| **Revenue model mapping** | Algorithmic fit labels (high/medium/low) for monetization patterns |
| **Builder intelligence** | Top repos, hiring companies, protocols, and funding headlines per domain |
| **AI narratives** | Executive summary + top-3 domain narratives with hallucination guards |
| **Adjustable weights** | UI sliders persist signal weights to database |
| **Versioned snapshots** | Every refresh creates a batch; history preserved for trend analysis |

---

## 12 Tracked Domains

| Domain | Track | Example Keywords |
|--------|-------|------------------|
| Smart Contract Engineering | blockchain | solidity, smart contract, ethereum |
| DeFi Protocol Engineering | blockchain | defi, amm, liquidity protocol |
| Stablecoin & Payments Engineering | blockchain | stablecoin, usdc, usdt, payment rail |
| RWA / Tokenization Engineering | blockchain | rwa, tokenization, real world asset |
| Blockchain Security / Auditing | blockchain | blockchain audit, smart contract security |
| L2 / Infra Engineering | blockchain | layer 2, rollup, blockchain infrastructure |
| Web3 Growth/Tokenomics | blockchain | tokenomics, web3 growth, crypto marketing |
| LLM Application Engineering | ai | llm, langchain, rag application |
| AI Agent Orchestration | ai | ai agent, agent orchestration, autonomous agent |
| LLMOps / Inference Infra | ai | llmops, inference, model serving |
| AI Security / Red-teaming | ai | ai security, llm red team, prompt injection |
| Applied ML / Data Engineering | ai | machine learning, data engineering, mlops |

---

## How It Works (Pipeline)

```
fetching → scoring → narrating → done
```

1. **Fetch** — Pull raw signals from 5 external sources per domain (parallel, rate-limited).
2. **Score** — Min-max normalize across all domains; compute weighted composite score.
3. **Product landscape** — Deterministic keyword pattern matching on combined signal text.
4. **Narrate** — LLM generates executive summary and top-3 domain narratives (validated against input numbers).
5. **Store** — Snapshot batch written to Postgres (`market_depth_snapshots`, `market_depth_reports`).

**Trigger:** `POST /refresh` from dashboard or API.  
**Recommended cadence:** Weekly (Monday morning before Fit Analysis).

---

## Signal Sources & Weights

Five independent signals per domain. **Missing data does not penalize** — unavailable signals are excluded from the composite weight sum.

| Signal | Default Weight | Source | Raw Value |
|--------|----------------|--------|-----------|
| **hiring_demand** | 0.30 | Adzuna API + RemoteOK | `max(adzuna_job_counts) + remoteok_keyword_matches` |
| **capital_flow** | 0.25 | DefiLlama (blockchain) or CoinGecko (AI) | Sum of TVL or market cap for keyword-matched protocols/coins |
| **developer_momentum** | 0.20 | GitHub Search API | `total_count` of repos matching domain keywords (90-day filter; falls back to all-time on 403) |
| **funding_signal** | 0.15 | TechCrunch AI + Crypto RSS | `mention_count + log10(disclosed_usd + 1)` |
| **public_interest** | 0.10 | Google Trends (pytrends) | Mean 12-month interest index across up to 3 keywords |

### Normalization (Min-Max)

```
normalized = ((value - min) / (max - min)) × 100
```

- Clamped to `[0, 100]`
- If all domains equal (`max == min`): returns **50.0**
- Unavailable signals: normalized to **0.0** but **excluded** from composite

### Composite Score

```
weight_sum = Σ weights[k]  for k in available_signals only

composite_score = Σ (normalized[k] × weights[k]) / weight_sum
```

Domains ranked by `composite_score` descending.

---

## Product Landscape (Deterministic — Not LLM)

Built from raw signals using **14 product-type patterns**:

- AI Agents & Copilots
- RAG / Knowledge Apps
- LLM APIs & Dev Tools
- Smart Contract Platforms
- DeFi Protocols (DEX/Lending)
- **Stablecoins & Payment Rails**
- **RWA & Asset Tokenization**
- Blockchain Security / Auditing
- L2 / Rollup Infrastructure
- Tokenomics / Growth Tools
- MLOps / Data Pipelines
- AI Safety / Red-teaming
- Wallets & Custody
- Analytics & Dashboards

**Detection:** Keyword frequency in combined signal text blobs. Top **6** types by hit count become `product_types_in_demand`.

**Revenue model fit** (derived from product types):

| Signal Strength | Fit Label |
|-----------------|-----------|
| ≥ 3 | high |
| ≥ 2 | medium |
| else | low |

Up to **5** revenue models per domain; padded from defaults if fewer than 3 detected.

**Example — Stablecoins & Payment Rails revenue models:**
- Payment API fees (per-transaction B2B rails)
- Reserve yield / issuance spread
- Cross-border remittance fees
- Compliance & attestation SaaS (reserve proof, KYC/AML)

**Builders extracted from:** GitHub top repos (8), job top companies (8), protocols/coins (6), funding headlines (6) — max **12** total.

---

## AI Narrative Layer

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

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health |
| GET | `/config` | Key status, chat model |
| GET | `/domains` | List active domains |
| POST | `/domains` | Add custom domain |
| GET | `/weights` | Current signal weights |
| POST | `/refresh` | Start market refresh job |
| GET | `/jobs/{job_id}` | Job status (fetching → scoring → narrating → done) |
| GET | `/snapshots/latest` | Latest snapshot per domain |
| GET | `/reports/latest` | Latest narrative reports |
| POST | `/compensation/import` | Import compensation benchmarks |

---

## Configuration & API Keys

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Recommended | AI narratives |
| `MARKET_DEPTH_OPENAI_API_KEY` | Optional override | Narratives only |
| `GITHUB_TOKEN` | Recommended | Developer momentum signal |
| `ADZUNA_APP_ID` | Recommended | Hiring demand |
| `ADZUNA_APP_KEY` | Recommended | Hiring demand |

Without keys, scoring still runs on available signals; narratives fall back to deterministic summaries.

---

## Integration With Other Tool Hub Modules

```
Market Depth Analyzer
        │
        │  market_depth_snapshots (composite_score, product_landscape, raw_evidence)
        ▼
┌───────────────────┐     ┌──────────────────────┐
│ Build Readiness   │     │ Lead Intelligence    │
│ (market_score,    │     │ (demand_domains,     │
│  product types)   │     │  future_domains,     │
└───────────────────┘     │  keyword sync)       │
                          └──────────────────────┘
```

- **Build Readiness** reads latest snapshots via shared Postgres to compute opportunity scores and fit verdicts.
- **Lead Intelligence** uses market scores + product landscape to classify leads as demand-oriented vs future-oriented.

**Downstream prerequisite:** Run Market Depth refresh **before** Build Readiness Fit Analysis and Lead Intelligence sync.

---

## Business Value

| Outcome | How |
|---------|-----|
| **Stop chasing cold markets** | Composite scores surface domains with weak hiring, capital, and developer signals |
| **Spot emerging categories early** | Stablecoin, RWA, and AI agent domains tracked with live data |
| **Sharper GTM positioning** | Product types and revenue models tell sales *what* to sell, not just *where* |
| **Board-ready narratives** | LLM summaries cite algorithmic evidence; validation prevents fabricated numbers |
| **Compounding intelligence** | Versioned snapshots create a decision history of market conditions over time |

---

## Operational Best Practices

| Practice | Why |
|----------|-----|
| Refresh weekly | Markets shift; stale scores mislead verdicts and leads |
| Review top 3 domains in narrative | Align leadership on where to invest BD and hiring |
| Adjust weights deliberately | e.g. overweight hiring if talent scarcity is your leading indicator |
| Run refresh before Fit Analysis | Build Readiness depends on latest `composite_score` |

---

## Known Limitations

| Area | Limitation |
|------|------------|
| **Normalization** | Min-max is batch-relative — scores shift when domain set changes |
| **Google Trends** | Can rate-limit; signal marked unavailable, not penalized |
| **GitHub API** | May 403 on heavy queries; falls back to all-time search |
| **Jobs** | BackgroundTasks are in-process — jobs lost on container restart |
| **Domain count** | Default 12 domains; adding domains changes relative rankings |

---

## Quick Reference — Key Formulas

```
# Composite score
composite = Σ(normalized[k] × weight[k]) / Σ(weight[k])   # available signals only

# Normalization
normalized = ((value - min) / (max - min)) × 100

# Revenue fit
high   = signal_strength ≥ 3
medium = signal_strength ≥ 2
low    = else
```

---

## Architecture Notes

- **Backend:** FastAPI (`modules/market-depth-analyzer/backend/`)
- **Frontend:** React panel loaded by Tool Hub web shell
- **Database tables:** `market_depth_domains`, `market_depth_snapshots`, `market_depth_reports`, `market_depth_jobs`, `market_depth_weights`
- **Key files:** `scoring/engine.py`, `sources/__init__.py`, `intelligence/product_landscape.py`, `narrative.py`, `pipeline.py`

---

*Standalone product brief — Tool Hub Market Depth Analyzer v1.0 · July 2026*
