# Lead Intelligence Engine — Complete Product One-Pager

**Product:** Lead Intelligence Engine  
**Part of:** Tool Hub — Revenue Intelligence Platform  
**Tagline:** Government tenders, funded projects, and hiring signals — organized, scored, never spammed.  
**Audience:** Sales leadership, BD teams, GTM ops, CEO, investors, technical stakeholders  
**Status:** Working POC (v1.0.0)  
**Default port:** `8103` (API) · Dashboard route: `/tools/lead-intelligence`

---

## One Sentence

Lead Intelligence Engine discovers leads from government tenders, Web3 funding, AI launches, and hiring signals — then scores and enriches them using **Market Depth demand data** and **Build Readiness company strengths**, tagging each lead as **demand-oriented** (pursue now) or **future-oriented** (build capability while the market heats up).

---

## The Problem It Solves

Lead lists are disconnected from market reality and company capability. Sales teams chase generic funding roundups, expired tenders, and opportunities in domains where the firm cannot deliver — wasting senior BD time and damaging brand. Auto-outreach tools create spam risk.

**This product answers:** *Who should we pursue right now — and who should we prepare for while we build depth?*

---

## What It Does

| Capability | Detail |
|------------|--------|
| **Multi-source discovery** | Government tenders, grants, Web3 funding, AI launches, hiring signals |
| **Orientation tagging** | Demand-oriented vs future-oriented vs generic per lead |
| **Composite scoring** | 7 weighted components aligned to market + capability fit |
| **Contact enrichment** | Apollo → Hunter → Clearbit with verification confidence |
| **Fit profile sync** | Keywords rebuilt from GO domains + future opportunity domains |
| **Pipeline stages** | new → qualified → contacted → replied → won / lost |
| **Human-reviewed outreach** | LLM drafts for review only — no auto-send |
| **CSV export** | Full lead export for CRM import |

---

## Two Lead Orientations

| Orientation | When | Strategy |
|-------------|------|----------|
| **Demand-oriented** | Hot market + proven depth (GO or CONDITIONAL with capability ≥ 35) | Pursue now — we can deliver |
| **Future-oriented** | Hot market (score ≥ 40) + capability gap (NO_GO or capability < 35) | Growth opportunity — build depth while market heats up |
| **Generic** | Weak domain match or low market signal | Lower priority; filtered in pipeline views |

This prevents both **ignoring growth markets** and **overselling into markets where delivery risk erodes margin**.

---

## How It Works

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
                           │
                           ▼
              enrichment → pipeline → human-reviewed outreach
```

**Prerequisites for aligned scoring:**
1. Refresh **Market Depth Analyzer** (domain snapshots)
2. Index website + **Run Fit Analysis** in Build Readiness
3. Run **Discover** + **Fit Profile Sync**

**Check readiness:** `GET /pipeline/status`

---

## Discovery Sources

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

**Trigger:** `POST /discover`

---

## Lead Scoring

### Default Weights

| Component | Weight | Role |
|-----------|--------|------|
| `market_demand_fit` | 0.22 | Market heat + opportunity score (orientation-aware) |
| `capability_fit` | 0.20 | Our depth vs gap (high for demand, inverted for future) |
| `keyword_fit` | 0.14 | Synced keywords from GO + future domains |
| `budget_indicator` | 0.14 | Signal value (funding, contract size) |
| `recency` | 0.12 | Signal freshness |
| `urgency` | 0.10 | Deadline proximity (government) |
| `contact_confidence` | 0.08 | Email verification |

### Orientation Classification

```
demand:  verdict GO, or CONDITIONAL + capability ≥ 35
future:  market_score ≥ 40 and (NO_GO or capability < 35 or no verdict)
generic: weak domain match or low market signal
```

### Component Formulas

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

---

## Fit Profile Sync

Rebuilds discovery keywords from:
- GO domains from Build Readiness verdicts
- Future opportunity domains (hot market + capability gap)
- Top company capabilities by depth score

Re-scores all existing leads after sync.

**Trigger:** `POST /fit-profile/sync`

---

## Contact Enrichment

Lookup priority: **Apollo** → **Hunter** → **Clearbit** (up to 3 contacts each).

Fallback: `info@{domain}` (unverified, lower `contact_confidence`).

---

## Pipeline Stages

```
new → qualified → contacted → replied → won / lost
```

- Outreach drafts are LLM-generated for **human review only** — no auto-send
- `POST /leads/{entity_id}/mark-sent` tracks outreach status
- Suppression list prevents re-contacting blocked entities

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Service health |
| GET | `/pipeline/status` | Readiness + demand/future domain counts |
| POST | `/discover` | Run lead discovery job |
| GET | `/jobs/{job_id}` | Discovery job status |
| GET | `/leads` | List leads (`?orientation=demand\|future\|generic`) |
| GET | `/leads/government` | Government tenders only |
| GET | `/leads/{entity_id}` | Lead detail + contacts |
| POST | `/leads/{entity_id}/mark-sent` | Mark outreach sent |
| GET | `/fit-profile` | Current synced keywords and domain map |
| POST | `/fit-profile/sync` | Rebuild keywords; re-score all leads |
| POST | `/leads/cleanup` | Remove stale/low-quality leads |
| POST | `/suppressions` | Add email/domain to suppression list |
| GET | `/export/csv` | Export leads to CSV |

---

## Configuration & API Keys

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Recommended | Outreach draft generation |
| `LEAD_INTELLIGENCE_OPENAI_API_KEY` | Optional override | Outreach only |
| `APOLLO_API_KEY` | Recommended | Contact enrichment (primary) |
| `HUNTER_API_KEY` | Recommended | Contact enrichment (fallback) |
| `SAM_GOV_API_KEY` | Recommended | US government tender discovery |

Without enrichment keys, leads still discover and score; contacts fall back to `info@domain` (unverified).

---

## Integration With Other Tool Hub Modules

```
┌────────────────────┐     ┌────────────────────┐
│ Market Depth       │     │ Build Readiness    │
│ (market_score,     │     │ (verdicts,         │
│  product_landscape)│     │  capabilities)     │
└─────────┬──────────┘     └─────────┬──────────┘
          │                          │
          └──────────┬───────────────┘
                     ▼
          ┌────────────────────┐
          │ Lead Intelligence    │
          │                      │
          │ demand + future      │
          │ domain-matched leads │
          └────────────────────┘
                     ▲
                     │
          ┌────────────────────┐
          │ Video Scraper      │
          │ (indirect — via    │
          │  Build Readiness)  │
          └────────────────────┘
```

**Capability → Domain mapping** (used in orientation):

| Capability Category | Market Depth Domain |
|--------------------|---------------------|
| `stablecoins_payments` | Stablecoin & Payments Engineering |
| `rwa_tokenization` | RWA / Tokenization Engineering |
| `blockchain_core` | Smart Contract Engineering |
| `blockchain_security` | Blockchain Security / Auditing |
| `ai_ml` | AI Agent Orchestration |
| `ai_governance` | AI Security / Red-teaming |
| `infrastructure` | L2 / Infra Engineering |
| `gaming_metaverse` | Web3 Growth/Tokenomics |

---

## Business Value

| Outcome | How |
|---------|-----|
| **Higher win rate** | Demand-oriented queue = hot market + proven depth |
| **Strategic investment** | Future-oriented leads guide hiring and productization |
| **Less wasted BD time** | Composite scoring filters junk roundups and weak fits |
| **Brand-safe GTM** | Human-reviewed outreach only; no auto-spam |
| **Government opportunity capture** | Tender deadlines scored by urgency component |
| **CRM-ready export** | CSV export for Salesforce, HubSpot, etc. |

---

## Operational Best Practices

| Practice | Why |
|----------|-----|
| Weekly discover + sync | Pipeline stays aligned to current verdicts |
| Review demand-oriented queue first | These are winnable pursuits now |
| Monthly review future-oriented | Guide capability build investments |
| Configure enrichment keys | Verified contacts dramatically improve outreach success |
| Use suppressions | Prevent re-contacting lost or blocked entities |

**Recommended cadence (Monday):**
1. Refresh Market Depth
2. Run Fit Analysis in Build Readiness
3. Discover leads + Fit Profile Sync
4. Sales reviews demand-oriented queue

---

## Known Limitations

| Area | Limitation |
|------|------------|
| **Government portals** | Scraping is brittle; some sources return empty without API keys |
| **Contact enrichment** | Quality depends on Apollo/Hunter coverage for target companies |
| **Jobs** | BackgroundTasks in-process — jobs lost on container restart |
| **Orientation accuracy** | Requires fresh Market Depth + Build Readiness data |
| **Outreach** | Drafts only — no send integration; human review required |

---

## Quick Reference — Key Formulas

```
# Composite lead score
lead_score = (Σ component[k] × weight[k]) / Σ(weight[k]) × 100

# Orientation
demand:  GO verdict, or CONDITIONAL + capability ≥ 35
future:  market ≥ 40 AND (NO_GO or capability < 35)
generic: else

# Recency
≤7d → 1.0 | ≤30d → 0.8 | ≤90d → 0.5 | else → 0.2
```

---

## Architecture Notes

- **Backend:** FastAPI (`modules/lead-intelligence/backend/`)
- **Frontend:** React panel loaded by Tool Hub web shell
- **Database tables:** `leads_entities`, `leads_contacts`, `leads_fit_profile`, `leads_suppressions`
- **Key files:** `intelligence_bridge.py`, `scoring/domain_match.py`, `scoring/lead_score.py`, `pipeline.py`, `outreach.py`, `sources/__init__.py`

---

*Standalone product brief — Tool Hub Lead Intelligence Engine v1.0 · July 2026*
