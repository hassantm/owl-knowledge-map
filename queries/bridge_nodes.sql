-- Bridge Node League Table
-- Ranks concepts by how many distinct cross-subject pairs they connect.
-- Use granularity = 'unit' for a broader view.

SELECT
    c.concept_id,
    c.term,
    c.tier,
    COUNT(*)                                                AS total_cross_subject_links,
    COUNT(DISTINCT co.subject_a || '-' || co.subject_b)    AS distinct_subject_pairs,
    SUM(co.weight)                                         AS cumulative_weight,
    ARRAY_AGG(DISTINCT
        CASE WHEN co.concept_a_id = c.concept_id THEN co.subject_a
             ELSE co.subject_b END
    )                                                      AS subjects_involved
FROM concepts c
JOIN co_occurrences co
    ON  (co.concept_a_id = c.concept_id OR co.concept_b_id = c.concept_id)
    AND co.is_cross_subject = true
    AND co.granularity = 'year_group'  -- lesson/unit granularities are always within-subject
GROUP BY c.concept_id, c.term, c.tier
ORDER BY distinct_subject_pairs DESC, cumulative_weight DESC;
