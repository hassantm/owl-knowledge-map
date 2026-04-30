#!/usr/bin/env python3
"""
Gap Fill: Booklet Occurrence Mining

Walks through units in year order (Y3 → Y6), subject by subject.
For each unit, loads the concepts that already have at least one
occurrence anywhere in the corpus (i.e. known, validated vocab),
then searches the unit's booklet_content text for any concept
that isn't already recorded as occurring in that unit.

New occurrences are inserted with:
  - is_introduction = 0  (not a bold introduction, just a usage)
  - vocab_source = 'booklet_gap_fill'
  - chapter derived from the page heading pattern (^N. Title)

Run:
    cd ~/dev/owl-knowledge-map
    python src/gap_fill_occurrences.py
    python src/gap_fill_occurrences.py --dry-run
    python src/gap_fill_occurrences.py --year 3 --subject History
    python src/gap_fill_occurrences.py --unit "Ancient Greece"
"""

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from db import get_connection  # noqa: E402


# ---------------------------------------------------------------------------
# Chapter detection
# ---------------------------------------------------------------------------

CHAPTER_RE = re.compile(r'^\d+\.\s+.+')


def detect_chapter_from_page(page_text: str) -> str | None:
    """
    Return the first chapter heading found in a page's text, or None.
    Chapter headings look like: "1. Howard Carter gets a big surprise"
    """
    for line in page_text.splitlines():
        line = line.strip()
        if CHAPTER_RE.match(line):
            # Normalise: collapse vertical-tab characters used in source
            return line.replace('\x0b', ' ').strip()
    return None


# ---------------------------------------------------------------------------
# Text matching
# ---------------------------------------------------------------------------

def build_pattern(term: str) -> re.Pattern:
    """
    Build a word-boundary regex for a term.
    Case-insensitive. Handles multi-word terms naturally.
    """
    escaped = re.escape(term)
    return re.compile(r'(?<![a-zA-Z])' + escaped + r'(?![a-zA-Z])', re.IGNORECASE)


def find_term_in_pages(term: str, pages: dict) -> list[dict]:
    """
    Search all pages for a term. Returns list of matches:
        [{'page': int, 'chapter': str|None, 'context': str}, ...]

    'chapter' is carried forward from the most recent chapter heading seen.
    """
    pattern = build_pattern(term)
    current_chapter = None
    matches = []

    for page_num in sorted(pages.keys(), key=lambda x: int(x)):
        page_text = pages[page_num].get('text', '')

        # Update current chapter if this page starts a new one
        chapter_on_page = detect_chapter_from_page(page_text)
        if chapter_on_page:
            current_chapter = chapter_on_page

        if pattern.search(page_text):
            # Get a short context snippet around the match
            m = pattern.search(page_text)
            start = max(0, m.start() - 60)
            end = min(len(page_text), m.end() + 60)
            snippet = page_text[start:end].replace('\n', ' ').replace('\x0b', ' ').strip()

            matches.append({
                'page': int(page_num),
                'chapter': current_chapter,
                'context': snippet,
            })

    return matches


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def load_units(conn, year: int | None, subject: str | None, unit_filter: str | None) -> list[dict]:
    """Load units in year/subject/term order, optionally filtered."""
    query = """
        SELECT unit_id, year, subject, term, unit
        FROM units
        WHERE booklet_content IS NOT NULL
    """
    params = []

    if year is not None:
        query += " AND year = %s"
        params.append(year)
    if subject is not None:
        query += " AND subject = %s"
        params.append(subject)
    if unit_filter is not None:
        query += " AND unit ILIKE %s"
        params.append(f'%{unit_filter}%')

    query += " ORDER BY year, subject, term, unit"

    with conn.cursor() as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]


def load_concepts_introduced_by_year(conn, year: int) -> list[dict]:
    """
    Load all concepts whose FIRST occurrence is in a year <= `year`.

    A concept is 'introduced' in the earliest year any of its occurrences
    appears. This means:
      - Y3 concepts are searched in Y3, Y4, Y5, Y6 booklets  ✓
      - Y5 concepts are NOT searched in Y3 or Y4 booklets    ✓
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.concept_id, c.term
            FROM concepts c
            JOIN (
                SELECT concept_id, MIN(u.year) AS first_year
                FROM occurrences o
                JOIN units u ON u.unit_id = o.unit_id
                GROUP BY concept_id
            ) first ON first.concept_id = c.concept_id
            WHERE first.first_year <= %s
            ORDER BY c.term
        """, (year,))
        return [dict(r) for r in cur.fetchall()]


def load_existing_occurrence_unit_ids(conn, concept_id: int) -> set[int]:
    """Return the set of unit_ids where this concept already has an occurrence."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT unit_id FROM occurrences WHERE concept_id = %s",
            (concept_id,)
        )
        return {r['unit_id'] for r in cur.fetchall()}


def load_booklet_pages(conn, unit_id: int) -> dict:
    """Return the pages dict from booklet_content for a unit."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT booklet_content->'pages' AS pages FROM units WHERE unit_id = %s",
            (unit_id,)
        )
        row = cur.fetchone()
    if not row or not row['pages']:
        return {}
    return row['pages']


def insert_occurrence(conn, concept_id: int, unit: dict, match: dict, dry_run: bool) -> bool:
    """
    Insert a gap-fill occurrence. Returns True if inserted (or would be in dry-run).
    """
    if dry_run:
        return True

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO occurrences (
                concept_id, unit_id, subject, year, term, unit,
                chapter, slide_number, is_introduction,
                term_in_context, vocab_source, needs_review
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT DO NOTHING
        """, (
            concept_id,
            unit['unit_id'],
            unit['subject'],
            unit['year'],
            unit['term'],
            unit['unit'],
            match['chapter'],
            match['page'],     # slide_number used as page number
            0,                 # is_introduction: not a bold intro, just a usage
            match['context'],
            'booklet_gap_fill',
            0,
        ))
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(year: int | None, subject: str | None, unit_filter: str | None, dry_run: bool):
    conn = get_connection()

    units = load_units(conn, year, subject, unit_filter)
    if not units:
        print("No units found matching filters.")
        return

    print(f"{'[DRY RUN] ' if dry_run else ''}Processing {len(units)} unit(s)\n")

    total_new = 0
    total_skipped = 0

    # Cache concepts per year to avoid re-querying on each unit
    concept_cache: dict[int, list[dict]] = {}

    for unit in units:
        unit_year = unit['year']
        unit_id = unit['unit_id']

        # Load concepts valid for this year (cached)
        if unit_year not in concept_cache:
            concept_cache[unit_year] = load_concepts_introduced_by_year(conn, unit_year)
        concepts = concept_cache[unit_year]

        # Load booklet pages
        pages = load_booklet_pages(conn, unit_id)
        if not pages:
            print(f"  [{unit['subject']} Y{unit_year} {unit['term']}] {unit['unit']} — no booklet content, skipping")
            continue

        # Concatenate all page text for a quick pre-filter
        all_text = ' '.join(p.get('text', '') for p in pages.values()).lower()

        new_for_unit = 0
        already_for_unit = 0

        for concept in concepts:
            concept_id = concept['concept_id']
            term = concept['term']

            # Quick pre-filter: skip if term not anywhere in booklet text
            if term.lower() not in all_text:
                continue

            # Check if this unit already has an occurrence for this concept
            existing_units = load_existing_occurrence_unit_ids(conn, concept_id)
            if unit_id in existing_units:
                already_for_unit += 1
                continue

            # Find actual matches with page/chapter context
            matches = find_term_in_pages(term, pages)
            if not matches:
                continue

            # Insert only the first match per unit (avoid duplicate rows for same unit)
            match = matches[0]

            inserted = insert_occurrence(conn, concept_id, unit, match, dry_run)
            if inserted:
                new_for_unit += 1
                if dry_run:
                    print(f"    [NEW] '{term}' — page {match['page']}, chapter: {match['chapter']}")
                    print(f"          context: ...{match['context']}...")

        total_new += new_for_unit
        total_skipped += already_for_unit

        print(f"  Y{unit_year} {unit['subject']} {unit['term']} | {unit['unit']}: "
              f"+{new_for_unit} new, {already_for_unit} already present")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Done. "
          f"New occurrences: {total_new} | Already present: {total_skipped}")

    conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Gap-fill occurrences from booklet text for known concepts"
    )
    parser.add_argument('--year',     type=int, help='Filter to a specific year (3-6)')
    parser.add_argument('--subject',  help='Filter to a subject (History, Geography, Religion)')
    parser.add_argument('--unit',     help='Filter to units containing this string')
    parser.add_argument('--dry-run',  action='store_true',
                        help='Report what would be inserted without writing to DB')
    args = parser.parse_args()

    run(
        year=args.year,
        subject=args.subject,
        unit_filter=args.unit,
        dry_run=args.dry_run,
    )


if __name__ == '__main__':
    sys.exit(main())
