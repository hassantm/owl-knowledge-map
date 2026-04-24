#!/usr/bin/env python3
"""
Batch Story Pack Generation

Generates story packs for all units that have both lesson and booklet content
ingested but no approved story pack yet. Skips units already generated unless
--force is passed.

Usage:
    python src/batch_generate.py
    python src/batch_generate.py --dry-run
    python src/batch_generate.py --force
    python src/batch_generate.py --no-qa
"""

import argparse
import sys
import time

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env', override=True)

from db import get_connection
from story_context import StoryPackRequest
from story_generator import generate_story_pack


def get_ready_units() -> list[dict]:
    """Return units with both lesson and booklet ingested."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT unit_id, year, subject, term, unit
                FROM units
                WHERE lesson_content IS NOT NULL
                  AND booklet_content IS NOT NULL
                ORDER BY year, subject, term
            """)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def already_generated(unit_id: int) -> bool:
    """Return True if a story pack already exists for this unit."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM generated_story_packs WHERE unit_id = %s LIMIT 1",
                (unit_id,)
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate story packs for all ingested units",
    )
    parser.add_argument("--force",      action="store_true",
                        help="Generate even if a pack already exists for the unit")
    parser.add_argument("--no-qa",      action="store_true",
                        help="Skip fact-check and rubric scoring passes")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Show which units would be processed without calling the API")
    parser.add_argument("--model",      default="claude-sonnet-4-6")
    parser.add_argument("--budget",     type=int, default=8000)
    parser.add_argument("--max-tokens", type=int, default=4000)
    args = parser.parse_args()

    units = get_ready_units()
    print(f"{len(units)} unit(s) with lesson + booklet content\n")

    to_run = []
    for u in units:
        if not args.force and already_generated(u["unit_id"]):
            print(f"  skip  {u['subject']} Y{u['year']} {u['term']} {u['unit']}")
        else:
            to_run.append(u)
            print(f"  queue {u['subject']} Y{u['year']} {u['term']} {u['unit']}")

    print(f"\n{len(to_run)} unit(s) to generate\n")

    if args.dry_run or not to_run:
        return 0

    ok, failed = [], []

    for i, u in enumerate(to_run, 1):
        label = f"{u['subject']} Y{u['year']} {u['term']} {u['unit']}"
        print(f"[{i}/{len(to_run)}] {label}")

        request = StoryPackRequest(
            unit_id=u["unit_id"],
            year=u["year"],
            context_budget_tokens=args.budget,
            model=args.model,
        )

        try:
            result = generate_story_pack(request, max_tokens=args.max_tokens,
                                         run_qa=not args.no_qa)
            unverified = sum(1 for r in (result["fact_check_results"] or [])
                             if not r.get("verified"))
            print(f"  pack id={result['id']}  "
                  f"tokens={result['input_tokens']}in/{result['output_tokens']}out  "
                  f"unverified_claims={unverified}")
            ok.append(label)
        except Exception as e:
            print(f"  ERROR: {e}")
            failed.append(f"{label}: {e}")

        if i < len(to_run):
            time.sleep(1)  # avoid hammering the API back-to-back

    print(f"\n--- Done ---")
    print(f"  Generated: {len(ok)}")
    print(f"  Failed:    {len(failed)}")

    if failed:
        print("\nFailed units:")
        for f in failed:
            print(f"  {f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
