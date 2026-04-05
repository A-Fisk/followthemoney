"""
AEC Transparency Register — bulk CSV ingestion script.

Usage (inside Docker):
    uv run scripts/ingest_aec.py --data-dir /data/aec

Usage (local, with DB on localhost):
    DATABASE_URL=postgresql://ftm:ftm@localhost:5432/followthemoney \\
        uv run scripts/ingest_aec.py --data-dir data/aec

Safe to re-run — clears and reloads all rows on each run.

Files loaded
------------
Annual:
  Detailed Receipts.csv              → donations (party/third-party recipients)
  Donations Made.csv                 → donations (donor perspective, with dates)
  Donor Donations Received.csv       → donations (registered donor entities)
  Detailed Discretionary Benefits.csv → expenditure (discretionary_benefits)
  Party Returns.csv                  → expenditure (operational totals)
  Senate Groups and Candidate Donations (annual) — not in bulk; covered by election files

Election:
  Donor Donations Made.csv           → donations (donor → candidate/party)
  Donor Donations Received.csv       → donations (registered donor entities, election)
  Senate Groups and Candidate Donations.csv → donations (candidate recipients)
"""

import argparse
import csv
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

AEC_SOURCE_URL = "https://transparency.aec.gov.au"

# ── Name normalisation ────────────────────────────────────────────────────────

# Known canonical party name aliases — maps messy AEC names → canonical name
PARTY_ALIASES: dict[str, str] = {
    "australian labor party (alp)": "Australian Labor Party",
    "alp": "Australian Labor Party",
    "labor": "Australian Labor Party",
    "liberal party of australia": "Liberal Party of Australia",
    "liberal party": "Liberal Party of Australia",
    "the nationals": "The Nationals",
    "nationals": "The Nationals",
    "national party": "The Nationals",
    "national party of australia": "The Nationals",
    "australian greens": "Australian Greens",
    "the greens": "Australian Greens",
    "greens": "Australian Greens",
    "liberal national party of queensland": "Liberal National Party of Queensland",
    "lnp": "Liberal National Party of Queensland",
    "pauline hanson's one nation": "Pauline Hanson's One Nation",
    "one nation": "Pauline Hanson's One Nation",
    "united australia party": "United Australia Party",
    "uap": "United Australia Party",
    "katter's australian party": "Katter's Australian Party",
    "katter's australian party (kap)": "Katter's Australian Party",
}


def normalise_party_name(name: str) -> str:
    stripped = name.strip()
    key = stripped.lower()
    # Strip state branch suffixes like " (ACT Branch)", " (NSW)"
    key_no_branch = re.sub(r"\s*\(.*?\)\s*$", "", key).strip()
    return PARTY_ALIASES.get(key_no_branch, PARTY_ALIASES.get(key, stripped))


_KEEP_UPPER = {"PTY", "LTD", "ACT", "NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ABN", "ATO"}


def normalise_donor_name(name: str) -> str:
    """
    Normalise donor names so that AEC capitalisation inconsistencies
    (e.g. 'MINERALOGY PTY LTD' vs 'Mineralogy Pty Ltd') resolve to the
    same canonical form.

    Strategy: title-case each word, but preserve known abbreviations in UPPER.
    """
    cleaned = re.sub(r"\s+", " ", name.strip())
    words = []
    for word in cleaned.split():
        upper = word.upper()
        if upper in _KEEP_UPPER:
            words.append(upper)
        else:
            words.append(word.capitalize())
    return " ".join(words)


# ── Amount parsing ────────────────────────────────────────────────────────────

def parse_amount(value: str) -> Decimal | None:
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

_party_cache: dict[str, int] = {}
_donor_cache: dict[str, int] = {}
_politician_cache: dict[str, int] = {}


def upsert_party(cur, name: str) -> int:
    canonical = normalise_party_name(name)
    if canonical in _party_cache:
        return _party_cache[canonical]
    cur.execute(
        "INSERT INTO parties (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (canonical,),
    )
    pid = cur.fetchone()[0]
    _party_cache[canonical] = pid
    return pid


def upsert_donor(cur, name: str) -> int:
    canonical = normalise_donor_name(name)
    if canonical in _donor_cache:
        return _donor_cache[canonical]
    cur.execute(
        "INSERT INTO donors (name, needs_review) VALUES (%s, true) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (canonical,),
    )
    did = cur.fetchone()[0]
    _donor_cache[canonical] = did
    return did


def upsert_politician(cur, name: str) -> int:
    canonical = normalise_donor_name(name)
    if canonical in _politician_cache:
        return _politician_cache[canonical]
    cur.execute(
        "INSERT INTO politicians (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (canonical,),
    )
    pid = cur.fetchone()[0]
    _politician_cache[canonical] = pid
    return pid


def insert_donation(cur, *, donor_id, party_id=None, politician_id=None,
                    amount, financial_year, donation_type, return_type,
                    election_event=None, source_file):
    cur.execute(
        """
        INSERT INTO donations
            (donor_id, recipient_party_id, recipient_politician_id,
             amount, financial_year, donation_type, return_type,
             election_event, source_file, source_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (donor_id, party_id, politician_id,
         amount, financial_year, donation_type, return_type,
         election_event, source_file, AEC_SOURCE_URL),
    )


# ── Annual loaders ────────────────────────────────────────────────────────────

def load_detailed_receipts(cur, data_dir: Path) -> int:
    """
    Columns: Financial Year, Return Type, Recipient Name, Received From, Receipt Type, Value
    """
    path = data_dir / "annual" / "Detailed Receipts.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            recipient = row.get("Recipient Name", "").strip()
            donor_name = row.get("Received From", "").strip()
            if not recipient or not donor_name:
                continue
            party_id = upsert_party(cur, recipient)
            donor_id = upsert_donor(cur, donor_name)
            insert_donation(
                cur,
                donor_id=donor_id,
                party_id=party_id,
                amount=amount,
                financial_year=row.get("Financial Year", "").strip(),
                donation_type=row.get("Receipt Type", "").strip(),
                return_type=row.get("Return Type", "").strip(),
                source_file="annual/Detailed Receipts.csv",
            )
            count += 1
    return count


def load_donations_made(cur, data_dir: Path) -> int:
    """
    Columns: Financial Year, Donor Name, Donation Made To, Date, Value
    """
    path = data_dir / "annual" / "Donations Made.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            donor_name = row.get("Donor Name", "").strip()
            recipient = row.get("Donation Made To", "").strip()
            if not donor_name or not recipient:
                continue
            donor_id = upsert_donor(cur, donor_name)
            party_id = upsert_party(cur, recipient)
            insert_donation(
                cur,
                donor_id=donor_id,
                party_id=party_id,
                amount=amount,
                financial_year=row.get("Financial Year", "").strip(),
                donation_type="donation",
                return_type="Donor Return",
                source_file="annual/Donations Made.csv",
            )
            count += 1
    return count


def load_donor_donations_received_annual(cur, data_dir: Path) -> int:
    """
    Columns: Financial Year, Name, Donation Received From, Date, Value
    'Name' = registered donor entity (recipient); 'Donation Received From' = actual donor.
    """
    path = data_dir / "annual" / "Donor Donations Received.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            donor_name = row.get("Donation Received From", "").strip()
            if not donor_name:
                continue
            donor_id = upsert_donor(cur, donor_name)
            insert_donation(
                cur,
                donor_id=donor_id,
                amount=amount,
                financial_year=row.get("Financial Year", "").strip(),
                donation_type="donation",
                return_type="Donor Return",
                source_file="annual/Donor Donations Received.csv",
            )
            count += 1
    return count


def load_party_returns(cur, data_dir: Path) -> int:
    """
    Columns: Financial Year, Name, Party Group, Total Receipts, Total Payments,
             Total Debts, Total Discretionary Benefits
    Loads Total Payments → expenditure (operational).
    """
    path = data_dir / "annual" / "Party Returns.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("Name", "").strip()
            fy = row.get("Financial Year", "").strip()
            total_payments = parse_amount(row.get("Total Payments", ""))
            if not name or total_payments is None:
                continue
            party_id = upsert_party(cur, name)
            cur.execute(
                "INSERT INTO expenditure (party_id, financial_year, category, amount, source_url) "
                "VALUES (%s, %s, %s, %s, %s)",
                (party_id, fy, "operational", total_payments, AEC_SOURCE_URL),
            )
            count += 1
    return count


def load_discretionary_benefits(cur, data_dir: Path) -> int:
    """
    Columns: Financial Year, Return Type, Name, Received From, Date, Value
    """
    path = data_dir / "annual" / "Detailed Discretionary Benefits.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            name = row.get("Name", "").strip()
            fy = row.get("Financial Year", "").strip()
            if not name:
                continue
            party_id = upsert_party(cur, name)
            cur.execute(
                "INSERT INTO expenditure (party_id, financial_year, category, amount, source_url) "
                "VALUES (%s, %s, %s, %s, %s)",
                (party_id, fy, "discretionary_benefits", amount, AEC_SOURCE_URL),
            )
            count += 1
    return count


# ── Election loaders ──────────────────────────────────────────────────────────

def load_election_donor_donations_made(cur, data_dir: Path) -> int:
    """
    Columns: Event, Donor Code, Donor Name, Donated To, Donated To Date Of Gift, Donated To Gift Value
    'Donated To' = candidate name (politician).
    """
    path = data_dir / "election" / "Donor Donations Made.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Donated To Gift Value", ""))
            if amount is None:
                continue
            donor_name = row.get("Donor Name", "").strip()
            recipient = row.get("Donated To", "").strip()
            event = row.get("Event", "").strip()
            if not donor_name or not recipient:
                continue
            donor_id = upsert_donor(cur, donor_name)
            politician_id = upsert_politician(cur, recipient)
            insert_donation(
                cur,
                donor_id=donor_id,
                politician_id=politician_id,
                amount=amount,
                financial_year=_event_to_financial_year(event),
                donation_type="donation",
                return_type="Donor Return",
                election_event=event,
                source_file="election/Donor Donations Made.csv",
            )
            count += 1
    return count


def load_election_candidate_donations(cur, data_dir: Path) -> int:
    """
    Columns: Event, Return Type (Candidate/Senate Group), Name, Donor Name, Date Of Gift, Gift Value
    'Name' = candidate/senate group (politician or party); 'Donor Name' = donor.
    """
    path = data_dir / "election" / "Senate Groups and Candidate Donations.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Gift Value", ""))
            if amount is None:
                continue
            recipient = row.get("Name", "").strip()
            donor_name = row.get("Donor Name", "").strip()
            event = row.get("Event", "").strip()
            return_type_raw = row.get("Return Type (Candidate/Senate Group)", "").strip()
            if not recipient or not donor_name:
                continue
            donor_id = upsert_donor(cur, donor_name)
            if return_type_raw == "Senate Group":
                party_id = upsert_party(cur, recipient)
                insert_donation(
                    cur, donor_id=donor_id, party_id=party_id,
                    amount=amount,
                    financial_year=_event_to_financial_year(event),
                    donation_type="donation",
                    return_type="Senate Group Return",
                    election_event=event,
                    source_file="election/Senate Groups and Candidate Donations.csv",
                )
            else:
                politician_id = upsert_politician(cur, recipient)
                insert_donation(
                    cur, donor_id=donor_id, politician_id=politician_id,
                    amount=amount,
                    financial_year=_event_to_financial_year(event),
                    donation_type="donation",
                    return_type="Candidate Return",
                    election_event=event,
                    source_file="election/Senate Groups and Candidate Donations.csv",
                )
            count += 1
    return count


def load_election_candidate_expenses(cur, data_dir: Path) -> int:
    """
    Columns: Event, Return Type, Name, Total Electoral Expenditure, ...
    Loads into expenditure table as 'electoral' category.
    """
    path = data_dir / "election" / "Senate Groups and Candidate Expenses.csv"
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            amount = parse_amount(row.get("Total Electoral Expenditure", ""))
            if amount is None or amount == 0:
                continue
            name = row.get("Name", "").strip()
            event = row.get("Event", "").strip()
            return_type_raw = row.get("Return Type (Candidate/Senate Group)", "").strip()
            if not name:
                continue
            fy = _event_to_financial_year(event)
            if return_type_raw == "Senate Group":
                party_id = upsert_party(cur, name)
                cur.execute(
                    "INSERT INTO expenditure (party_id, financial_year, category, amount, source_url) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (party_id, fy, "electoral", amount, AEC_SOURCE_URL),
                )
            else:
                # Individual candidate — no party_id, skip for now
                pass
            count += 1
    return count


# ── Utilities ─────────────────────────────────────────────────────────────────

def _event_to_financial_year(event: str) -> str:
    """
    Best-effort mapping of election event name to financial year.
    e.g. "2025 Federal Election" → "2024-25"
         "2022 Federal Election" → "2021-22"
    """
    m = re.search(r"(\d{4})", event)
    if m:
        year = int(m.group(1))
        return f"{year - 1}-{str(year)[-2:]}"
    return event


# ── Main ──────────────────────────────────────────────────────────────────────

LOADERS = [
    ("annual/Detailed Receipts.csv",              load_detailed_receipts),
    ("annual/Donations Made.csv",                 load_donations_made),
    ("annual/Donor Donations Received.csv",       load_donor_donations_received_annual),
    ("annual/Party Returns.csv",                  load_party_returns),
    ("annual/Detailed Discretionary Benefits.csv",load_discretionary_benefits),
    ("election/Donor Donations Made.csv",         load_election_donor_donations_made),
    ("election/Senate Groups and Candidate Donations.csv", load_election_candidate_donations),
    ("election/Senate Groups and Candidate Expenses.csv",  load_election_candidate_expenses),
]


def main():
    parser = argparse.ArgumentParser(description="Ingest AEC CSV data into PostgreSQL")
    parser.add_argument("--data-dir", default="/data/aec", help="Path to extracted AEC data directory")
    parser.add_argument("--no-clear", action="store_true", help="Skip clearing existing data (append mode)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                if not args.no_clear:
                    print("Clearing existing data ...")
                    cur.execute("TRUNCATE donations, expenditure, donors, politicians RESTART IDENTITY CASCADE")
                    # Re-seed the party abbreviations we cleared
                    cur.execute("""
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
                        ON CONFLICT (name) DO NOTHING
                    """)
                    _party_cache.clear()
                    _donor_cache.clear()
                    _politician_cache.clear()

                total = 0
                for label, loader in LOADERS:
                    path = data_dir / label
                    if not path.exists():
                        print(f"  SKIP (not found): {label}")
                        continue
                    n = loader(cur, data_dir)
                    print(f"  {n:>8,}  {label}")
                    total += n

        print(f"\n{'─' * 50}")
        print(f"  Total rows loaded: {total:,}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
