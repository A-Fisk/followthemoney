"""
LLM-assisted review of ambiguous donor merge candidates.

Runs after merge_donors.py --dry-run to resolve cases where two or more
donor records might be the same entity but can't be auto-merged safely.

Workflow:
    # 1. Generate ambiguous cases file
    uv run scripts/merge_donors.py --dry-run --export-ambiguous ambiguous.json

    # 2a. LLM review (writes decisions.json, auto-approves high-confidence cases)
    uv run scripts/review_ambiguous.py ambiguous.json

    # 2b. Interactive manual review (works on ambiguous.json or decisions.json)
    uv run scripts/review_ambiguous.py decisions.json --interactive

    # 3. Apply decisions
    uv run scripts/merge_donors.py --apply-decisions decisions.json

Options:
    --output FILE      Where to write decisions (default: decisions.json)
    --confidence low|medium|high
                       Minimum confidence to mark as auto-apply (default: high)
    --interactive      Step through unresolved cases one by one for manual review
    --dry-run          Print decisions without writing output file
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from llm_client import chat_json, LLM_MODEL

SYSTEM_PROMPT = """\
You are a data quality assistant reviewing Australian political donation records.
Your job is to decide whether two or more donor name variants refer to the same
real-world entity, and if so, which name is the canonical (most official/complete) form.

Rules:
- "Last, First" format and "First Last" format of the same name → same entity
- Full middle name vs first+last only → same entity if clearly the same person
- "Pty Ltd" / "Pty Limited" / "PTY LTD" variants → same entity
- Abbreviated company name vs full name (e.g. "Westpac" vs "Westpac Banking Corporation") → same entity
- Different people who happen to share a first and last name → different entities (be conservative)
- Couples ("Ian And Glenys Pascarl") vs individual ("Ian Pascarl") → different entities

Always respond with valid JSON matching the schema provided.
"""

DECISION_SCHEMA = {
    "same_entity": "boolean — true if all candidates refer to the same real-world entity",
    "canonical": "string — the best name to keep (most complete/official). Required if same_entity is true.",
    "confidence": "string — one of: high, medium, low",
    "reasoning": "string — one sentence explaining the decision",
}


def review_case(name: str, candidates: list[str], reason: str) -> dict:
    """Ask the LLM to resolve one ambiguous case. Returns a decision dict."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Ambiguous donor record: {name!r}\n"
                f"Possible matches: {json.dumps(candidates)}\n"
                f"Flagged by: {reason} matching\n\n"
                f"Respond with JSON matching this schema:\n{json.dumps(DECISION_SCHEMA, indent=2)}"
            ),
        },
    ]
    try:
        result = chat_json(messages)
        # Normalise keys
        return {
            "same_entity": bool(result.get("same_entity", False)),
            "canonical": result.get("canonical"),
            "confidence": result.get("confidence", "low"),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        return {
            "same_entity": False,
            "canonical": None,
            "confidence": "low",
            "reasoning": f"LLM error: {e}",
        }


def interactive_review(decisions: list[dict], output_path: Path) -> list[dict]:
    """
    Step through cases that aren't yet approved, prompting for a decision.

    Shows the LLM recommendation (if present) and waits for:
      y  — merge (approve auto_apply, or set it if missing)
      n  — don't merge (same_entity = false)
      c  — choose canonical manually (prompts for which candidate to keep)
      s  — skip for now (leave unchanged)
      q  — quit and save progress

    Saves the file after every answer so progress isn't lost on quit.
    """
    # Cases needing a decision: no auto_apply yet, or same_entity but not approved
    pending = [
        (i, d) for i, d in enumerate(decisions)
        if not d.get("auto_apply")
    ]
    total_pending = len(pending)

    KEYS = "  [y] merge  [n] reject  [c] choose canonical  [s] skip  [q] quit"

    if total_pending == 0:
        print("No pending cases — all decisions already resolved.")
        return decisions

    print(f"\n{total_pending} cases need manual review.\n")

    for step, (idx, d) in enumerate(pending, 1):
        name       = d["name"]
        candidates = d["candidates"]
        reason     = d.get("reason", "")

        # Header
        print(f"── [{step}/{total_pending}] ──────────────────────────────────────────")
        print(KEYS)
        print(f"  Ambiguous : {name!r}")
        print(f"  Candidates: {candidates}")
        print(f"  Reason    : {reason}")

        # Show LLM recommendation if present
        if d.get("reasoning"):
            verdict = "MERGE → " + repr(d["canonical"]) if d.get("same_entity") else "SKIP"
            print(f"  LLM says  : {verdict}  [{d.get('confidence', '?')}]")
            print(f"  Reasoning : {d['reasoning']}")

        # Prompt
        while True:
            try:
                key = input("\n  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                key = "q"

            if key == "y":
                # Use LLM canonical if available, else first candidate
                if not d.get("canonical"):
                    d["canonical"] = candidates[0]
                d["same_entity"] = True
                d["auto_apply"]  = True
                print(f"  ✓ MERGE → {d['canonical']!r}")
                break

            elif key == "n":
                d["same_entity"] = False
                d["auto_apply"]  = False
                print("  ✗ SKIP (will not merge)")
                break

            elif key == "c":
                print("  Choose canonical:")
                all_names = [name] + candidates
                for j, n in enumerate(all_names):
                    print(f"    {j}: {n!r}")
                try:
                    choice = int(input("  > ").strip())
                    d["canonical"]   = all_names[choice]
                    d["same_entity"] = True
                    d["auto_apply"]  = True
                    print(f"  ✓ MERGE → {d['canonical']!r}")
                except (ValueError, IndexError):
                    print("  Invalid choice — try again.")
                    continue
                break

            elif key == "s":
                print("  → Skipped (unchanged)")
                break

            elif key == "q":
                print("\nQuitting — saving progress...")
                decisions[idx] = d
                output_path.write_text(json.dumps(decisions, indent=2))
                print(f"Saved to {output_path}. Resume with --interactive.")
                return decisions

            else:
                print("  Keys: y / n / c / s / q")
                continue

        decisions[idx] = d
        # Save after every answer
        output_path.write_text(json.dumps(decisions, indent=2))

    approved = sum(1 for d in decisions if d.get("auto_apply"))
    print(f"\nDone. {approved} merges approved total.")
    return decisions


def main():
    parser = argparse.ArgumentParser(description="LLM review of ambiguous donor merges")
    parser.add_argument("input", help="ambiguous.json or decisions.json")
    parser.add_argument("--output", default="decisions.json", help="Output file for decisions")
    parser.add_argument(
        "--confidence",
        choices=["low", "medium", "high"],
        default="high",
        help="Minimum confidence to flag as auto-apply (default: high)",
    )
    parser.add_argument("--interactive", action="store_true",
                        help="Step through unresolved cases for manual review")
    parser.add_argument("--dry-run", action="store_true", help="Print decisions, don't write file")
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text())
    output_path = Path(args.output)

    # ── Interactive-only mode: input is already a decisions file ──────────────
    # Detected by presence of "auto_apply" key in first entry.
    if args.interactive and raw and "auto_apply" in raw[0]:
        decisions = raw
        decisions = interactive_review(decisions, output_path)
        if not args.dry_run:
            output_path.write_text(json.dumps(decisions, indent=2))
            print(f"Saved to {output_path}")
        return

    cases = raw
    total = len(cases)

    if args.interactive and not any("auto_apply" in c for c in cases):
        # Pure interactive mode on ambiguous.json — skip LLM entirely
        decisions = [
            {**c, "same_entity": False, "canonical": None,
             "confidence": "unreviewed", "reasoning": "", "auto_apply": False}
            for c in cases
        ]
        decisions = interactive_review(decisions, output_path)
        if not args.dry_run:
            output_path.write_text(json.dumps(decisions, indent=2))
            print(f"Saved to {output_path}")
        return

    print(f"Reviewing {total} ambiguous cases using {LLM_MODEL}...")
    print(f"Auto-apply threshold: confidence >= {args.confidence}\n")

    conf_rank = {"low": 0, "medium": 1, "high": 2}
    threshold = conf_rank[args.confidence]

    decisions = []
    auto_merge = 0
    skip = 0
    errors = 0

    for i, case in enumerate(cases, 1):
        name = case["name"]
        candidates = case["candidates"]
        reason = case["reason"]

        print(f"[{i}/{total}] {name!r}", end=" ... ", flush=True)
        decision = review_case(name, candidates, reason)

        decision["name"] = name
        decision["candidates"] = candidates
        decision["reason"] = reason
        decision["auto_apply"] = (
            decision["same_entity"]
            and conf_rank.get(decision["confidence"], 0) >= threshold
        )

        if "error" in decision["reasoning"].lower():
            errors += 1
            status = "ERROR"
        elif decision["auto_apply"]:
            auto_merge += 1
            status = f"MERGE → {decision['canonical']!r} [{decision['confidence']}]"
        elif decision["same_entity"]:
            status = f"MERGE (low confidence, manual) → {decision['canonical']!r}"
        else:
            skip += 1
            status = f"SKIP [{decision['confidence']}]"

        print(status)
        if decision["reasoning"] and "error" not in decision["reasoning"].lower():
            print(f"    {decision['reasoning']}")

        decisions.append(decision)

    print(f"\n{'='*60}")
    print(f"Total cases   : {total}")
    print(f"Auto-merge    : {auto_merge}  (confidence >= {args.confidence})")
    print(f"Skip          : {skip}")
    print(f"Errors        : {errors}")
    print(f"Manual review : {total - auto_merge - skip - errors}")

    if not args.dry_run:
        output_path.write_text(json.dumps(decisions, indent=2))
        print(f"\nDecisions written to {output_path}")
        if args.interactive:
            # Drop straight into manual review for anything the LLM didn't auto-approve
            decisions = interactive_review(decisions, output_path)
            output_path.write_text(json.dumps(decisions, indent=2))
        else:
            print(f"Apply with: uv run scripts/merge_donors.py --apply-decisions {output_path}")
            pending = sum(1 for d in decisions if not d.get("auto_apply"))
            if pending:
                print(f"Tip: {pending} cases need manual review —"
                      f" run with --interactive to step through them.")
    else:
        print("\n(dry run — no output file written)")


if __name__ == "__main__":
    main()
