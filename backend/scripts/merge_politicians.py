"""
Merge last-name-only politician stubs (from House PDF parser) with
full-name records (from TVFY/Senate API).

The House register PDF parser creates politicians using the slug from the
APH URL, which is usually just a last name (e.g. "Albanese"). TVFY creates
full-name records ("Anthony Albanese"). This script finds matches and
reassigns interests, votes, and donations to the canonical full-name record.

Safe to re-run — skips already-merged records.

Usage:
    uv run scripts/merge_politicians.py [--dry-run]
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


def normalise_slug(slug: str) -> tuple[str, str | None]:
    """
    Turn PDF slugs into (base_name, first_initial) pairs.
    Examples:
      "CookK"         → ("Cook", "K")
      "WilsonJ"       → ("Wilson", "J")
      "Peter_Khalil"  → ("Peter Khalil", None)
      "Albanese"      → ("Albanese", None)
      "SmithD_"       → ("Smith", "D")
    """
    # "SmithD_" — strip trailing underscores
    slug = slug.rstrip("_").strip()
    # "Peter_Khalil" → "Peter Khalil"
    slug = slug.replace("_", " ").strip()

    # Check for trailing initial: "CookK" or "McCormackM"
    m = re.match(r"^(.+?)([A-Z])$", slug)
    if m:
        base = m.group(1)
        initial = m.group(2)
        # Only treat as initial if base part ends with a lowercase letter
        if base and base[-1].islower():
            return base.strip(), initial

    return slug, None


def find_match(cur, stub_name: str, stub_id: int) -> list[tuple[int, str]]:
    """Return list of (id, name) full-name politicians matching this stub."""
    base, initial = normalise_slug(stub_name)

    if " " in base:
        # Multi-word slug like "Peter Khalil" — try exact match
        cur.execute(
            "SELECT id, name FROM politicians WHERE LOWER(name) = LOWER(%s) AND id != %s",
            (base, stub_id),
        )
    else:
        # Single word — match as last name
        cur.execute(
            """
            SELECT id, name FROM politicians
            WHERE (name ILIKE %s OR name ILIKE %s)
              AND id != %s
              AND name NOT LIKE '%%,%%'
            """,
            (base, f"% {base}", stub_id),
        )

    candidates = cur.fetchall()

    # Narrow by first-name initial when available (e.g. "CookK" → first name starts with K)
    if initial and len(candidates) > 1:
        narrowed = [
            (cid, cname) for cid, cname in candidates
            if cname.split()[0].upper().startswith(initial.upper())
        ]
        if narrowed:
            candidates = narrowed

    return candidates


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate politician records")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Find all single-word (stub) politicians
            cur.execute("""
                SELECT p.id, p.name,
                    (SELECT COUNT(*) FROM interests WHERE politician_id = p.id) AS interests,
                    (SELECT COUNT(*) FROM votes WHERE politician_id = p.id) AS votes,
                    (SELECT COUNT(*) FROM donations WHERE recipient_politician_id = p.id) AS donations
                FROM politicians p
                WHERE p.name NOT LIKE '% %'
                ORDER BY p.name
            """)
            stubs = cur.fetchall()

        merged = 0
        skipped_empty = 0
        ambiguous = []
        no_match = []

        for stub_id, stub_name, interests, votes, donations in stubs:
            total_data = interests + votes + donations
            if total_data == 0:
                skipped_empty += 1
                continue

            matches = find_match(conn.cursor(), stub_name, stub_id)

            if len(matches) == 1:
                target_id, target_name = matches[0]
                print(f"MERGE  {stub_name!r:25} ({interests}i/{votes}v/{donations}d)"
                      f" → {target_name!r} (id={target_id})")

                if not args.dry_run:
                    with conn.cursor() as cur:
                        if interests:
                            cur.execute(
                                "UPDATE interests SET politician_id = %s WHERE politician_id = %s",
                                (target_id, stub_id),
                            )
                        if votes:
                            cur.execute(
                                "UPDATE votes SET politician_id = %s WHERE politician_id = %s",
                                (target_id, stub_id),
                            )
                        if donations:
                            cur.execute(
                                "UPDATE donations SET recipient_politician_id = %s "
                                "WHERE recipient_politician_id = %s",
                                (target_id, stub_id),
                            )
                        cur.execute("DELETE FROM politicians WHERE id = %s", (stub_id,))
                    conn.commit()
                merged += 1

            elif len(matches) > 1:
                ambiguous.append((stub_name, matches))
            else:
                no_match.append(stub_name)

        print(f"\n{'='*60}")
        print(f"Merged  : {merged}")
        print(f"Skipped (no data): {skipped_empty}")
        if ambiguous:
            print(f"Ambiguous ({len(ambiguous)} — manual review needed):")
            for name, matches in ambiguous:
                print(f"  {name!r} → {[m[1] for m in matches]}")
        if no_match:
            print(f"No match ({len(no_match)} — kept as-is):")
            for name in no_match[:10]:
                print(f"  {name!r}")
            if len(no_match) > 10:
                print(f"  ... and {len(no_match)-10} more")
        if args.dry_run:
            print("\n(dry run — no changes written)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
