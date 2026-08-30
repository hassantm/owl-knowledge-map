-- Migration 002: Create co_occurrences table
-- Concept-to-concept co-occurrence graph at three granularities.
-- Safe to re-run: uses IF NOT EXISTS throughout.

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

    -- Enforce canonical ordering (a < b) to prevent mirrored duplicates
    CONSTRAINT concept_ordering
        CHECK (concept_a_id < concept_b_id)
);

CREATE INDEX IF NOT EXISTS idx_co_occ_concept_a
    ON co_occurrences(concept_a_id);

CREATE INDEX IF NOT EXISTS idx_co_occ_concept_b
    ON co_occurrences(concept_b_id);

CREATE INDEX IF NOT EXISTS idx_co_occ_cross_subject
    ON co_occurrences(is_cross_subject)
    WHERE is_cross_subject = true;

CREATE INDEX IF NOT EXISTS idx_co_occ_granularity
    ON co_occurrences(granularity);
