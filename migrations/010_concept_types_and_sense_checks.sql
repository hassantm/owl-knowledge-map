-- 010: concept-type tags and recurrence sense checks (Phase 4, 2026-10-04).
--
-- Method (docs/20261003_method_reset_plan.md): every vocab-list entry stays in
-- the map, tagged by the kind of word it is, so views can filter; recurrences of
-- ambiguous terms are checked for sense, and a recurrence in a different sense
-- (river 'bank' vs money 'bank') does not count.

ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS concept_type TEXT
        CHECK (concept_type IN ('transferable', 'proper_noun', 'unit_specific')),
    ADD COLUMN IF NOT EXISTS concept_category TEXT
        CHECK (concept_category IN ('ABSTRACT', 'DESCRIPTIVE', 'HUMAN', 'MORAL', 'PROCESS', 'VERBADJ',
                                    'PROPER', 'SACRED', 'ACT',
                                    'TECHNICAL', 'INFRA', 'LABEL', 'SPECIES')),
    ADD COLUMN IF NOT EXISTS concept_type_note TEXT,
    ADD COLUMN IF NOT EXISTS is_ambiguous BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_concepts_concept_type ON concepts (concept_type);

ALTER TABLE occurrences
    ADD COLUMN IF NOT EXISTS sense_check TEXT
        CHECK (sense_check IN ('same', 'different', 'unclear')),
    ADD COLUMN IF NOT EXISTS sense_note TEXT;

-- Recurrences judged to be a different sense drop out of the inclusion rule.
-- The view also exposes sense_check (appended).
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
        o.sense_check,
        o.is_introduction = 1 AS legacy_is_introduction,
        u.year * 10 + array_position(
            ARRAY['Autumn1','Autumn2','Spring1','Spring2','Summer1','Summer2'], u.term
        ) AS curriculum_pos,
        CASE
            WHEN o.vocab_source = 'booklet_gap_fill'  THEN 'gap_fill'
            WHEN o.vocab_source = 'list_removed'      THEN 'list_removed'
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
            WHEN p.intro_source IN ('gap_fill', 'list_removed') THEN FALSE
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
    c.authored_term, c.sense_check
FROM classified c
JOIN concepts k    ON k.concept_id = c.concept_id
JOIN first_intro f ON f.concept_id = c.concept_id
WHERE k.term ~ '[[:alpha:]]'
  AND k.merged_into IS NULL
  AND c.sense_check IS DISTINCT FROM 'different'
  AND (c.is_introduction OR c.curriculum_pos >= f.first_intro_pos);

COMMENT ON VIEW v_occurrences IS
  'Single inclusion rule for occurrences (migrations 007-010). Read this, not occurrences.';
