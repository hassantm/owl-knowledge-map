-- Semantic Neighbourhood Query
-- Retrieves the 10 closest co-occurring concepts for a given concept_id.
-- Usage: substitute the target concept_id for :concept_id

SELECT
    c2.term,
    co.subject_a,
    co.subject_b,
    co.is_cross_subject,
    co.granularity,
    co.weight
FROM co_occurrences co
JOIN concepts c2
    ON c2.concept_id = CASE
        WHEN co.concept_a_id = :concept_id THEN co.concept_b_id
        ELSE co.concept_a_id
    END
WHERE (co.concept_a_id = :concept_id OR co.concept_b_id = :concept_id)
  AND co.granularity = 'lesson'
ORDER BY co.is_cross_subject DESC, co.weight DESC
LIMIT 10;
