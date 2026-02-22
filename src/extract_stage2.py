#!/usr/bin/env python3
"""
Stage 2: PPTX Extraction with Database Persistence

Extends Stage 1 extraction by adding:
- Metadata parsing from file paths
- SQLite database writes (concepts + occurrences)
- CSV export for human review

Reuses Stage 1 extraction functions as a library.

Created: 2026-02-22
"""

import re
import csv
import sqlite3
from pathlib import Path
from datetime import datetime

# Import Stage 1 extraction functions
from extract_stage1 import extract_bold_runs


# =============================================================================
# METADATA PARSING
# =============================================================================

def parse_filename_metadata(filepath: str) -> dict:
    """
    Extract curriculum metadata from file path.

    Handles two path patterns:
    1. Full corpus: /{Subject}/{Year} {Subject} {Term} {Unit}/Booklet/filename.pptx
    2. Sample files: /data/sample/Y{Year} {Term} {Unit} Booklet.pptx

    Args:
        filepath: Full path to PPTX file

    Returns:
        dict with keys: subject, year, term, unit, source_path
    """
    path = Path(filepath)
    filename = path.stem  # Filename without extension

    # Try to parse from filename (sample file pattern)
    # Pattern: Y4 Spring 2 Christianity in 3 empires Booklet
    match = re.match(r'Y(\d+)\s+(\w+\s+\d+)\s+(.+?)\s+Booklet', filename)

    if match:
        year = int(match.group(1))
        term_raw = match.group(2)  # e.g., "Spring 2"
        unit = match.group(3)      # e.g., "Christianity in 3 empires"

        # Normalize term format: "Spring 2" → "Spring2"
        term = term_raw.replace(' ', '')

        # Infer subject from unit name or filename
        # For now, default to History since sample is a history unit
        # TODO: Add logic to detect subject from parent folder in full corpus
        subject = infer_subject(filename, str(path.parent))

        return {
            'subject': subject,
            'year': year,
            'term': term,
            'unit': unit,
            'source_path': str(path.absolute())
        }

    # If parsing fails, return None values
    return {
        'subject': None,
        'year': None,
        'term': None,
        'unit': None,
        'source_path': str(path.absolute())
    }


def infer_subject(filename: str, parent_path: str) -> str:
    """
    Infer subject from filename or parent folder.

    Args:
        filename: PPTX filename
        parent_path: Parent directory path

    Returns:
        Subject name: 'History', 'Geography', or 'Religion'
    """
    # Check for subject abbreviations in filename or path
    text = f"{filename} {parent_path}".lower()

    if 'hist' in text:
        return 'History'
    elif 'geog' in text:
        return 'Geography'
    elif 'relig' in text:
        return 'Religion'

    # Default to History for sample file
    return 'History'


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def get_or_create_concept(cursor: sqlite3.Cursor, term: str, subject_area: str = None) -> int:
    """
    Get existing concept_id or create new concept.

    Args:
        cursor: SQLite cursor
        term: Concept term text
        subject_area: Optional subject classification

    Returns:
        concept_id (int)
    """
    # Check if concept exists
    cursor.execute(
        "SELECT concept_id FROM concepts WHERE term = ?",
        (term,)
    )
    result = cursor.fetchone()

    if result:
        return result[0]

    # Create new concept
    cursor.execute(
        "INSERT INTO concepts (term, subject_area) VALUES (?, ?)",
        (term, subject_area)
    )
    return cursor.lastrowid


def insert_occurrence(cursor: sqlite3.Cursor, concept_id: int, metadata: dict,
                     term_data: dict) -> int:
    """
    Insert an occurrence record.

    Args:
        cursor: SQLite cursor
        concept_id: Foreign key to concepts table
        metadata: File metadata (subject, year, term, unit, source_path)
        term_data: Extracted term data (slide, chapter, context, flagged)

    Returns:
        occurrence_id (int)
    """
    cursor.execute("""
        INSERT INTO occurrences (
            concept_id, subject, year, term, unit, chapter,
            slide_number, is_introduction, term_in_context, source_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        concept_id,
        metadata['subject'],
        metadata['year'],
        metadata['term'],
        metadata['unit'],
        term_data['chapter'],
        term_data['slide'],
        True,  # All bold terms in Stage 2 are introductions
        term_data['context'],
        metadata['source_path']
    ))
    return cursor.lastrowid


def write_to_database(db_path: str, metadata: dict, extraction_results: dict) -> dict:
    """
    Write extraction results to SQLite database.

    Args:
        db_path: Path to SQLite database file
        metadata: File metadata from parse_filename_metadata()
        extraction_results: Results from extract_bold_runs()

    Returns:
        dict with write statistics
    """
    stats = {
        'concepts_created': 0,
        'concepts_reused': 0,
        'occurrences_created': 0,
        'errors': []
    }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for term_data in extraction_results['terms']:
            term = term_data['term']

            # Get or create concept
            existing_count = cursor.execute(
                "SELECT COUNT(*) FROM concepts WHERE term = ?", (term,)
            ).fetchone()[0]

            concept_id = get_or_create_concept(
                cursor, term, metadata['subject']
            )

            if existing_count > 0:
                stats['concepts_reused'] += 1
            else:
                stats['concepts_created'] += 1

            # Insert occurrence
            insert_occurrence(cursor, concept_id, metadata, term_data)
            stats['occurrences_created'] += 1

        conn.commit()
        conn.close()

    except Exception as e:
        stats['errors'].append(f"Database error: {str(e)}")

    return stats


# =============================================================================
# CSV EXPORT
# =============================================================================

def export_to_csv(csv_path: str, metadata: dict, extraction_results: dict) -> bool:
    """
    Export extraction results to CSV for human review.

    CSV columns:
    - term, slide, chapter, context, flagged, subject, year, term, unit

    Args:
        csv_path: Output CSV file path
        metadata: File metadata
        extraction_results: Results from extract_bold_runs()

    Returns:
        True if successful, False otherwise
    """
    try:
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'term', 'slide', 'chapter', 'context', 'flagged',
                'subject', 'year', 'term_period', 'unit'
            ])
            writer.writeheader()

            for term_data in extraction_results['terms']:
                writer.writerow({
                    'term': term_data['term'],
                    'slide': term_data['slide'],
                    'chapter': term_data['chapter'] or '',
                    'context': term_data['context'],
                    'flagged': 'YES' if term_data['flagged'] else 'NO',
                    'subject': metadata['subject'],
                    'year': metadata['year'],
                    'term_period': metadata['term'],
                    'unit': metadata['unit']
                })

        return True

    except Exception as e:
        print(f"CSV export error: {str(e)}")
        return False


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def process_file(pptx_path: str, db_path: str, csv_output_dir: str = None) -> dict:
    """
    Complete Stage 2 pipeline: extract, parse metadata, write to DB, export CSV.

    Args:
        pptx_path: Path to PPTX file
        db_path: Path to SQLite database
        csv_output_dir: Optional directory for CSV export

    Returns:
        dict with processing results and statistics
    """
    results = {
        'file': pptx_path,
        'success': False,
        'metadata': None,
        'extraction': None,
        'db_stats': None,
        'csv_path': None,
        'errors': []
    }

    try:
        # Step 1: Parse metadata
        print(f"Parsing metadata from: {Path(pptx_path).name}")
        metadata = parse_filename_metadata(pptx_path)
        results['metadata'] = metadata

        if not metadata['subject'] or not metadata['year']:
            results['errors'].append("Failed to parse required metadata from filename")
            return results

        # Step 2: Extract bold terms (reuse Stage 1)
        print(f"Extracting bold terms...")
        extraction = extract_bold_runs(pptx_path)
        results['extraction'] = extraction

        if extraction['errors']:
            results['errors'].extend(extraction['errors'])

        # Step 3: Write to database
        print(f"Writing to database: {db_path}")
        db_stats = write_to_database(db_path, metadata, extraction)
        results['db_stats'] = db_stats

        if db_stats['errors']:
            results['errors'].extend(db_stats['errors'])

        # Step 4: Export to CSV (optional)
        if csv_output_dir:
            csv_filename = f"{Path(pptx_path).stem}_extracted.csv"
            csv_path = Path(csv_output_dir) / csv_filename
            print(f"Exporting to CSV: {csv_path}")

            if export_to_csv(str(csv_path), metadata, extraction):
                results['csv_path'] = str(csv_path)
            else:
                results['errors'].append("CSV export failed")

        results['success'] = len(results['errors']) == 0

    except Exception as e:
        results['errors'].append(f"Processing error: {str(e)}")

    return results


def print_results(results: dict):
    """
    Print processing results summary.

    Args:
        results: Results dict from process_file()
    """
    print("\n" + "=" * 60)
    print("=== STAGE 2 PROCESSING RESULTS ===")
    print("=" * 60)

    print(f"File: {Path(results['file']).name}")
    print(f"Success: {'✓' if results['success'] else '✗'}")

    if results['metadata']:
        m = results['metadata']
        print(f"\nMetadata:")
        print(f"  Subject: {m['subject']}")
        print(f"  Year: {m['year']}")
        print(f"  Term: {m['term']}")
        print(f"  Unit: {m['unit']}")

    if results['extraction']:
        e = results['extraction']
        print(f"\nExtraction:")
        print(f"  Slides processed: {e['total_slides']}")
        print(f"  Terms extracted: {len(e['terms'])}")
        print(f"  Flagged: {sum(1 for t in e['terms'] if t['flagged'])}")

    if results['db_stats']:
        s = results['db_stats']
        print(f"\nDatabase:")
        print(f"  New concepts: {s['concepts_created']}")
        print(f"  Existing concepts: {s['concepts_reused']}")
        print(f"  Occurrences created: {s['occurrences_created']}")

    if results['csv_path']:
        print(f"\nCSV exported to: {results['csv_path']}")

    if results['errors']:
        print(f"\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")

    print("=" * 60)


def main():
    """
    Main execution: Process sample file through Stage 2 pipeline.
    """
    # Paths
    project_root = Path(__file__).parent.parent
    sample_file = project_root / "data" / "sample" / "Y4 Spring 2 Christianity in 3 empires Booklet.pptx"
    db_file = project_root / "db" / "owl_knowledge_map.db"
    csv_output = project_root / "output"

    # Verify sample file exists
    if not sample_file.exists():
        print(f"ERROR: Sample file not found at {sample_file}")
        return

    # Verify database exists
    if not db_file.exists():
        print(f"ERROR: Database not found at {db_file}")
        print("Please run src/init_db.py first to create the database.")
        return

    # Create output directory if needed
    csv_output.mkdir(exist_ok=True)

    # Process file
    print(f"Starting Stage 2 processing...")
    print(f"Sample file: {sample_file.name}\n")

    results = process_file(
        str(sample_file),
        str(db_file),
        str(csv_output)
    )

    # Print results
    print_results(results)


if __name__ == "__main__":
    main()
