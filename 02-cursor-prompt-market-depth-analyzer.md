# Cursor Build Prompt — Module: Market Depth Analyzer

Paste this into Cursor as a task inside the same `tool-hub` monorepo, after (or alongside) the video-scraper module. References `00-tool-hub-architecture.md` for the shell/registry pattern.

---

## ROLE

You are building a module called **Market Depth Analyzer** inside `modules/market-depth-analyzer/`. Its job: tell a technical CEO which engineering domain — across Blockchain and AI sub-fields — currently has the strongest revenue/demand signal, **backed by real quantitative data, not LLM opinion.**

## THE NON-NEGOTIABLE DESIGN CONSTRAINT

This is the part that matters most: **Gemini is never the source of the score. Gemini only narrates a score that a deterministic scoring engine already computed from real data.** If you build this any other way — asking Gemini "which field has more revenue potential" and rendering its answer — you have built a toy, not a tool. The architecture below exists specifically to prevent that.

```
Real data sources (pulled on a schedule)
        │
        ▼
Deterministic Scoring Engine (Python, pure functions, unit-tested)
        │  → produces numeric scores + the raw evidence behind each
        ▼
Gemini (narrative layer ONLY)
        │  → receives the computed scores + evidence as structured input
        │  → required to cite which input metric supports each claim
        │  → forbidden from introducing any figure not present in the input
        ▼
Dashboard (charts of the real numbers + Gemini's cited narrative)
```

## DOMAINS TO SCORE (seed list — must be config-driven, not hardcoded, so more can be added later)

**Blockchain track:** Smart Contract Engineering, DeFi Protocol Engineering, Blockchain Security / Auditing, L2 / Infra Engineering, Web3 Growth/Tokenomics.
**AI track:** LLM Application Engineering, AI Agent Orchestration, LLMOps / Inference Infra, AI Security / Red-teaming, Applied ML / Data Engineering.

## DATA SOURCES (all have free or low-cost API access — use real ones, don't fabricate)

| Signal | Source | What it measures |
|---|---|---|
| Developer momentum | GitHub REST/GraphQL API | Star/fork growth rate, commit velocity, new-repo count per topic tag over trailing 90 days |
| Hiring demand | Adzuna API / RemoteOK API / We Work Remotely RSS | Job posting volume + trend, filtered by domain keyword sets |
| Capital flow (blockchain) | DefiLlama API (free, no key) | TVL by chain/protocol category, trend over time |
| Capital flow (crypto market) | CoinGecko API (free tier) | Market cap trend by sector tag |
| VC funding signal | Crunchbase News RSS / TechCrunch RSS (free) | Funding round mentions per domain keyword, count + recency |
| Public interest | Google Trends (via `pytrends`) | Search interest trend per domain keyword set, 12-month |
| Compensation | User-supplied CSV import (levels.fyi/Glassdoor have no public API — do not scrape these; give the user an import screen instead) | Salary/rate benchmarks by role |

Each source module lives in `backend/sources/{source_name}.py`, implements a common interface (`fetch(domain_keywords: list[str]) -> RawSignal`), and is independently swappable/mockable in tests.

## SCORING ENGINE (`backend/scoring/engine.py`)

Deterministic, documented, and **adjustable by the user in the UI** (this matters — a CEO needs to see and change the weights, not trust a black box):

```python
# Pseudocode structure Cursor should implement for real, with real math
def compute_domain_score(domain: str, signals: dict[str, RawSignal], weights: dict[str, float]) -> DomainScore:
    normalized = {name: normalize_0_to_100(signal) for name, signal in signals.items()}
    composite = sum(normalized[name] * weights[name] for name in normalized) / sum(weights.values())
    return DomainScore(
        domain=domain,
        composite_score=composite,
        components=normalized,        # keep every component score, don't collapse to just the total
        raw_evidence=signals,         # keep the actual numbers, not just the normalized score
        computed_at=now(),
    )
```

Default weights (surfaced as sliders in the UI, persisted per-user):
`hiring_demand: 0.30, capital_flow: 0.25, developer_momentum: 0.20, funding_signal: 0.15, public_interest: 0.10`

Normalization method: min-max against the trailing 12-month range across all tracked domains (documented in-code — this is a judgment call and should be visible, not hidden).

## GEMINI'S ROLE — grounded narrative only

### System prompt for the Gemini call

```
You are a market analyst. You will be given a JSON object containing computed
domain scores and their underlying raw evidence. You must:

1. Write a 2-3 sentence executive summary ranking the top domains.
2. For each of the top 3 domains, write one paragraph explaining WHY, and every
   claim must cite the specific metric and number it comes from
   (e.g. "hiring demand rose 34% over the trailing quarter per job-posting data").
3. You are FORBIDDEN from stating any number that is not present in the input JSON.
4. You are FORBIDDEN from making a ranking claim not supported by the composite_score
   ordering already computed. Your job is to explain the ranking, not produce it.
5. If the evidence for a domain is thin (fewer than 3 signal sources available),
   say so explicitly rather than filling the gap with confidence.

Output valid JSON matching this schema:
{
  "executive_summary": string,
  "domain_narratives": [{ "domain": string, "narrative": string, "cited_metrics": string[] }],
  "confidence_flags": [{ "domain": string, "reason": string }]
}
```

Backend must **validate** Gemini's output against the input data after the call: parse `cited_metrics`, confirm each cited number actually exists in `raw_evidence`. If Gemini invents a number, reject the response and retry once with an explicit correction note. This validation step is not optional — it's the actual mechanism that makes this "not just AI agreeing."

## DB SCHEMA (table prefix `market_depth_`)

```sql
CREATE TABLE market_depth_domains (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  track TEXT NOT NULL,          -- 'blockchain' | 'ai'
  keywords TEXT[] NOT NULL,
  active BOOLEAN DEFAULT true
);

CREATE TABLE market_depth_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id UUID REFERENCES market_depth_domains(id),
  raw_evidence JSONB NOT NULL,
  component_scores JSONB NOT NULL,
  composite_score NUMERIC NOT NULL,
  weights_used JSONB NOT NULL,
  fetched_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE market_depth_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  snapshot_batch_id UUID NOT NULL,
  gemini_output JSONB NOT NULL,
  validation_passed BOOLEAN NOT NULL,
  validation_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

## BACKEND ENDPOINTS

- `POST /refresh` — triggers a full data pull across all active domains + recompute + Gemini narrative. Long-running, return a job id, same async pattern as the video-scraper module.
- `GET /snapshots/latest` — latest composite scores for all domains, for the chart.
- `GET /domains` / `POST /domains` — manage the tracked domain list + keyword sets.
- `PATCH /weights` — update scoring weights, triggers recompute (not a fresh data pull, just re-score from the latest raw evidence).
- `GET /reports/latest` — the validated Gemini narrative for the latest snapshot batch.
- `POST /compensation/import` — CSV upload endpoint for the manual comp-data source.

## FRONTEND (`modules/market-depth-analyzer/frontend/`)

1. **Ranked bar chart** (recharts) — all domains by composite score, colored by track (blockchain vs AI), sortable.
2. **Weight sliders panel** — the 5 weight dials, live-updates the chart on change (calls `PATCH /weights`).
3. **Domain detail drawer** — click a bar → shows component score breakdown (radar or stacked bar) + raw evidence numbers + the Gemini narrative paragraph for that domain, with cited metrics visually underlined/linked back to the evidence they reference.
4. **Executive summary card** — pinned at top, the 2-3 sentence Gemini summary, with a "validated ✓" or "flagged ⚠" badge based on the backend's citation-check result.
5. **Confidence flags banner** — if any domain has thin data, show it plainly, don't bury it.
6. **"Refresh data" button** with last-updated timestamp — this should never auto-refresh silently; the CEO should always know how fresh the numbers are.

## `manifest.json`

```json
{
  "id": "market-depth-analyzer",
  "name": "Market Depth Analyzer",
  "tagline": "Real signal, not AI opinion — where the revenue actually is.",
  "icon": "trending-up",
  "route": "/tools/market-depth-analyzer",
  "backendBaseUrl": "http://market-depth-api:8002",
  "status": "active",
  "requiredEnv": ["GEMINI_API_KEY", "GITHUB_TOKEN", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"],
  "category": "intelligence",
  "version": "1.0.0"
}
```

## ENV VARS

```
GEMINI_API_KEY=
GITHUB_TOKEN=
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
DATABASE_URL=
REDIS_URL=
```

## ACCEPTANCE CRITERIA

- [ ] Running `/refresh` pulls real numbers from at least GitHub + one job API + DefiLlama/CoinGecko — no mocked/hardcoded data in the default run.
- [ ] Changing a weight slider re-ranks domains instantly without a new data pull.
- [ ] Gemini's narrative output is validated against raw evidence, and the validation pass/fail is visible in the UI — build a test case where you deliberately feed Gemini a fabricated number and confirm the validator catches it.
- [ ] A domain with sparse data is visibly flagged, not silently ranked with false confidence.
- [ ] Full pipeline runs end-to-end and you report actual composite scores for all 10 seed domains before declaring done.

This module is intelligence infrastructure a CEO will make funding decisions from — treat every shortcut (mocked data, unvalidated LLM output, hidden weights) as a bug, not a v1 simplification.
