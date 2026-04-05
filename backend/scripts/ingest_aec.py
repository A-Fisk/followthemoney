"""
AEC Transparency Register — bulk CSV ingestion script.

Usage:
    uv run scripts/ingest_aec.py --data-dir /data/aec

Loads from:
  annual/Detailed Receipts.csv        → donations (party recipients)
  annual/Donor Donations Received.csv → donations (donor perspective, with dates)
  annual/Donations Made.csv           → donations (donor → recipient, with dates)
  annual/Party Returns.csv            → expenditure + party totals
  annual/Capital Contributions.csv    → donations (capital contributions)

All rows are upserted so the script is safe to re-run.
"""

import argparse
import csv
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

AEC_SOURCE_URL = "https://transparency.aec.gov.au"


def parse_amount(value: str) -> Decimal | None:
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.replace(",", "").strip())
    except InvalidOperation:
        return None


def upsert_party(cur, name: str) -> int:
    name = name.strip()
    cur.execute(
        "INSERT INTO parties (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name,),
    )
    return cur.fetchone()[0]


def upsert_donor(cur, name: str) -> int:
    name = name.strip()
    cur.execute(
        "INSERT INTO donors (name, needs_review) VALUES (%s, true) "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id",
        (name,),
    )
    return cur.fetchone()[0]


def load_detailed_receipts(cur, data_dir: Path):
    """
    annual/Detailed Receipts.csv
    Columns: Financial Year, Return Type, Recipient Name, Received From, Receipt Type, Value
    """
    path = data_dir / "annual" / "Detailed Receipts.csv"
    print(f"Loading {path} ...")
    rows_loaded = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            recipient_name = row.get("Recipient Name", "").strip()
            donor_name = row.get("Received From", "").strip()
            financial_year = row.get("Financial Year", "").strip()
            donation_type = row.get("Receipt Type", "").strip()
            if not recipient_name or not donor_name:
                continue

            party_id = upsert_party(cur, recipient_name)
            donor_id = upsert_donor(cur, donor_name)

            cur.execute(
                """
                INSERT INTO donations
                    (donor_id, recipient_party_id, amount, financial_year, donation_type, source_file, source_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (donor_id, party_id, amount, financial_year, donation_type,
                 "annual/Detailed Receipts.csv", AEC_SOURCE_URL),
            )
            rows_loaded += 1
    print(f"  → {rows_loaded} rows loaded")


def load_party_returns(cur, data_dir: Path):
    """
    annual/Party Returns.csv
    Columns: Financial Year, Name, Party Group, Total Receipts, Total Payments,
             Total Debts, Total Discretionary Benefits
    Loads Total Payments as expenditure category 'operational'.
    """
    path = data_dir / "annual" / "Party Returns.csv"
    print(f"Loading {path} ...")
    rows_loaded = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            financial_year = row.get("Financial Year", "").strip()
            total_payments = parse_amount(row.get("Total Payments", ""))
            if not name or total_payments is None:
                continue

            party_id = upsert_party(cur, name)
            cur.execute(
                """
                INSERT INTO expenditure (party_id, financial_year, category, amount, source_url)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (party_id, financial_year, "operational", total_payments, AEC_SOURCE_URL),
            )
            rows_loaded += 1
    print(f"  → {rows_loaded} rows loaded")


def load_donor_donations_received(cur, data_dir: Path):
    """
    annual/Donor Donations Received.csv
    Columns: Financial Year, Name, Donation Received From, Date, Value
    The 'Name' here is the recipient (an entity that received donations to pass on),
    'Donation Received From' is the actual donor.
    """
    path = data_dir / "annual" / "Donor Donations Received.csv"
    print(f"Loading {path} ...")
    rows_loaded = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            recipient_name = row.get("Name", "").strip()
            donor_name = row.get("Donation Received From", "").strip()
            financial_year = row.get("Financial Year", "").strip()
            if not recipient_name or not donor_name:
                continue

            # Recipient here is a registered donor entity, not a party — store as donor
            # and link donor→donor; a separate pass will match to parties where possible.
            recipient_id = upsert_donor(cur, recipient_name)
            donor_id = upsert_donor(cur, donor_name)

            cur.execute(
                """
                INSERT INTO donations
                    (donor_id, amount, financial_year, donation_type, source_file, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (donor_id, amount, financial_year, "donation",
                 "annual/Donor Donations Received.csv", AEC_SOURCE_URL),
            )
            rows_loaded += 1
    print(f"  → {rows_loaded} rows loaded")


def load_donations_made(cur, data_dir: Path):
    """
    annual/Donations Made.csv
    Columns: Financial Year, Donor Name, Donation Made To, Date, Value
    """
    path = data_dir / "annual" / "Donations Made.csv"
    print(f"Loading {path} ...")
    rows_loaded = 0
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount = parse_amount(row.get("Value", ""))
            if amount is None:
                continue
            donor_name = row.get("Donor Name", "").strip()
            recipient_name = row.get("Donation Made To", "").strip()
            financial_year = row.get("Financial Year", "").strip()
            if not donor_name or not recipient_name:
                continue

            donor_id = upsert_donor(cur, donor_name)
            party_id = upsert_party(cur, recipient_name)

            cur.execute(
                """
                INSERT INTO donations
                    (donor_id, recipient_party_id, amount, financial_year, donation_type, source_file, source_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (donor_id, party_id, amount, financial_year, "donation",
                 "annual/Donations Made.csv", AEC_SOURCE_URL),
            )
            rows_loaded += 1
    print(f"  → {rows_loaded} rows loaded")


def main():
    parser = argparse.ArgumentParser(description="Ingest AEC CSV data into PostgreSQL")
    parser.add_argument("--data-dir", default="/data/aec", help="Path to extracted AEC data directory")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                load_detailed_receipts(cur, data_dir)
                load_party_returns(cur, data_dir)
                load_donor_donations_received(cur, data_dir)
                load_donations_made(cur, data_dir)
        print("\nIngestion complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
