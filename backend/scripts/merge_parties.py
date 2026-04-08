"""
Normalize duplicate party name variants in the database.

Two passes:
  1. Strip " - STATE" / " - NATIONAL" AEC artefact suffixes.
     A suffix is only stripped when the state name is already present in the
     base name, e.g. "(NSW Branch) - NSW" → "(NSW Branch)".
     This prevents stripping meaningful branch identifiers like
     "National Party of Australia - NSW" which would wrongly merge into the
     national body.
  2. Apply a hardcoded canonical name mapping for known abbreviation /
     spelling variants that Pass 1 can't catch automatically.

For each pair:
  - If the canonical name already exists as a party record:
      reassign all FK references → delete the duplicate.
  - If the canonical name does not yet exist:
      rename the record in-place.

Safe to re-run — skips any name not present in the database.

Usage:
    uv run scripts/merge_parties.py [--dry-run]
"""

import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)

# ── Pass 1: suffix detection ────────────────────────────────────────────────
# Captures the base name and the trailing state/national abbreviation.

_SUFFIX_RE = re.compile(
    r"^(.*?)\s*-\s*(ACT|NSW|NT|QLD|SA|TAS|VIC|WA|NATIONAL)\s*$",
    re.IGNORECASE,
)

# Variants of each state abbreviation to look for in the base name.
# "NATIONAL" is always safe to strip (it's never a real branch identifier).
_STATE_VARIANTS: dict[str, list[str]] = {
    "ACT":      ["ACT", "AUSTRALIAN CAPITAL TERRITORY"],
    "NSW":      ["NSW", "N.S.W.", "NEW SOUTH WALES"],
    "NT":       ["NT", "NORTHERN TERRITORY"],
    "QLD":      ["QLD", "QUEENSLAND"],
    "SA":       ["SA", "S.A.", "SOUTH AUSTRALIA", "SOUTH AUSTRALIAN"],
    "TAS":      ["TAS", "TASMANIA", "TASMANIAN"],
    "VIC":      ["VIC", "VICTORIA", "VICTORIAN"],
    "WA":       ["WA", "W.A.", "WESTERN AUSTRALIA", "WESTERN AUSTRALIAN"],
    "NATIONAL": [],
}


def _should_strip_suffix(base_name: str, state_abbr: str) -> bool:
    """
    Return True only if the state is already referenced in the base name,
    meaning the trailing abbreviation is a redundant AEC artefact.
    NATIONAL is always treated as an artefact suffix.
    """
    if state_abbr.upper() == "NATIONAL":
        return True
    base_upper = base_name.upper()
    for variant in _STATE_VARIANTS.get(state_abbr.upper(), []):
        if variant.upper() in base_upper:
            return True
    return False


# ── Pass 2: canonical name map ──────────────────────────────────────────────
# Maps variant name → canonical name.
# Extend this dict as other parties are ingested and new variants appear.
# Pass 1 runs first so some variants arrive here already partially cleaned.

CANONICAL_MAP: dict[str, str] = {
    # ── Australian Labor Party — national ─────────────────────────────────
    "Australian Labor Party(ALP)":                       "Australian Labor Party",
    "Australian Labor Party (ALP)":                      "Australian Labor Party",  # after Pass 1 strips "- NATIONAL"
    "Australian Labor Party - National Secretariat":     "Australian Labor Party",

    # ── ALP — NSW ─────────────────────────────────────────────────────────
    "Australian Labor Party (N.S.W. Branch)":            "Australian Labor Party (NSW Branch)",

    # ── ALP — Queensland ──────────────────────────────────────────────────
    "Australian Labor Party - State of Queensland":      "Australian Labor Party (State of Queensland)",

    # ── ALP — South Australia ─────────────────────────────────────────────
    "Australian Labor Party (SA Branch)":                "Australian Labor Party (South Australian Branch)",

    # ── ALP — Victoria ───────────────────────────────────────────────────
    "Australian Labor Party (VIC Branch)":               "Australian Labor Party (Victorian Branch)",

    # ── ALP — Western Australia ──────────────────────────────────────────
    "Australian Labor Party (WA Branch)":                "Australian Labor Party (Western Australian Branch)",

    # ── ALP — Northern Territory ─────────────────────────────────────────
    "Australian Labor Party (Northern Territory) Branch": "Australian Labor Party (NT Branch)",

    # ── Liberal Party — national ──────────────────────────────────────────
    # "- NATIONAL" is handled by Pass 1 (strips to "Liberal Party of Australia"
    # which already exists as the seed record).
    "Liberal Party of Australia(LIB)":                   "Liberal Party of Australia",
    "Liberal Party of Australia - Federal Secretariat":  "Liberal Party of Australia",

    # ── Liberal Party — Western Australia ────────────────────────────────
    # Multiple forms: with/without "of Australia", with/without trailing period,
    # and a separate state-incorporated entity "The Liberal Party of WA Pty Ltd".
    # Pass 1 merges "Inc. - WA" → "Inc." first, then this map cleans up.
    "Liberal Party (W.A. Division) Inc":                 "Liberal Party of Australia (WA Division) Inc",
    "Liberal Party (W.A. Division) Inc.":                "Liberal Party of Australia (WA Division) Inc",
    "The Liberal Party of Western Australia Pty Ltd":    "Liberal Party of Australia (WA Division) Inc",

    # ── LNP ───────────────────────────────────────────────────────────────
    "Liberal National Party of Queensland(LNP)":         "Liberal National Party of Queensland",

    # ── The Nationals — national ──────────────────────────────────────────
    # Pass 1 strips "- NATIONAL" → renames to "National Party of Australia"
    # (if that record doesn't already exist), then this map merges it into
    # the seed canonical "The Nationals".
    "National Party of Australia":                       "The Nationals",
    "National Party of Australia - National Secretariat": "The Nationals",
    # "(NAT)" variant — real DB entry or UI display artefact; harmless either way.
    "The Nationals(NAT)":                                "The Nationals",

    # ── The Nationals — NSW ───────────────────────────────────────────────
    # "- N.S.W. - NSW" is handled by Pass 1 (N.S.W. is in the base name).
    # This map consolidates the abbreviated "- NSW" form into the dotted form.
    "National Party of Australia - NSW":                 "National Party of Australia - N.S.W.",

    # ── Pauline Hanson's One Nation ───────────────────────────────────────
    "Pauline Hanson's One Nation Ltd":                   "Pauline Hanson's One Nation",

    # ── Australian Greens ─────────────────────────────────────────────────
    # Add variants here after running --dry-run against your dataset.
    # State Greens branches (e.g. "The Greens NSW") are separate registered
    # entities and should remain distinct from "Australian Greens".
}


# ── Data loading ──────────────────────────────────────────────────────────────

def load_parties(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.name, p.abbreviation, p.ideology_tags,
                   COALESCE(d.cnt,   0) AS donations,
                   COALESCE(e.cnt,   0) AS expenditures,
                   COALESCE(pol.cnt, 0) AS politicians
            FROM parties p
            LEFT JOIN (
                SELECT recipient_party_id AS pid, COUNT(*) AS cnt
                FROM donations GROUP BY pid
            ) d   ON d.pid = p.id
            LEFT JOIN (
                SELECT party_id AS pid, COUNT(*) AS cnt
                FROM expenditure GROUP BY pid
            ) e   ON e.pid = p.id
            LEFT JOIN (
                SELECT party_id AS pid, COUNT(*) AS cnt
                FROM politicians GROUP BY pid
            ) pol ON pol.pid = p.id
            ORDER BY p.name
        """)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Merge / rename helper ─────────────────────────────────────────────────────

def apply_merge(
    conn,
    discard_name: str,
    canonical_name: str,
    reason: str,
    dry_run: bool,
    name_index: dict[str, dict],
) -> bool:
    """
    Merge or rename discard_name → canonical_name.
    Returns True if an action was taken (or would be in dry-run).
    """
    if discard_name == canonical_name:
        return False

    discard = name_index.get(discard_name)
    if not discard:
        return False  # already gone or never existed

    canonical = name_index.get(canonical_name)

    if canonical:
        # ── Merge: canonical already exists ──────────────────────────────
        print(
            f"MERGE  [{reason}]  {discard_name!r} "
            f"({discard['donations']}d) → {canonical_name!r}",
            flush=True,
        )
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE donations SET recipient_party_id = %s WHERE recipient_party_id = %s",
                    (canonical["id"], discard["id"]),
                )
                cur.execute(
                    "UPDATE expenditure SET party_id = %s WHERE party_id = %s",
                    (canonical["id"], discard["id"]),
                )
                cur.execute(
                    "UPDATE public_funding SET party_id = %s WHERE party_id = %s",
                    (canonical["id"], discard["id"]),
                )
                cur.execute(
                    "UPDATE politicians SET party_id = %s WHERE party_id = %s",
                    (canonical["id"], discard["id"]),
                )
                # Backfill abbreviation / ideology_tags if canonical lacks them
                if not canonical["abbreviation"] and discard["abbreviation"]:
                    cur.execute(
                        "UPDATE parties SET abbreviation = %s WHERE id = %s",
                        (discard["abbreviation"], canonical["id"]),
                    )
                if not canonical["ideology_tags"] and discard["ideology_tags"]:
                    cur.execute(
                        "UPDATE parties SET ideology_tags = %s WHERE id = %s",
                        (discard["ideology_tags"], canonical["id"]),
                    )
                cur.execute("DELETE FROM parties WHERE id = %s", (discard["id"],))
            conn.commit()
        name_index.pop(discard_name, None)

    else:
        # ── Rename: canonical doesn't exist yet ───────────────────────────
        print(
            f"RENAME [{reason}]  {discard_name!r} → {canonical_name!r}",
            flush=True,
        )
        if not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE parties SET name = %s WHERE id = %s",
                    (canonical_name, discard["id"]),
                )
            conn.commit()
        name_index.pop(discard_name, None)
        discard["name"] = canonical_name
        name_index[canonical_name] = discard

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Normalize duplicate party name variants")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned changes without writing to the database")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    merged = 0
    renamed = 0

    try:
        parties = load_parties(conn)
        name_index = {p["name"]: p for p in parties}
        print(f"Loaded {len(parties)} party records.\n")

        # ── Pass 1: strip AEC state/national artefact suffixes ────────────
        print(f"── Pass 1: suffix stripping ({len(parties)} parties) ──")
        for party in list(parties):
            name = party["name"]
            m = _SUFFIX_RE.match(name)
            if not m:
                continue
            base, state_abbr = m.group(1).strip(), m.group(2)
            if not _should_strip_suffix(base, state_abbr):
                continue  # suffix is a meaningful branch identifier — leave it
            if base == name:
                continue
            action = apply_merge(conn, name, base, "suffix-strip", args.dry_run, name_index)
            if action:
                if base in name_index:
                    merged += 1
                else:
                    renamed += 1

        # ── Pass 2: apply canonical name map ──────────────────────────────
        print(f"\n── Pass 2: canonical name mapping ({len(CANONICAL_MAP)} rules) ──")
        for variant, canonical in CANONICAL_MAP.items():
            action = apply_merge(conn, variant, canonical, "canonical-map", args.dry_run, name_index)
            if action:
                if canonical in name_index:
                    merged += 1
                else:
                    renamed += 1

        # ── Summary ───────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"Merges : {merged}")
        print(f"Renames: {renamed}")
        remaining = load_parties(conn)
        print(f"Parties remaining: {len(remaining)}")
        if args.dry_run:
            print("\n(dry run — no changes written)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
