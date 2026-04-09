-- Party financial summary from AEC Party Returns.csv
-- Stores all four aggregate columns per party per year so the API can
-- expose a complete income / expenditure / debt picture.
--
-- Run with:
--   docker exec followthemoney-db-1 psql -U ftm -d followthemoney \
--     -f /docker-entrypoint-initdb.d/migrations/003_party_financials.sql

CREATE TABLE IF NOT EXISTS party_financials (
    id                           SERIAL PRIMARY KEY,
    party_id                     INTEGER NOT NULL REFERENCES parties(id),
    financial_year               TEXT NOT NULL,
    total_receipts               NUMERIC(14, 2),
    total_payments               NUMERIC(14, 2),
    total_debts                  NUMERIC(14, 2),
    total_discretionary_benefits NUMERIC(14, 2),
    source_url                   TEXT,
    UNIQUE (party_id, financial_year)
);

CREATE INDEX IF NOT EXISTS party_financials_party_id_idx ON party_financials (party_id);
CREATE INDEX IF NOT EXISTS party_financials_year_idx     ON party_financials (financial_year);
