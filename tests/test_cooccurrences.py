"""
Tests for co-occurrence SQL logic.

Exercises the three SQL queries (lesson, unit, year_group) directly against
the test database to verify correctness of join conditions, canonical ordering,
weight computation, and the absence of self-pairs.
"""

import pytest
import psycopg2.extras


# ── SQL copied verbatim from compute_cooccurrences.py ────────────────────────

LESSON_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)    AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id) AS concept_b_id,
        o1.subject                             AS subject_a,
        o2.subject                             AS subject_b,
        'lesson'                               AS granularity,
        COUNT(*)                               AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.slide_number = o2.slide_number
        AND o1.unit         = o2.unit
        AND o1.concept_id   < o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(*) > 0
"""

UNIT_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'unit'                                      AS granularity,
        COUNT(DISTINCT o1.unit)                     AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.unit        = o2.unit
        AND o1.subject     = o2.subject
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.unit) > 0
"""

YEAR_GROUP_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'year_group'                                AS granularity,
        COUNT(DISTINCT o1.year)                     AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.year        = o2.year
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.year) > 0
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def insert_concept(conn, term):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO concepts (term) VALUES (%s) RETURNING concept_id", (term,)
        )
        return cur.fetchone()['concept_id']


def insert_occurrence(conn, concept_id, subject='History', year=4,
                      term='Spring2', unit='Roman Britain', slide_number=1):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO occurrences
                (concept_id, subject, year, term, unit, slide_number, is_introduction)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
        """, (concept_id, subject, year, term, unit, slide_number))


def run_sql(conn, sql):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        return cur.fetchall()


# ── Canonical ordering ────────────────────────────────────────────────────────

class TestCanonicalOrdering:
    """concept_a_id must always be less than concept_b_id."""

    def test_lesson_ordering(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, slide_number=1)
        insert_occurrence(db, b, slide_number=1)

        rows = run_sql(db, LESSON_SQL)
        for row in rows:
            assert row['concept_a_id'] < row['concept_b_id'], \
                "concept_a_id must always be less than concept_b_id"

    def test_unit_ordering(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a)
        insert_occurrence(db, b)

        rows = run_sql(db, UNIT_SQL)
        for row in rows:
            assert row['concept_a_id'] < row['concept_b_id']

    def test_year_group_ordering(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, unit='Unit A')
        insert_occurrence(db, b, unit='Unit B')

        rows = run_sql(db, YEAR_GROUP_SQL)
        for row in rows:
            assert row['concept_a_id'] < row['concept_b_id']


# ── No self-pairs ─────────────────────────────────────────────────────────────

class TestNoSelfPairs:

    def test_lesson_no_self_pairs(self, db):
        a = insert_concept(db, 'empire')
        insert_occurrence(db, a, slide_number=1)
        insert_occurrence(db, a, slide_number=1)  # same concept, same slide

        rows = run_sql(db, LESSON_SQL)
        for row in rows:
            assert row['concept_a_id'] != row['concept_b_id']

    def test_unit_no_self_pairs(self, db):
        a = insert_concept(db, 'empire')
        insert_occurrence(db, a, slide_number=1)
        insert_occurrence(db, a, slide_number=2)  # same concept, different slide

        rows = run_sql(db, UNIT_SQL)
        for row in rows:
            assert row['concept_a_id'] != row['concept_b_id']


# ── Lesson-level join correctness ─────────────────────────────────────────────

class TestLessonCooccurrence:

    def test_same_slide_same_unit_produces_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, unit='Roman Britain', slide_number=5)
        insert_occurrence(db, b, unit='Roman Britain', slide_number=5)

        rows = run_sql(db, LESSON_SQL)
        assert len(rows) == 1

    def test_different_slides_same_unit_no_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, unit='Roman Britain', slide_number=5)
        insert_occurrence(db, b, unit='Roman Britain', slide_number=6)

        rows = run_sql(db, LESSON_SQL)
        assert len(rows) == 0

    def test_same_slide_number_different_unit_no_pair(self, db):
        # slide_number resets per unit — slide 5 in Unit A ≠ slide 5 in Unit B
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, unit='Roman Britain',  slide_number=5)
        insert_occurrence(db, b, unit='Anglo-Saxons',   slide_number=5)

        rows = run_sql(db, LESSON_SQL)
        assert len(rows) == 0

    def test_weight_counts_shared_slides(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        # Appear together on slides 5 and 7
        insert_occurrence(db, a, unit='Roman Britain', slide_number=5)
        insert_occurrence(db, b, unit='Roman Britain', slide_number=5)
        insert_occurrence(db, a, unit='Roman Britain', slide_number=7)
        insert_occurrence(db, b, unit='Roman Britain', slide_number=7)

        rows = run_sql(db, LESSON_SQL)
        assert len(rows) == 1
        assert rows[0]['weight'] == 2

    def test_no_pair_when_concepts_never_share_slide(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, unit='Roman Britain', slide_number=1)
        insert_occurrence(db, b, unit='Roman Britain', slide_number=2)
        insert_occurrence(db, a, unit='Roman Britain', slide_number=3)

        rows = run_sql(db, LESSON_SQL)
        assert len(rows) == 0


# ── Unit-level join correctness ───────────────────────────────────────────────

class TestUnitCooccurrence:

    def test_same_unit_same_subject_produces_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, subject='History', unit='Roman Britain', slide_number=1)
        insert_occurrence(db, b, subject='History', unit='Roman Britain', slide_number=3)

        rows = run_sql(db, UNIT_SQL)
        assert len(rows) == 1

    def test_different_units_same_subject_no_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, subject='History', unit='Roman Britain', slide_number=1)
        insert_occurrence(db, b, subject='History', unit='Anglo-Saxons',  slide_number=1)

        rows = run_sql(db, UNIT_SQL)
        assert len(rows) == 0

    def test_same_unit_name_different_subject_no_pair(self, db):
        # Unit join also requires subject match for unit-level SQL
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, subject='History',   unit='Shared Unit', slide_number=1)
        insert_occurrence(db, b, subject='Geography', unit='Shared Unit', slide_number=1)

        rows = run_sql(db, UNIT_SQL)
        assert len(rows) == 0

    def test_weight_counts_distinct_units(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        # Together in two different units
        insert_occurrence(db, a, subject='History', unit='Roman Britain', slide_number=1)
        insert_occurrence(db, b, subject='History', unit='Roman Britain', slide_number=2)
        insert_occurrence(db, a, subject='History', unit='Medieval Trade', slide_number=1)
        insert_occurrence(db, b, subject='History', unit='Medieval Trade', slide_number=3)

        rows = run_sql(db, UNIT_SQL)
        assert len(rows) == 1
        assert rows[0]['weight'] == 2


# ── Year-group-level join correctness ────────────────────────────────────────

class TestYearGroupCooccurrence:

    def test_same_year_different_units_produces_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'irrigation')
        insert_occurrence(db, a, subject='History',   year=4, unit='Roman Britain',   slide_number=1)
        insert_occurrence(db, b, subject='Geography', year=4, unit='Rivers',          slide_number=1)

        rows = run_sql(db, YEAR_GROUP_SQL)
        # At least one pair across subjects
        pairs = {(r['concept_a_id'], r['concept_b_id']) for r in rows}
        min_id, max_id = min(a, b), max(a, b)
        assert (min_id, max_id) in pairs

    def test_different_years_no_pair(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'irrigation')
        insert_occurrence(db, a, year=3, unit='Unit A', slide_number=1)
        insert_occurrence(db, b, year=5, unit='Unit B', slide_number=1)

        rows = run_sql(db, YEAR_GROUP_SQL)
        min_id, max_id = min(a, b), max(a, b)
        pairs = {(r['concept_a_id'], r['concept_b_id']) for r in rows}
        assert (min_id, max_id) not in pairs

    def test_weight_counts_distinct_years(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        # Together in year 3 and year 5
        insert_occurrence(db, a, subject='History', year=3, unit='A', slide_number=1)
        insert_occurrence(db, b, subject='History', year=3, unit='B', slide_number=1)
        insert_occurrence(db, a, subject='History', year=5, unit='C', slide_number=1)
        insert_occurrence(db, b, subject='History', year=5, unit='D', slide_number=1)

        rows = run_sql(db, YEAR_GROUP_SQL)
        # Find the pair
        pair_rows = [r for r in rows
                     if r['concept_a_id'] == min(a, b) and r['concept_b_id'] == max(a, b)]
        assert len(pair_rows) >= 1
        assert any(r['weight'] == 2 for r in pair_rows)


# ── is_cross_subject generated column ────────────────────────────────────────

class TestCrossSubjectFlag:

    def test_same_subject_co_occurrence_is_not_cross_subject(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'trade')
        insert_occurrence(db, a, subject='History', unit='Roman Britain', slide_number=1)
        insert_occurrence(db, b, subject='History', unit='Roman Britain', slide_number=1)

        # Insert directly into co_occurrences to test the generated column
        a_id, b_id = min(a, b), max(a, b)
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO co_occurrences
                    (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                VALUES (%s, %s, 'History', 'History', 'lesson', 1)
                RETURNING is_cross_subject
            """, (a_id, b_id))
            row = cur.fetchone()
        assert row['is_cross_subject'] is False

    def test_different_subject_co_occurrence_is_cross_subject(self, db):
        a = insert_concept(db, 'empire')
        b = insert_concept(db, 'irrigation')
        a_id, b_id = min(a, b), max(a, b)
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO co_occurrences
                    (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
                VALUES (%s, %s, 'History', 'Geography', 'lesson', 1)
                RETURNING is_cross_subject
            """, (a_id, b_id))
            row = cur.fetchone()
        assert row['is_cross_subject'] is True
