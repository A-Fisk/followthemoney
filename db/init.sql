-- ============================================================
-- Follow The Money — Database Schema
-- ============================================================

-- Political entities
CREATE TABLE IF NOT EXISTS parties (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    abbreviation TEXT,
    ideology_tags TEXT[],
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS politicians (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    party_id    INTEGER REFERENCES parties(id),
    chamber     TEXT CHECK (chamber IN ('house', 'senate')),
    electorate  TEXT,
    active      BOOLEAN DEFAULT TRUE,
    UNIQUE (name)
);

-- Donors
CREATE TABLE IF NOT EXISTS donors (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    abn              TEXT,
    entity_type      TEXT,   -- company, trust, individual, association, etc.
    anzsic_code      TEXT,
    industry_label   TEXT,
    controlling_person TEXT,
    notes            TEXT,
    needs_review     BOOLEAN DEFAULT FALSE,
    UNIQUE (name)
);

-- Donations — from AEC annual "Detailed Receipts" and "Donor Donations Received"
CREATE TABLE IF NOT EXISTS donations (
    id                    SERIAL PRIMARY KEY,
    donor_id              INTEGER REFERENCES donors(id),
    recipient_party_id    INTEGER REFERENCES parties(id),
    recipient_politician_id INTEGER REFERENCES politicians(id),
    amount                NUMERIC(14, 2) NOT NULL,
    financial_year        TEXT NOT NULL,   -- e.g. "2023-24"
    donation_type         TEXT,            -- 'donation', 'other_receipt', etc.
    source_file           TEXT,            -- which CSV this came from
    source_url            TEXT             -- link to AEC transparency register
);

CREATE INDEX ON donations (donor_id);
CREATE INDEX ON donations (recipient_party_id);
CREATE INDEX ON donations (financial_year);

-- Expenditure — from AEC "Party Returns" (Total Payments) and detailed files
CREATE TABLE IF NOT EXISTS expenditure (
    id             SERIAL PRIMARY KEY,
    party_id       INTEGER REFERENCES parties(id),
    financial_year TEXT NOT NULL,
    category       TEXT NOT NULL CHECK (category IN ('electoral', 'operational', 'discretionary_benefits', 'other')),
    amount         NUMERIC(14, 2) NOT NULL,
    source_url     TEXT
);

-- Public funding received
CREATE TABLE IF NOT EXISTS public_funding (
    id             SERIAL PRIMARY KEY,
    party_id       INTEGER REFERENCES parties(id),
    financial_year TEXT NOT NULL,
    amount         NUMERIC(14, 2) NOT NULL,
    basis          TEXT,   -- 'per_vote', 'administrative', 'policy_development'
    source_url     TEXT
);

-- Gifts and travel from Register of Interests (Phase 2)
CREATE TABLE IF NOT EXISTS interests (
    id               SERIAL PRIMARY KEY,
    politician_id    INTEGER REFERENCES politicians(id),
    donor_id         INTEGER REFERENCES donors(id),
    description      TEXT,
    value_approx     NUMERIC(14, 2),
    date_received    DATE,
    date_declared    DATE,
    days_late        INTEGER GENERATED ALWAYS AS (
                         CASE WHEN date_received IS NOT NULL AND date_declared IS NOT NULL
                              THEN (date_declared - date_received) - 35
                              ELSE NULL
                         END
                     ) STORED,
    source_url       TEXT
);

-- Voting records (Phase 3)
CREATE TABLE IF NOT EXISTS bills (
    id                   SERIAL PRIMARY KEY,
    title                TEXT NOT NULL,
    issue_tags           TEXT[],
    summary              TEXT,
    theyvoteforyou_id    TEXT,
    UNIQUE (theyvoteforyou_id)
);

CREATE TABLE IF NOT EXISTS votes (
    id             SERIAL PRIMARY KEY,
    politician_id  INTEGER REFERENCES politicians(id),
    bill_id        INTEGER REFERENCES bills(id),
    vote_direction TEXT CHECK (vote_direction IN ('aye', 'no', 'abstain', 'absent')),
    vote_date      DATE,
    UNIQUE (politician_id, bill_id)
);

-- Donor-industry-to-bill relevance (Phase 3 — seeded manually)
CREATE TABLE IF NOT EXISTS bill_industry_relevance (
    bill_id        INTEGER REFERENCES bills(id),
    anzsic_code    TEXT NOT NULL,
    relevance_note TEXT,
    PRIMARY KEY (bill_id, anzsic_code)
);

-- ============================================================
-- Seed data: known party abbreviations
-- (will be expanded by ingestion scripts)
-- ============================================================
INSERT INTO parties (name, abbreviation) VALUES
    ('Australian Labor Party',           'ALP'),
    ('Liberal Party of Australia',       'LIB'),
    ('The Nationals',                    'NAT'),
    ('Australian Greens',                'GRN'),
    ('United Australia Party',           'UAP'),
    ('Pauline Hanson''s One Nation',     'PHON'),
    ('Centre Alliance',                  'CA'),
    ('Katter''s Australian Party',       'KAP'),
    ('Liberal National Party of Queensland', 'LNP')
ON CONFLICT (name) DO NOTHING;
