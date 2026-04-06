-- Fast ILIKE search on name columns used by /api/v1/search
-- Run once against a live DB:
--   psql -U ftm -d followthemoney -f db/migrations/002_trigram_search_indexes.sql

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_donors_name_trgm     ON donors     USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_politicians_name_trgm ON politicians USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_parties_name_trgm     ON parties     USING gin (name gin_trgm_ops);
