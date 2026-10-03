#!/usr/bin/env python3
"""
Gap Fill: Booklet Occurrence Mining

Walks through units in curriculum order. For each unit, loads the concepts
introduced (on a vocab list) at or before that unit in curriculum order
(year, then term), and searches the unit's cleaned booklet text for any of
each concept's approved forms (authored spellings and reviewed inflections)
where the concept isn't already recorded in that unit.

New occurrences are inserted with:
  - is_introduction = 0  (a recurrence, not an introduction)
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
# Page text cleaning
# ---------------------------------------------------------------------------
# Booklet text includes picture credits, URLs and pronunciation guides, which
# produce false matches ("imperial" in "Imperial War Museums", "pub" in
# "(re-pub-lick)"). Credit lines are dropped whole; URLs and pronunciation
# guides are removed from the remaining lines. Reviewed 2026-10-02/03, see
# docs/20261002_recurrence_gap_fill_session.md.

CREDIT_LINE_RE = re.compile(
    r'CC[ -]BY|creative commons|wikimedia|commons\.|own work|public domain|curid'
    r'|©|unsplash|flickr|pixabay|shutterstock|alamy|getty|picture credit'
    r'|photo(?:graph)? by|image by|courtesy of|\.(?:jpe?g|png)\b|indebted to',
    re.IGNORECASE,
)
URL_RE = re.compile(r'(?:https?://|www\.)\S+|\S+\.(?:com|co\.uk|org|net|de|br|html?)(?:/\S*)?', re.IGNORECASE)
PRONUNCIATION_RE = re.compile(r"\((?=[^)]*-)[a-z’'\- ]+\)")


def clean_page_text(text: str) -> str:
    """Remove credit lines, URLs and pronunciation guides from booklet page text."""
    kept = [line for line in text.splitlines() if not CREDIT_LINE_RE.search(line)]
    return PRONUNCIATION_RE.sub(' ', URL_RE.sub(' ', '\n'.join(kept)))


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
    # straight and curly apostrophes are interchangeable: lists write Qur'an, booklets Qur’an
    escaped = re.sub(r"\\?['’]", "['’]", re.escape(term))
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


TERM_ORDER = ['Autumn1', 'Autumn2', 'Spring1', 'Spring2', 'Summer1', 'Summer2']


def curriculum_pos(year: int, term: str) -> int:
    """Position in curriculum order (year, then term); same scale as v_occurrences.curriculum_pos."""
    return year * 10 + TERM_ORDER.index(term) + 1


def load_concepts_introduced_by(conn, pos: int) -> list[dict]:
    """
    Concepts whose first vocab-list introduction is at or before curriculum position `pos`,
    with every approved form they are matched by (authored spellings and reviewed inflections).

    Recurrences are only counted from the point of introduction onward, in curriculum
    order (year, then term), so a Summer 1 term is not searched for in a Spring unit
    of the same year.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.concept_id, c.term,
                   array_remove(array_agg(DISTINCT f.form), NULL) AS forms
            FROM concepts c
            JOIN (SELECT concept_id, min(curriculum_pos) AS first_pos
                  FROM v_occurrences WHERE is_introduction GROUP BY concept_id) fi
              ON fi.concept_id = c.concept_id
            LEFT JOIN concept_forms f
              ON f.concept_id = c.concept_id AND f.status = 'approved'
            WHERE c.merged_into IS NULL AND fi.first_pos <= %s
            GROUP BY c.concept_id, c.term
            ORDER BY c.term
        """, (pos,))
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r['forms'] = sorted({r['term'], *r['forms']}, key=len, reverse=True)
    return rows


def load_existing_pairs(conn) -> set[tuple[int, int]]:
    """All (concept_id, unit_id) pairs that already have an occurrence."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT concept_id, unit_id FROM occurrences")
        return {(r['concept_id'], r['unit_id']) for r in cur.fetchall()}


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
    return {k: {**v, 'text': clean_page_text(v.get('text') or '')}
            for k, v in row['pages'].items()}


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

    existing = load_existing_pairs(conn)
    concept_cache: dict[int, list[dict]] = {}

    for unit in units:
        unit_year = unit['year']
        unit_id = unit['unit_id']

        # Concepts introduced at or before this unit in curriculum order (cached per position)
        pos = curriculum_pos(unit_year, unit['term'])
        if pos not in concept_cache:
            concept_cache[pos] = load_concepts_introduced_by(conn, pos)
        concepts = concept_cache[pos]

        # Load booklet pages
        pages = load_booklet_pages(conn, unit_id)
        if not pages:
            print(f"  [{unit['subject']} Y{unit_year} {unit['term']}] {unit['unit']} — no booklet content, skipping")
            continue

        # Concatenate all page text for a quick pre-filter
        all_text = ' '.join(p.get('text', '') for p in pages.values()).lower().replace('’', "'")

        new_for_unit = 0
        already_for_unit = 0

        for concept in concepts:
            concept_id = concept['concept_id']
            term = concept['term']

            # Skip junk concepts with no letters (e.g. '–'), which match every dash
            if not re.search(r'[A-Za-z]', term):
                continue

            # Quick pre-filter: skip if no form appears anywhere in booklet text
            forms = [f for f in concept['forms'] if f.lower().replace('’', "'") in all_text]
            if not forms:
                continue

            # Check if this unit already has an occurrence for this concept
            if (concept_id, unit_id) in existing:
                already_for_unit += 1
                continue

            # Find matches for every form, with page/chapter context; keep the earliest page
            matches = [m for f in forms for m in find_term_in_pages(f, pages)]
            if not matches:
                continue

            # Insert only the first match per unit (avoid duplicate rows for same unit)
            match = min(matches, key=lambda m: m['page'])

            inserted = insert_occurrence(conn, concept_id, unit, match, dry_run)
            if inserted:
                existing.add((concept_id, unit_id))
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
