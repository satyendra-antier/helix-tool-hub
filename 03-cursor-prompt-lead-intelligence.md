# Cursor Build Prompt — Module: Lead Intelligence Engine

Module 03 in the `tool-hub` monorepo — slot 03 in the registry rack. References `00-tool-hub-architecture.md` for the shell pattern this plugs into.

---

## ROLE

You are building **Lead Intelligence Engine** inside `modules/lead-intelligence/`. It continuously discovers, enriches, scores, and organizes leads across three tracks — **Web3, Web2/Enterprise, AI** — plus a fourth, distinct track: **Government & institutional procurement opportunities** (tenders, RFPs, grants), which behaves differently enough (deadlines, budgets, eligibility criteria) that it needs its own pipeline stage, not a bolted-on category.

## THE DESIGN CONSTRAINT THAT MATTERS HERE

Same principle as the Market Depth module: **sourcing must be from licensed/consented APIs, not scraped personal data.** Specifically:
- **Do not scrape LinkedIn.** It violates their ToS, gets IPs/accounts banned, and personal profile data scraped without consent is legally exposed under India's DPDP Act (2023) and GDPR if any EU contacts are involved. Use Apollo.io / Hunter.io / Clearbit APIs instead — they're built for exactly this, are ToS-compliant, and the data is licensed for outreach use.
- **Government sources are public by design** — procurement portals publish tenders specifically so vendors can find them. These are the safest, highest-signal sources and should be weighted accordingly.
- **Every stored contact needs a `consent_basis` field** (e.g. `public-government-listing`, `licensed-api-apollo`, `publicly-listed-company-contact`) — this makes the system auditable if you're ever asked "where did this contact come from."
- **Outreach drafts always end in a review queue, never auto-send.** This is a lead-discovery and organization engine, not a spam bot — Gemini drafts, a human sends.

## THE FOUR TRACKS AND THEIR SOURCES

### 1. Government & Institutional (highest priority — build this first)
| Source | What it gives you | Access |
|---|---|---|
| GeM (Government e-Marketplace, India) | Live tenders/bids across all Indian govt departments | Public portal, structured HTML — build a respectful scraper (rate-limited, robots.txt-respecting) since there's no public API |
| CPPP (Central Public Procurement Portal, India) | Central + state tenders | Same as above |
| SAM.gov (US) | Federal contract opportunities | Official public API, free key |
| grants.gov (US) | Federal grant opportunities | Official public API |
| TED (EU) | EU public procurement notices | Official open data API |
| UN Global Marketplace | UN agency procurement | Public portal |
| World Bank Procurement | Development-bank funded projects | Public API |

### 2. Web3
| Source | Signal | Access |
|---|---|---|
| DeFiLlama "Raises" | Recently funded protocols → budget to hire | Free API |
| Gitcoin Grants | Funded builders/projects | Public API |
| CryptoJobsList / Web3.career | Companies actively hiring → active projects | RSS/public listings |
| Messari / CryptoRank | New project launches, funding rounds | Free tier API |

### 3. Web2 / Enterprise
| Source | Signal | Access |
|---|---|---|
| Crunchbase (via API or their free news RSS) | Funding rounds → budget signal | API key |
| BuiltWith | Tech stack detection → migration/modernization leads | API key |
| Clutch.co | Companies actively seeking dev/agency partners | Public listings |
| Product Hunt API | New launches → early-stage teams needing scale help | Official API |

### 4. AI
| Source | Signal | Access |
|---|---|---|
| Y Combinator company directory | Funded AI startups | Public, structured |
| Product Hunt (AI category filter) | Same as above, product-stage signal | Official API |
| AI-specific job boards (e.g. AI Jobs, Otta AI filter) | Hiring surge = scaling = needs help | Public listings |

**Enrichment layer (applies after any source hit):** Apollo.io API (contact + company firmographics), Hunter.io API (verified email finder), Clearbit (company metadata) — this is where actual named contacts and verified emails come from, not from scraping.

## PIPELINE

```
Source connectors (scheduled, per-source, independently runnable)
  → Raw lead candidate (company/entity + signal + source + timestamp)
  → Deduplication & entity resolution (match on domain/name, merge multi-source hits —
     a company appearing in both "funding" and "hiring" signals should merge into
     one lead record with both signals attached, not two separate leads)
  → Enrichment (Apollo/Hunter/Clearbit — pulls contact, role, verified email, company size)
  → Deterministic Lead Scoring Engine (see below)
  → Track categorization + pipeline stage assignment
  → Gemini-drafted personalized outreach angle (grounded in the actual enrichment data)
  → Lands in the Kanban pipeline for human review
```

## LEAD SCORING ENGINE (`backend/scoring/lead_score.py`)

Deterministic, same philosophy as the Market Depth module — Gemini explains, doesn't decide.

```python
def score_lead(lead: LeadCandidate, fit_profile: FitProfile) -> LeadScore:
    signal_strength = weighted_sum({
        "recency": recency_decay(lead.signal_date),          # fresher signal = higher score
        "budget_indicator": normalize(lead.funding_amount or lead.tender_value),
        "keyword_fit": keyword_match_score(lead.description, fit_profile.keywords),
        # fit_profile.keywords defaults to Satya's actual positioning:
        # ["blockchain security", "smart contract audit", "AI agent architecture",
        #  "multi-agent systems", "fintech compliance", "LLM governance", ...]
        "urgency": deadline_proximity(lead.deadline) if lead.track == "government" else 0.5,
        "contact_confidence": lead.enrichment.email_verified_score,
    }, weights=fit_profile.weights)  # user-adjustable, same slider pattern as Market Depth
    return LeadScore(lead_id=lead.id, score=signal_strength, breakdown=..., computed_at=now())
```

`fit_profile.keywords` is the mechanism that makes this "your" lead engine instead of a generic scraper — it's editable in Settings, and should default to the domains from the Market Depth Analyzer module so the two tools reinforce each other (a domain scoring high in Market Depth should automatically weight higher in lead fit).

## DB SCHEMA (table prefix `leads_`)

```sql
CREATE TABLE leads_entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  track TEXT NOT NULL,               -- web3 | web2 | ai | government
  domain TEXT,                       -- company website, for dedup matching
  description TEXT,
  source TEXT NOT NULL,              -- which connector found it
  signal_type TEXT,                  -- funding | hiring | tender | grant | tech-stack
  signal_value NUMERIC,              -- funding amount / tender value, if known
  signal_date DATE,
  deadline DATE,                     -- for government track
  raw_payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads_contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID REFERENCES leads_entities(id),
  full_name TEXT,
  role_title TEXT,
  email TEXT,
  email_verified BOOLEAN DEFAULT false,
  enrichment_source TEXT,            -- apollo | hunter | clearbit
  consent_basis TEXT NOT NULL,       -- audit trail, required, not nullable
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_id UUID REFERENCES leads_entities(id),
  score NUMERIC NOT NULL,
  breakdown JSONB NOT NULL,
  fit_profile_version TEXT,
  computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads_pipeline (
  entity_id UUID PRIMARY KEY REFERENCES leads_entities(id),
  stage TEXT NOT NULL DEFAULT 'new',  -- new | qualified | contacted | replied | won | lost
  outreach_draft TEXT,
  outreach_sent_at TIMESTAMPTZ,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT now()
);
```

## GEMINI'S ROLE — outreach draft, grounded, human-reviewed

```
You are drafting a first-outreach message. You will receive a JSON object with the
entity's real signal data and the sender's positioning. Rules:

1. Reference the SPECIFIC signal that makes this lead relevant right now
   (e.g. "saw your Series A raise" / "saw the tender for X" / "saw you're hiring
   for smart contract auditors") — never write a generic template.
2. Do not fabricate any detail about the company not present in the input.
3. Keep it under 120 words, one clear ask, no hype language.
4. Output JSON: { "subject": string, "body": string, "cited_signal": string }

The output is a DRAFT for human review — it will never be sent automatically.
```

## FRONTEND (`modules/lead-intelligence/frontend/`)

1. **Kanban pipeline board** — columns `New → Qualified → Contacted → Replied → Won/Lost`, drag to move stage, card shows entity name, track badge (color-coded, reuse the Hub's track colors), score, signal summary.
2. **Track filter tabs** — Web3 / Web2 / AI / Government, plus "All."
3. **Government Opportunities calendar view** (distinct from the Kanban — deadlines matter here) — list/calendar hybrid sorted by submission deadline, with a "days remaining" countdown badge, red when under 5 days.
4. **Lead detail drawer** — full enrichment data, score breakdown (same radar/bar pattern as Market Depth for consistency), contact list with verified-email badges, the Gemini outreach draft with an editable textarea + "Mark as sent" button (never an auto-send button).
5. **Fit Profile settings panel** — the keyword list + scoring weights, editable, versioned so you can see how scoring changed over time.
6. **Export** — CSV, and a Google Sheets / Notion sync button (via their respective APIs) for whoever on the team works outreach outside this tool.

## `manifest.json`

```json
{
  "id": "lead-intelligence",
  "name": "Lead Intelligence Engine",
  "tagline": "Government tenders, funded projects, and hiring signals — organized, scored, never spammed.",
  "icon": "radar",
  "route": "/tools/lead-intelligence",
  "backendBaseUrl": "http://lead-intelligence-api:8003",
  "status": "active",
  "requiredEnv": ["GEMINI_API_KEY", "APOLLO_API_KEY", "HUNTER_API_KEY", "SAM_GOV_API_KEY"],
  "category": "growth",
  "version": "1.0.0"
}
```

## ENV VARS

```
GEMINI_API_KEY=
APOLLO_API_KEY=
HUNTER_API_KEY=
CLEARBIT_API_KEY=
SAM_GOV_API_KEY=
CRUNCHBASE_API_KEY=
DATABASE_URL=
REDIS_URL=
```

## COMPLIANCE CHECKLIST (build these in, don't treat as optional)

- [ ] No LinkedIn scraping anywhere in the codebase.
- [ ] Every `leads_contacts` row has a non-null `consent_basis`.
- [ ] Government-source scrapers respect `robots.txt` and are rate-limited.
- [ ] Outreach drafts require explicit human action to mark as "sent" — no scheduled auto-send exists in the codebase at all, not even as a disabled feature.
- [ ] A suppression list exists — any contact who replies "unsubscribe"/"remove" is flagged and permanently excluded from future outreach draft generation.

## ACCEPTANCE CRITERIA

- [ ] Government track pulls at least 10 real live opportunities from GeM/CPPP or SAM.gov on first run.
- [ ] A funding-round hit on DeFiLlama or Crunchbase correctly enriches to a named contact via Apollo/Hunter, with `email_verified` reflecting reality (not assumed true).
- [ ] Two source hits on the same company merge into one `leads_entities` row, not duplicates — verify with a deliberate test case.
- [ ] Lead score changes visibly and correctly when Fit Profile keywords are edited.
- [ ] Gemini outreach draft cites the real signal, and a fabricated-detail test case (feed it an entity with sparse data) results in a draft that stays generic/honest rather than inventing specifics.

Report actual pipeline output — real entities pulled, real scores, one real (unsent) outreach draft — before declaring this module done.