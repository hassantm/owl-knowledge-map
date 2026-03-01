#!/usr/bin/env python3
"""
OWL Knowledge Map — Curriculum Insights
========================================
Standalone script to derive analytical insights from the SQLite database
before network analysis begins.

Run individual analyses or all at once:
  python src/insights.py                       # run all
  python src/insights.py --analysis density    # run one
  python src/insights.py --csv-dir /tmp/owl   # export to CSV

Each function prints a formatted table to stdout.

Created: 2026-03-01
"""

import argparse
import csv
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "owl_knowledge_map.db"

TERM_ORDER_SQL = """
    CASE term
        WHEN 'Autumn1' THEN 1 WHEN 'Autumn2' THEN 2
        WHEN 'Spring1' THEN 3 WHEN 'Spring2' THEN 4
        WHEN 'Summer1' THEN 5 WHEN 'Summer2' THEN 6
        ELSE 7
    END
"""


def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _print_table(title, rows, headers):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")
    if not rows:
        print("  (no data)")
        return
    col_widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    print(fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in col_widths))
    for row in rows:
        print(fmt.format(*[str(v) for v in row]))


def _write_csv(path, rows, headers):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"  → Written to {path}")


# =============================================================================
# 1. TERM DENSITY BY UNIT
# =============================================================================

def analysis_density(conn, csv_dir=None):
    """Vocabulary density: introductions per unit, sorted heaviest first."""
    sql = """
        SELECT
            o.subject,
            o.year,
            o.term                                                          AS term_period,
            o.unit,
            COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)              AS introductions,
            COUNT(*)                                                        AS total_occurrences,
            ROUND(
                COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END) * 1.0
                / COUNT(*) * 100, 1
            )                                                               AS intro_pct
        FROM occurrences o
        WHERE o.validation_status = 'confirmed'
        GROUP BY o.subject, o.year, o.term, o.unit
        ORDER BY introductions DESC, total_occurrences DESC
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["subject"], r["year"], r["term_period"], r["unit"],
         r["introductions"], r["total_occurrences"], str(r["intro_pct"]) + "%")
        for r in cur.fetchall()
    ]
    headers = ["Subject", "Year", "Term", "Unit", "Intros", "Total", "Intro%"]
    _print_table("1. VOCABULARY DENSITY BY UNIT (heaviest first)", rows, headers)
    if csv_dir:
        _write_csv(Path(csv_dir) / "density_by_unit.csv", rows, headers)
    return rows


# =============================================================================
# 2. INTRODUCTION vs RECURRENCE RATIO BY SUBJECT
# =============================================================================

def analysis_intro_recurrence(conn, csv_dir=None):
    """Intro vs recurrence ratio per subject."""
    sql = """
        SELECT
            subject,
            COUNT(CASE WHEN is_introduction = 1 THEN 1 END)    AS introductions,
            COUNT(CASE WHEN is_introduction = 0 THEN 1 END)    AS recurrences,
            COUNT(*)                                            AS total,
            ROUND(
                COUNT(CASE WHEN is_introduction = 1 THEN 1 END) * 100.0 / COUNT(*), 1
            )                                                   AS intro_pct
        FROM occurrences
        WHERE validation_status = 'confirmed'
        GROUP BY subject
        ORDER BY intro_pct DESC
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["subject"], r["introductions"], r["recurrences"],
         r["total"], str(r["intro_pct"]) + "%")
        for r in cur.fetchall()
    ]
    headers = ["Subject", "Introductions", "Recurrences", "Total", "Intro%"]
    _print_table("2. INTRODUCTION vs RECURRENCE RATIO BY SUBJECT", rows, headers)
    if csv_dir:
        _write_csv(Path(csv_dir) / "intro_recurrence_by_subject.csv", rows, headers)
    return rows


# =============================================================================
# 3. ORPHANED CONCEPTS (introduced but never revisited)
# =============================================================================

def analysis_orphans(conn, csv_dir=None):
    """Concepts introduced once and never revisited."""
    sql = """
        SELECT
            c.term,
            c.subject_area,
            o.subject,
            o.year,
            o.term      AS term_period,
            o.unit
        FROM concepts c
        JOIN occurrences o ON c.concept_id = o.concept_id
        WHERE o.is_introduction = 1
          AND o.validation_status = 'confirmed'
          AND (
              SELECT COUNT(*) FROM occurrences o2
              WHERE o2.concept_id = c.concept_id
                AND o2.validation_status = 'confirmed'
          ) = 1
        ORDER BY o.subject, o.year, o.term, c.term
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["term"], r["subject_area"] or r["subject"],
         r["year"], r["term_period"], r["unit"])
        for r in cur.fetchall()
    ]
    headers = ["Term", "Subject", "Year", "Term Period", "Unit"]
    _print_table(
        f"3. ORPHANED CONCEPTS — introduced once, never revisited ({len(rows)} terms)",
        rows, headers
    )
    if csv_dir:
        _write_csv(Path(csv_dir) / "orphaned_concepts.csv", rows, headers)
    return rows


# =============================================================================
# 4. CROSS-SUBJECT VOCABULARY OVERLAP
# =============================================================================

def analysis_cross_subject(conn, csv_dir=None):
    """Terms appearing across multiple subjects."""
    sql = """
        SELECT
            c.term,
            COUNT(DISTINCT o.subject)                               AS subject_count,
            GROUP_CONCAT(DISTINCT o.subject ORDER BY o.subject)    AS subjects,
            COUNT(*)                                                AS total_occurrences,
            MIN(o.year)                                             AS first_year,
            MAX(o.year)                                             AS last_year
        FROM concepts c
        JOIN occurrences o ON c.concept_id = o.concept_id
        WHERE o.validation_status = 'confirmed'
        GROUP BY c.concept_id
        HAVING COUNT(DISTINCT o.subject) > 1
        ORDER BY subject_count DESC, total_occurrences DESC, c.term
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["term"], r["subjects"], r["subject_count"],
         r["total_occurrences"], r["first_year"], r["last_year"])
        for r in cur.fetchall()
    ]
    headers = ["Term", "Subjects", "Subject Count", "Total Occ", "First Year", "Last Year"]
    _print_table(
        f"4. CROSS-SUBJECT VOCABULARY OVERLAP ({len(rows)} terms span multiple subjects)",
        rows, headers
    )
    if csv_dir:
        _write_csv(Path(csv_dir) / "cross_subject_overlap.csv", rows, headers)
    return rows


# =============================================================================
# 5. YEAR-ON-YEAR VOCABULARY GROWTH RATIO
# =============================================================================

def analysis_year_ratio(conn, csv_dir=None):
    """New vs. recurring ratio per year."""
    sql = """
        SELECT
            year,
            COUNT(CASE WHEN is_introduction = 1 THEN 1 END)    AS new_terms,
            COUNT(CASE WHEN is_introduction = 0 THEN 1 END)    AS recurrences,
            COUNT(*)                                            AS total,
            ROUND(
                COUNT(CASE WHEN is_introduction = 0 THEN 1 END) * 100.0 / COUNT(*), 1
            )                                                   AS recurrence_pct
        FROM occurrences
        WHERE validation_status = 'confirmed'
        GROUP BY year
        ORDER BY year
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["year"], r["new_terms"], r["recurrences"],
         r["total"], str(r["recurrence_pct"]) + "%")
        for r in cur.fetchall()
    ]
    headers = ["Year", "New Terms", "Recurrences", "Total", "Recurrence%"]
    _print_table(
        "5. YEAR-ON-YEAR NEW vs RECURRING RATIO (recurrence% should rise with year)",
        rows, headers
    )
    if csv_dir:
        _write_csv(Path(csv_dir) / "year_ratio.csv", rows, headers)
    return rows


# =============================================================================
# 6. CHAPTER-LEVEL VOCABULARY CLUSTERING
# =============================================================================

def analysis_chapters(conn, csv_dir=None):
    """Chapter-level intro vs. recurrence."""
    sql = """
        SELECT
            o.subject,
            o.year,
            o.unit,
            o.chapter,
            COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)  AS introductions,
            COUNT(CASE WHEN o.is_introduction = 0 THEN 1 END)  AS recurrences,
            COUNT(*)                                            AS total
        FROM occurrences o
        WHERE o.validation_status = 'confirmed'
          AND o.chapter IS NOT NULL
          AND o.chapter != ''
        GROUP BY o.subject, o.year, o.unit, o.chapter
        HAVING introductions > 0
        ORDER BY introductions DESC
        LIMIT 30
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["subject"], r["year"], r["unit"][:30], r["chapter"][:40],
         r["introductions"], r["recurrences"])
        for r in cur.fetchall()
    ]
    headers = ["Subject", "Year", "Unit", "Chapter", "Intros", "Recurrences"]
    _print_table("6. TOP 30 KNOWLEDGE-LOADING CHAPTERS (most introductions)", rows, headers)
    if csv_dir:
        _write_csv(Path(csv_dir) / "chapter_clusters.csv", rows, headers)
    return rows


# =============================================================================
# 7. TERM LONGEVITY
# =============================================================================

def analysis_longevity(conn, csv_dir=None):
    """Years each term spans from introduction to last appearance."""
    sql = """
        SELECT
            c.term,
            c.subject_area,
            MIN(o.year)                         AS introduced_year,
            MAX(o.year)                         AS last_seen_year,
            MAX(o.year) - MIN(o.year) + 1       AS years_active,
            COUNT(*)                            AS total_occurrences
        FROM concepts c
        JOIN occurrences o ON c.concept_id = o.concept_id
        WHERE o.validation_status = 'confirmed'
        GROUP BY c.concept_id
        HAVING total_occurrences > 1
        ORDER BY years_active DESC, total_occurrences DESC
        LIMIT 40
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["term"], r["subject_area"] or "—", r["introduced_year"],
         r["last_seen_year"], r["years_active"], r["total_occurrences"])
        for r in cur.fetchall()
    ]
    headers = ["Term", "Subject", "Intro Year", "Last Year", "Years Active", "Occurrences"]
    _print_table("7. TOP 40 LONGEST-LIVED TERMS (most years in play)", rows, headers)
    if csv_dir:
        _write_csv(Path(csv_dir) / "term_longevity.csv", rows, headers)
    return rows


# =============================================================================
# 8. CROSS-SUBJECT EDGE REVIEW PRIORITY QUEUE
# =============================================================================

def analysis_review_priority(conn, csv_dir=None):
    """Priority queue for edge review — cross-subject terms, most occurrences first."""
    sql = """
        SELECT
            c.concept_id,
            c.term,
            COUNT(DISTINCT o.subject)                               AS subject_count,
            GROUP_CONCAT(DISTINCT o.subject ORDER BY o.subject)    AS subjects,
            COUNT(*)                                                AS total_occurrences,
            COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)      AS introductions,
            MIN(o.year)                                             AS first_year,
            MAX(o.year)                                             AS last_year,
            (
                SELECT COUNT(*) FROM edges e
                JOIN occurrences oe
                    ON e.from_occurrence = oe.occurrence_id
                    OR e.to_occurrence = oe.occurrence_id
                WHERE oe.concept_id = c.concept_id
                  AND e.confirmed_by IS NOT NULL
            )                                                       AS confirmed_edges
        FROM concepts c
        JOIN occurrences o ON c.concept_id = o.concept_id
        WHERE o.validation_status = 'confirmed'
        GROUP BY c.concept_id
        HAVING COUNT(DISTINCT o.subject) > 1
           AND COUNT(*) >= 3
        ORDER BY subject_count DESC, total_occurrences DESC
        LIMIT 50
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = [
        (r["term"], r["subjects"], r["total_occurrences"],
         r["introductions"], r["first_year"], r["last_year"], r["confirmed_edges"])
        for r in cur.fetchall()
    ]
    headers = ["Term", "Subjects", "Total Occ", "Intros", "First", "Last", "Confirmed Edges"]
    _print_table(
        "8. CROSS-SUBJECT EDGE REVIEW PRIORITY QUEUE (3+ occurrences, multiple subjects)",
        rows, headers
    )
    if csv_dir:
        _write_csv(Path(csv_dir) / "review_priority.csv", rows, headers)
    return rows


# =============================================================================
# REGISTRY
# =============================================================================

ANALYSES = {
    "density":         (analysis_density,          "Vocabulary density by unit"),
    "intro_ratio":     (analysis_intro_recurrence, "Intro vs recurrence by subject"),
    "orphans":         (analysis_orphans,          "Orphaned concepts (introduced, never revisited)"),
    "cross_subject":   (analysis_cross_subject,    "Cross-subject vocabulary overlap"),
    "year_ratio":      (analysis_year_ratio,       "Year-on-year new vs recurring ratio"),
    "chapters":        (analysis_chapters,         "Chapter-level vocabulary clustering"),
    "longevity":       (analysis_longevity,        "Term longevity across years"),
    "review_priority": (analysis_review_priority,  "Cross-subject edge review priority queue"),
}


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="OWL Knowledge Map — curriculum insights from SQLite"
    )
    parser.add_argument(
        "--analysis", "-a",
        choices=list(ANALYSES.keys()),
        help="Run a single analysis. Choices: " + ", ".join(ANALYSES.keys())
    )
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help=f"Path to SQLite database (default: {DB_PATH})"
    )
    parser.add_argument(
        "--csv-dir", "-o",
        help="Directory to write CSV exports (one file per analysis)"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        print("Run: python src/init_db.py")
        return 1

    if args.csv_dir:
        Path(args.csv_dir).mkdir(parents=True, exist_ok=True)

    conn = get_conn(db_path)
    try:
        if args.analysis:
            fn, _ = ANALYSES[args.analysis]
            fn(conn, csv_dir=args.csv_dir)
        else:
            for key, (fn, desc) in ANALYSES.items():
                fn(conn, csv_dir=args.csv_dir)
    finally:
        conn.close()

    print("\nDone.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
