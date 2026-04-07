.PHONY: help up down db-wait ingest-aec enrich-abr ingest-register ingest-tvfy \
        merge-politicians merge-donors review-ambiguous apply-decisions \
        ingest-all frontend dev

BACKEND = cd backend &&
UV     = uv run scripts

# ── Default ────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Follow The Money — data pipeline"
	@echo ""
	@echo "  make up                 Start database + backend (Docker)"
	@echo "  make down               Stop all services"
	@echo ""
	@echo "  make ingest-all         Run the full pipeline in order"
	@echo ""
	@echo "  Individual steps:"
	@echo "  make ingest-aec         AEC bulk donation CSVs"
	@echo "  make enrich-abr         ABR ABN enrichment"
	@echo "  make ingest-register    Register of Interests (House PDF + Senate API)"
	@echo "  make ingest-tvfy        They Vote For You voting records (full history)"
	@echo "  make merge-politicians  Merge duplicate politician records"
	@echo "  make merge-donors       Auto-merge unambiguous donor duplicates"
	@echo "  make review-ambiguous   LLM review of ambiguous donor merges"
	@echo "  make apply-decisions    Apply LLM-reviewed merge decisions"
	@echo ""
	@echo "  make frontend           Install frontend deps + start dev server"
	@echo "  make dev                Start backend + frontend together"
	@echo ""

# ── Docker ─────────────────────────────────────────────────────────────────────

up:
	docker compose up -d db backend

down:
	docker compose down

db-wait:
	@echo "Waiting for database..."
	@until docker compose exec -T db pg_isready -U ftm -q; do sleep 1; done
	@echo "Database ready."

# ── AEC ────────────────────────────────────────────────────────────────────────

data/aec/annual/%.csv:
	mkdir -p data/aec
	curl -L -o data/aec/annual_data.zip https://transparency.aec.gov.au/Download/AllAnnualData
	curl -L -o data/aec/election_data.zip https://transparency.aec.gov.au/Download/AllElectionsData
	unzip -o data/aec/annual_data.zip -d data/aec/annual
	unzip -o data/aec/election_data.zip -d data/aec/election

ingest-aec: data/aec
	$(BACKEND) $(UV)/ingest_aec.py --data-dir ../data/aec

data/aec:
	mkdir -p data/aec
	@echo "Downloading AEC bulk CSVs..."
	curl -L -o data/aec/annual_data.zip https://transparency.aec.gov.au/Download/AllAnnualData
	curl -L -o data/aec/election_data.zip https://transparency.aec.gov.au/Download/AllElectionsData
	unzip -o data/aec/annual_data.zip -d data/aec/annual
	unzip -o data/aec/election_data.zip -d data/aec/election

# ── Enrichment ─────────────────────────────────────────────────────────────────

enrich-abr:
	$(BACKEND) $(UV)/enrich_abr.py

# ── Register of Interests ──────────────────────────────────────────────────────

ingest-register:
	$(BACKEND) $(UV)/ingest_register.py

ingest-register-house:
	$(BACKEND) $(UV)/ingest_register.py --house

ingest-register-senate:
	$(BACKEND) $(UV)/ingest_register.py --senate

# ── They Vote For You ──────────────────────────────────────────────────────────

TVFY_SINCE ?= 2004-01-01

ingest-tvfy:
	$(BACKEND) $(UV)/ingest_tvfy.py --since $(TVFY_SINCE)

# ── Deduplication ──────────────────────────────────────────────────────────────

merge-politicians:
	$(BACKEND) $(UV)/merge_politicians.py

merge-donors:
	$(BACKEND) $(UV)/merge_donors.py

# Export ambiguous cases, run LLM review, apply high-confidence decisions
AMBIGUOUS_FILE  = backend/ambiguous.json
DECISIONS_FILE  = backend/decisions.json

review-ambiguous: merge-donors
	$(BACKEND) $(UV)/merge_donors.py --dry-run --export-ambiguous ambiguous.json
	$(BACKEND) $(UV)/review_ambiguous.py ambiguous.json --output decisions.json

apply-decisions:
	$(BACKEND) $(UV)/merge_donors.py --apply-decisions decisions.json

# ── Full pipeline ──────────────────────────────────────────────────────────────

ingest-all: up db-wait ingest-aec enrich-abr ingest-register ingest-tvfy \
            merge-politicians merge-donors
	@echo ""
	@echo "Pipeline complete."
	@echo "Optional: run 'make review-ambiguous' to resolve ~1,300 ambiguous donor merges with LLM."

# ── Frontend ───────────────────────────────────────────────────────────────────

frontend:
	cd frontend && npm install && npm run dev

dev: up
	cd frontend && npm install && npm run dev
