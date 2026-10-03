-- 009: introductions dropped from a current vocab list but referenced by a
-- confirmed edge are kept as recurrences (Phase 2 list alignment, 2026-10-03).
--
-- align_vocab_lists.py deletes introductions that are no longer on the unit's
-- current authored list. Where a human-confirmed edge points at the row it is
-- demoted instead: vocab_source = 'list_removed', is_introduction = 0. The view
-- treats these as recurrences, so the edge stays valid.

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
    c.authored_term
FROM classified c
JOIN concepts k    ON k.concept_id = c.concept_id
JOIN first_intro f ON f.concept_id = c.concept_id
WHERE k.term ~ '[[:alpha:]]'
  AND k.merged_into IS NULL
  AND (c.is_introduction OR c.curriculum_pos >= f.first_intro_pos);

COMMENT ON VIEW v_occurrences IS
  'Single inclusion rule for occurrences (migrations 007-009). Read this, not occurrences.';
