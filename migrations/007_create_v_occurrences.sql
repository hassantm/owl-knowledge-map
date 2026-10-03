-- 007: one inclusion rule for which occurrences count as data.
-- Method decided 2026-10-03 (docs/20261003_method_reset_plan.md, Phase 1):
--   * a concept is an entry on a unit's core vocab list;
--   * introduction = the concept is on that unit's vocab list
--     (derived from vocab_source, not the legacy is_introduction flag);
--   * recurrence = booklet gap-fill match, counted only at or after the
--     concept's first introduction in curriculum order (year, then term);
--   * unit labels come from units, never the copies on occurrences.
-- Rows still awaiting a Phase 2 decision (bold-only or unsourced
-- introductions) are included but flagged via intro_source.
-- Every consumer (pipeline, dashboard API, story context) should read
-- this view instead of occurrences.

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
        -- Bold-only and unsourced rows keep their legacy flag until Phase 2 decides them.
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
    c.term_in_context, c.source_path, c.vocab_source
FROM classified c
JOIN concepts k    ON k.concept_id = c.concept_id
JOIN first_intro f ON f.concept_id = c.concept_id      -- concept must be introduced somewhere
WHERE k.term ~ '[[:alpha:]]'                           -- drop letterless junk (e.g. '–')
  AND (c.is_introduction OR c.curriculum_pos >= f.first_intro_pos);

COMMENT ON VIEW v_occurrences IS
  'Single inclusion rule for occurrences (migration 007, 2026-10-03). Read this, not occurrences.';
