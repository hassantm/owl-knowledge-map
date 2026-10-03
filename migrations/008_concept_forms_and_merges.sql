-- 008: concept forms, soft merges and authored terms (Phase 2, 2026-10-03).
--
-- Method (docs/20261003_method_reset_plan.md): a concept is a vocab-list entry,
-- recurrences match inflected forms, and terms are kept exactly as authored.
-- Concepts that are forms of one word (empire/empires, Prophet/prophet) become
-- one concept, so matching does not double count:
--   * concepts.merged_into   points a merged concept at the concept it now lives in;
--                            the row is kept so the merge is traceable and reversible.
--   * occurrences.authored_term  the term exactly as written on the vocab list for
--                            that introduction (NULL for gap-fill recurrences).
--   * concept_forms          every form a concept is matched by: authored spellings
--                            and lemmatiser-generated inflections, each reviewable.

ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS merged_into INTEGER REFERENCES concepts(concept_id);

ALTER TABLE occurrences
    ADD COLUMN IF NOT EXISTS authored_term TEXT;

CREATE TABLE IF NOT EXISTS concept_forms (
    form_id     SERIAL PRIMARY KEY,
    concept_id  INTEGER NOT NULL REFERENCES concepts(concept_id),
    form        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('authored', 'inflection')),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('approved', 'pending', 'rejected')),
    source      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS concept_forms_concept_form_uq
    ON concept_forms (concept_id, lower(form));
CREATE INDEX IF NOT EXISTS idx_concept_forms_status ON concept_forms (status);

-- v_occurrences gains authored_term (appended: CREATE OR REPLACE VIEW can only add
-- columns at the end) and excludes merged concepts.
CREATE OR REPLACE VIEW v_occurrences AS
WITH placed AS (
    SELECT
        o.occurrence_id,
        o.concept_id,
        o.unit_id,
        u.subject,
        u.year,
        u.term,
        u.unit,
        o.chapter,
        o.slide_number,
        o.term_in_context,
        o.source_path,
        o.vocab_source,
        o.authored_term,
        o.is_introduction = 1 AS legacy_is_introduction,
        u.year * 10 + array_position(
            ARRAY['Autumn1','Autumn2','Spring1','Spring2','Summer1','Summer2'], u.term
        ) AS curriculum_pos,
        CASE
            WHEN o.vocab_source = 'booklet_gap_fill'  THEN 'gap_fill'
            WHEN o.vocab_source = 'bold_extraction'   THEN 'bold_only'
            WHEN o.vocab_source IS NULL               THEN 'unsourced'
            ELSE 'vocab_list'
        END AS intro_source
    FROM occurrences o
    JOIN units u ON u.unit_id = o.unit_id
),
classified AS (
    SELECT
        p.*,
        CASE
            WHEN p.intro_source = 'vocab_list' THEN TRUE
            WHEN p.intro_source = 'gap_fill'   THEN FALSE
            ELSE p.legacy_is_introduction
        END AS is_introduction
    FROM placed p
),
first_intro AS (
    SELECT concept_id, min(curriculum_pos) AS first_intro_pos
    FROM classified
    WHERE is_introduction
    GROUP BY concept_id
)
SELECT
    c.occurrence_id, c.concept_id, k.term AS concept_term,
    c.unit_id, c.subject, c.year, c.term, c.unit, c.curriculum_pos,
    c.chapter, c.slide_number, c.is_introduction, c.intro_source,
    c.term_in_context, c.source_path, c.vocab_source,
    c.authored_term
FROM classified c
JOIN concepts k    ON k.concept_id = c.concept_id
JOIN first_intro f ON f.concept_id = c.concept_id
WHERE k.term ~ '[[:alpha:]]'
  AND k.merged_into IS NULL
  AND (c.is_introduction OR c.curriculum_pos >= f.first_intro_pos);

COMMENT ON VIEW v_occurrences IS
  'Single inclusion rule for occurrences (migrations 007, 008). Read this, not occurrences.';
