#!/usr/bin/env python3
"""
Apply Audit Decisions Script

Reads output/term_audit_enriched.csv (after reviewer fills in 'decision' column)
and applies changes to the database:

  delete — remove occurrence from DB; clean up orphan concepts afterwards
  keep   — mark occurrence as confirmed (validation_status = 'confirmed')
  add    — insert new occurrence for missed terms (requires appears_unbolded=True)
  skip   — no action (also used for blank decision)

Idempotent — safe to re-run. Checks existence before insert/delete.

Writes audit trail to output/audit_decisions_log.csv with timestamp, action,
term and unit for every row processed.

Created: 2026-02-24
"""

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def delete_occurrence(cursor: sqlite3.Cursor, occurrence_id: int) -> str:
    """
    Delete an occurrence by ID.

    Returns:
        'deleted'         — row was present and deleted
        'already_deleted' — row not found (idempotent)

    Created: 2026-02-24
    """
    cursor.execute(
        "SELECT occurrence_id FROM occurrences WHERE occurrence_id = ?",
        (occurrence_id,)
    )
    if not cursor.fetchone():
        return 'already_deleted'

    cursor.execute(
        "DELETE FROM occurrences WHERE occurrence_id = ?",
        (occurrence_id,)
    )
    return 'deleted'


def cleanup_orphan_concepts(cursor: sqlite3.Cursor) -> int:
    """
    Remove concepts with no remaining occurrences.

    Returns count of concepts deleted.

    Created: 2026-02-24
    """
    cursor.execute("""
        DELETE FROM concepts
        WHERE concept_id NOT IN (SELECT DISTINCT concept_id FROM occurrences)
    """)
    return cursor.rowcount


def confirm_occurrence(cursor: sqlite3.Cursor, occurrence_id: int) -> str:
    """
    Set validation_status = 'confirmed' on an occurrence.

    Returns:
        'confirmed' — update applied
        'not_found' — occurrence_id not in database

    Created: 2026-02-24
    """
    cursor.execute(
        "SELECT occurrence_id FROM occurrences WHERE occurrence_id = ?",
        (occurrence_id,)
    )
    if not cursor.fetchone():
        return 'not_found'

    cursor.execute(
        "UPDATE occurrences SET validation_status = 'confirmed' WHERE occurrence_id = ?",
        (occurrence_id,)
    )
    return 'confirmed'


def get_or_create_concept(cursor: sqlite3.Cursor, term: str) -> int:
    """
    Return concept_id for term; insert concept if not found.

    Created: 2026-02-24
    """
    cursor.execute("SELECT concept_id FROM concepts WHERE term = ?", (term,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("INSERT INTO concepts (term) VALUES (?)", (term,))
    return cursor.lastrowid


def add_occurrence(cursor: sqlite3.Cursor, row: dict) -> str:
    """
    Insert a new occurrence for a missed term.

    is_introduction = 0 because the term appeared unbolded — not a formal
    curriculum introduction, so it should not claim introductory status.

    Returns:
        'inserted'       — occurrence created
        'already_exists' — already in database (idempotent)

    Created: 2026-02-24
    """
    term = row['term']
    subject = row['subject']
    year = int(row['year'])
    term_period = row['term_period']
    unit = row['unit']
    chapter = row.get('chapter', '') or None
    source_path = row.get('_source_path', '') or None
    vocab_source = row.get('vocab_source', '') or None

    # Parse first slide from unbolded_slides (comma-separated)
    slide_number = None
    unbolded_slides = row.get('unbolded_slides', '').strip()
    if unbolded_slides:
        try:
            slide_number = int(unbolded_slides.split(',')[0].strip())
        except ValueError:
            pass

    term_in_context = row.get('unbolded_context', '') or None

    concept_id = get_or_create_concept(cursor, term)

    # Idempotent check — don't double-insert same location
    cursor.execute(
        """
        SELECT occurrence_id FROM occurrences
        WHERE concept_id=? AND subject=? AND year=? AND term=? AND unit=?
        AND (slide_number IS ? OR (slide_number IS NULL AND ? IS NULL))
        """,
        (concept_id, subject, year, term_period, unit, slide_number, slide_number)
    )
    if cursor.fetchone():
        return 'already_exists'

    cursor.execute(
        """
        INSERT INTO occurrences (
            concept_id, subject, year, term, unit, chapter,
            slide_number, is_introduction, term_in_context, source_path,
            needs_review, review_reason,
            validation_status, vocab_confidence, vocab_match_type, vocab_source
        ) VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, 0,
            ?, ?,
            0, NULL,
            'confirmed', 1.0, 'manual_add', ?
        )
        """,
        (
            concept_id, subject, year, term_period, unit, chapter,
            slide_number, term_in_context, source_path,
            vocab_source
        )
    )
    return 'inserted'


# =============================================================================
# SOURCE PATH LOOKUP
# =============================================================================

def get_source_path(db_path: Path, subject: str, year: str, term: str, unit: str) -> str:
    """
    Look up source_path for a unit from existing occurrences.

    Created: 2026-02-24
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT DISTINCT source_path FROM occurrences
           WHERE subject=? AND year=? AND term=? AND unit=? LIMIT 1""",
        (subject, int(year), term, unit)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ''


# =============================================================================
# APPLY DECISIONS
# =============================================================================

def apply_decisions(input_path: Path, db_path: Path, log_path: Path) -> dict:
    """
    Read enriched CSV and apply reviewer decisions to the database.

    Processes all rows:
    - delete : remove occurrence, then clean orphan concepts
    - keep   : confirm occurrence as valid
    - add    : insert new occurrence (missed term, must have appears_unbolded=True)
    - skip   : no action

    Returns summary counts dict.

    Created: 2026-02-24
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} rows from {input_path.name}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    counts = {
        'deleted': 0,
        'kept': 0,
        'added': 0,
        'skipped': 0,
        'errors': 0,
        'orphans_cleaned': 0
    }

    log_rows = []
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Cache source paths for 'add' operations to avoid repeated queries
    source_path_cache: dict[tuple, str] = {}

    for row in rows:
        decision = row.get('decision', '').strip().lower()
        issue_type = row['issue_type']
        term = row['term']
        unit = row['unit']
        subject = row['subject']
        year = row['year']
        term_period = row['term_period']

        log_entry = {
            'timestamp': timestamp,
            'issue_type': issue_type,
            'decision': decision or 'skip',
            'subject': subject,
            'year': year,
            'term_period': term_period,
            'unit': unit,
            'term': term,
            'occurrence_id': row.get('occurrence_id', ''),
            'result': '',
            'notes': ''
        }

        # Blank decision = skip
        if not decision or decision == 'skip':
            counts['skipped'] += 1
            log_entry['result'] = 'skipped'
            log_rows.append(log_entry)
            continue

        try:
            if decision == 'delete':
                occ_id_str = row.get('occurrence_id', '').strip()
                if not occ_id_str:
                    raise ValueError("No occurrence_id for delete — row may be a missed_from_extraction")
                occ_id = int(occ_id_str)
                result = delete_occurrence(cursor, occ_id)
                if result == 'deleted':
                    counts['deleted'] += 1
                log_entry['result'] = result

            elif decision == 'keep':
                occ_id_str = row.get('occurrence_id', '').strip()
                if not occ_id_str:
                    raise ValueError("No occurrence_id for keep — row may be a missed_from_extraction")
                occ_id = int(occ_id_str)
                result = confirm_occurrence(cursor, occ_id)
                if result == 'confirmed':
                    counts['kept'] += 1
                else:
                    log_entry['notes'] = 'Occurrence not found in database'
                log_entry['result'] = result

            elif decision == 'add':
                if issue_type != 'missed_from_extraction':
                    raise ValueError(
                        f"'add' is only valid for missed_from_extraction rows, "
                        f"not '{issue_type}'"
                    )
                appears_unbolded = row.get('appears_unbolded', '').strip()
                if appears_unbolded != 'True':
                    raise ValueError(
                        f"'add' requires appears_unbolded=True, got '{appears_unbolded}'"
                    )

                # Fetch source path via cache
                cache_key = (subject, year, term_period, unit)
                if cache_key not in source_path_cache:
                    source_path_cache[cache_key] = get_source_path(
                        db_path, subject, year, term_period, unit
                    )
                row['_source_path'] = source_path_cache[cache_key]

                result = add_occurrence(cursor, row)
                if result == 'inserted':
                    counts['added'] += 1
                else:
                    log_entry['notes'] = 'Occurrence already in database — skipped'
                log_entry['result'] = result

            else:
                raise ValueError(f"Unknown decision value: '{decision}'")

        except Exception as e:
            counts['errors'] += 1
            log_entry['result'] = 'error'
            log_entry['notes'] = str(e)
            print(f"  [ERROR] '{term}' | {subject} Y{year} {term_period} | {unit}: {e}")

        log_rows.append(log_entry)

    # Orphan concept cleanup — run once after all deletes
    if counts['deleted'] > 0:
        counts['orphans_cleaned'] = cleanup_orphan_concepts(cursor)

    conn.commit()
    conn.close()

    # Write audit trail log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fieldnames = [
        'timestamp', 'issue_type', 'decision', 'subject', 'year',
        'term_period', 'unit', 'term', 'occurrence_id', 'result', 'notes'
    ]
    with open(log_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=log_fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)

    return counts


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    project_root = Path(__file__).parent.parent
    db_path = project_root / "db" / "owl_knowledge_map.db"
    input_path = project_root / "output" / "term_audit_enriched.csv"
    log_path = project_root / "output" / "audit_decisions_log.csv"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    if not input_path.exists():
        print(f"ERROR: Enriched audit CSV not found at {input_path}")
        print("Run: python src/enrich_audit.py")
        return 1

    print("Applying audit decisions...")
    print()

    counts = apply_decisions(input_path, db_path, log_path)

    print()
    print("=" * 60)
    print("APPLY DECISIONS SUMMARY")
    print("=" * 60)
    print(f"Deleted occurrences:     {counts['deleted']}")
    print(f"Orphan concepts cleaned: {counts['orphans_cleaned']}")
    print(f"Kept / confirmed:        {counts['kept']}")
    print(f"Added (manual):          {counts['added']}")
    print(f"Skipped:                 {counts['skipped']}")
    print(f"Errors:                  {counts['errors']}")
    print()
    print(f"Audit log written to: {log_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
