"""
ABR enrichment script — queries the Australian Business Register API to add
industry classification and entity type to donor records.

Requirements:
  - A free ABR GUID from https://api.abr.business.gov.au/documentation/content/page/index.html
  - Set the ABR_GUID environment variable

Usage:
    ABR_GUID=your-guid-here uv run scripts/enrich_abr.py

Options:
    --limit N        Only process N donors (useful for testing)
    --min-total N    Only enrich donors with total donations >= N (default: 5000)
    --dry-run        Print matches without writing to DB

Rate limiting: the ABR API is free but requests are throttled to ~1/second.
This script pauses 1.1s between requests. A full run over all donors will
take several hours — use --min-total to focus on high-value donors first.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

ABR_GUID = os.environ.get("ABR_GUID", "")
ABR_NAME_SEARCH_URL = "https://abr.business.gov.au/json/MatchingNames.aspx"
ABR_ABN_LOOKUP_URL = "https://abr.business.gov.au/json/AbnDetails.aspx"

ANZSIC_LABELS_PATH = Path(__file__).parent.parent / "data" / "anzsic_labels.json"


def load_anzsic_labels() -> dict[str, str]:
    with open(ANZSIC_LABELS_PATH) as f:
        return json.load(f)


def abr_name_search(name: str, guid: str) -> list[dict]:
    """Search ABR by entity name. Returns list of matches."""
    params = urllib.parse.urlencode({"name": name, "guid": guid})
    url = f"{ABR_NAME_SEARCH_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        # ABR returns JSONP-ish: "callback({...})" — strip wrapper
        raw = raw.strip()
        if raw.startswith("callback(") and raw.endswith(")"):
            raw = raw[9:-1]
        data = json.loads(raw)
        return data.get("Names", [])
    except Exception as e:
        print(f"  ABR name search error for '{name}': {e}", file=sys.stderr)
        return []


def abr_abn_lookup(abn: str, guid: str) -> dict | None:
    """Look up full ABR record by ABN."""
    params = urllib.parse.urlencode({"abn": abn, "guid": guid})
    url = f"{ABR_ABN_LOOKUP_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        raw = raw.strip()
        if raw.startswith("callback(") and raw.endswith(")"):
            raw = raw[9:-1]
        return json.loads(raw)
    except Exception as e:
        print(f"  ABR ABN lookup error for '{abn}': {e}", file=sys.stderr)
        return None


def pick_best_match(name: str, matches: list[dict]) -> dict | None:
    """
    Pick the best ABR match for a donor name.
    Strategy:
      1. Exact name match (case-insensitive)
      2. Single result
      3. Otherwise return None (flag for manual review)
    """
    if not matches:
        return None
    name_lower = name.lower().strip()
    exact = [m for m in matches if m.get("Name", "").lower().strip() == name_lower]
    if len(exact) == 1:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    return None


def enrich_donor(cur, donor: dict, guid: str, anzsic_labels: dict[str, str], dry_run: bool):
    name = donor["name"]
    donor_id = donor["id"]

    matches = abr_name_search(name, guid)
    best = pick_best_match(name, matches)

    if best is None:
        # No confident match — leave needs_review = true
        print(f"  NO MATCH   {name[:60]}")
        return

    abn = best.get("Abn", "")
    detail = abr_abn_lookup(abn, guid) if abn else None
    time.sleep(0.5)  # extra pause for the detail lookup

    entity_type = best.get("EntityTypeText", "")
    anzsic_code = None
    industry_label = None

    if detail:
        # ABR detail response has IndustryCodes list
        codes = detail.get("IndustryCodes", [])
        if codes:
            anzsic_code = codes[0].get("IndustryCode", "")
            industry_label = anzsic_labels.get(anzsic_code) or codes[0].get("IndustryCodeDescription", "")

    print(f"  MATCH      {name[:50]:<50}  ABN={abn}  type={entity_type}  ANZSIC={anzsic_code} {industry_label or ''}")

    if not dry_run:
        cur.execute(
            """
            UPDATE donors SET
                abn            = %s,
                entity_type    = %s,
                anzsic_code    = %s,
                industry_label = %s,
                needs_review   = false
            WHERE id = %s
            """,
            (abn or None, entity_type or None, anzsic_code or None, industry_label or None, donor_id),
        )


def main():
    parser = argparse.ArgumentParser(description="Enrich donor records via ABR API")
    parser.add_argument("--limit",     type=int, default=0,    help="Max donors to process (0 = all)")
    parser.add_argument("--min-total", type=int, default=5000, help="Min total donations to include donor")
    parser.add_argument("--dry-run",   action="store_true",    help="Print matches without writing to DB")
    args = parser.parse_args()

    if not ABR_GUID:
        print("ERROR: ABR_GUID environment variable not set.", file=sys.stderr)
        print("Register for a free GUID at: https://api.abr.business.gov.au/documentation/content/page/index.html", file=sys.stderr)
        sys.exit(1)

    anzsic_labels = load_anzsic_labels()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Get donors that need enrichment, ordered by total donation value
            query = """
                SELECT d.id, d.name, COALESCE(SUM(don.amount), 0) AS total
                FROM donors d
                LEFT JOIN donations don ON don.donor_id = d.id
                WHERE d.anzsic_code IS NULL
                GROUP BY d.id, d.name
                HAVING COALESCE(SUM(don.amount), 0) >= %s
                ORDER BY total DESC
            """
            if args.limit:
                query += f" LIMIT {args.limit}"
            cur.execute(query, (args.min_total,))
            donors = [{"id": r[0], "name": r[1], "total": r[2]} for r in cur.fetchall()]

        print(f"Enriching {len(donors)} donors (min total: ${args.min_total:,}) ...")
        if args.dry_run:
            print("DRY RUN — no writes\n")

        with conn:
            with conn.cursor() as cur:
                for i, donor in enumerate(donors, 1):
                    print(f"[{i}/{len(donors)}] ${donor['total']:>12,.0f}  ", end="")
                    enrich_donor(cur, donor, ABR_GUID, anzsic_labels, args.dry_run)
                    time.sleep(1.1)  # ABR rate limit

        print("\nEnrichment complete.")
        if args.dry_run:
            print("(dry run — no changes written)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
