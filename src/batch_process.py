#!/usr/bin/env python3
"""
Batch Processing Script for Curriculum Corpus

Discovers and processes multiple booklet files across the curriculum.
Provides filtering, resume capability, error resilience, and batch reporting.

Created: 2026-02-23
"""

import argparse
import sqlite3
from pathlib import Path
from typing import List, Set, Dict

# Import Stage 2 processing functions
from extract_stage2 import process_file


# =============================================================================
# FILE DISCOVERY
# =============================================================================

def discover_booklet_files(root_dir: Path, subject_filter: str = None,
                          year_filter: int = None) -> List[Path]:
    """
    Walk directory tree to discover booklet PPTX files.

    2026-02-23: Created for batch processing

    Args:
        root_dir: Root directory to search (e.g., /path/to/HEP History/)
        subject_filter: Optional subject name to filter ('History', 'Geography', 'Religion')
        year_filter: Optional year to filter (3, 4, 5, or 6)

    Returns:
        List of Path objects for discovered booklet files
    """
    # Find all PPTX files in Booklet folders
    # Pattern: .../Y4 Hist Autumn 1 Unit/Y4 Autumn 1 Unit Booklet/*.pptx
    all_files = list(root_dir.rglob('**/*Booklet/*.pptx'))

    # Filter macOS temp files
    all_files = [f for f in all_files if not f.name.startswith('.') and not f.name.startswith('~$')]

    # Apply filters if specified
    filtered_files = []
    for file_path in all_files:
        # Check subject filter (from parent folder structure)
        if subject_filter:
            unit_folder = file_path.parent.parent.name
            if subject_filter == 'History' and 'Hist' not in unit_folder:
                continue
            elif subject_filter == 'Geography' and 'Geog' not in unit_folder:
                continue
            elif subject_filter == 'Religion' and 'Relig' not in unit_folder:
                continue

        # Check year filter
        if year_filter:
            unit_folder = file_path.parent.parent.name
            if not unit_folder.startswith(f'Y{year_filter} '):
                continue

        filtered_files.append(file_path)

    # Sort by path for consistent ordering
    filtered_files.sort()

    return filtered_files


def get_processed_file_paths(db_path: Path) -> Set[str]:
    """
    Query database for already-processed files (resume capability).

    2026-02-23: Created for batch processing

    Args:
        db_path: Path to SQLite database

    Returns:
        Set of absolute file paths already in database
    """
    processed_paths = set()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get distinct source paths from occurrences table
        cursor.execute("SELECT DISTINCT source_path FROM occurrences")
        rows = cursor.fetchall()

        for row in rows:
            processed_paths.add(row[0])

        conn.close()

    except Exception as e:
        print(f"Warning: Could not query database for processed files: {e}")

    return processed_paths


# =============================================================================
# BATCH ORCHESTRATION
# =============================================================================

def batch_process(root_dir: Path, db_path: Path, csv_output_dir: Path,
                 subject_filter: str = None, year_filter: int = None,
                 resume: bool = False, dry_run: bool = False) -> Dict:
    """
    Main batch processing orchestration.

    2026-02-23: Created for batch processing

    Args:
        root_dir: Root directory to search
        db_path: Path to SQLite database
        csv_output_dir: Directory for CSV exports
        subject_filter: Optional subject filter
        year_filter: Optional year filter
        resume: Skip files already in database
        dry_run: Discover files without processing

    Returns:
        Dict with batch statistics
    """
    # Initialize statistics
    batch_stats = {
        'files_discovered': 0,
        'files_processed': 0,
        'files_skipped': 0,
        'files_failed': 0,
        'total_concepts': 0,
        'total_occurrences': 0,
        'errors': [],
        'file_results': []
    }

    # Discover files
    print(f"Discovering booklet files in: {root_dir}")
    files = discover_booklet_files(root_dir, subject_filter, year_filter)
    batch_stats['files_discovered'] = len(files)
    print(f"Found {len(files)} booklet file{'s' if len(files) != 1 else ''}\n")

    if len(files) == 0:
        print("No files found matching criteria.")
        return batch_stats

    # Dry run mode - just list files
    if dry_run:
        print("=" * 60)
        print("=== DRY RUN: Files discovered ===")
        print("=" * 60)
        for i, file_path in enumerate(files, 1):
            print(f"{i}. {file_path}")
        print("=" * 60)
        return batch_stats

    # Get already-processed files for resume mode
    processed_paths = set()
    if resume:
        print("Resume mode: checking database for processed files...")
        processed_paths = get_processed_file_paths(db_path)
        print(f"Found {len(processed_paths)} already-processed files\n")

    # Create output directory
    csv_output_dir.mkdir(parents=True, exist_ok=True)

    # Process each file
    for i, file_path in enumerate(files, 1):
        print("=" * 60)
        print(f"[{i}/{len(files)}] Processing: {file_path.name}")
        print("=" * 60)

        # Check if already processed (resume mode)
        if resume and str(file_path.absolute()) in processed_paths:
            print("SKIPPING (already processed)")
            batch_stats['files_skipped'] += 1
            batch_stats['file_results'].append({
                'file': file_path.name,
                'success': None,
                'terms': 0,
                'skipped': True
            })
            continue

        # Process file
        try:
            results = process_file(
                str(file_path),
                str(db_path),
                str(csv_output_dir)
            )

            # Update statistics
            if results['success']:
                batch_stats['files_processed'] += 1

                if results['db_stats']:
                    batch_stats['total_concepts'] += results['db_stats']['concepts_created']
                    batch_stats['total_occurrences'] += results['db_stats']['occurrences_created']

                term_count = len(results['extraction']['terms']) if results['extraction'] else 0

                batch_stats['file_results'].append({
                    'file': file_path.name,
                    'success': True,
                    'terms': term_count,
                    'skipped': False
                })

                print(f"Success: {term_count} terms extracted")

            else:
                batch_stats['files_failed'] += 1
                batch_stats['errors'].append({
                    'file': file_path.name,
                    'errors': results['errors']
                })
                batch_stats['file_results'].append({
                    'file': file_path.name,
                    'success': False,
                    'terms': 0,
                    'skipped': False
                })
                print(f"Failed: {results['errors']}")

        except Exception as e:
            batch_stats['files_failed'] += 1
            error_msg = f"Unexpected error: {str(e)}"
            batch_stats['errors'].append({
                'file': file_path.name,
                'errors': [error_msg]
            })
            batch_stats['file_results'].append({
                'file': file_path.name,
                'success': False,
                'terms': 0,
                'skipped': False
            })
            print(f"Failed: {error_msg}")

        print()

    return batch_stats


# =============================================================================
# REPORTING
# =============================================================================

def print_batch_report(stats: Dict):
    """
    Print comprehensive batch processing report.

    2026-02-23: Created for batch processing

    Args:
        stats: Batch statistics dict from batch_process()
    """
    print("=" * 60)
    print("=== BATCH PROCESSING REPORT ===")
    print("=" * 60)
    print()

    # Summary statistics
    print(f"Files discovered: {stats['files_discovered']}")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Files skipped: {stats['files_skipped']}")
    print(f"Files failed: {stats['files_failed']}")
    print()

    print(f"Total concepts created: {stats['total_concepts']}")
    print(f"Total occurrences created: {stats['total_occurrences']}")
    print()

    # Success rate
    total_attempted = stats['files_processed'] + stats['files_failed']
    if total_attempted > 0:
        success_rate = (stats['files_processed'] / total_attempted) * 100
        print(f"Success rate: {success_rate:.1f}%")
    print()

    # Per-file results
    print("=" * 60)
    print("=== PER-FILE RESULTS ===")
    print("=" * 60)

    for result in stats['file_results']:
        if result['skipped']:
            print(f"⊘ {result['file']}: skipped (already processed)")
        elif result['success']:
            print(f"✓ {result['file']}: {result['terms']} terms")
        else:
            print(f"✗ {result['file']}: 0 terms")

    print()

    # Errors
    if stats['errors']:
        print("=" * 60)
        print("=== ERRORS ===")
        print("=" * 60)

        for error_entry in stats['errors']:
            print(f"File: {error_entry['file']}")
            for error in error_entry['errors']:
                print(f"  - {error}")
            print()

    print("=" * 60)


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    """
    CLI entry point for batch processing.

    2026-02-23: Created for batch processing
    """
    parser = argparse.ArgumentParser(
        description='Batch process curriculum booklet files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be processed
  python batch_process.py "$DROPBOX_ROOT/HEP History" --year 4 --dry-run

  # Process all Year 4 History booklets
  python batch_process.py "$DROPBOX_ROOT/HEP History" --year 4

  # Resume after interruption
  python batch_process.py "$DROPBOX_ROOT/HEP History" --year 4 --resume

  # Process entire History corpus
  python batch_process.py "$DROPBOX_ROOT/HEP History"
        """
    )

    # Positional arguments
    parser.add_argument('root_dir',
                       help='Root directory to search (e.g., /path/to/HEP History/)')

    # Optional arguments
    parser.add_argument('--db',
                       default='../db/owl_knowledge_map.db',
                       help='Database path (default: ../db/owl_knowledge_map.db)')

    parser.add_argument('--output',
                       default='../output',
                       help='CSV output directory (default: ../output)')

    parser.add_argument('--subject',
                       choices=['History', 'Geography', 'Religion'],
                       help='Filter by subject')

    parser.add_argument('--year',
                       type=int,
                       choices=[3, 4, 5, 6],
                       help='Filter by year')

    parser.add_argument('--dry-run',
                       action='store_true',
                       help='Discover files without processing')

    parser.add_argument('--resume',
                       action='store_true',
                       help='Skip files already in database')

    args = parser.parse_args()

    # Resolve paths
    script_dir = Path(__file__).parent
    root_dir = Path(args.root_dir).expanduser().resolve()
    db_path = (script_dir / args.db).resolve()
    csv_output_dir = (script_dir / args.output).resolve()

    # Validate root directory
    if not root_dir.exists():
        print(f"ERROR: Root directory not found: {root_dir}")
        return 1

    # Validate database (unless dry run)
    if not args.dry_run and not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Please run src/init_db.py first to create the database.")
        return 1

    # Run batch processing
    print("Starting batch processing...")
    print(f"Root: {root_dir}")
    if args.subject:
        print(f"Subject filter: {args.subject}")
    if args.year:
        print(f"Year filter: {args.year}")
    if args.resume:
        print("Resume mode: ON")
    if args.dry_run:
        print("Dry run mode: ON")
    print()

    stats = batch_process(
        root_dir=root_dir,
        db_path=db_path,
        csv_output_dir=csv_output_dir,
        subject_filter=args.subject,
        year_filter=args.year,
        resume=args.resume,
        dry_run=args.dry_run
    )

    # Print report (unless dry run already printed)
    if not args.dry_run:
        print_batch_report(stats)

    return 0


if __name__ == "__main__":
    exit(main())
