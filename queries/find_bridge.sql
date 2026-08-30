-- Two-Hop Bridge Finder
-- Given two concepts in different subjects, finds what bridge concept connects them.
-- Usage: substitute concept terms for :concept_a and :concept_b

WITH cross_subject AS (
    SELECT concept_a_id, concept_b_id, subject_a, subject_b, weight
    FROM co_occurrences
    WHERE is_cross_subject = true
      AND granularity IN ('lesson', 'unit')
)
SELECT
    c_bridge.term                          AS bridge_concept,
    c_a.term                               AS concept_a,
    c_b.term                               AS concept_b,
    left_path.subject_a                    AS subject_a,
    right_path.subject_b                   AS subject_b,
    left_path.weight + right_path.weight   AS total_path_weight
FROM cross_subject left_path
JOIN cross_subject right_path  ON left_path.concept_b_id = right_path.concept_a_id
JOIN concepts c_bridge ON c_bridge.concept_id = left_path.concept_b_id
JOIN concepts c_a      ON c_a.concept_id      = left_path.concept_a_id
JOIN concepts c_b      ON c_b.concept_id      = right_path.concept_b_id
WHERE c_a.term = :concept_a
  AND c_b.term = :concept_b
ORDER BY total_path_weight DESC;
