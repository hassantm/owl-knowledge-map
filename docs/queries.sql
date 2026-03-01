-- OWL Knowledge Map — Analytical SQL Queries
-- For direct use against: db/owl_knowledge_map.db
--
-- Open with: sqlite3 db/owl_knowledge_map.db
-- Run a query: sqlite3 db/owl_knowledge_map.db < docs/queries.sql
-- Pretty output: .mode column / .headers on (run in sqlite3 REPL first)
--
-- Created: 2026-03-01


-- ============================================================
-- SETUP (run in sqlite3 REPL for readable output)
-- ============================================================
-- .mode column
-- .headers on
-- .width 25 4 8 30 8 8 8


-- ============================================================
-- 1. VOCABULARY DENSITY BY UNIT
--    Which units are most vocabulary-heavy?
--    Reveals the "knowledge-loading" moments in the curriculum.
-- ============================================================

SELECT
    o.subject,
    o.year,
    o.term                                                              AS term_period,
    o.unit,
    COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)                  AS introductions,
    COUNT(*)                                                            AS total_occurrences,
    ROUND(
        COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                                                   AS intro_pct
FROM occurrences o
WHERE o.validation_status = 'confirmed'
GROUP BY o.subject, o.year, o.term, o.unit
ORDER BY introductions DESC, total_occurrences DESC;


-- ============================================================
-- 2. INTRODUCTION vs RECURRENCE RATIO BY SUBJECT
--    Which subject introduces most new vocabulary vs consolidates?
--    High intro% = knowledge-loading subject
--    High recurrence% = consolidation/application subject
-- ============================================================

SELECT
    subject,
    COUNT(CASE WHEN is_introduction = 1 THEN 1 END)    AS introductions,
    COUNT(CASE WHEN is_introduction = 0 THEN 1 END)    AS recurrences,
    COUNT(*)                                            AS total,
    ROUND(
        COUNT(CASE WHEN is_introduction = 1 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                                   AS intro_pct,
    ROUND(
        COUNT(CASE WHEN is_introduction = 0 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                                   AS recurrence_pct
FROM occurrences
WHERE validation_status = 'confirmed'
GROUP BY subject
ORDER BY intro_pct DESC;


-- ============================================================
-- 3. ORPHANED CONCEPTS (introduced once, never revisited)
--    Either noise that slipped through review, or genuine
--    curriculum gaps — concepts introduced but never built upon.
-- ============================================================

SELECT
    c.term,
    c.subject_area,
    o.subject,
    o.year,
    o.term      AS term_period,
    o.unit
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.is_introduction = 1
  AND o.validation_status = 'confirmed'
  AND (
      SELECT COUNT(*) FROM occurrences o2
      WHERE o2.concept_id = c.concept_id
        AND o2.validation_status = 'confirmed'
  ) = 1
ORDER BY o.subject, o.year,
    CASE o.term
        WHEN 'Autumn1' THEN 1 WHEN 'Autumn2' THEN 2
        WHEN 'Spring1' THEN 3 WHEN 'Spring2' THEN 4
        WHEN 'Summer1' THEN 5 WHEN 'Summer2' THEN 6 ELSE 7
    END,
    c.term;


-- Quick count of orphans
SELECT COUNT(*) AS orphaned_concept_count
FROM concepts c
WHERE (
    SELECT COUNT(*) FROM occurrences o
    WHERE o.concept_id = c.concept_id
      AND o.validation_status = 'confirmed'
) = 1
AND EXISTS (
    SELECT 1 FROM occurrences o
    WHERE o.concept_id = c.concept_id
      AND o.is_introduction = 1
);


-- ============================================================
-- 4. CROSS-SUBJECT VOCABULARY OVERLAP
--    Terms appearing in more than one subject.
--    This is your cross-subject candidate pool — queryable
--    right now, before any edges are confirmed.
-- ============================================================

SELECT
    c.term,
    COUNT(DISTINCT o.subject)                               AS subject_count,
    GROUP_CONCAT(DISTINCT o.subject ORDER BY o.subject)    AS subjects,
    COUNT(*)                                                AS total_occurrences,
    MIN(o.year)                                             AS first_year,
    MAX(o.year)                                             AS last_year
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.validation_status = 'confirmed'
GROUP BY c.concept_id
HAVING COUNT(DISTINCT o.subject) > 1
ORDER BY subject_count DESC, total_occurrences DESC, c.term;


-- Terms spanning ALL THREE subjects
SELECT
    c.term,
    GROUP_CONCAT(DISTINCT o.subject ORDER BY o.subject)    AS subjects,
    COUNT(*)                                                AS total_occurrences
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.validation_status = 'confirmed'
GROUP BY c.concept_id
HAVING COUNT(DISTINCT o.subject) = 3
ORDER BY total_occurrences DESC;


-- ============================================================
-- 5. YEAR-ON-YEAR VOCABULARY GROWTH RATIO
--    Tests whether the curriculum architecture is sound:
--    Year 6 should be recurrence-heavy (applying prior knowledge)
--    not introducing lots of new terms.
-- ============================================================

SELECT
    year,
    COUNT(CASE WHEN is_introduction = 1 THEN 1 END)    AS new_terms,
    COUNT(CASE WHEN is_introduction = 0 THEN 1 END)    AS recurrences,
    COUNT(*)                                            AS total,
    ROUND(
        COUNT(CASE WHEN is_introduction = 0 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                                   AS recurrence_pct
FROM occurrences
WHERE validation_status = 'confirmed'
GROUP BY year
ORDER BY year;


-- Same but broken down by subject per year
SELECT
    year,
    subject,
    COUNT(CASE WHEN is_introduction = 1 THEN 1 END)    AS new_terms,
    COUNT(CASE WHEN is_introduction = 0 THEN 1 END)    AS recurrences,
    ROUND(
        COUNT(CASE WHEN is_introduction = 0 THEN 1 END) * 100.0
        / COUNT(*), 1
    )                                                   AS recurrence_pct
FROM occurrences
WHERE validation_status = 'confirmed'
GROUP BY year, subject
ORDER BY year, subject;


-- ============================================================
-- 6. CHAPTER-LEVEL VOCABULARY CLUSTERING
--    Which chapters do the heavy knowledge-loading?
--    Which are consolidation chapters?
-- ============================================================

SELECT
    o.subject,
    o.year,
    o.unit,
    o.chapter,
    COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)  AS introductions,
    COUNT(CASE WHEN o.is_introduction = 0 THEN 1 END)  AS recurrences,
    COUNT(*)                                            AS total
FROM occurrences o
WHERE o.validation_status = 'confirmed'
  AND o.chapter IS NOT NULL
  AND o.chapter != ''
GROUP BY o.subject, o.year, o.unit, o.chapter
HAVING introductions > 0
ORDER BY introductions DESC
LIMIT 30;


-- ============================================================
-- 7. TERM LONGEVITY
--    How many years does a term stay "in play"?
--    Long-lived terms are candidates for the most interesting edges.
-- ============================================================

SELECT
    c.term,
    c.subject_area,
    MIN(o.year)                     AS introduced_year,
    MAX(o.year)                     AS last_seen_year,
    MAX(o.year) - MIN(o.year) + 1  AS years_active,
    COUNT(*)                        AS total_occurrences
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.validation_status = 'confirmed'
GROUP BY c.concept_id
HAVING total_occurrences > 1
ORDER BY years_active DESC, total_occurrences DESC
LIMIT 40;


-- ============================================================
-- 8. CROSS-SUBJECT EDGE REVIEW PRIORITY QUEUE
--    Multi-subject terms with 3+ occurrences.
--    Start edge review with these — highest analytical value.
-- ============================================================

SELECT
    c.concept_id,
    c.term,
    COUNT(DISTINCT o.subject)                               AS subject_count,
    GROUP_CONCAT(DISTINCT o.subject ORDER BY o.subject)    AS subjects,
    COUNT(*)                                                AS total_occurrences,
    COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)      AS introductions,
    MIN(o.year)                                             AS first_year,
    MAX(o.year)                                             AS last_year,
    (
        SELECT COUNT(*) FROM edges e
        JOIN occurrences oe
            ON e.from_occurrence = oe.occurrence_id
            OR e.to_occurrence = oe.occurrence_id
        WHERE oe.concept_id = c.concept_id
          AND e.confirmed_by IS NOT NULL
    )                                                       AS confirmed_edges
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.validation_status = 'confirmed'
GROUP BY c.concept_id
HAVING COUNT(DISTINCT o.subject) > 1
   AND COUNT(*) >= 3
ORDER BY subject_count DESC, total_occurrences DESC
LIMIT 50;


-- ============================================================
-- 9. CONCEPTS INTRODUCED IN YEAR 3/4 BUT ABSENT FROM YEAR 5/6
--    "Dropped" concepts — introduced early but never built upon
--    in the upper years. Genuine curriculum gaps or intentional?
-- ============================================================

SELECT
    c.term,
    c.subject_area,
    MIN(o.year)     AS introduced_year,
    MAX(o.year)     AS last_seen_year,
    COUNT(*)        AS total_occurrences
FROM concepts c
JOIN occurrences o ON c.concept_id = o.concept_id
WHERE o.validation_status = 'confirmed'
GROUP BY c.concept_id
HAVING MIN(o.year) <= 4      -- introduced in Y3 or Y4
   AND MAX(o.year) <= 4      -- never appears in Y5 or Y6
   AND COUNT(*) > 1          -- not orphaned (has recurrences within Y3-Y4)
ORDER BY total_occurrences DESC, c.term;


-- ============================================================
-- 10. SLIDE-LEVEL DENSITY
--     Slides with the most bold term introductions.
--     Potentially indicates slides doing heavy pedagogical lifting.
-- ============================================================

SELECT
    o.subject,
    o.year,
    o.term          AS term_period,
    o.unit,
    o.chapter,
    o.slide_number,
    COUNT(CASE WHEN o.is_introduction = 1 THEN 1 END)  AS introductions,
    COUNT(*)                                            AS total_terms,
    GROUP_CONCAT(c.term, ', ')                         AS terms_on_slide
FROM occurrences o
JOIN concepts c ON o.concept_id = c.concept_id
WHERE o.validation_status = 'confirmed'
  AND o.slide_number IS NOT NULL
GROUP BY o.subject, o.year, o.term, o.unit, o.chapter, o.slide_number
HAVING introductions >= 3
ORDER BY introductions DESC
LIMIT 20;


-- ============================================================
-- 11. TERM CO-OCCURRENCE (same slide, same paragraph)
--     Which terms appear together most frequently?
--     Pre-graph indicator of conceptual neighbourhood.
-- ============================================================

SELECT
    a.term      AS term_a,
    b.term      AS term_b,
    COUNT(*)    AS co_occurrences
FROM occurrences oa
JOIN occurrences ob
    ON oa.subject = ob.subject
   AND oa.year = ob.year
   AND oa.term = ob.term
   AND oa.unit = ob.unit
   AND oa.slide_number = ob.slide_number
   AND oa.occurrence_id < ob.occurrence_id   -- avoid duplicates
JOIN concepts a ON oa.concept_id = a.concept_id
JOIN concepts b ON ob.concept_id = b.concept_id
WHERE oa.validation_status = 'confirmed'
  AND ob.validation_status = 'confirmed'
GROUP BY a.term, b.term
HAVING co_occurrences >= 2
ORDER BY co_occurrences DESC
LIMIT 30;
