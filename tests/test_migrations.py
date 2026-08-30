"""
Tests for database migrations.

Verifies that migrations produce the expected schema:
- 001: enrichment columns added to concepts with correct defaults and constraints
- 002: co_occurrences table created with correct structure and constraints

These tests rely on the session-scoped db_session fixture from conftest.py,
which applies both migrations to owl_test at session start. The tests then
inspect the resulting schema by querying information_schema.
"""

import pytest
import psycopg2.extras


def get_columns(conn, table_name):
    """Return a dict of column_name → column info for the given table."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT column_name, data_type, column_default, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s
              AND table_schema = 'public'
        """, (table_name,))
        return {row['column_name']: row for row in cur.fetchall()}


def get_constraints(conn, table_name):
    """Return constraint names for the given table."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = %s AND table_schema = 'public'
        """, (table_name,))
        return {row['constraint_name']: row['constraint_type'] for row in cur.fetchall()}


def table_exists(conn, table_name):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s AND table_schema = 'public'
        """, (table_name,))
        return cur.fetchone() is not None


# ── Migration 001: enrichment columns ────────────────────────────────────────

class TestMigration001:

    def test_definition_column_exists(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'definition' in cols

    def test_etymology_column_exists(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'etymology' in cols

    def test_word_family_column_is_array(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'word_family' in cols
        assert cols['word_family']['data_type'] == 'ARRAY'

    def test_register_column_exists(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'register' in cols

    def test_tier_column_is_integer(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'tier' in cols
        assert cols['tier']['data_type'] == 'integer'

    def test_enrichment_status_defaults_to_pending(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'enrichment_status' in cols
        assert 'pending' in (cols['enrichment_status']['column_default'] or '')

    def test_enrichment_status_is_not_nullable(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert cols['enrichment_status']['is_nullable'] == 'NO'

    def test_enriched_at_is_timestamptz(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'enriched_at' in cols
        assert 'timestamp' in cols['enriched_at']['data_type']

    def test_enriched_by_defaults_to_claude_batch(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'enriched_by' in cols
        assert 'claude-batch' in (cols['enriched_by']['column_default'] or '')

    def test_enrichment_notes_column_exists(self, db_session):
        cols = get_columns(db_session, 'concepts')
        assert 'enrichment_notes' in cols

    def test_register_check_constraint_rejects_invalid_value(self, db_session):
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term, register)
                    VALUES ('test_concept', 'slang')
                """)
            db_session.rollback()
        db_session.rollback()

    def test_register_check_constraint_accepts_subject_specific(self, db_session):
        with db_session.cursor() as cur:
            cur.execute("""
                INSERT INTO concepts (term, register)
                VALUES ('test_reg_valid', 'subject-specific')
                RETURNING concept_id
            """)
            cid = cur.fetchone()['concept_id']
            cur.execute("DELETE FROM concepts WHERE concept_id = %s", (cid,))

    def test_tier_check_constraint_rejects_zero(self, db_session):
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term, tier) VALUES ('test_tier', 0)
                """)
        db_session.rollback()

    def test_tier_check_constraint_rejects_four(self, db_session):
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term, tier) VALUES ('test_tier', 4)
                """)
        db_session.rollback()

    def test_tier_check_constraint_accepts_1_2_3(self, db_session):
        for tier in (1, 2, 3):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term, tier)
                    VALUES (%s, %s)
                    RETURNING concept_id
                """, (f'test_tier_{tier}', tier))
                cid = cur.fetchone()['concept_id']
                cur.execute("DELETE FROM concepts WHERE concept_id = %s", (cid,))

    def test_enrichment_status_check_constraint_rejects_invalid(self, db_session):
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term, enrichment_status)
                    VALUES ('test_status', 'in_progress')
                """)
        db_session.rollback()

    def test_migration_is_idempotent(self, db_session):
        # Running the ALTER TABLE ... ADD COLUMN IF NOT EXISTS again should not raise
        with db_session.cursor() as cur:
            cur.execute("""
                ALTER TABLE concepts
                    ADD COLUMN IF NOT EXISTS definition text,
                    ADD COLUMN IF NOT EXISTS enrichment_status text
            """)


# ── Migration 002: co_occurrences table ──────────────────────────────────────

class TestMigration002:

    def test_co_occurrences_table_exists(self, db_session):
        assert table_exists(db_session, 'co_occurrences')

    def test_required_columns_exist(self, db_session):
        cols = get_columns(db_session, 'co_occurrences')
        for col in ('id', 'concept_a_id', 'concept_b_id', 'subject_a', 'subject_b',
                    'granularity', 'weight', 'is_cross_subject', 'computed_at'):
            assert col in cols, f"Expected column '{col}' in co_occurrences"

    def test_is_cross_subject_is_generated(self, db_session):
        # A generated column should not appear in information_schema.columns
        # with an editable data_type but should be queryable.
        # Verify by trying to insert a value into it (should fail for generated column)
        with pytest.raises(Exception):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO concepts (term) VALUES ('tmp_gen') RETURNING concept_id
                """)
                cid = cur.fetchone()['concept_id']
                cur.execute("""
                    INSERT INTO co_occurrences
                        (concept_a_id, concept_b_id, subject_a, subject_b,
                         granularity, weight, is_cross_subject)
                    VALUES (%s, %s, 'History', 'Geography', 'lesson', 1, false)
                """, (cid, cid + 1))
        db_session.rollback()

    def test_concept_ordering_constraint_rejects_a_greater_than_b(self, db_session):
        with db_session.cursor() as cur:
            cur.execute("INSERT INTO concepts (term) VALUES ('c1') RETURNING concept_id")
            c1 = cur.fetchone()['concept_id']
            cur.execute("INSERT INTO concepts (term) VALUES ('c2') RETURNING concept_id")
            c2 = cur.fetchone()['concept_id']

        higher, lower = max(c1, c2), min(c1, c2)
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO co_occurrences
                        (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                    VALUES (%s, %s, 'History', 'History', 'lesson', 1)
                """, (higher, lower))
        db_session.rollback()

        # Cleanup
        with db_session.cursor() as cur:
            cur.execute("DELETE FROM concepts WHERE concept_id IN (%s, %s)", (c1, c2))

    def test_unique_constraint_prevents_duplicate_pairs(self, db_session):
        with db_session.cursor() as cur:
            cur.execute("INSERT INTO concepts (term) VALUES ('dup1') RETURNING concept_id")
            c1 = cur.fetchone()['concept_id']
            cur.execute("INSERT INTO concepts (term) VALUES ('dup2') RETURNING concept_id")
            c2 = cur.fetchone()['concept_id']

        a, b = min(c1, c2), max(c1, c2)
        with db_session.cursor() as cur:
            cur.execute("""
                INSERT INTO co_occurrences
                    (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                VALUES (%s, %s, 'History', 'History', 'unit', 1)
            """, (a, b))

        with pytest.raises(Exception, match='unique'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO co_occurrences
                        (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                    VALUES (%s, %s, 'History', 'History', 'unit', 2)
                """, (a, b))
        db_session.rollback()

        # Cleanup
        with db_session.cursor() as cur:
            cur.execute(
                "DELETE FROM co_occurrences WHERE concept_a_id = %s AND concept_b_id = %s",
                (a, b)
            )
            cur.execute("DELETE FROM concepts WHERE concept_id IN (%s, %s)", (c1, c2))

    def test_granularity_check_constraint_rejects_invalid(self, db_session):
        with db_session.cursor() as cur:
            cur.execute("INSERT INTO concepts (term) VALUES ('g1') RETURNING concept_id")
            c1 = cur.fetchone()['concept_id']
            cur.execute("INSERT INTO concepts (term) VALUES ('g2') RETURNING concept_id")
            c2 = cur.fetchone()['concept_id']

        a, b = min(c1, c2), max(c1, c2)
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO co_occurrences
                        (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                    VALUES (%s, %s, 'History', 'History', 'chapter', 1)
                """, (a, b))
        db_session.rollback()

        # Cleanup
        with db_session.cursor() as cur:
            cur.execute("DELETE FROM concepts WHERE concept_id IN (%s, %s)", (c1, c2))

    def test_weight_must_be_positive(self, db_session):
        with db_session.cursor() as cur:
            cur.execute("INSERT INTO concepts (term) VALUES ('w1') RETURNING concept_id")
            c1 = cur.fetchone()['concept_id']
            cur.execute("INSERT INTO concepts (term) VALUES ('w2') RETURNING concept_id")
            c2 = cur.fetchone()['concept_id']

        a, b = min(c1, c2), max(c1, c2)
        with pytest.raises(Exception, match='check'):
            with db_session.cursor() as cur:
                cur.execute("""
                    INSERT INTO co_occurrences
                        (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                    VALUES (%s, %s, 'History', 'History', 'lesson', 0)
                """, (a, b))
        db_session.rollback()

        with db_session.cursor() as cur:
            cur.execute("DELETE FROM concepts WHERE concept_id IN (%s, %s)", (c1, c2))
