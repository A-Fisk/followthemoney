"""
They Vote For You ingestion — imports voting records for all federal politicians.

Fetches divisions (parliamentary votes) from the They Vote For You public API,
stores them in the bills and votes tables, and auto-populates
bill_industry_relevance based on policy tags.

Requirements:
    TVFY_API_KEY env var. Register free at https://theyvoteforyou.org.au/help/data

Usage:
    uv run scripts/ingest_tvfy.py

Options:
    --since DATE   Import votes on or after this date
                   (default: 2004-01-01, full TVFY history)
    --dry-run      Print stats without writing to DB
    --no-clear     Append to existing data instead of truncating
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)
TVFY_API_KEY = os.environ.get("TVFY_API_KEY", "")
TVFY_BASE = "https://theyvoteforyou.org.au/api/v1"

# TVFY policy name keywords → relevant ANZSIC codes
# A bill's policy tags are checked against these keywords (case-insensitive).
# When matched, the bill is linked to those industries in bill_industry_relevance.
POLICY_ANZSIC: dict[str, list[str]] = {
    "coal":              ["0600"],
    "mining":            ["0500", "0600", "0700", "0800", "0900"],
    "petroleum":         ["0700"],
    " gas":              ["0700"],  # space avoids matching "gas lighting" etc.
    "climate":           ["0600", "0700"],
    "gambling":          ["9201"],
    "banking":           ["6210", "6220", "6230"],
    "financial service": ["6210", "6220", "6230"],
    "insurance":         ["6310", "6321", "6322"],
    "superannuation":    ["6330"],
    "pharmaceutical":    ["1841", "8401"],
    "live animal":       ["0100", "0121"],
    "agriculture":       ["0100", "0121", "0131"],
    "media":             ["5610", "5620"],
    "telecommunication": ["5801", "5802"],
    "housing":           ["6711", "6712"],
    "property":          ["6711", "6712", "6721"],
    "construction":      ["3101", "3102", "3103"],
    "alcohol":           ["1123", "5121"],
    "tobacco":           ["1130"],
}

VALID_VOTE_DIRECTIONS = {"aye", "no", "abstain", "absent"}
CHAMBER_MAP = {"representatives": "house", "senate": "senate"}


# ── API helpers ────────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "FollowTheMoney/0.1 (civic transparency research; +https://github.com/followthemoney)"}


def tvfy_get(path: str, **params) -> dict | list:
    params["key"] = TVFY_API_KEY
    url = f"{TVFY_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for {path}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error fetching {path}: {e}", file=sys.stderr)
        return []


def fetch_divisions(since: date) -> list[dict]:
    """
    Fetch all divisions on or after `since`.

    TVFY's divisions.json endpoint caps results (~100 per request). We iterate
    month-by-month with start_date/end_date parameters to page through the full
    historical record without hitting the cap.
    """
    from calendar import monthrange

    print("Fetching division lists from TVFY...")
    seen_ids: set[int] = set()
    result = []
    today = date.today()

    # Generate (year, month) pairs from since → today
    y, m = since.year, since.month
    windows: list[tuple[str, str]] = []
    while (y, m) <= (today.year, today.month):
        last_day = monthrange(y, m)[1]
        window_end = min(date(y, m, last_day), today)
        windows.append((f"{y}-{m:02d}-01", window_end.strftime("%Y-%m-%d")))
        m += 1
        if m > 12:
            m = 1
            y += 1

    for start_str, end_str in windows:
        for house in ("representatives", "senate"):
            divs = tvfy_get("divisions.json", house=house, start_date=start_str, end_date=end_str)
            if not isinstance(divs, list):
                continue
            new_in_window = 0
            for d in divs:
                div_id = d.get("id")
                if div_id in seen_ids:
                    continue
                try:
                    datetime.strptime(d["date"], "%Y-%m-%d")
                except (KeyError, ValueError):
                    continue
                seen_ids.add(div_id)
                result.append(d)
                new_in_window += 1
            if new_in_window:
                print(f"  {start_str[:7]} {house}: +{new_in_window} (total {len(result)})")

    print(f"  Total: {len(result)} divisions on or after {since}")
    return result


def fetch_division_detail(div_id: int) -> dict:
    time.sleep(0.35)  # ~3 req/s — well within fair-use limits
    detail = tvfy_get(f"divisions/{div_id}.json")
    return detail if isinstance(detail, dict) else {}


def build_policy_map() -> dict[int, list[dict]]:
    """
    Build a reverse map of division_id → [{name, vote}, ...] by fetching all
    policies. TVFY tags live on the policy side, not the division side.

    `vote` is "aye" or "no" — the direction that SUPPORTS the policy position.
    e.g. if vote="aye", a politician who voted aye SUPPORTS the policy.
    """
    policies = tvfy_get("policies.json")
    if not isinstance(policies, list):
        print("  Could not fetch policies list", file=sys.stderr)
        return {}
    print(f"  Fetching {len(policies)} policy details to build tag map...")
    div_to_policies: dict[int, list[dict]] = {}
    for i, policy in enumerate(policies, 1):
        detail = tvfy_get(f"policies/{policy['id']}.json")
        time.sleep(0.35)
        if not isinstance(detail, dict):
            continue
        name = detail.get("name", policy.get("name", ""))
        for pd in detail.get("policy_divisions", []):
            div_id = pd.get("division", {}).get("id")
            if div_id is not None:
                div_to_policies.setdefault(div_id, []).append({
                    "name": name,
                    "vote": pd.get("vote", "aye"),  # direction that supports policy
                })
        if i % 50 == 0:
            print(f"  ... {i}/{len(policies)} policies fetched")
    tagged = sum(1 for v in div_to_policies.values() if v)
    print(f"  Policy map built: {len(div_to_policies)} divisions tagged across {len(policies)} policies")
    return div_to_policies


# ── DB helpers ─────────────────────────────────────────────────────────────────

def upsert_party(cur, name: str) -> int:
    cur.execute("SELECT id FROM parties WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO parties (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
        (name,),
    )
    cur.execute("SELECT id FROM parties WHERE name = %s", (name,))
    return cur.fetchone()[0]


def upsert_politician(cur, member: dict, div_house: str | None = None) -> int | None:
    # TVFY vote member has first_name + last_name, not a single name field
    first = (member.get("first_name") or "").strip()
    last = (member.get("last_name") or "").strip()
    name = f"{first} {last}".strip() if (first or last) else (member.get("name") or "").strip()
    if not name:
        return None
    cur.execute("SELECT id FROM politicians WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    # Create from TVFY data — they have current parliament details
    # Chamber comes from the division (member dict doesn't include house)
    chamber = CHAMBER_MAP.get(div_house or "")
    electorate = member.get("electorate") or None
    party_name = (member.get("party") or "").strip() or None
    party_id = upsert_party(cur, party_name) if party_name else None
    cur.execute(
        """
        INSERT INTO politicians (name, party_id, chamber, electorate, active)
        VALUES (%s, %s, %s, %s, true)
        ON CONFLICT (name) DO NOTHING
        """,
        (name, party_id, chamber, electorate),
    )
    cur.execute("SELECT id FROM politicians WHERE name = %s", (name,))
    row = cur.fetchone()
    return row[0] if row else None


# ── Tagging helpers ────────────────────────────────────────────────────────────

def extract_policy_positions(detail: dict, policy_map: dict[int, list[dict]] | None = None) -> list[dict]:
    """Return [{name, vote}, ...] — 'vote' is the direction that supports the policy."""
    if policy_map is not None:
        div_id = detail.get("id")
        if div_id and div_id in policy_map:
            return policy_map[div_id]
    # Fallback: policy_divisions on the division itself (older/edited divisions)
    policy_divisions = detail.get("policy_divisions") or []
    return [
        {"name": pd["policy"]["name"], "vote": pd.get("vote", "aye")}
        for pd in policy_divisions if pd.get("policy")
    ]


def extract_issue_tags(detail: dict, policy_map: dict[int, list[dict]] | None = None) -> list[str]:
    return [p["name"] for p in extract_policy_positions(detail, policy_map)]


def tags_to_anzsic(tags: list[str]) -> list[str]:
    codes: set[str] = set()
    combined = " ".join(tags).lower()
    for keyword, anzsic_list in POLICY_ANZSIC.items():
        if keyword in combined:
            codes.update(anzsic_list)
    return sorted(codes)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest They Vote For You voting records")
    parser.add_argument(
        "--since",
        default="2004-01-01",
        help="Import votes on or after YYYY-MM-DD (default: 2004-01-01, full TVFY history)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing to DB")
    parser.add_argument("--no-clear", action="store_true", help="Append instead of truncating")
    args = parser.parse_args()

    if not TVFY_API_KEY:
        print("ERROR: TVFY_API_KEY not set.", file=sys.stderr)
        print("Register for a free key at: https://theyvoteforyou.org.au/help/data", file=sys.stderr)
        sys.exit(1)

    try:
        since = datetime.strptime(args.since, "%Y-%m-%d").date()
    except ValueError:
        print(f"ERROR: --since must be YYYY-MM-DD, got '{args.since}'", file=sys.stderr)
        sys.exit(1)

    divisions = fetch_divisions(since)
    if not divisions:
        print("No divisions found — nothing to import.")
        return

    print("Building policy tag map...")
    policy_map = build_policy_map()

    if args.dry_run:
        tagged = sum(1 for d in divisions if d["id"] in policy_map)
        print(f"\nDRY RUN — would process {len(divisions)} divisions ({tagged} with policy tags). No DB writes.")
        return

    conn = psycopg2.connect(DATABASE_URL)
    try:
        if not args.no_clear:
            with conn.cursor() as cur:
                print("Clearing existing bills, votes, and bill_industry_relevance...")
                cur.execute("TRUNCATE bills, votes, bill_industry_relevance RESTART IDENTITY")
            conn.commit()

        bills_count = 0
        votes_count = 0
        relevance_count = 0
        unmatched: set[str] = set()

        for i, div in enumerate(divisions, 1):
            div_id = div["id"]
            print(f"[{i}/{len(divisions)}] {div['date']}  #{div_id}  {div['name'][:55]}", end="  ", flush=True)

            detail = fetch_division_detail(div_id)
            if not detail:
                print("SKIP (no detail)")
                continue

            positions = extract_policy_positions(detail, policy_map)
            tags = [p["name"] for p in positions]
            anzsic_codes = tags_to_anzsic(tags)
            div_house = detail.get("house") or div.get("house")
            member_votes = detail.get("votes") or []
            div_date_str = detail.get("date", div.get("date"))
            try:
                div_date = datetime.strptime(div_date_str, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                div_date = None

            with conn:
                with conn.cursor() as cur:
                    # Upsert bill
                    tvfy_number = detail.get("number") or div.get("number")
                    cur.execute(
                        """
                        INSERT INTO bills (title, issue_tags, policy_positions, summary, theyvoteforyou_id, tvfy_house, tvfy_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (theyvoteforyou_id) DO UPDATE SET
                            title            = EXCLUDED.title,
                            issue_tags       = EXCLUDED.issue_tags,
                            policy_positions = EXCLUDED.policy_positions,
                            summary          = EXCLUDED.summary,
                            tvfy_house       = EXCLUDED.tvfy_house,
                            tvfy_number      = EXCLUDED.tvfy_number
                        RETURNING id
                        """,
                        (
                            detail.get("name") or div["name"],
                            tags or None,
                            json.dumps(positions) if positions else None,
                            (detail.get("motion") or "")[:2000] or None,
                            str(div_id),
                            div_house,
                            tvfy_number,
                        ),
                    )
                    bill_db_id = cur.fetchone()[0]
                    bills_count += 1

                    # Link to industries
                    tag_note = ", ".join(tags) if tags else ""
                    for code in anzsic_codes:
                        cur.execute(
                            """
                            INSERT INTO bill_industry_relevance (bill_id, anzsic_code, relevance_note)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (bill_db_id, code, f"TVFY policy: {tag_note}" if tag_note else None),
                        )
                        relevance_count += 1

                    # Insert individual votes
                    for mv in member_votes:
                        vote_dir = (mv.get("vote") or "").lower()
                        if vote_dir not in VALID_VOTE_DIRECTIONS:
                            continue
                        member = mv.get("member") or {}
                        pol_id = upsert_politician(cur, member, div_house)
                        if pol_id is None:
                            first = member.get("first_name", "")
                            last = member.get("last_name", "")
                            unmatched.add(f"{first} {last}".strip() or "?")
                            continue
                        cur.execute(
                            """
                            INSERT INTO votes (politician_id, bill_id, vote_direction, vote_date)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (politician_id, bill_id) DO NOTHING
                            """,
                            (pol_id, bill_db_id, vote_dir, div_date),
                        )
                        votes_count += 1

            print(f"tags={len(tags)} industry={len(anzsic_codes)} votes={len(member_votes)}")

        print(f"\n{'='*60}")
        print(f"Bills inserted/updated : {bills_count}")
        print(f"Votes inserted         : {votes_count}")
        print(f"Industry links created : {relevance_count}")
        if unmatched:
            print(f"Unmatched members      : {len(unmatched)}")
            sample = sorted(unmatched)[:5]
            print(f"  Sample: {', '.join(sample)}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
