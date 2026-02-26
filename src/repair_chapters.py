#!/usr/bin/env python3
"""
Chapter Repair Script

Two-pass cleanup of the occurrences.chapter field:

  Pass 1 — Strip dirty chapter strings
      Table-of-contents slides produced chapter strings with trailing
      tab characters and "Page N" references (e.g. "6. Volcanoes\t\tPage 18").
      Strip these to produce clean titles.

  Pass 2 — Fix chapter number mismatches
      For each unit, compare DB chapter numbers against the authoritative
      vocab list chapter. Where they differ, look up the correct full chapter
      title from non-conflicted occurrences in the same unit and update.
      Falls back to the bare chapter number if no reliable title is available.

Usage:
    python src/repair_chapters.py [--dry-run]

Created: 2026-02-26
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vocab_validator import find_vocab_list, parse_vocab_docx
from vocab_validator import _normalise  # noqa: PLC2701


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_all_units(cursor: sqlite3.Cursor) -> list[dict]:
    """Return distinct units with source_path. Created: 2026-02-26"""
    cursor.execute("""
        SELECT DISTINCT subject, year, term, unit, source_path
        FROM occurrences ORDER BY subject, year, term, unit
    """)
    return [
        {'subject': r[0], 'year': r[1], 'term': r[2],
         'unit': r[3], 'source_path': r[4]}
        for r in cursor.fetchall()
    ]


def get_unit_occurrences(cursor: sqlite3.Cursor, subject, year, term, unit) -> list[dict]:
    """Return all occurrences + concept terms for a unit. Created: 2026-02-26"""
    cursor.execute("""
        SELECT o.occurrence_id, c.term AS concept_term, o.chapter
        FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE o.subject=? AND o.year=? AND o.term=? AND o.unit=?
    """, (subject, year, term, unit))
    return [
        {'occurrence_id': r[0], 'concept_term': r[1], 'chapter': r[2]}
        for r in cursor.fetchall()
    ]


# =============================================================================
# PASS 1 — CLEAN DIRTY CHAPTER STRINGS
# =============================================================================

_PAGE_RE = re.compile(r'[\t ]+Page\s+\d+\s*$', re.IGNORECASE)


def clean_chapter_string(chapter: str | None) -> str | None:
    """
    Strip trailing tabs and 'Page N' from a chapter string.

    '6. Volcanoes\t\tPage 18' → '6. Volcanoes'

    Returns the cleaned string, or None if input is None/empty.

    Created: 2026-02-26
    """
    if not chapter:
        return chapter
    cleaned = _PAGE_RE.sub('', chapter).rstrip()
    return cleaned if cleaned else chapter


def pass1_clean_dirty_chapters(
    cursor: sqlite3.Cursor,
    dry_run: bool
) -> int:
    """
    Find and clean all chapter strings containing 'Page N'.

    Returns count of rows updated.

    Created: 2026-02-26
    """
    cursor.execute("""
        SELECT occurrence_id, chapter FROM occurrences
        WHERE chapter LIKE '%Page%'
    """)
    rows = cursor.fetchall()
    updated = 0

    for occ_id, chapter in rows:
        cleaned = clean_chapter_string(chapter)
        if cleaned != chapter:
            updated += 1
            if not dry_run:
                cursor.execute(
                    "UPDATE occurrences SET chapter=? WHERE occurrence_id=?",
                    (cleaned, occ_id)
                )

    return updated


# =============================================================================
# PASS 2 — FIX CHAPTER NUMBER MISMATCHES
# =============================================================================

def chapter_number_from_string(chapter_str: str | None) -> str | None:
    """
    Extract leading chapter number from a chapter string.

    '1. The Roman Empire' → '1'
    'Chapter 2'           → '2'
    '3'                   → '3'
    None/''               → None

    Created: 2026-02-26
    """
    if not chapter_str:
        return None
    m = re.match(r'^(?:Chapter\s+)?(\d+)', chapter_str.strip(), re.IGNORECASE)
    return m.group(1) if m else None


def build_term_chapter_map(vocab_data: dict) -> dict[str, str]:
    """
    Build lowercased-term → chapter_number map from parsed vocab data.

    Created: 2026-02-26
    """
    mapping = {}
    for ch_num, ch_terms in vocab_data['chapters'].items():
        for t in ch_terms:
            mapping[t.lower()] = ch_num
    return mapping


def lookup_vocab_chapter(term: str, term_chapter_map: dict[str, str]) -> str | None:
    """
    Look up vocab chapter for a term — exact then normalised match.

    Created: 2026-02-26
    """
    if term.lower() in term_chapter_map:
        return term_chapter_map[term.lower()]
    norm = _normalise(term)
    for vt, ch in term_chapter_map.items():
        if _normalise(vt) == norm:
            return ch
    return None


def build_reliable_chapter_title_map(
    occurrences: list[dict],
    term_chapter_map: dict[str, str]
) -> dict[str, str]:
    """
    Build chapter_number → full_chapter_title from non-conflicted occurrences.

    A non-conflicted occurrence is one where its DB chapter number matches its
    vocab chapter number. These are reliable — use their full chapter title
    to look up titles for conflicted occurrences.

    Created: 2026-02-26
    """
    title_map: dict[str, str] = {}

    for occ in occurrences:
        if not occ['chapter']:
            continue
        db_num = chapter_number_from_string(occ['chapter'])
        if not db_num:
            continue
        vocab_num = lookup_vocab_chapter(occ['concept_term'], term_chapter_map)
        if not vocab_num:
            continue
        # Non-conflicted: DB chapter number == vocab chapter number
        if db_num == vocab_num and vocab_num not in title_map:
            # Use this occurrence's chapter string as the reliable title
            # Only accept strings that actually start with 'N.' (not bare numbers)
            if re.match(r'^\d+\.', occ['chapter'].strip()):
                title_map[vocab_num] = occ['chapter']

    return title_map


def pass2_fix_chapter_mismatches(
    cursor: sqlite3.Cursor,
    dry_run: bool
) -> dict:
    """
    For each unit: compare DB chapter numbers against vocab list chapters.

    Where they differ, look up the correct full chapter title from
    non-conflicted occurrences in the same unit and update.

    Falls back to the bare chapter number if no reliable title is available.

    Returns dict: fixed, no_vocab, fallback_to_number.

    Created: 2026-02-26
    """
    units = get_all_units(cursor)
    counts = {'fixed': 0, 'no_vocab': 0, 'fallback_to_number': 0}

    for unit_meta in units:
        source_path = unit_meta['source_path']
        if not source_path:
            counts['no_vocab'] += 1
            continue

        vocab_path = find_vocab_list(source_path)
        if not vocab_path:
            counts['no_vocab'] += 1
            continue

        try:
            vocab_data = parse_vocab_docx(vocab_path)
        except Exception as e:
            print(f"  [WARN] Vocab parse error for {unit_meta['unit']}: {e}")
            counts['no_vocab'] += 1
            continue

        term_chapter_map = build_term_chapter_map(vocab_data)

        # Read occurrences after Pass 1 (chapters already cleaned)
        occurrences = get_unit_occurrences(
            cursor,
            unit_meta['subject'], unit_meta['year'],
            unit_meta['term'], unit_meta['unit']
        )

        # Build reliable title map from non-conflicted occurrences
        title_map = build_reliable_chapter_title_map(occurrences, term_chapter_map)

        # Find and fix conflicted occurrences
        for occ in occurrences:
            vocab_chapter = lookup_vocab_chapter(occ['concept_term'], term_chapter_map)
            if not vocab_chapter:
                continue  # Term not in vocab list; skip

            # Chapter '0' is the vocab list's pre-chapter catch-all (terms listed
            # before the first "Chapter N" heading). The PPTX assigns these to
            # chapter 1 (first heading found), which is more informative than '0'.
            # Leave these alone.
            if vocab_chapter == '0':
                continue

            db_chapter_num = chapter_number_from_string(occ['chapter'])

            # Only act where there's a mismatch (or NULL chapter)
            if occ['chapter'] and db_chapter_num == vocab_chapter:
                continue  # Already correct

            # Determine the correct chapter title
            correct_title = title_map.get(vocab_chapter)

            if not correct_title:
                # No reliable title found — fall back to bare chapter number
                correct_title = str(vocab_chapter)
                counts['fallback_to_number'] += 1
                print(
                    f"  [FALLBACK] '{occ['concept_term']}' in "
                    f"{unit_meta['subject']} Y{unit_meta['year']} "
                    f"{unit_meta['term']} | "
                    f"chapter '{vocab_chapter}' — no title found, using bare number"
                )

            counts['fixed'] += 1
            if not dry_run:
                cursor.execute(
                    "UPDATE occurrences SET chapter=? WHERE occurrence_id=?",
                    (correct_title, occ['occurrence_id'])
                )

    return counts


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Two-pass repair of chapter field in occurrences.'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print counts only; do not modify the database.'
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    db_path = project_root / "db" / "owl_knowledge_map.db"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    if args.dry_run:
        print("DRY RUN — no changes will be made.")
        print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ------------------------------------------------------------------
    # Pass 1
    # ------------------------------------------------------------------
    print("Pass 1: Stripping dirty chapter strings (Page N / tabs)...")
    cleaned = pass1_clean_dirty_chapters(cursor, args.dry_run)
    action = "Would clean" if args.dry_run else "Cleaned"
    print(f"  {action} {cleaned} chapter strings")
    print()

    # ------------------------------------------------------------------
    # Pass 2
    # ------------------------------------------------------------------
    print("Pass 2: Fixing chapter number mismatches via vocab list...")
    p2 = pass2_fix_chapter_mismatches(cursor, args.dry_run)
    action = "Would fix" if args.dry_run else "Fixed"
    print(f"  {action} {p2['fixed']} chapter mismatches")
    if p2['fallback_to_number']:
        print(f"  Fell back to bare chapter number: {p2['fallback_to_number']}")
    if p2['no_vocab']:
        print(f"  Units without vocab list: {p2['no_vocab']}")
    print()

    # ------------------------------------------------------------------
    # Commit or rollback
    # ------------------------------------------------------------------
    if args.dry_run:
        conn.rollback()
        print("DRY RUN complete — no changes made.")
    else:
        conn.commit()
        print("All changes committed.")

    conn.close()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print("CHAPTER REPAIR SUMMARY")
    print("=" * 60)
    print(f"Dirty strings cleaned (Pass 1):   {cleaned}")
    print(f"Chapter mismatches fixed (Pass 2): {p2['fixed']}")
    print(f"  of which fell back to number:    {p2['fallback_to_number']}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
