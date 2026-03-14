#!/usr/bin/env python3
"""
Migration script: SQLite → PostgreSQL
OWL Knowledge Map

Copies all data from the local SQLite database into the Postgres owl database.
Safe to re-run — truncates tables before inserting.

Usage:
    python src/migrate_to_postgres.py

Requirements:
    pip install psycopg2-binary

Created: 2026-03-14
"""

import sqlite3
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# =============================================================================
# CONFIG
# =============================================================================

SQLITE_PATH = Path(__file__).parent.parent / "db" / "owl_knowledge_map.db"

PG_CONN_STRING = "dbname=owl user=htmadmin password=dev host=localhost port=5432"

# =============================================================================
# MIGRATE
# =============================================================================

def migrate():
    print(f"Source: {SQLITE_PATH}")
    if not SQLITE_PATH.exists():
        print("ERROR: SQLite database not found.")
        return

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(PG_CONN_STRING)
    pg_cursor = pg_conn.cursor()

    try:
        # ---- Truncate in reverse FK order ----
        print("Truncating existing Postgres tables...")
        pg_cursor.execute("TRUNCATE edges, occurrences, concepts RESTART IDENTITY CASCADE")

        # ---- Concepts ----
        rows = sqlite_conn.execute("SELECT * FROM concepts ORDER BY concept_id").fetchall()
        print(f"Migrating {len(rows)} concepts...")
        for r in rows:
            pg_cursor.execute(
                "INSERT INTO concepts (concept_id, term, subject_area) VALUES (%s, %s, %s)",
                (r["concept_id"], r["term"], r["subject_area"])
            )
        # Reset sequence to max id
        pg_cursor.execute("SELECT setval('concepts_concept_id_seq', (SELECT MAX(concept_id) FROM concepts))")

        # ---- Occurrences ----
        rows = sqlite_conn.execute("SELECT * FROM occurrences ORDER BY occurrence_id").fetchall()
        print(f"Migrating {len(rows)} occurrences...")
        for r in rows:
            pg_cursor.execute("""
                INSERT INTO occurrences (
                    occurrence_id, concept_id, subject, year, term, unit,
                    chapter, slide_number, is_introduction, term_in_context,
                    source_path, needs_review, review_reason, validation_status,
                    vocab_confidence, vocab_match_type, vocab_source,
                    audit_decision, audit_notes
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
            """, (
                r["occurrence_id"], r["concept_id"], r["subject"], r["year"],
                r["term"], r["unit"], r["chapter"], r["slide_number"],
                r["is_introduction"], r["term_in_context"], r["source_path"],
                r["needs_review"], r["review_reason"], r["validation_status"],
                r["vocab_confidence"], r["vocab_match_type"], r["vocab_source"],
                r["audit_decision"], r["audit_notes"]
            ))
        pg_cursor.execute("SELECT setval('occurrences_occurrence_id_seq', (SELECT MAX(occurrence_id) FROM occurrences))")

        # ---- Edges ----
        rows = sqlite_conn.execute("SELECT * FROM edges ORDER BY edge_id").fetchall()
        print(f"Migrating {len(rows)} edges...")
        for r in rows:
            pg_cursor.execute("""
                INSERT INTO edges (
                    edge_id, from_occurrence, to_occurrence,
                    edge_type, edge_nature, confirmed_by, confirmed_date
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                r["edge_id"], r["from_occurrence"], r["to_occurrence"],
                r["edge_type"], r["edge_nature"], r["confirmed_by"], r["confirmed_date"]
            ))
        if rows:
            pg_cursor.execute("SELECT setval('edges_edge_id_seq', (SELECT MAX(edge_id) FROM edges))")

        pg_conn.commit()
        print("\n✓ Migration complete.")

        # ---- Verify ----
        pg_cursor.execute("SELECT COUNT(*) FROM concepts")
        print(f"  concepts:    {pg_cursor.fetchone()[0]}")
        pg_cursor.execute("SELECT COUNT(*) FROM occurrences")
        print(f"  occurrences: {pg_cursor.fetchone()[0]}")
        pg_cursor.execute("SELECT COUNT(*) FROM edges")
        print(f"  edges:       {pg_cursor.fetchone()[0]}")

    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    migrate()
