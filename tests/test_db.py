"""
Tests for db.py — database query layer.

Requires the owl_test PostgreSQL database (see conftest.py).
Tests use the `db` fixture which truncates tables between each test.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'enrichment'))

# Patch DATABASE_URL before importing db.py so it connects to the test database
os.environ.setdefault(
    'DATABASE_URL',
    'postgresql://htmadmin:dev@localhost:5432/owl_test'
)

import db as db_module


# ── Helpers ──────────────────────────────────────────────────────────────────

def insert_concept(conn, term, subject_area=None, status='pending'):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO concepts (term, subject_area, enrichment_status)
            VALUES (%s, %s, %s)
            RETURNING concept_id
        """, (term, subject_area, status))
        return cur.fetchone()['concept_id']


def insert_occurrence(conn, concept_id, subject='History', year=4,
                      term='Spring2', unit='Roman Britain', slide_number=1):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO occurrences
                (concept_id, subject, year, term, unit, slide_number, is_introduction)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            RETURNING occurrence_id
        """, (concept_id, subject, year, term, unit, slide_number))
        return cur.fetchone()['occurrence_id']


# ── get_pending_concepts ──────────────────────────────────────────────────────

class TestGetPendingConcepts:

    def test_returns_only_pending(self, db):
        pending_id  = insert_concept(db, 'empire',   status='pending')
        approved_id = insert_concept(db, 'trade',    status='approved')
        generated_id = insert_concept(db, 'dynasty', status='generated')
        insert_occurrence(db, pending_id)
        insert_occurrence(db, approved_id)
        insert_occurrence(db, generated_id)

        results = db_module.get_pending_concepts(db)
        terms = [r['term'] for r in results]
        assert 'empire' in terms
        assert 'trade' not in terms
        assert 'dynasty' not in terms

    def test_result_contains_required_fields(self, db):
        cid = insert_concept(db, 'irrigation')
        insert_occurrence(db, cid, subject='Geography', year=5)

        results = db_module.get_pending_concepts(db)
        assert len(results) == 1
        row = results[0]
        assert 'id' in row
        assert 'term' in row
        assert 'subjects' in row
        assert 'years' in row

    def test_aggregates_subjects_across_occurrences(self, db):
        cid = insert_concept(db, 'evidence')
        insert_occurrence(db, cid, subject='History',   year=4, unit='Unit A', slide_number=1)
        insert_occurrence(db, cid, subject='Geography', year=5, unit='Unit B', slide_number=1)

        results = db_module.get_pending_concepts(db)
        assert len(results) == 1
        row = results[0]
        assert set(row['subjects']) == {'History', 'Geography'}
        assert set(row['years']) == {4, 5}

    def test_no_duplicate_subjects(self, db):
        cid = insert_concept(db, 'trade')
        insert_occurrence(db, cid, subject='History', year=4, unit='Unit A', slide_number=1)
        insert_occurrence(db, cid, subject='History', year=5, unit='Unit B', slide_number=2)

        results = db_module.get_pending_concepts(db)
        row = results[0]
        assert row['subjects'].count('History') == 1

    def test_returns_empty_list_when_none_pending(self, db):
        cid = insert_concept(db, 'dynasty', status='approved')
        insert_occurrence(db, cid)

        results = db_module.get_pending_concepts(db)
        assert results == []


# ── write_generated ───────────────────────────────────────────────────────────

class TestWriteGenerated:

    ENRICHMENT = {
        'definition':  'A territory controlled by a single ruler.',
        'etymology':   'From Latin imperium.',
        'word_family': ['empire', 'imperial', 'emperor'],
        'register':    'subject-specific',
        'tier':        3,
    }

    def test_sets_status_to_generated(self, db):
        cid = insert_concept(db, 'empire')
        db_module.write_generated(db, cid, self.ENRICHMENT)

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_status FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_status'] == 'generated'

    def test_writes_all_enrichment_fields(self, db):
        cid = insert_concept(db, 'empire')
        db_module.write_generated(db, cid, self.ENRICHMENT)

        with db.cursor() as cur:
            cur.execute("""
                SELECT definition, etymology, word_family, register, tier
                FROM concepts WHERE concept_id = %s
            """, (cid,))
            row = cur.fetchone()

        assert row['definition'] == self.ENRICHMENT['definition']
        assert row['etymology']  == self.ENRICHMENT['etymology']
        assert row['register']   == self.ENRICHMENT['register']
        assert row['tier']       == self.ENRICHMENT['tier']
        assert list(row['word_family']) == self.ENRICHMENT['word_family']

    def test_sets_enriched_at_timestamp(self, db):
        cid = insert_concept(db, 'empire')
        db_module.write_generated(db, cid, self.ENRICHMENT)

        with db.cursor() as cur:
            cur.execute("SELECT enriched_at FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enriched_at'] is not None


# ── write_approved ────────────────────────────────────────────────────────────

class TestWriteApproved:

    FIELDS = {
        'definition':  'A territory controlled by a single ruler.',
        'etymology':   'From Latin imperium.',
        'word_family': ['empire', 'imperial'],
        'register':    'subject-specific',
        'tier':        3,
    }

    def test_sets_status_to_approved(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.write_approved(db, cid, self.FIELDS, notes='Looks good', reviewer='HM')

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_status FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_status'] == 'approved'

    def test_sets_enriched_by_to_reviewer(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.write_approved(db, cid, self.FIELDS, notes=None, reviewer='HM')

        with db.cursor() as cur:
            cur.execute("SELECT enriched_by FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enriched_by'] == 'HM'

    def test_saves_reviewer_notes(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.write_approved(db, cid, self.FIELDS, notes='Edited definition', reviewer='HM')

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_notes FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_notes'] == 'Edited definition'

    def test_null_notes_allowed(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.write_approved(db, cid, self.FIELDS, notes=None, reviewer='HM')

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_notes FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_notes'] is None


# ── set_status ────────────────────────────────────────────────────────────────

class TestSetStatus:

    def test_rejected_sets_status(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.set_status(db, cid, 'rejected', 'Definition too vague')

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_status, enrichment_notes FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_status'] == 'rejected'
        assert row['enrichment_notes'] == 'Definition too vague'

    def test_rejected_to_pending_state_machine(self, db):
        cid = insert_concept(db, 'empire', status='rejected')
        db_module.set_status(db, cid, 'pending')

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_status FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_status'] == 'pending'

    def test_null_notes_does_not_overwrite_existing_notes(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        db_module.set_status(db, cid, 'rejected', 'Original note')
        db_module.set_status(db, cid, 'pending', None)

        with db.cursor() as cur:
            cur.execute("SELECT enrichment_notes FROM concepts WHERE concept_id = %s", (cid,))
            row = cur.fetchone()
        assert row['enrichment_notes'] == 'Original note'


# ── get_next_for_review ───────────────────────────────────────────────────────

class TestGetNextForReview:

    def test_returns_generated_concept(self, db):
        cid = insert_concept(db, 'empire', status='generated')
        result = db_module.get_next_for_review(db)
        assert result is not None
        assert result['term'] == 'empire'

    def test_returns_none_when_queue_empty(self, db):
        insert_concept(db, 'empire', status='pending')
        result = db_module.get_next_for_review(db)
        assert result is None

    def test_skips_approved_concepts(self, db):
        insert_concept(db, 'empire', status='approved')
        result = db_module.get_next_for_review(db)
        assert result is None

    def test_returns_lowest_concept_id_first(self, db):
        # Insert two generated concepts — first inserted should be returned first
        cid1 = insert_concept(db, 'aardvark', status='generated')
        cid2 = insert_concept(db, 'zebra',    status='generated')
        result = db_module.get_next_for_review(db)
        assert result['id'] == cid1

    def test_result_contains_all_display_fields(self, db):
        insert_concept(db, 'empire', status='generated')
        result = db_module.get_next_for_review(db)
        for field in ('id', 'term', 'definition', 'etymology',
                      'word_family', 'register', 'tier', 'enrichment_notes'):
            assert field in result, f"Expected field '{field}' in review result"


# ── get_enrichment_summary ────────────────────────────────────────────────────

class TestGetEnrichmentSummary:

    def test_returns_correct_counts(self, db):
        insert_concept(db, 'a', status='pending')
        insert_concept(db, 'b', status='pending')
        insert_concept(db, 'c', status='generated')
        insert_concept(db, 'd', status='approved')

        summary = db_module.get_enrichment_summary(db)
        assert summary['pending']   == 2
        assert summary['generated'] == 1
        assert summary['approved']  == 1

    def test_omits_zero_count_statuses(self, db):
        # If no concepts are rejected, 'rejected' key should be absent
        insert_concept(db, 'a', status='pending')
        summary = db_module.get_enrichment_summary(db)
        assert 'rejected' not in summary

    def test_returns_empty_dict_when_no_concepts(self, db):
        summary = db_module.get_enrichment_summary(db)
        assert summary == {}
