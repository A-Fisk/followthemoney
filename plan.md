# AusPol Transparency — Project Plan

## Project Overview

A civic transparency aggregator that pulls together publicly available Australian political data from multiple sources and presents it in one place, per politician and per donor. The goal is not to allege corruption but to make the existing public record easy to read, easy to share, and impossible to ignore.

The core insight: all this data already exists, but it's scattered across incompatible government websites in formats designed for compliance, not public understanding. This project joins it together.

**Primary purpose: lowering the cost of accountability journalism.** When the Guardian broke the Hanson/Rinehart flights story, a reporter had to manually check the Register of Interests, cross-reference the AEC register, and piece together the picture from multiple sources. Steps like those — pure information retrieval from public records — are what this project automates. The journalism still requires humans. The finding shouldn't.

The primary audience is journalists, researchers, political staffers, and engaged advocates — not the general public. Design decisions should reflect this: prioritise search speed, data export, source links, and shareability over consumer-friendly simplification.

---

## Principles

- **Descriptive, not accusatory.** Every data point links back to its original public source. The site presents facts; users draw conclusions.
- **Methodology is transparent.** Every data source, every editorial decision, and every known gap in the data is documented publicly on the site.
- **Source data first.** Pull from official government data sources directly, not from third-party sites that may change or disappear.
- **No invented connections.** If a link between a donor and a politician can't be sourced to a public record, it doesn't appear on the site.
- **Export over display.** Every view has a CSV/JSON export. Journalists can't cite this site — they need to cite the primary source. This site is the finding tool, not the reference.
- **Source links are non-negotiable.** Every data point links directly to the original government record so journalists can verify and cite upstream.
- **Flag what's unknown.** Unidentified donor entities, late declarations, and data gaps are surfaced explicitly — these are often the most interesting leads.

---

## Data Sources

### 1. AEC Transparency Register (Primary donations and expenditure data)
- **URL:** https://transparency.aec.gov.au
- **Format:** Bulk CSV download (available via "Download All Disclosure Data")
- **Contains:** Party-level donations, donor returns, election returns, annual returns back to the 1990s, **and expenditure data** — all in the same bulk download
- **Expenditure categories disclosed:** Electoral expenditure (advertising, campaign materials), total payments (staff, office, operational costs), and discretionary benefits. Third parties such as lobby groups and industry associations must also disclose their electoral expenditure.
- **Key limitation on income side:** Donations below the disclosure threshold (~$16,900 in recent years, now lowered to $5,000 under 2025 reforms) are not itemised. A large portion of party income is reported as "other receipts" with no donor breakdown.
- **Key limitation on expenditure side:** Spending categories are broad and parties have discretion in classification. "Other payments" is a catch-all that can obscure granular spending detail. Line-item expenditure (e.g. specific media buys) is not disclosed.
- **Update cadence:** Annual release on 1 February each year; real-time disclosures now required under the Electoral Legislation Amendment (Electoral Reform) Act 2025

### 2. Parliament House Register of Interests
- **URL:** https://www.aph.gov.au/Senators_and_Members/Members/Register (House) and equivalent Senate register
- **Format:** HTML pages and PDFs, one per MP/Senator — this is the least machine-readable source
- **Contains:** Gifts, sponsored travel, hospitality, shareholdings, and other financial interests declared by individual politicians. Declarations must be made within 35 days of receiving a benefit over $300.
- **Key limitation:** No bulk download. Requires scraping individual pages. Historically inconsistent in formatting. Late or missing declarations (as seen in the Hanson/Rinehart flights case) mean the register is not always complete.
- **Why it matters:** This is where gifts-in-kind (private jet flights, event hospitality, overseas travel) live — things that never appear in the AEC donation data.

### 3. They Vote For You
- **URL:** https://theyvoteforyou.org.au
- **Format:** Public API
- **Contains:** Voting records for every federal MP and Senator, with bills already tagged by policy issue area (e.g. "coal and gas", "climate change", "gambling")
- **Why use this rather than raw Hansard:** They Vote For You has already done the hard editorial work of tagging votes by issue, and their methodology is publicly documented and scrutinised. Citing their data insulates the project from having to defend issue-tagging decisions independently.
- **Attribution:** Always credit They Vote For You as the source of voting data and issue tagging.

### 4. ABR (Australian Business Register) — ABN Lookup API
- **URL:** https://abr.business.gov.au/Tools/AbnLookup
- **Format:** Free API (requires ABN Lookup GUID registration)
- **Contains:** Registered business name, entity type (company, trust, individual, etc.), ANZSIC industry code, state, registration status
- **Use:** Automatically enrich every donor entity with their industry classification and entity type

### 5. ASIC Companies Register
- **URL:** https://connectonline.asic.gov.au
- **Format:** Web search + API (ASIC Connect)
- **Contains:** Company directors and officeholders, registered address, related entities
- **Use:** Surface who controls obscure donor entities — e.g. identify that an unnamed Pty Ltd is directed by a known mining executive

### 6. Attorney-General's Lobbyist Register
- **URL:** https://lobbyists.ag.gov.au
- **Format:** Searchable web interface / CSV
- **Contains:** Registered lobbyists, their clients, and former government representatives working in lobbying
- **Use (v2+):** Add a "lobbyist connections" layer showing when a donor is also a registered lobbying client

---

## Architecture

### Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Best ecosystem for data pipelines, CSV processing, API calls |
| Database | PostgreSQL | Relational structure suits the donor→donation→politician→vote graph; scales to production without migration |
| Backend API | FastAPI | Lightweight, fast, good for serving JSON to the frontend |
| Frontend | Next.js (React) | Server-side rendering for SEO (important for a public interest site); component model suits profile pages |
| Local orchestration | Docker Compose | Runs Postgres + backend + frontend with one command; mirrors eventual production setup |
| Data pipeline | Python scripts (initially) | Scheduled ETL jobs to refresh AEC data, re-run ABR enrichment, pull They Vote For You API |

### Local Development Setup

The entire stack runs on localhost via Docker Compose. No hosting or cloud infrastructure required for v1.

```
localhost:3000  → Next.js frontend
localhost:8000  → FastAPI backend
localhost:5432  → PostgreSQL
```

---

## Data Model (Core Tables)

```sql
-- Political entities
politicians (id, name, party_id, chamber, electorate, active)
parties (id, name, abbreviation, ideology_tags)

-- Donors
donors (id, name, abn, entity_type, anzsic_code, industry_label, 
        controlling_person, notes, needs_review)

-- Donations (from AEC)
donations (id, donor_id, recipient_party_id, recipient_politician_id,
           amount, financial_year, donation_type, source_url)

-- Gifts and travel (from Register of Interests)
interests (id, politician_id, donor_id, description, value_approx,
           date_received, date_declared, days_late, source_url)

-- Votes (from They Vote For You)
votes (id, politician_id, bill_id, vote_direction, date)
bills (id, title, issue_tags, summary, theyvoteforyou_id)

-- Expenditure (from AEC — same bulk download as donations)
expenditure (id, party_id, financial_year, category, amount, source_url)
-- category values: 'electoral', 'operational', 'discretionary_benefits', 'other'

-- Public funding received (from AEC)
public_funding (id, party_id, financial_year, amount, basis, source_url)
-- basis: per-vote election funding, administrative funding, policy development funding

-- Donor-industry-to-bill relevance mapping
bill_industry_relevance (bill_id, anzsic_code, relevance_note)
```

The `bill_industry_relevance` table is the key join that powers the "this politician received donations from fossil fuel companies and voted X times in their favour" view. This is seeded manually for the most important bills and industries initially.

The `expenditure` and `public_funding` tables complete the financial picture for each party — income (donations + public funding) alongside outgoings — enabling the full money-in / money-out view on party profile pages.

---

## Project Phases

### Phase 0 — Environment Setup (Day 1)
- Install Docker Desktop
- Create project repository
- Set up Docker Compose with Postgres, FastAPI, and Next.js containers
- Confirm all three services run and can talk to each other on localhost
- Download AEC bulk CSV data and load into Postgres manually to understand the data shape

**Deliverable:** `docker-compose up` spins up the full stack. AEC data is queryable in Postgres.

---

### Phase 1 — Data Pipeline: Donations (Week 1–2)

**1a. AEC CSV ingestion**
- Parse and normalise the AEC bulk download CSVs
- Handle the multiple file types (annual returns, election returns, donor returns)
- Load into the `donations` and `parties` tables
- **Also load expenditure data** into the `expenditure` table — this is in the same bulk download, no additional source required
- Load public funding figures into the `public_funding` table
- Handle known data quality issues (typos in party names, inconsistent donor naming across years)

**1b. ABR enrichment**
- For each unique donor entity, query the ABR API using their name or ABN
- Store ANZSIC industry code and entity type
- Flag entities with no ABN match as `needs_review = true`
- Map ANZSIC codes to human-readable industry labels (e.g. ANZSIC 0600 → "Coal Mining")

**1c. ASIC director lookup**
- For `needs_review` entities and high-value donors, query ASIC for directors/officeholders
- Store controlling person name(s) against the donor record
- This will be partially manual for obscure entities

**Deliverable:** Database populated with enriched donation data. Can run a query like: "Show me all donations from coal mining entities to any party, 2015–2025."

---

### Phase 2 — Data Pipeline: Register of Interests (Week 2–3)

This is the hardest data problem in the project.

**2a. Scraper for parliamentary register pages**
- Write a scraper for the House of Representatives and Senate register of interests pages
- Parse HTML/PDF to extract: politician name, benefit description, approximate value, date received, date declared
- Calculate days between receipt and declaration (to flag late declarations like the Hanson case)
- Store in the `interests` table with a link to the source page

**2b. Donor matching**
- Attempt to match the entity named in an interests declaration to an existing donor record
- Where a match is uncertain, flag for manual review
- Where no match exists, create a new donor record

**Known limitation to document publicly:** The register relies on politicians self-declaring. Late, vague, or missing declarations cannot be detected programmatically — only compared against media reports.

**Deliverable:** Register of Interests data is in the database and linked to politician profiles. The Hanson/Rinehart flights would appear on Hanson's profile page with a "declared X days late" flag.

---

### Phase 3 — Data Pipeline: Voting Records (Week 3–4)

**3a. They Vote For You API integration**
- Pull voting records for all current MPs and Senators via the They Vote For You API
- Store votes and bills in the `votes` and `bills` tables
- Import their issue tags for each bill

**3b. Bill-to-industry relevance mapping**
- Manually create initial `bill_industry_relevance` entries for the most important bills and industry categories (e.g. Safeguard Mechanism bill → coal/gas industry; gambling advertising bill → gambling industry)
- This is an editorial layer — document the methodology clearly
- Design so community contributors can propose additions

**Deliverable:** Can query: "Show me all votes by politician X on bills tagged as relevant to the mining industry."

---

### Phase 4 — Frontend: Core Pages (Week 4–6)

**4a. Party profile page** (`/party/[slug]`)
- Total donations received over time (chart)
- Breakdown by donor industry (pie/bar chart)
- Top 20 donors listed with enriched entity info
- Link to each donor's profile page
- **Complete financial picture:** Total income (private donations + public funding) vs total expenditure over time — presented as a single chart so the full scale of party finances is visible
- **Public funding breakdown:** How much of the party's income comes from taxpayers vs private donors, per year
- **Expenditure breakdown:** Electoral advertising spend vs operational costs vs other payments — with a note on the "other payments" limitation
- **Where the money goes:** Electoral expenditure by category, surfacing the scale of spending on political advertising

**4b. Politician profile page** (`/politician/[slug]`)
- Party affiliation, electorate, chamber
- Donations received (direct + via party, where attributable)
- Gifts and travel from Register of Interests, with source links and any "declared late" flags
- Voting record summary by issue area (sourced from They Vote For You, attributed)
- Where donor industries overlap with voting record, surface this clearly but factually

**4c. Donor profile page** (`/donor/[slug]`)
- Company name, industry (from ANZSIC via ABR)
- Controlling person / directors (from ASIC)
- Total donations by party over time
- All individual donation records with source links
- "Also appears in Register of Interests" section where relevant

**4d. Search** (`/search`)
- Single search box across politicians, parties, and donors
- Filter by industry, year, amount range
- **Every search result and every page has a prominent CSV/JSON export button** — this is a first-class feature, not an afterthought

**4e. Journalist-facing features (built into every page)**
- **Export button** on every view: downloads the underlying data as CSV or JSON with source URLs included in every row
- **Direct source links** on every individual data point, linking to the original government record
- **"Needs review" public queue** — donor entities the pipeline couldn't identify are listed publicly at `/unresolved`, with the donation amount and recipient visible. This surfaces research leads for journalists and researchers who may be able to identify them.
- **Shareable URLs** for every search and filter state, so a journalist can share an exact view with an editor or colleague

**Deliverable:** The three profile page types are functional and populated with real data. A user can look up "Hancock Prospecting" and see every donation on record, what industry they're in, who controls the company, and which politicians have declared gifts from them — and export all of it to a spreadsheet in one click.

---

### Phase 5 — The Cross-Reference View (Week 6–7)

This is the feature that makes the site genuinely novel.

**5a. Donor-to-vote alignment view**
On a donor profile page, add a section: *"How did recipients vote on relevant legislation?"*
- Takes the donor's industry tag
- Finds all bills tagged as relevant to that industry
- Shows how each recipient politician voted on those bills
- Presented factually: "Received $X from coal mining donors. Voted [for/against] the Safeguard Mechanism bill."

**5b. Politician alignment score (careful framing required)**
- Not a "corruption score" — frame as "voting record alignment with donor industries"
- Documented methodology, caveats prominent
- Shows the data; explicitly does not imply causation

**Deliverable:** The site can answer the question: "Here is everything the public record tells us about how this party has been supported by the mining industry, and here is how its members voted on mining-relevant legislation."

---

### Phase 6 — Public API (Week 7–8)

This is what separates a useful website from an infrastructure asset. FastAPI already generates an API as part of the backend — this phase is about making it stable, documented, and genuinely usable by external developers and journalists with technical skills.

**6a. Stable versioned API endpoints**

All core data exposed as queryable JSON endpoints, for example:

```
GET /api/v1/donors?name=hancock
GET /api/v1/donors/{id}/donations
GET /api/v1/parties/{id}/donations?year=2024
GET /api/v1/parties/{id}/expenditure
GET /api/v1/politicians/{id}/interests
GET /api/v1/politicians/{id}/votes?issue=mining
GET /api/v1/unresolved   ← publicly lists unidentified donor entities
```

**6b. API documentation**
- Auto-generated via FastAPI's built-in OpenAPI/Swagger support — minimal extra work
- Hosted at `/api/docs`
- Includes example queries, field descriptions, and known data limitations for each endpoint

**6c. Rate limiting and attribution requirements**
- Generous rate limits (this is a public interest tool, not a commercial API)
- API responses include a required attribution field: `"source": "AusPol Transparency / AEC Transparency Register"`
- No authentication required for read-only access

**6d. Bulk data download**
- A static nightly export of the full normalised dataset as CSV and JSON, available at `/data/download`
- This is how OpenSecrets became indispensable — their data underlies countless other tools and analyses
- Include a data dictionary explaining every field and its source

**Deliverable:** A documented, stable API that a journalist, researcher, or developer can query without touching the frontend. Bulk data download available. This multiplies the reach of the project without ongoing effort.

---

## Known Gaps to Document Publicly

The site should have a permanent "What we can't show you" page that is honest about:

1. **Donations below the threshold** — a large portion of party income is never itemised by donor
2. **"Other receipts"** — fundraising dinners, forum memberships, and similar structured payments that are declared in aggregate but with no donor detail
3. **Expenditure granularity** — spending categories are broad; which specific media organisations, consultants, or suppliers received party money is not disclosed
4. **Trust structures** — some donor entities are investment trusts where the ultimate source of funds is not publicly identifiable
5. **Undeclared interests** — the Register of Interests only shows what politicians chose to declare; undeclared gifts cannot be detected from public data alone
6. **State-level politics** — v1 covers federal politics only; state registers exist but vary significantly in format and accessibility

---

## V1 Launch Checklist

- [ ] Docker Compose stack running locally
- [ ] AEC data loaded and enriched with ABR industry tags
- [ ] Expenditure and public funding data loaded from same AEC bulk download
- [ ] Party profile pages live with donation data, expenditure breakdown, and public funding figures
- [ ] Donor profile pages live with company info
- [ ] Politician profile pages live
- [ ] Search working
- [ ] CSV/JSON export on every page and search view
- [ ] Source links on every individual data point
- [ ] `/unresolved` page listing unidentified donor entities
- [ ] Public API live at `/api/v1` with Swagger docs at `/api/docs`
- [ ] Nightly bulk data download available at `/data/download`
- [ ] Every data point has a source link
- [ ] "What we can't show you" page published
- [ ] Methodology page published

---

## V2 Features (Post-Launch)

- Register of Interests scraper and integration
- They Vote For You voting record integration
- Donor-to-vote cross-reference view
- Lobbyist register integration
- State-level politics (NSW and Victoria first, as they have the best structured data)
- Community contribution layer for annotating obscure donor entities
- **Email / RSS alerts** — journalists can watch a donor, politician, or party and receive a notification when new data appears involving that entity. This is likely the highest-value feature for working journalists after the core data is live.

---

## Legal Considerations

- All data is sourced from public government records — use is legal
- Every claim on the site must be sourced to a specific public record with a link
- The site presents correlation data only; it does not assert causation or allege corrupt intent
- Framing should be reviewed by a media lawyer before public launch, particularly the cross-reference view
- Defamation risk lives in framing, not facts — "received $X from Y, voted Z" is defensible; implying quid pro quo is not
- The site should carry a clear methodology disclaimer on every profile page


## Addendum: Journalist Briefing Card

> **Context:** This feature was added after the core plan was written, following a clearer articulation of the primary use case. The site's highest-value function is as a real-time research tool for working journalists — enabling them to retrieve political donation context fast enough to use it within a news cycle. The CGT example: a journalist covering a Labor policy announcement should be able to search in 30 seconds and ask in their next press conference call: "You've received $X from property industry donors — how does that bear on your position?" This feature is the interface that makes that workflow possible.

### What it is

A "briefing card" — a single, scannable page per politician optimised for speed of reading rather than depth of research. Designed to be pulled up on a phone during a press conference or skimmed in two minutes before an interview.

### URL structure

```
/brief/[politician-slug]
/brief/[politician-slug]?topic=property
/brief/[politician-slug]?topic=mining
```

The optional `?topic=` parameter filters all sections to show only donors and votes relevant to that industry or policy area — so a journalist covering a specific story gets only what's relevant without noise.

### Page contents (in order)

**1. Identity bar** — name, party, chamber, electorate, current role. One line.

**2. Donor snapshot** — total donations received (direct + via party where attributable) in the last 3 financial years, broken down by industry in plain English. Not a chart — a short readable list:
```
Property & construction:  $142,000
Financial services:        $89,000
Mining & resources:        $45,000
```

**3. Declared interests** — gifts, travel, and hospitality from the Register of Interests, most recent first, with days-late flag where applicable. Maximum five entries shown, link to full list.

**4. Votes on active topics** *(v2 — requires They Vote For You integration)* — if a `?topic=` is specified, show the politician's voting record on the three most recent and relevant bills, sourced and attributed to They Vote For You.

**5. Quick copy** — a pre-formatted, citable one-liner the journalist can paste directly into notes or copy to a colleague:
```
According to AEC records [source link], [Name] or their party
received $X from [industry] donors between [year] and [year].
```

**6. Full profile link** — one prominent link to the full politician profile page for deeper research.

### Design constraints

- **Must load in under 3 seconds** — if it's slower than that it won't be used in a live workflow
- **Must be fully usable on mobile** — journalists pull this up on their phones
- **No charts on this page** — charts take time to read; this page uses plain text and numbers only
- **Shareable URL** — the full URL including any `?topic=` parameter should be shareable so a journalist can send it to an editor or colleague and they see exactly the same view
- **Print/PDF friendly** — some journalists will want to print or screenshot this for notes

### Implementation notes

- This is a new frontend view on existing data — no new data pipeline work required
- The `?topic=` filter maps to the existing ANZSIC industry tags already on donor records
- The "quick copy" one-liner is generated server-side from the same data, not editable by users
- Should be added in Phase 4 alongside the other frontend pages — it uses the same underlying API endpoints, just a different presentation layer
- Mobile layout should be the primary design target, with desktop as
  secondary

