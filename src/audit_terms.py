#!/usr/bin/env python3
"""
Term Audit Script

Compares extracted terms in the database against authoritative vocab lists
to identify:
  1. Missed terms  — in vocab list but not extracted from booklet
  2. Potential noise — extracted but not in vocab list (needs human review)
  3. High priority review — not in vocab AND flagged by Stage 1 filters

Produces a single output/term_audit.csv for human review.

Created: 2026-02-24
"""

import csv
import sqlite3
from pathlib import Path

from vocab_validator import find_vocab_list, parse_vocab_docx, match_term


# =============================================================================
# DATABASE QUERIES
# =============================================================================

def get_all_units(db_path: Path) -> list[dict]:
    """
    Return distinct units with their source_path for vocab list discovery.

    Created: 2026-02-24
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT subject, year, term, unit, source_path
        FROM occurrences
        ORDER BY subject, year, term, unit
    """)
    units = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return units


def get_unit_terms(db_path: Path, subject: str, year: int, term: str, unit: str) -> list[dict]:
    """
    Return all extracted occurrences for a specific unit, with concept text.

    NOTE: occurrences.term = curriculum term period (Autumn1 etc.).
    The concept text is in concepts.term — must JOIN to get it.

    Created: 2026-02-24
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT o.occurrence_id, c.term AS concept_term,
               o.slide_number, o.chapter,
               o.term_in_context, o.needs_review, o.review_reason,
               o.validation_status, o.vocab_confidence,
               o.vocab_match_type, o.vocab_source
        FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE o.subject = ? AND o.year = ? AND o.term = ? AND o.unit = ?
        ORDER BY o.slide_number
    """, (subject, year, term, unit))

    terms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return terms


# =============================================================================
# AUDIT LOGIC
# =============================================================================

def audit_unit(unit_meta: dict, db_path: Path) -> dict:
    """
    Audit a single unit: compare DB terms against vocab list.

    Returns dict with:
    - missed: list of terms in vocab but not in DB
    - noise: list of DB term dicts flagged as potential_noise
    - high_priority: list of DB term dicts flagged as high_priority_review
    - no_vocab: bool — no vocab list available for this unit
    - vocab_path: str or None

    Created: 2026-02-24
    """
    source_path = unit_meta['source_path']
    subject = unit_meta['subject']
    year = unit_meta['year']
    term = unit_meta['term']
    unit = unit_meta['unit']

    db_terms = get_unit_terms(db_path, subject, year, term, unit)

    noise = [t for t in db_terms if t['validation_status'] == 'potential_noise']
    high_priority = [t for t in db_terms if t['validation_status'] == 'high_priority_review']


    vocab_path = find_vocab_list(source_path)

    if not vocab_path:
        return {
            'missed': [],
            'noise': noise,
            'high_priority': high_priority,
            'no_vocab': True,
            'vocab_path': None,
            'vocab_total': 0
        }

    vocab_data = parse_vocab_docx(vocab_path)
    vocab_terms = vocab_data['all_terms']
    extracted_terms = [t['concept_term'] for t in db_terms]

    # Find vocab terms not matched by any extracted term
    missed = []
    for vocab_term in vocab_terms:
        result = match_term(vocab_term, extracted_terms)
        if not result['matched']:
            # Find which chapter this term is in
            chapter = None
            for ch_num, ch_terms in vocab_data['chapters'].items():
                if vocab_term in ch_terms:
                    chapter = ch_num
                    break
            missed.append({
                'term': vocab_term,
                'vocab_chapter': chapter
            })

    return {
        'missed': missed,
        'noise': noise,
        'high_priority': high_priority,
        'no_vocab': False,
        'vocab_path': vocab_path,
        'vocab_total': vocab_data['metadata']['total_terms']
    }


# =============================================================================
# REPORTING
# =============================================================================

def run_audit(db_path: Path, output_path: Path) -> dict:
    """
    Run full term audit across all units and write CSV report.

    CSV columns:
    issue_type, subject, year, term_period, unit, chapter, term,
    slide, context, review_reason, vocab_source, notes

    issue_type values:
    - missed_from_extraction : in vocab, not in DB
    - potential_noise        : in DB, not in vocab, not flagged by Stage 1
    - high_priority_review   : in DB, not in vocab, flagged by Stage 1

    Created: 2026-02-24

    Returns:
        Summary stats dict
    """
    units = get_all_units(db_path)
    print(f"Auditing {len(units)} units...\n")

    totals = {
        'units_audited': 0,
        'units_no_vocab': 0,
        'total_missed': 0,
        'total_noise': 0,
        'total_high_priority': 0
    }

    rows = []

    for unit_meta in units:
        label = f"{unit_meta['subject']} Y{unit_meta['year']} {unit_meta['term']} — {unit_meta['unit']}"
        result = audit_unit(unit_meta, db_path)
        totals['units_audited'] += 1

        if result['no_vocab']:
            totals['units_no_vocab'] += 1
            print(f"  NO VOCAB  {label}")
            continue

        missed_count = len(result['missed'])
        noise_count = len(result['noise'])
        hp_count = len(result['high_priority'])
        totals['total_missed'] += missed_count
        totals['total_noise'] += noise_count
        totals['total_high_priority'] += hp_count

        vocab_name = Path(result['vocab_path']).name

        print(f"  {label}")
        print(f"    Vocab: {vocab_name} ({result['vocab_total']} terms) | "
              f"Missed: {missed_count} | Noise: {noise_count} | High priority: {hp_count}")

        # Missed terms rows
        for missed in result['missed']:
            rows.append({
                'issue_type': 'missed_from_extraction',
                'subject': unit_meta['subject'],
                'year': unit_meta['year'],
                'term_period': unit_meta['term'],
                'unit': unit_meta['unit'],
                'chapter': missed['vocab_chapter'] or '',
                'term': missed['term'],
                'slide': '',
                'context': '',
                'review_reason': '',
                'vocab_source': vocab_name,
                'notes': 'In vocab list but not found in booklet extraction'
            })

        # Potential noise rows
        for t in result['noise']:
            rows.append({
                'issue_type': 'potential_noise',
                'subject': unit_meta['subject'],
                'year': unit_meta['year'],
                'term_period': unit_meta['term'],
                'unit': unit_meta['unit'],
                'chapter': t['chapter'] or '',
                'term': t['concept_term'],
                'slide': t['slide_number'] or '',
                'context': t['term_in_context'] or '',
                'review_reason': t['review_reason'] or '',
                'vocab_source': vocab_name,
                'notes': 'Extracted but not in vocab list'
            })

        # High priority rows
        for t in result['high_priority']:
            rows.append({
                'issue_type': 'high_priority_review',
                'subject': unit_meta['subject'],
                'year': unit_meta['year'],
                'term_period': unit_meta['term'],
                'unit': unit_meta['unit'],
                'chapter': t['chapter'] or '',
                'term': t['concept_term'],
                'slide': t['slide_number'] or '',
                'context': t['term_in_context'] or '',
                'review_reason': t['review_reason'] or '',
                'vocab_source': vocab_name,
                'notes': 'Extracted, not in vocab, AND flagged by filters'
            })

    # Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'issue_type', 'subject', 'year', 'term_period', 'unit',
        'chapter', 'term', 'slide', 'context', 'review_reason',
        'vocab_source', 'notes'
    ]
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return totals


def print_summary(totals: dict, output_path: Path):
    """Print audit summary to console."""
    print()
    print("=" * 60)
    print("=== TERM AUDIT SUMMARY ===")
    print("=" * 60)
    print(f"Units audited:          {totals['units_audited']}")
    print(f"Units without vocab:    {totals['units_no_vocab']}")
    print()
    print(f"Missed from extraction: {totals['total_missed']}")
    print(f"  (in vocab list but not in database — investigate)")
    print()
    print(f"Potential noise:        {totals['total_noise']}")
    print(f"  (extracted, not in vocab, not flagged — review)")
    print()
    print(f"High priority review:   {totals['total_high_priority']}")
    print(f"  (extracted, not in vocab, AND flagged — review first)")
    print()
    total_issues = totals['total_missed'] + totals['total_noise'] + totals['total_high_priority']
    print(f"Total issues to review: {total_issues}")
    print()
    print(f"Report written to: {output_path}")
    print("=" * 60)


# =============================================================================
# MAIN
# =============================================================================

def main():
    project_root = Path(__file__).parent.parent
    db_path = project_root / "db" / "owl_knowledge_map.db"
    output_path = project_root / "output" / "term_audit.csv"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print("Starting term audit...")
    print()

    totals = run_audit(db_path, output_path)
    print_summary(totals, output_path)
    return 0


if __name__ == "__main__":
    exit(main())
