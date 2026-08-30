import argparse
import psycopg2.extras
from db import get_connection

# slide_number resets per unit, so both must match to identify the same physical slide
LESSON_COOCCURRENCE_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)    AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id) AS concept_b_id,
        o1.subject                             AS subject_a,
        o2.subject                             AS subject_b,
        'lesson'                               AS granularity,
        COUNT(*)                               AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.slide_number = o2.slide_number
        AND o1.unit         = o2.unit
        AND o1.concept_id   < o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(*) > 0
"""

UNIT_COOCCURRENCE_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'unit'                                      AS granularity,
        COUNT(DISTINCT o1.unit)                     AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.unit        = o2.unit
        AND o1.subject     = o2.subject
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.unit) > 0
"""

YEAR_GROUP_COOCCURRENCE_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'year_group'                                AS granularity,
        COUNT(DISTINCT o1.year)                     AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.year        = o2.year
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.year) > 0
"""

INSERT_SQL = """
    INSERT INTO co_occurrences
        (concept_a_id, concept_b_id, subject_a, subject_b, granularity, weight)
    VALUES %s
    ON CONFLICT (concept_a_id, concept_b_id, subject_a, subject_b, granularity)
    DO UPDATE SET
        weight      = EXCLUDED.weight,
        computed_at = now()
"""

TASKS = {
    'lesson':     LESSON_COOCCURRENCE_SQL,
    'unit':       UNIT_COOCCURRENCE_SQL,
    'year_group': YEAR_GROUP_COOCCURRENCE_SQL,
}


def compute_and_insert(conn, label: str, select_sql: str, dry_run: bool = False):
    print(f"\nComputing {label} co-occurrences...", end=" ", flush=True)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(select_sql)
        rows = cur.fetchall()
    print(f"{len(rows)} pairs found")

    if dry_run:
        print(f"  [dry-run] would insert/update {len(rows)} rows")
        if rows:
            s = rows[0]
            print(f"  Sample: concept_a={s['concept_a_id']}, concept_b={s['concept_b_id']}, "
                  f"subjects={s['subject_a']}/{s['subject_b']}, weight={s['weight']}")
        return len(rows)

    if not rows:
        return 0

    values = [
        (r['concept_a_id'], r['concept_b_id'],
         r['subject_a'],    r['subject_b'],
         r['granularity'],  r['weight'])
        for r in rows
    ]
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, INSERT_SQL, values, page_size=500)
    conn.commit()
    print(f"  Inserted/updated {len(rows)} rows")
    return len(rows)


def _count_cross_subject(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM co_occurrences WHERE is_cross_subject = true")
        return cur.fetchone()['count']


def run_computation(dry_run: bool = False, granularities: list[str] = None):
    if granularities is None:
        granularities = list(TASKS.keys())

    conn = get_connection()

    if not dry_run:
        print("\nTruncating co_occurrences table for full recompute...")
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE co_occurrences")
        conn.commit()

    total = sum(
        compute_and_insert(conn, g, TASKS[g], dry_run)
        for g in granularities
    )

    cross_subject = _count_cross_subject(conn) if not dry_run else '(skipped in dry-run)'
    print(f"\nTotal pairs: {total}")
    print(f"Cross-subject pairs: {cross_subject}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute vocabulary co-occurrence edges")
    parser.add_argument('--dry-run',       action='store_true')
    parser.add_argument('--granularities', nargs='+',
                        choices=list(TASKS.keys()),
                        default=list(TASKS.keys()))
    args = parser.parse_args()
    run_computation(dry_run=args.dry_run, granularities=args.granularities)
