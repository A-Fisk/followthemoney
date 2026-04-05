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
# 1. Start the database and backend
docker compose up -d db backend

# 2. Run the AEC data ingestion (downloads ~190k rows back to 1998)
docker exec followthemoney-backend-1 uv run scripts/ingest_aec.py --data-dir /data/aec

# 3. Start the frontend (dev mode, outside Docker)
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
│   │   ├── main.py          # FastAPI app, CORS, router registration
│   │   ├── database.py      # SQLAlchemy engine and session
│   │   └── models.py        # ORM models for all 10 tables
│   ├── scripts/
│   │   └── ingest_aec.py    # AEC bulk CSV ingestion
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/                 # Next.js App Router pages
│   └── Dockerfile
├── db/
│   └── init.sql             # Schema — runs automatically on first `docker compose up`
├── data/
│   └── aec/                 # Downloaded AEC CSVs (not committed)
├── docker-compose.yml
└── plan.md                  # Full project plan and phase breakdown
```

---

## Data pipeline

AEC data lives in `data/aec/` (excluded from git — large files). To refresh it:

```bash
# Re-download bulk CSVs from AEC
mkdir -p data/aec && cd data/aec
curl -L -o annual_data.zip https://transparency.aec.gov.au/Download/AllAnnualData
curl -L -o election_data.zip https://transparency.aec.gov.au/Download/AllElectionsData
unzip -o annual_data.zip -d annual
unzip -o election_data.zip -d election

# Re-run ingestion
docker exec followthemoney-backend-1 uv run scripts/ingest_aec.py --data-dir /data/aec
```

---

## Phases

| Phase | Description | Status |
|---|---|---|
| 0 | Environment setup, schema, AEC data loaded | Done |
| 1 | Data pipeline: donations + ABR/ASIC enrichment | Next |
| 2 | Data pipeline: Register of Interests scraper | Planned |
| 3 | Data pipeline: They Vote For You voting records | Planned |
| 4 | Frontend: party, politician, and donor profile pages | Planned |
| 5 | Cross-reference view: donor industries vs voting records | Planned |
| 6 | Public API + bulk data download | Planned |

See `plan.md` for full detail on each phase.

---

## Principles

- **Descriptive, not accusatory.** Every data point links to its original public source.
- **Source data first.** Official government sources only — no third-party intermediaries.
- **No invented connections.** If a link can't be sourced to a public record, it doesn't appear.
- **Export over display.** Every view has a CSV/JSON export. This is a finding tool, not a reference.
- **Flag what's unknown.** Data gaps and unidentified donor entities are surfaced explicitly.

---

## Legal

All data is sourced from public government records. The site presents correlation data only and does not assert causation or allege corrupt intent. Every claim links to a specific public record. See `plan.md` for full legal considerations.
