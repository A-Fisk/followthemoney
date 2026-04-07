"""
Merge duplicate donor records.

Three passes:
  1. "Last, First" format  → normalise to "First Last" and find exact match
  2. Legal suffix variants → e.g. "Ltd" / "Limited" / "LTD" / "Pty Ltd"
  3. Prefix abbreviations  → e.g. "Westpac" ⊂ "Westpac Banking Corporation"

For each duplicate pair the canonical record is the one with more metadata
(ABN, industry_label, etc.) and more total donations; the other is deleted
after its donations/interests are reassigned.

Safe to re-run — only merges where there is a single unambiguous match.

Usage:
    uv run scripts/merge_donors.py [--dry-run]
"""

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://ftm:ftm@localhost:5432/followthemoney",
)


# ── Name normalisation ─────────────────────────────────────────────────────────

_SUFFIX_SUBS = [
    # Must come first: compound forms
    (r"\bpty\.?\s+ltd\.?\b",        "pty limited"),
    (r"\bproprietary\s+limited\b",  "pty limited"),
    # Simple forms
    (r"\bltd\.?\b",                 "limited"),
    (r"\bcorp\.?\b",                "corporation"),
    (r"\binc\.?\b",                 "incorporated"),
    (r"\bco\.?\b",                  "company"),
    (r"\bno\.?\b",                  "number"),
]

def _norm(name: str) -> str:
    """Lowercase, normalise legal suffixes, strip punctuation noise."""
    n = name.lower().strip()
    for pattern, replacement in _SUFFIX_SUBS:
        n = re.sub(pattern, replacement, n)
    n = re.sub(r"['.,-]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


# ── Canonical record selection ─────────────────────────────────────────────────

def _score(row: dict) -> int:
    """Higher score = better candidate to keep as canonical."""
    score = 0
    if row["abn"]:          score += 10
    if row["industry_label"]: score += 5
    if row["entity_type"]:  score += 3
    if row["anzsic_code"]:  score += 2
    if row["controlling_person"]: score += 1
    score += row["donations"]
    return score


def _pick_canonical(a: dict, b: dict) -> tuple[dict, dict]:
    """Return (keep, discard)."""
    if _score(a) >= _score(b):
        return a, b
    return b, a


# ── Merge helper ───────────────────────────────────────────────────────────────

def merge_donors(conn, keep: dict, discard: dict, reason: str, dry_run: bool) -> None:
    print(
        f"MERGE  [{reason}] {discard['name']!r:45} "
        f"({discard['donations']}d) → {keep['name']!r} (id={keep['id']})",
        flush=True,
    )
    if dry_run:
        return
    with conn.cursor() as cur:
        cur.execute("UPDATE donations SET donor_id = %s WHERE donor_id = %s",
                    (keep["id"], discard["id"]))
        cur.execute("UPDATE interests SET donor_id = %s WHERE donor_id = %s",
                    (keep["id"], discard["id"]))
        # Backfill any missing metadata onto the canonical record
        for col in ("abn", "entity_type", "anzsic_code", "industry_label",
                    "controlling_person", "notes"):
            if not keep[col] and discard[col]:
                cur.execute(f"UPDATE donors SET {col} = %s WHERE id = %s",
                            (discard[col], keep["id"]))
        cur.execute("DELETE FROM donors WHERE id = %s", (discard["id"],))
    conn.commit()


# ── Data loading ───────────────────────────────────────────────────────────────

def load_donors(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT d.id, d.name, d.abn, d.entity_type, d.anzsic_code,
                   d.industry_label, d.controlling_person, d.notes,
                   COUNT(don.id) AS donations
            FROM donors d
            LEFT JOIN donations don ON don.donor_id = d.id
            GROUP BY d.id
            ORDER BY d.name
        """)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Merge duplicate donor records")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--export-ambiguous",
        metavar="FILE",
        help="Write ambiguous cases to a JSON file for LLM review",
    )
    parser.add_argument(
        "--apply-decisions",
        metavar="FILE",
        help="Read decisions.json from review_ambiguous.py and apply auto_apply merges",
    )
    args = parser.parse_args()

    # ── Apply decisions mode ──────────────────────────────────────────────────
    if args.apply_decisions:
        import json as _json
        decisions = _json.loads(Path(args.apply_decisions).read_text())
        to_apply = [d for d in decisions if d.get("auto_apply") and d.get("canonical")]
        print(f"Applying {len(to_apply)} auto-approved decisions from {args.apply_decisions}...")
        conn = psycopg2.connect(DATABASE_URL)
        applied = 0
        try:
            for d in to_apply:
                canonical_name = d["canonical"]
                candidates = d["candidates"] + [d["name"]]
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name FROM donors WHERE name = ANY(%s)",
                        (candidates,),
                    )
                    rows = {name: did for did, name in cur.fetchall()}
                if canonical_name not in rows:
                    print(f"  SKIP (canonical not found): {canonical_name!r}")
                    continue
                keep_id = rows[canonical_name]
                for name, did in rows.items():
                    if did == keep_id:
                        continue
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM donations WHERE donor_id = %s", (did,))
                        dcount = cur.fetchone()[0]
                    # Reuse existing merge helper logic inline
                    print(f"  MERGE {name!r} ({dcount}d) → {canonical_name!r}")
                    if not args.dry_run:
                        with conn.cursor() as cur:
                            cur.execute("UPDATE donations SET donor_id = %s WHERE donor_id = %s", (keep_id, did))
                            cur.execute("UPDATE interests SET donor_id = %s WHERE donor_id = %s", (keep_id, did))
                            for col in ("abn", "entity_type", "anzsic_code", "industry_label", "controlling_person", "notes"):
                                cur.execute(
                                    f"UPDATE donors d SET {col} = src.{col} FROM donors src "
                                    f"WHERE d.id = %s AND src.id = %s AND d.{col} IS NULL AND src.{col} IS NOT NULL",
                                    (keep_id, did),
                                )
                            cur.execute("DELETE FROM donors WHERE id = %s", (did,))
                        conn.commit()
                        applied += 1
        finally:
            conn.close()
        print(f"\nApplied: {applied} merges")
        if args.dry_run:
            print("(dry run — no changes written)")
        return

    conn = psycopg2.connect(DATABASE_URL)
    merged = 0
    ambiguous = []

    try:
        donors = load_donors(conn)
        by_id = {d["id"]: d for d in donors}

        # ── Pass 1: "Last, First" format ──────────────────────────────────────
        print(f"\n── Pass 1: Last, First format ({len(donors)} donors) ──", flush=True)
        name_index: dict[str, dict] = {d["name"]: d for d in donors}

        for donor in list(donors):
            name = donor["name"]
            if "," not in name:
                continue
            parts = [p.strip() for p in name.split(",", 1)]
            if len(parts) != 2:
                continue
            last, given = parts
            # Skip organisational / couple names — heuristic: "And" in given
            if " and " in given.lower():
                continue
            first = given.split()[0] if given else ""
            candidates = []
            for candidate_name in (f"{given} {last}", f"{first} {last}"):
                if candidate_name in name_index and name_index[candidate_name]["id"] != donor["id"]:
                    candidates.append(name_index[candidate_name])
            # Deduplicate
            seen: set[int] = set()
            candidates = [c for c in candidates if not (c["id"] in seen or seen.add(c["id"]))]

            if len(candidates) == 1:
                keep, discard = _pick_canonical(candidates[0], donor)
                merge_donors(conn, keep, discard, "last,first", args.dry_run)
                merged += 1
                if not args.dry_run:
                    # Refresh index only when we actually changed the DB
                    donors = load_donors(conn)
                    name_index = {d["name"]: d for d in donors}
                else:
                    # In dry-run, just remove the discarded entry from the in-memory index
                    name_index.pop(discard["name"], None)
            elif len(candidates) > 1:
                ambiguous.append((name, [c["name"] for c in candidates], "last,first"))

        # ── Pass 2: legal suffix normalisation ────────────────────────────────
        donors = load_donors(conn)
        print(f"\n── Pass 2: Legal suffix variants ({len(donors)} donors) ──", flush=True)

        norm_map: dict[str, list[dict]] = {}
        for d in donors:
            n = _norm(d["name"])
            norm_map.setdefault(n, []).append(d)

        for norm_key, group in norm_map.items():
            if len(group) < 2:
                continue
            # Skip if any name in the group has a comma — handled by Pass 1
            if any("," in d["name"] for d in group):
                continue
            if len(group) == 2:
                keep, discard = _pick_canonical(group[0], group[1])
                merge_donors(conn, keep, discard, "suffix", args.dry_run)
                merged += 1
            else:
                ambiguous.append((norm_key, [d["name"] for d in group], "suffix"))

        # ── Pass 3: prefix abbreviations ──────────────────────────────────────
        # e.g. "Westpac" matches "Westpac Banking Corporation"
        # Uses a sorted name list + bisect so lookups are O(log n) not O(n²).
        print("\n── Pass 3: Prefix abbreviations ──")
        import bisect
        donors = load_donors(conn)
        # Build a sorted list of (lowercase_name, donor) for binary search
        sorted_lower = sorted((d["name"].lower(), i, d) for i, d in enumerate(donors))
        sorted_keys = [x[0] for x in sorted_lower]


        shorts = [d for d in donors if len(d["name"]) <= 40]
        print(f"  Checking {len(shorts)} short names against {len(donors)} donors...")

        for i, short in enumerate(shorts):
            if i % 500 == 0 and i:
                print(f"  ... {i}/{len(shorts)}", flush=True)
            prefix = short["name"].lower()
            # Find all names that start with this prefix followed by space or comma
            lo = bisect.bisect_left(sorted_keys, prefix)
            matches = []
            for _, _i, d in sorted_lower[lo:]:
                name_l = d["name"].lower()
                if not name_l.startswith(prefix):
                    break
                if d["id"] == short["id"]:
                    continue
                rest = d["name"][len(short["name"]):]
                if rest and rest[0] in (" ", ","):
                    matches.append(d)

            if len(matches) == 1:
                keep, discard = _pick_canonical(matches[0], short)
                merge_donors(conn, keep, discard, "prefix", args.dry_run)
                merged += 1
                if not args.dry_run:
                    donors = load_donors(conn)
                    sorted_lower = sorted((d["name"].lower(), i, d) for i, d in enumerate(donors))
                    sorted_keys = [x[0] for x in sorted_lower]

            elif len(matches) > 1:
                ambiguous.append((short["name"], [m["name"] for m in matches], "prefix"))

        # ── Summary ───────────────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"Merged: {merged}")
        if ambiguous:
            print(f"Ambiguous ({len(ambiguous)} — manual review needed):")
            for name, matches, reason in ambiguous[:20]:
                print(f"  [{reason}] {name!r} → {matches}")
        if args.dry_run:
            print("\n(dry run — no changes written)")

        if args.export_ambiguous:
            import json as _json
            export = [
                {"name": name, "candidates": matches, "reason": reason}
                for name, matches, reason in ambiguous
            ]
            Path(args.export_ambiguous).write_text(_json.dumps(export, indent=2))
            print(f"\nAmbiguous cases written to {args.export_ambiguous}")
            print(f"Review with: uv run scripts/review_ambiguous.py {args.export_ambiguous}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
