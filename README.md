# Follow The Money

A civic transparency aggregator for Australian federal politics. Pulls together publicly available data from multiple government sources and presents it in one place, per politician and per donor.

All data is sourced directly from official government records. Every data point links back to its original source. The site presents facts; users draw conclusions.

**Primary audience:** journalists, researchers, political staffers, and engaged advocates.

---

## Data sources

| Source | What it contains |
|---|---|
| [AEC Transparency Register](https://transparency.aec.gov.au) | Party donations, donor returns, expenditure, public funding — bulk CSV |
| [Parliament House Register of Interests](https://www.aph.gov.au/Senators_and_Members/Members/Register) | Gifts, travel, and financial interests declared by individual MPs/Senators |
| [They Vote For You](https://theyvoteforyou.org.au) | Voting records for every federal MP and Senator, tagged by policy issue |
| [ABR ABN Lookup](https://abr.business.gov.au) | Registered business name, entity type, ANZSIC industry code |
| [ASIC Companies Register](https://connectonline.asic.gov.au) | Company directors and officeholders |

---

## Stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 |
| Backend API | FastAPI (Python 3.12, managed by uv) |
| Frontend | Next.js 15 (TypeScript + Tailwind) |
| Local orchestration | Docker Compose |
| Data pipeline | Python scripts in `backend/scripts/` |

---

## Getting started

**Prerequisites:** Docker Desktop, Node.js 22+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Clone and configure environment
cp .env.example .env
# Edit .env — set TVFY_API_KEY at minimum; see optional keys below

# 2. Start the database and backend
docker compose up -d db backend

# 3. Run data ingestion (see pipeline section below for full sequence)
cd backend
uv run scripts/ingest_aec.py --data-dir /data/aec
uv run scripts/ingest_register.py
uv run scripts/ingest_tvfy.py --since 2004-01-01

# 4. Start the frontend (dev mode)
cd frontend && npm install && npm run dev
```

Services:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/api/docs |
| PostgreSQL | localhost:5432 (user: `ftm`, password: `ftm`, db: `followthemoney`) |

---

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router registration
│   │   ├── database.py          # SQLAlchemy engine and session
│   │   ├── schemas.py           # Pydantic response models
│   │   └── routers/             # API route handlers (politicians, parties, donors, search)
│   ├── scripts/
│   │   ├── ingest_aec.py        # AEC bulk CSV ingestion
│   │   ├── enrich_abr.py        # ABR donor enrichment (ABN, industry codes)
│   │   ├── ingest_register.py   # Register of Interests (House PDF + Senate API)
│   │   ├── ingest_tvfy.py       # They Vote For You voting records
│   │   ├── merge_politicians.py # Merge duplicate politician records
│   │   ├── merge_donors.py      # Merge duplicate donor records (3 passes)
│   │   ├── review_ambiguous.py  # LLM-assisted review of ambiguous donor merges
│   │   └── llm_client.py        # Shared LLM client (Anthropic or Ollama via .env)
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── politician/[id]/     # Politician profile page
│   │   ├── party/[id]/          # Party profile page
│   │   ├── donor/[id]/          # Donor profile page
│   │   ├── brief/[id]/          # Journalist briefing card
│   │   └── lib/api.ts           # Typed API fetch functions
│   └── Dockerfile
├── db/
│   └── init.sql                 # Schema — runs automatically on first `docker compose up`
├── data/
│   ├── aec/                     # Downloaded AEC CSVs (not committed)
│   └── register/
│       ├── pdfs/                # Cached House register PDFs
│       ├── ocr_cache/           # Docling OCR results (JSON sidecars)
│       └── llm_cache/           # LLM extraction results (JSON sidecars)
├── docker-compose.yml
└── .env.example                 # Copy to .env and fill in keys
```

---

## Data pipeline

Run scripts from the `backend/` directory with `uv run scripts/<name>.py`.

### 1. AEC donations

Downloads bulk CSVs from the AEC Transparency Register (~190k rows back to 1998):

```bash
mkdir -p data/aec && cd data/aec
curl -L -o annual_data.zip https://transparency.aec.gov.au/Download/AllAnnualData
curl -L -o election_data.zip https://transparency.aec.gov.au/Download/AllElectionsData
unzip -o annual_data.zip -d annual
unzip -o election_data.zip -d election
cd ../backend
uv run scripts/ingest_aec.py --data-dir /data/aec
```

### 2. ABR enrichment

Enriches donor records with ABN, entity type, and ANZSIC industry codes. Requires a free ABR GUID:

```bash
# Register at https://abr.business.gov.au/Tools/WebServices
# Add ABR_GUID=your-guid to .env
uv run scripts/enrich_abr.py
```

### 3. Register of Interests

Scrapes the House of Representatives PDF register and the Senate JSON API. Image-only PDF pages are processed with docling OCR (results cached). When the rules-based parser gets no items from an OCR page, an LLM fallback is triggered (requires `LLM_API_KEY` in `.env`):

```bash
uv run scripts/ingest_register.py              # both chambers
uv run scripts/ingest_register.py --senate     # Senate only
uv run scripts/ingest_register.py --house      # House only
uv run scripts/ingest_register.py --no-clear   # append mode
```

### 4. Voting records (They Vote For You)

Requires a free TVFY API key — register at https://theyvoteforyou.org.au/help/data.

Fetches all divisions from 2004 onwards month-by-month (the API caps per-request results). Full history takes ~2 hours; use `--since` to limit:

```bash
uv run scripts/ingest_tvfy.py --since 2004-01-01   # full history (~2h)
uv run scripts/ingest_tvfy.py --since 2022-05-21   # 47th Parliament only (~15min)
uv run scripts/ingest_tvfy.py --dry-run            # preview without writing
uv run scripts/ingest_tvfy.py --no-clear           # append / update existing data
```

### 5. Deduplication

The AEC data contains donors in multiple name formats ("Smith, John" / "John Smith" / "John Smith Limited" / "John Smith Ltd"). Run after ingestion:

```bash
# Auto-merge 3,400+ unambiguous duplicates
uv run scripts/merge_donors.py

# Export the ~1,300 ambiguous cases
uv run scripts/merge_donors.py --dry-run --export-ambiguous ambiguous.json
```

For the ambiguous cases there are three review options:

**Option A — LLM only** (auto-approves high-confidence decisions, flags the rest):
```bash
uv run scripts/review_ambiguous.py ambiguous.json
uv run scripts/merge_donors.py --apply-decisions decisions.json
```

**Option B — LLM then interactive** (LLM runs first, then drops into manual review for anything it wasn't confident about):
```bash
uv run scripts/review_ambiguous.py ambiguous.json --interactive
uv run scripts/merge_donors.py --apply-decisions decisions.json
```

**Option C — Manual only** (skip LLM, review everything yourself):
```bash
uv run scripts/review_ambiguous.py ambiguous.json --interactive
# or, after a prior LLM run:
uv run scripts/review_ambiguous.py decisions.json --interactive
uv run scripts/merge_donors.py --apply-decisions decisions.json
```

Interactive review keys: `y` merge · `n` reject · `c` choose canonical · `s` skip · `q` quit and save. Progress is saved after every answer so you can quit and resume safely.

Politician duplicates (e.g. stubs from PDF slugs vs full TVFY names):

```bash
uv run scripts/merge_politicians.py
```

---

## LLM configuration

Two features use an LLM: ambiguous donor review and register gift extraction fallback. Both read from `.env`:

```bash
# Anthropic (default)
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_API_KEY=your-anthropic-key-here
LLM_MODEL=claude-haiku-4-5-20251001

# Ollama (local — no API key required)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3.2
```

Switching providers requires only changing `.env` — no code changes. LLM results are cached to `data/register/llm_cache/` so re-runs don't re-call the API.

---

## What each politician page shows

- **Register of Interests** — declared gifts and travel from the House/Senate register
- **Top donors to their party** — top 10 donors to their party overall (links to full party profile)
- **Direct donations received** — AEC-reported donations made directly to this politician
- **Donations via named party branch** — donations to party branches named after the politician
- **Donations made** — AEC donor records matching this politician's name
- **Voting record** — every parliamentary division they voted in, filterable by parliament (41st–47th), with policy stance indicators (✓ supports / ✗ opposes) where TVFY has annotated the vote

---

## Principles

- **Descriptive, not accusatory.** Every data point links to its original public source.
- **Source data first.** Official government sources only — no third-party intermediaries.
- **No invented connections.** If a link can't be sourced to a public record, it doesn't appear.
- **Export over display.** Every view has a CSV/JSON export. This is a finding tool, not a reference.
- **Flag what's unknown.** Data gaps and unidentified donor entities are surfaced explicitly.

---

## Legal

All data is sourced from public government records. The site presents correlation data only and does not assert causation or allege corrupt intent. Every claim links to a specific public record.
