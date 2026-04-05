-- Phase 1 schema additions
-- Run with: docker exec followthemoney-db-1 psql -U ftm -d followthemoney -f /docker-entrypoint-initdb.d/migrations/001_phase1_schema.sql
-- (or via the apply_migrations.sh helper)

-- Add return_type and election_event to donations so we can filter by source
ALTER TABLE donations
    ADD COLUMN IF NOT EXISTS return_type   TEXT,
    ADD COLUMN IF NOT EXISTS election_event TEXT;   -- NULL for annual, e.g. "2025 Federal Election"

-- Index for common filter patterns
CREATE INDEX IF NOT EXISTS donations_return_type_idx ON donations (return_type);
CREATE INDEX IF NOT EXISTS donations_election_event_idx ON donations (election_event);
