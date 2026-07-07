# Tool Hub — Data Room Checklist

**Document type:** Due diligence preparation  
**Audience:** Investors, legal counsel, technical diligence teams  
**Status:** Pre-seed / seed stage

---

## How to Use This Document

Before or during term sheet negotiations, investors request a **data room** — a secure folder of company documents. Use this checklist to prepare. Items marked ✅ exist today; items marked 📝 need creation; items marked ⏳ post-close.

---

## 1. Corporate & Legal

| Document | Status | Location / Notes |
|----------|--------|----------------|
| Certificate of incorporation | 📝 | Delaware C-Corp recommended |
| Cap table (current + pro forma) | 📝 | Include option pool (10–15%) |
| Bylaws / operating agreement | 📝 | |
| Board resolutions | 📝 | |
| Founder IP assignment agreements | 📝 | All code + docs assigned to company |
| Contractor / advisor agreements | 📝 | With IP clauses |
| Pending litigation (none) | ✅ | Statement of no litigation |
| Material contracts | 📝 | API vendor terms, cloud agreements |

---

## 2. Financial

| Document | Status | Location / Notes |
|----------|--------|----------------|
| Historical financials | 📝 | Minimal pre-revenue — burn tracker |
| 3-year financial projections | ✅ | `07_FINANCIAL_PROJECTIONS.md` |
| Use of funds | ✅ | `08_USE_OF_FUNDS.md` |
| Unit economics model | ✅ | `05_BUSINESS_MODEL.md` |
| Bank statements | 📝 | Last 3 months |
| Tax returns (if any) | 📝 | |
| API / infrastructure cost breakdown | ✅ | `05_BUSINESS_MODEL.md` COGS section |

---

## 3. Product & Technology

| Document | Status | Location / Notes |
|----------|--------|----------------|
| Product documentation | ✅ | `../PRODUCT_DOCUMENTATION.md` |
| Architecture diagram | ✅ | In PRODUCT_DOCUMENTATION.md §2 |
| Live demo access | ✅ | Dashboard `:3200`, API ports 8101–8104 |
| Source code repository | ✅ | `tool-hub/` monorepo |
| Tech stack summary | ✅ | Next.js, FastAPI, Postgres, Redis, Docker |
| Security overview | 📝 | Auth, encryption, tenant isolation roadmap |
| Dependency / license audit | 📝 | `npm audit`, `pip` licenses |
| Uptime / incident history | 📝 | POC stage — document known issues |
| Roadmap (12 months) | ✅ | `08_USE_OF_FUNDS.md` engineering milestones |
| Known limitations | ✅ | PRODUCT_DOCUMENTATION.md §9 |

---

## 4. Commercial & GTM

| Document | Status | Location / Notes |
|----------|--------|----------------|
| Executive summary | ✅ | `01_EXECUTIVE_SUMMARY.md` |
| Investor memo | ✅ | `03_INVESTOR_MEMO.md` |
| Pitch deck | ✅ | `02_PITCH_DECK.md` |
| Market opportunity | ✅ | `04_MARKET_OPPORTUNITY.md` |
| Business model & pricing | ✅ | `05_BUSINESS_MODEL.md` |
| Go-to-market plan | ✅ | `06_GO_TO_MARKET.md` |
| Competitive landscape | ✅ | `09_COMPETITIVE_LANDSCAPE.md` |
| Customer list / pipeline | 📝 | Design partners, discovery call log |
| Case studies | 📝 | Target: 2 by month 6 |
| LOIs / pilot agreements | 📝 | Template + signed pilots |
| Pricing page / packaging | 📝 | From `05_BUSINESS_MODEL.md` tiers |

---

## 5. Team & HR

| Document | Status | Location / Notes |
|----------|--------|----------------|
| Founder bios / LinkedIn | 📝 | 1-page per founder |
| Org chart (current + planned) | ✅ | `07_FINANCIAL_PROJECTIONS.md` headcount |
| Key hire plan | ✅ | `08_USE_OF_FUNDS.md` |
| Employment agreements | 📝 | |
| Option grant plan | ⏳ | Post-incorporation |
| Advisor agreements | 📝 | |
| Background checks | ⏳ | Post-close if required |

---

## 6. IP & Compliance

| Document | Status | Location / Notes |
|----------|--------|----------------|
| IP ownership statement | 📝 | All code owned by company |
| Open-source usage policy | 📝 | List major OSS dependencies |
| Patent applications | N/A | None planned at seed |
| Trademark (Tool Hub) | 📝 | USPTO filing recommended |
| Privacy policy (draft) | 📝 | Required before SaaS launch |
| Terms of service (draft) | 📝 | |
| GDPR / data processing | 📝 | Customer website crawl disclosure |
| SOC 2 roadmap | 📝 | Target: Type I by month 18 |

---

## 7. Investor Materials (This Folder)

| # | Document | File |
|---|----------|------|
| — | Index | `README.md` |
| 01 | Executive Summary | `01_EXECUTIVE_SUMMARY.md` |
| 02 | Pitch Deck | `02_PITCH_DECK.md` |
| 03 | Investor Memo | `03_INVESTOR_MEMO.md` |
| 04 | Market Opportunity | `04_MARKET_OPPORTUNITY.md` |
| 05 | Business Model | `05_BUSINESS_MODEL.md` |
| 06 | Go-to-Market | `06_GO_TO_MARKET.md` |
| 07 | Financial Projections | `07_FINANCIAL_PROJECTIONS.md` |
| 08 | Use of Funds | `08_USE_OF_FUNDS.md` |
| 09 | Competitive Landscape | `09_COMPETITIVE_LANDSCAPE.md` |
| 10 | Data Room Checklist | `10_DATA_ROOM_CHECKLIST.md` |

---

## 8. Data Room Platform Setup

| Step | Action |
|------|--------|
| 1 | Choose platform: DocSend, Google Drive (restricted), Notion, or Pulley |
| 2 | Create folder structure matching sections 1–6 above |
| 3 | Upload ✅ documents from this package |
| 4 | Mark 📝 items with owner + due date |
| 5 | Share view-only link after first partner meeting |
| 6 | Track investor access / engagement (DocSend analytics) |

### Recommended folder structure

```
Tool Hub Data Room/
├── 01_Corporate/
├── 02_Financial/
├── 03_Product/
├── 04_Commercial/
├── 05_Team/
├── 06_IP_Compliance/
└── 07_Pitch_Package/    ← copy of /pitch folder
```

---

## 9. Diligence Q&A Prep

Common investor questions and where to find answers:

| Question | Answer location |
|----------|-----------------|
| What is the TAM/SAM/SOM? | `04_MARKET_OPPORTUNITY.md` |
| How do you make money? | `05_BUSINESS_MODEL.md` |
| What's the moat? | `09_COMPETITIVE_LANDSCAPE.md` §4–5 |
| What does the raise achieve? | `08_USE_OF_FUNDS.md` |
| What are unit economics? | `05_BUSINESS_MODEL.md` §4 |
| What's the 3-year plan? | `07_FINANCIAL_PROJECTIONS.md` |
| How does the product work? | `../PRODUCT_DOCUMENTATION.md` |
| What are the risks? | `03_INVESTOR_MEMO.md` risks section |
| Who are competitors? | `09_COMPETITIVE_LANDSCAPE.md` |
| What's traction? | `01_EXECUTIVE_SUMMARY.md` traction table |

---

## 10. Pre-Close Action Items

| Priority | Action | Owner | Due |
|----------|--------|-------|-----|
| P0 | Incorporate (Delaware C-Corp) | Founder | Before close |
| P0 | Cap table + option pool | Founder + counsel | Before close |
| P0 | IP assignment (founders → company) | Founder | Before close |
| P1 | Founder bios (1 page each) | Founder | First meeting |
| P1 | Demo video (5 min) | Product | Month 1 |
| P1 | Design partner LOI template | GTM | Month 1 |
| P2 | Privacy policy + ToS drafts | Counsel | Before SaaS launch |
| P2 | Trademark filing | Counsel | Month 3 |
| P2 | SOC 2 scoping call | CTO | Month 6 |

---

*Update this checklist as documents are completed. Mark items ✅ when ready for investor sharing.*
