"""
Pytest fixtures for vocabulary enrichment tests.

Uses a dedicated test database (owl_test) to avoid touching live data.
Set TEST_DATABASE_URL in environment to override the default connection.

Session-scoped fixture creates and tears down the full schema once per run.
Function-scoped fixture truncates tables between individual tests.
"""

import os
import pytest
import psycopg2
import psycopg2.extras

TEST_DB_URL = os.environ.get(
    'TEST_DATABASE_URL',
    'postgresql://htmadmin:dev@localhost:5432/owl_test'
)

# Base schema matching the live owl database exactly
BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concepts (
    concept_id   serial  PRIMARY KEY,
    term         text    NOT NULL,
    subject_area text
);

CREATE TABLE IF NOT EXISTS occurrences (
    occurrence_id       serial  PRIMARY KEY,
    concept_id          integer REFERENCES concepts(concept_id),
    subject             text    NOT NULL,
    year                integer NOT NULL,
    term                text    NOT NULL,
    unit                text    NOT NULL,
    chapter             text,
    slide_number        integer,
    is_introduction     integer NOT NULL,
    term_in_context     text,
    source_path         text,
    needs_review        integer DEFAULT 0,
    review_reason       text,
    validation_status   text,
    vocab_confidence    float,
    vocab_match_type    text,
    vocab_source        text,
    audit_decision      text,
    audit_notes         text
);

CREATE TABLE IF NOT EXISTS edges (
    edge_id         serial  PRIMARY KEY,
    from_occurrence integer REFERENCES occurrences(occurrence_id),
    to_occurrence   integer REFERENCES occurrences(occurrence_id),
    edge_type       text,
    edge_nature     text,
    confirmed_by    text,
    confirmed_date  text
);
"""

ENRICHMENT_MIGRATION_SQL = """
ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS definition         text,
    ADD COLUMN IF NOT EXISTS etymology          text,
    ADD COLUMN IF NOT EXISTS word_family        text[],
    ADD COLUMN IF NOT EXISTS register           text
        CHECK (register IN (
            'subject-specific', 'formal academic', 'technical', 'general formal'
        )),
    ADD COLUMN IF NOT EXISTS tier               integer
        CHECK (tier IN (1, 2, 3)),
    ADD COLUMN IF NOT EXISTS enrichment_status  text
        NOT NULL DEFAULT 'pending'
        CHECK (enrichment_status IN ('pending', 'generated', 'approved', 'rejected')),
    ADD COLUMN IF NOT EXISTS enrichment_notes   text,
    ADD COLUMN IF NOT EXISTS enriched_at        timestamptz,
    ADD COLUMN IF NOT EXISTS enriched_by        text DEFAULT 'claude-batch';
"""

CO_OCCURRENCES_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS co_occurrences (
    id              serial  PRIMARY KEY,
    concept_a_id    integer NOT NULL REFERENCES concepts(concept_id),
    concept_b_id    integer NOT NULL REFERENCES concepts(concept_id),
    subject_a       text    NOT NULL,
    subject_b       text    NOT NULL,
    granularity     text    NOT NULL
        CHECK (granularity IN ('lesson', 'unit', 'year_group')),
    weight          integer NOT NULL CHECK (weight > 0),
    is_cross_subject boolean GENERATED ALWAYS AS (subject_a != subject_b) STORED,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT co_occurrences_unique
        UNIQUE (concept_a_id, concept_b_id, subject_a, subject_b, granularity),
    CONSTRAINT concept_ordering
        CHECK (concept_a_id < concept_b_id)
);
CREATE INDEX IF NOT EXISTS idx_co_occ_concept_a     ON co_occurrences(concept_a_id);
CREATE INDEX IF NOT EXISTS idx_co_occ_concept_b     ON co_occurrences(concept_b_id);
CREATE INDEX IF NOT EXISTS idx_co_occ_cross_subject ON co_occurrences(is_cross_subject)
    WHERE is_cross_subject = true;
CREATE INDEX IF NOT EXISTS idx_co_occ_granularity   ON co_occurrences(granularity);
"""


@pytest.fixture(scope='session')
def db_session():
    """
    Session-scoped connection to owl_test.
    Creates the full schema (base + both migrations) once per test run.
    Drops and recreates tables to ensure a clean starting state.
    """
    conn = psycopg2.connect(TEST_DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True

    with conn.cursor() as cur:
        # Drop in reverse dependency order
        cur.execute("""
            DROP TABLE IF EXISTS co_occurrences CASCADE;
            DROP TABLE IF EXISTS edges CASCADE;
            DROP TABLE IF EXISTS occurrences CASCADE;
            DROP TABLE IF EXISTS concepts CASCADE;
        """)
        cur.execute(BASE_SCHEMA_SQL)
        cur.execute(ENRICHMENT_MIGRATION_SQL)
        cur.execute(CO_OCCURRENCES_MIGRATION_SQL)

    yield conn
    conn.close()


@pytest.fixture
def db(db_session):
    """
    Function-scoped fixture. Truncates all tables before each test and
    returns an open connection using a transaction (rolled back on teardown).
    """
    conn = db_session

    with conn.cursor() as cur:
        cur.execute("""
            TRUNCATE co_occurrences, edges, occurrences, concepts
            RESTART IDENTITY CASCADE
        """)

    yield conn


@pytest.fixture
def sample_concepts(db):
    """Insert a small set of concepts and return their ids."""
    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO concepts (term, subject_area) VALUES
                ('empire',        'History'),
                ('trade',         'History'),
                ('irrigation',    'Geography'),
                ('monotheism',    'Religion'),
                ('evidence',      NULL)
            RETURNING concept_id, term
        """)
        rows = cur.fetchall()
    return {row['term']: row['concept_id'] for row in rows}


@pytest.fixture
def sample_occurrences(db, sample_concepts):
    """
    Insert occurrences covering several test scenarios:
    - empire and trade appear on the same slide in the same unit (lesson co-occurrence)
    - empire and irrigation appear in the same year but different subjects (year_group co-occurrence)
    - monotheism appears in a different unit, same subject as empire
    """
    c = sample_concepts
    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO occurrences
                (concept_id, subject, year, term, unit, slide_number, is_introduction)
            VALUES
                -- empire + trade on same slide, same unit → lesson co-occurrence
                (%(empire)s,      'History',   4, 'Spring2', 'Roman Britain',        5, 1),
                (%(trade)s,       'History',   4, 'Spring2', 'Roman Britain',        5, 1),
                -- empire appears on a different slide in same unit
                (%(empire)s,      'History',   4, 'Spring2', 'Roman Britain',        7, 0),
                -- irrigation in same year as empire but different subject
                (%(irrigation)s,  'Geography', 4, 'Autumn1', 'Rivers and valleys',   3, 1),
                -- monotheism in same subject as empire but different unit
                (%(monotheism)s,  'Religion',  5, 'Spring1', 'World religions',      2, 1),
                -- evidence appears in a completely different year
                (%(evidence)s,    'History',   6, 'Summer1', 'The Enlightenment',    1, 1)
            RETURNING occurrence_id
        """, c)
    return c
