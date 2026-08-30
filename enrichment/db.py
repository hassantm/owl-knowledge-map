import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        os.environ['DATABASE_URL'],
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def get_pending_concepts(conn, limit: int = None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                c.concept_id                        AS id,
                c.term,
                ARRAY_AGG(DISTINCT o.subject)       AS subjects,
                ARRAY_AGG(DISTINCT o.year)          AS years
            FROM concepts c
            JOIN occurrences o ON o.concept_id = c.concept_id
            WHERE c.enrichment_status = 'pending'
            GROUP BY c.concept_id, c.term
            ORDER BY c.concept_id
            LIMIT %s
        """, (limit,))
        return cur.fetchall()


def write_generated(conn, concept_id: int, enrichment: dict):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE concepts SET
                definition        = %(definition)s,
                etymology         = %(etymology)s,
                word_family       = %(word_family)s,
                register          = %(register)s,
                tier              = %(tier)s,
                enrichment_status = 'generated',
                enriched_at       = now()
            WHERE concept_id = %(id)s
        """, {**enrichment, 'id': concept_id})
    conn.commit()


def write_approved(conn, concept_id: int, fields: dict, notes: str, reviewer: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE concepts SET
                definition        = %(definition)s,
                etymology         = %(etymology)s,
                word_family       = %(word_family)s,
                register          = %(register)s,
                tier              = %(tier)s,
                enrichment_status = 'approved',
                enrichment_notes  = %(notes)s,
                enriched_by       = %(reviewer)s,
                enriched_at       = now()
            WHERE concept_id = %(id)s
        """, {**fields, 'notes': notes, 'reviewer': reviewer, 'id': concept_id})
    conn.commit()


def set_status(conn, concept_id: int, status: str, notes: str = None):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE concepts SET
                enrichment_status = %s,
                enrichment_notes  = COALESCE(%s, enrichment_notes)
            WHERE concept_id = %s
        """, (status, notes, concept_id))
    conn.commit()


def get_next_for_review(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT concept_id AS id, term, definition, etymology,
                   word_family, register, tier, enrichment_notes
            FROM concepts
            WHERE enrichment_status = 'generated'
            ORDER BY concept_id
            LIMIT 1
        """)
        return cur.fetchone()


def get_enrichment_summary(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT enrichment_status, COUNT(*) AS count
            FROM concepts
            GROUP BY enrichment_status
            ORDER BY enrichment_status
        """)
        return {row['enrichment_status']: row['count'] for row in cur.fetchall()}
