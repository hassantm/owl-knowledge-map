#!/usr/bin/env python3
"""
Extract bold terms from a booklet PPTX and write concepts + occurrences
directly to Postgres.

Usage:
    python src/extract_unit_to_postgres.py \
        --unit-id 61 \
        --booklet /path/to/booklet.pptx \
        --subject Religion --year 6 --term Autumn1 --unit "The teaching of the gurus"

    python src/extract_unit_to_postgres.py --unit-id 61 --booklet ... --dry-run
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from db import get_connection          # noqa: E402
from extract_stage1 import extract_bold_runs  # noqa: E402


def extract_and_insert(unit_id: int, booklet_path: str,
                       subject: str, year: int, term: str, unit_name: str,
                       dry_run: bool = False):

    pptx_path = Path(booklet_path)
    if not pptx_path.exists():
        print(f"ERROR: file not found: {pptx_path}")
        sys.exit(1)

    print(f"Extracting bold terms from: {pptx_path.name}")
    result = extract_bold_runs(str(pptx_path))

    if result['errors']:
        for e in result['errors']:
            print(f"  WARNING: {e}")

    terms = result['terms']
    print(f"  Slides processed: {result['total_slides']}")
    print(f"  Bold terms extracted: {len(terms)}")

    if not terms:
        print("No terms found — check the PPTX is readable.")
        sys.exit(1)

    if dry_run:
        print(f"\n[dry-run] Would insert up to {len(terms)} occurrences for unit_id={unit_id}")
        for t in terms[:20]:
            print(f"  slide {t['slide']:3d}  {t['term']}")
        if len(terms) > 20:
            print(f"  ... and {len(terms) - 20} more")
        return

    conn = get_connection()
    inserted_concepts = 0
    inserted_occurrences = 0
    skipped = 0

    try:
        with conn:
            with conn.cursor() as cur:
                for entry in terms:
                    term_text = entry['term'].strip()
                    slide_num = entry.get('slide')
                    chapter   = entry.get('chapter')
                    context   = entry.get('context')

                    if not term_text:
                        skipped += 1
                        continue

                    # Get or create concept
                    cur.execute(
                        "SELECT concept_id FROM concepts WHERE LOWER(term) = LOWER(%s)",
                        (term_text,)
                    )
                    row = cur.fetchone()
                    if row:
                        concept_id = row['concept_id']
                    else:
                        cur.execute(
                            "INSERT INTO concepts (term) VALUES (%s) RETURNING concept_id",
                            (term_text,)
                        )
                        concept_id = cur.fetchone()['concept_id']
                        inserted_concepts += 1

                    # Skip if introduction occurrence already exists for this unit
                    cur.execute("""
                        SELECT occurrence_id FROM occurrences
                        WHERE concept_id = %s AND unit_id = %s AND is_introduction = 1
                    """, (concept_id, unit_id))
                    if cur.fetchone():
                        skipped += 1
                        continue

                    # Insert occurrence
                    cur.execute("""
                        INSERT INTO occurrences (
                            concept_id, subject, year, term, unit,
                            slide_number, chapter, term_in_context,
                            is_introduction, vocab_source, unit_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'bold_extraction', %s)
                    """, (
                        concept_id, subject, year, term, unit_name,
                        slide_num, chapter, context, unit_id
                    ))
                    inserted_occurrences += 1

        print(f"\nDone.")
        print(f"  New concepts inserted:    {inserted_concepts}")
        print(f"  New occurrences inserted: {inserted_occurrences}")
        print(f"  Skipped (dup/empty):      {skipped}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit-id',  type=int, required=True)
    parser.add_argument('--booklet',  required=True, help='Path to booklet PPTX')
    parser.add_argument('--subject',  required=True)
    parser.add_argument('--year',     type=int, required=True)
    parser.add_argument('--term',     required=True, help='e.g. Autumn1')
    parser.add_argument('--unit',     required=True, help='Unit name')
    parser.add_argument('--dry-run',  action='store_true')
    args = parser.parse_args()

    extract_and_insert(
        unit_id=args.unit_id,
        booklet_path=args.booklet,
        subject=args.subject,
        year=args.year,
        term=args.term,
        unit_name=args.unit,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    main()
