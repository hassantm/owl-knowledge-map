import json
import time
import argparse
import anthropic
from db import get_connection, get_pending_concepts, write_generated, get_enrichment_summary
from prompts import build_enrichment_prompt
from constants import REQUIRED_FIELDS, VALID_REGISTERS, VALID_TIERS

client = anthropic.Anthropic()


def validate_enrichment(data: dict) -> tuple[bool, str]:
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return False, f"Missing fields: {missing}"
    if data['register'] not in VALID_REGISTERS:
        return False, f"Invalid register: '{data['register']}'"
    if data['tier'] not in VALID_TIERS:
        return False, f"Invalid tier: {data['tier']}"
    if not isinstance(data['word_family'], list):
        return False, "word_family must be a list"
    return True, ""


def _strip_markdown_fences(text: str) -> str:
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text


def enrich_concept(concept: dict) -> dict | None:
    prompt = build_enrichment_prompt(
        concept['term'],
        list(concept['subjects']),
        list(concept['years'])
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = _strip_markdown_fences(response.content[0].text.strip())
        data = json.loads(raw)
        valid, reason = validate_enrichment(data)
        if not valid:
            print(f"  x Validation failed for '{concept['term']}': {reason}")
            return None
        return data

    except json.JSONDecodeError as e:
        print(f"  x JSON parse failed for '{concept['term']}': {e}")
        return None
    except Exception as e:
        print(f"  x API error for '{concept['term']}': {e}")
        return None


def run_batch(batch_size: int = 50, delay: float = 0.5, dry_run: bool = False):
    conn = get_connection()

    summary = get_enrichment_summary(conn)
    print("\nCurrent enrichment status:")
    for status, count in summary.items():
        print(f"  {status}: {count}")
    print()

    concepts = get_pending_concepts(conn, limit=batch_size)

    if not concepts:
        print("No concepts pending enrichment.")
        conn.close()
        return

    print(f"Processing {len(concepts)} pending concepts\n")

    success, failed = 0, 0

    for i, concept in enumerate(concepts, 1):
        print(f"[{i}/{len(concepts)}] '{concept['term']}'...", end=" ", flush=True)
        enrichment = enrich_concept(concept)
        if enrichment:
            if not dry_run:
                write_generated(conn, concept['id'], enrichment)
            print("ok")
            success += 1
        else:
            failed += 1
        time.sleep(delay)

    print(f"\nDone: {success} enriched, {failed} failed")
    if failed > 0:
        print(f"Re-run to retry {failed} failed concepts (they remain 'pending')")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch enrich vocabulary concepts")
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--delay',      type=float, default=0.5,
                        help="Seconds between API calls")
    parser.add_argument('--dry-run',    action='store_true',
                        help="Run without writing to DB")
    args = parser.parse_args()
    run_batch(batch_size=args.batch_size, delay=args.delay, dry_run=args.dry_run)
