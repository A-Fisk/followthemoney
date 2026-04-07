"""
LLM-assisted review of ambiguous donor merge candidates.

Runs after merge_donors.py --dry-run to resolve cases where two or more
donor records might be the same entity but can't be auto-merged safely.

Workflow:
    # 1. Generate ambiguous cases file
    uv run scripts/merge_donors.py --dry-run --export-ambiguous ambiguous.json

    # 2. Submit to LLM for review (writes decisions.json)
    uv run scripts/review_ambiguous.py ambiguous.json

    # 3. Apply decisions
    uv run scripts/merge_donors.py --apply-decisions decisions.json

Options:
    --output FILE      Where to write decisions (default: decisions.json)
    --confidence low|medium|high
                       Minimum confidence to mark as auto-apply (default: high)
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


def main():
    parser = argparse.ArgumentParser(description="LLM review of ambiguous donor merges")
    parser.add_argument("input", help="ambiguous.json produced by merge_donors.py --export-ambiguous")
    parser.add_argument("--output", default="decisions.json", help="Output file for decisions")
    parser.add_argument(
        "--confidence",
        choices=["low", "medium", "high"],
        default="high",
        help="Minimum confidence to flag as auto-apply (default: high)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print decisions, don't write file")
    args = parser.parse_args()

    cases = json.loads(Path(args.input).read_text())
    total = len(cases)
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
        Path(args.output).write_text(json.dumps(decisions, indent=2))
        print(f"\nDecisions written to {args.output}")
        print(f"Apply with: uv run scripts/merge_donors.py --apply-decisions {args.output}")
    else:
        print("\n(dry run — no output file written)")


if __name__ == "__main__":
    main()
