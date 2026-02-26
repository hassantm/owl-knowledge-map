#!/usr/bin/env python3
"""
Migration: Add audit columns to occurrences table

Adds audit_decision and audit_notes to support the Anvil review interface,
replacing the CSV-based workflow for in-DB decision storage.

Idempotent — safe to re-run. Checks for column existence before adding.

Run from project root: python src/migrate_add_audit_columns.py

Created: 2026-02-26
"""

import sqlite3
from pathlib import Path


def column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    added = []

    if not column_exists(cursor, 'occurrences', 'audit_decision'):
        cursor.execute(
            "ALTER TABLE occurrences ADD COLUMN audit_decision TEXT"
        )
        # Values: 'keep', 'delete', 'add', 'skip', NULL = unreviewed
        added.append('audit_decision TEXT')
    else:
        print("  audit_decision — already exists, skipped")

    if not column_exists(cursor, 'occurrences', 'audit_notes'):
        cursor.execute(
            "ALTER TABLE occurrences ADD COLUMN audit_notes TEXT"
        )
        added.append('audit_notes TEXT')
    else:
        print("  audit_notes — already exists, skipped")

    conn.commit()
    conn.close()

    if added:
        print(f"  Added columns: {', '.join(added)}")
    print("Migration complete.")


def main() -> int:
    project_root = Path(__file__).parent.parent
    db_path = project_root / "db" / "owl_knowledge_map.db"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print(f"Migrating: {db_path}")
    migrate(db_path)
    return 0


if __name__ == "__main__":
    exit(main())
