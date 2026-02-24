#!/usr/bin/env python3
"""
Database initialization script for OWL Knowledge Map
Created: 2026-02-22
Schema reference: CLAUDE.md

Creates SQLite database with tables for concepts, occurrences, and edges.
Run from project root: python src/init_db.py
"""

import sqlite3
from pathlib import Path


def init_database():
    """Initialize the OWL Knowledge Map database with schema and indexes."""

    # Define database path relative to project root
    project_root = Path(__file__).parent.parent
    db_dir = project_root / "db"
    db_path = db_dir / "owl_knowledge_map.db"

    # Check if database already exists
    if db_path.exists():
        response = input(f"Database already exists at {db_path}. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Database initialization cancelled.")
            return
        db_path.unlink()  # Delete existing database

    # Create db directory if it doesn't exist
    db_dir.mkdir(parents=True, exist_ok=True)

    # Create connection
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create concepts table
    cursor.execute("""
        CREATE TABLE concepts (
            concept_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            term            TEXT NOT NULL,
            subject_area    TEXT
        )
    """)

    # Create occurrences table
    cursor.execute("""
        CREATE TABLE occurrences (
            occurrence_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id      INTEGER REFERENCES concepts(concept_id),
            subject         TEXT NOT NULL,
            year            INTEGER NOT NULL,
            term            TEXT NOT NULL,
            unit            TEXT NOT NULL,
            chapter         TEXT,
            slide_number    INTEGER,
            is_introduction INTEGER NOT NULL,
            term_in_context TEXT,
            source_path     TEXT,
            needs_review        INTEGER DEFAULT 0,  -- 2026-02-22: Added for review workflow (0=no, 1=needs review, 2=approved, 3=rejected)
            review_reason       TEXT,               -- 2026-02-22: Why flagged: 'short_term', 'potential_heading', 'url', 'citation', etc.
            validation_status   TEXT,               -- 2026-02-24: 'confirmed', 'confirmed_with_flag', 'potential_noise', 'high_priority_review', NULL
            vocab_confidence    REAL,               -- 2026-02-24: 0.0–1.0, NULL if no vocab available
            vocab_match_type    TEXT,               -- 2026-02-24: 'exact', 'normalised', 'fuzzy', 'none', NULL
            vocab_source        TEXT                -- 2026-02-24: Filename of vocab .docx used, NULL if no validation
        )
    """)

    # Create edges table
    cursor.execute("""
        CREATE TABLE edges (
            edge_id             INTEGER PRIMARY KEY AUTOINCREMENT,
            from_occurrence     INTEGER REFERENCES occurrences(occurrence_id),
            to_occurrence       INTEGER REFERENCES occurrences(occurrence_id),
            edge_type           TEXT,
            edge_nature         TEXT,
            confirmed_by        TEXT,
            confirmed_date      TEXT
        )
    """)

    # Create indexes for performance
    cursor.execute("""
        CREATE INDEX idx_occurrences_concept_id
        ON occurrences(concept_id)
    """)

    cursor.execute("""
        CREATE INDEX idx_occurrences_is_introduction
        ON occurrences(is_introduction)
    """)

    cursor.execute("""
        CREATE INDEX idx_edges_from_occurrence
        ON edges(from_occurrence)
    """)

    cursor.execute("""
        CREATE INDEX idx_edges_to_occurrence
        ON edges(to_occurrence)
    """)

    # Commit and close
    conn.commit()
    conn.close()

    print(f"✓ Database initialized successfully at: {db_path}")
    print(f"✓ Created tables: concepts, occurrences, edges")
    print(f"✓ Created 4 indexes for performance")
    print(f"\nVerify schema with: sqlite3 {db_path} \".schema\"")


if __name__ == "__main__":
    init_database()
