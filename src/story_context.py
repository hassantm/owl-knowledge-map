#!/usr/bin/env python3
"""
Context Assembly for Story Pack Generator

Queries the database to build a token-budgeted prompt context for story pack
generation. All data comes from the database — no Drive access at generation time.

The assembled context dict is passed directly to story_generator.build_user_prompt().

Usage (standalone diagnostic):
    python story_context.py --unit-id 35 --year 5
    python story_context.py --unit-id 35 --year 5 --budget 6000
"""

import argparse
import json
import sys
from dataclasses import dataclass

from db import get_connection

# Token budget reserved for the system prompt (estimated constant cost)
SYSTEM_PROMPT_TOKENS = 1400
# Rough per-concept token estimate when enrichment data is included
TOKENS_PER_CONCEPT = 80


@dataclass
class StoryPackRequest:
    unit_id:               int
    year:                  int
    context_budget_tokens: int  = 8000
    model:                 str  = "claude-sonnet-4-6"


def get_story_slide_data(unit_id: int) -> list[dict]:
    """
    Return all story slides from a unit's lesson content, ordered by slide number.

    Each dict contains:
      slide_key, notes, animation_notes, source_pages, vocabulary_notes, token_count
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    slide_key,
                    (slide_value->>'notes')             AS notes,
                    (slide_value->>'animation_notes')   AS animation_notes,
                    (slide_value->'source_pages')       AS source_pages,
                    (slide_value->'vocabulary_notes')   AS vocabulary_notes,
                    (slide_value->>'token_count')::int  AS token_count
                FROM units,
                    jsonb_each(lesson_content->'slides') AS slides(slide_key, slide_value)
                WHERE unit_id = %s
                  AND (slide_value->>'story_slide')::boolean = true
                ORDER BY slide_key::int ASC
            """, (unit_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_booklet_pages(unit_id: int, page_numbers: list[int]) -> dict[int, dict]:
    """
    Return text and token counts for specific booklet pages (slide numbers).

    Returns {page_number: {text, token_count}}.
    If page_numbers is empty, returns all pages.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            base_query = """
                SELECT
                    page_key::int                       AS page_number,
                    (page_value->>'text')               AS text,
                    (page_value->>'token_count')::int   AS token_count
                FROM units,
                    jsonb_each(booklet_content->'pages') AS pages(page_key, page_value)
                WHERE unit_id = %s
            """
            if page_numbers:
                cur.execute(base_query + "  AND page_key::int = ANY(%s) ORDER BY page_key::int ASC",
                            (unit_id, page_numbers))
            else:
                cur.execute(base_query + "ORDER BY page_key::int ASC", (unit_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return {r["page_number"]: {"text": r["text"], "token_count": r["token_count"]}
            for r in rows}


def get_vocabulary_with_prior_context(unit_id: int, year: int) -> list[dict]:
    """
    Return approved concepts for the unit enriched with:
      - prior_occurrences: earlier appearances across the curriculum (same or lower year)
      - connected_concepts: co-occurring concepts at unit granularity (weight >= 2)

    Uses co_occurrences (concept-to-concept) not edges (occurrence-to-occurrence).
    Only concepts with enrichment_status='approved' are included.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH current_unit_concepts AS (
                    SELECT DISTINCT
                        c.concept_id,
                        c.term,
                        c.definition,
                        c.etymology,
                        c.word_family,
                        c.tier
                    FROM concepts c
                    JOIN occurrences o ON o.concept_id = c.concept_id
                    WHERE o.unit_id = %s
                      AND c.enrichment_status = 'approved'
                ),
                prior_occs AS (
                    SELECT
                        o.concept_id,
                        o.year,
                        o.term            AS curriculum_term,
                        o.unit            AS unit_name,
                        o.subject
                    FROM occurrences o
                    JOIN current_unit_concepts cuc ON cuc.concept_id = o.concept_id
                    WHERE o.year <= %s
                      AND o.unit_id != %s
                    ORDER BY o.year, o.subject
                ),
                connected AS (
                    SELECT source_id, neighbour_id, is_cross_subject, weight
                    FROM (
                        SELECT
                            cuc.concept_id AS source_id,
                            CASE
                                WHEN co.concept_a_id = cuc.concept_id THEN co.concept_b_id
                                ELSE co.concept_a_id
                            END             AS neighbour_id,
                            co.is_cross_subject,
                            co.weight,
                            ROW_NUMBER() OVER (
                                PARTITION BY cuc.concept_id
                                ORDER BY co.is_cross_subject DESC, co.weight DESC
                            ) AS rn
                        FROM current_unit_concepts cuc
                        JOIN co_occurrences co
                            ON co.concept_a_id = cuc.concept_id
                            OR co.concept_b_id = cuc.concept_id
                        WHERE co.granularity = 'unit'
                    ) ranked
                    WHERE rn <= 10
                )
                SELECT
                    cuc.concept_id,
                    cuc.term,
                    cuc.definition,
                    cuc.etymology,
                    cuc.word_family,
                    cuc.tier,
                    json_agg(DISTINCT jsonb_build_object(
                        'year',            po.year,
                        'curriculum_term', po.curriculum_term,
                        'unit',            po.unit_name,
                        'subject',         po.subject
                    )) FILTER (WHERE po.concept_id IS NOT NULL)  AS prior_occurrences,
                    json_agg(DISTINCT jsonb_build_object(
                        'term',            c2.term,
                        'is_cross_subject', conn.is_cross_subject,
                        'weight',          conn.weight
                    )) FILTER (WHERE conn.source_id IS NOT NULL) AS connected_concepts
                FROM current_unit_concepts cuc
                LEFT JOIN prior_occs po       ON po.concept_id  = cuc.concept_id
                LEFT JOIN connected conn      ON conn.source_id = cuc.concept_id
                LEFT JOIN concepts c2         ON c2.concept_id  = conn.neighbour_id
                GROUP BY
                    cuc.concept_id, cuc.term, cuc.definition,
                    cuc.etymology, cuc.word_family, cuc.tier
                ORDER BY cuc.concept_id
            """, (unit_id, year, unit_id))
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["prior_occurrences"] = [
            p for p in (d["prior_occurrences"] or [])
            if p and p.get("year") is not None
        ]
        d["connected_concepts"] = [
            c for c in (d["connected_concepts"] or [])
            if c and c.get("term") is not None
        ]
        result.append(d)
    return result


def _trim_pages_to_budget(pages: dict[int, dict], token_budget: int) -> dict[int, dict]:
    """Keep pages in slide order until the token budget is exhausted."""
    kept, running = {}, 0
    for page_num, page in sorted(pages.items()):
        cost = page["token_count"]
        if running + cost <= token_budget:
            kept[page_num] = page
            running += cost
    return kept


def _check_content_ready(unit_id: int) -> tuple[list[str], list[str]]:
    """
    Return (warnings, errors) about content availability for a unit.
    Errors block generation; warnings are passed through to the output.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    lesson_content IS NOT NULL          AS has_lesson,
                    lesson_content_stale                AS lesson_stale,
                    lesson_content_extracted_at         AS lesson_at,
                    booklet_content IS NOT NULL         AS has_booklet,
                    booklet_content_stale               AS booklet_stale,
                    booklet_content_extracted_at        AS booklet_at
                FROM units WHERE unit_id = %s
            """, (unit_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return [], [f"No unit found with unit_id={unit_id}"]

    warnings, errors = [], []
    if not row["has_lesson"]:
        errors.append("lesson_content is NULL — run content_ingestion.py --lesson first")
    elif row["lesson_stale"]:
        warnings.append(
            f"Lesson content flagged stale since {row['lesson_at']}. "
            "Proceeding with cached content."
        )

    if not row["has_booklet"]:
        errors.append("booklet_content is NULL — run content_ingestion.py --booklet first")
    elif row["booklet_stale"]:
        warnings.append(
            f"Booklet content flagged stale since {row['booklet_at']}. "
            "Proceeding with cached content."
        )

    return warnings, errors


def assemble_context(request: StoryPackRequest) -> dict:
    """
    Assemble prompt context from database records.

    Returns a dict with:
      story_slides     — list of story slide dicts
      booklet_pages    — {page_num: {text, token_count}}
      vocabulary       — list of concept dicts with prior context
      year             — int
      warnings         — list of warning strings (stale content, trimming)
      total_estimated_tokens — int

    Raises RuntimeError if content is missing (not yet ingested).
    """
    warnings, errors = _check_content_ready(request.unit_id)
    if errors:
        raise RuntimeError("\n".join(errors))

    story_slides = get_story_slide_data(request.unit_id)

    if not story_slides:
        warnings.append(
            "No story slides detected in lesson content. "
            "The full lesson will be passed as context."
        )

    source_pages = sorted(set(
        p
        for slide in story_slides
        for p in (slide.get("source_pages") or [])
    ))

    booklet_pages = get_booklet_pages(request.unit_id, source_pages)

    if not booklet_pages and source_pages:
        booklet_pages = get_booklet_pages(request.unit_id, [])
        if booklet_pages:
            warnings.append(
                "No source page references found in story slide notes. "
                "Using all booklet pages."
            )

    vocabulary = get_vocabulary_with_prior_context(request.unit_id, request.year)

    story_tokens   = sum(s["token_count"] for s in story_slides)
    booklet_tokens = sum(p["token_count"] for p in booklet_pages.values())
    vocab_tokens   = len(vocabulary) * TOKENS_PER_CONCEPT
    total          = SYSTEM_PROMPT_TOKENS + story_tokens + booklet_tokens + vocab_tokens

    if total > request.context_budget_tokens:
        booklet_budget = (
            request.context_budget_tokens
            - SYSTEM_PROMPT_TOKENS
            - story_tokens
            - vocab_tokens
        )
        if booklet_budget > 0:
            booklet_pages = _trim_pages_to_budget(booklet_pages, booklet_budget)
            warnings.append(
                f"Booklet pages trimmed to fit token budget "
                f"({len(booklet_pages)} page(s) kept)."
            )
        else:
            booklet_pages = {}
            warnings.append(
                "Token budget too tight to include any booklet pages. "
                "Consider increasing --budget."
            )
        total = request.context_budget_tokens

    return {
        "unit_id":                request.unit_id,
        "year":                   request.year,
        "story_slides":           story_slides,
        "booklet_pages":          booklet_pages,
        "vocabulary":             vocabulary,
        "warnings":               warnings,
        "total_estimated_tokens": total,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Assemble and inspect story pack context for a unit",
    )
    parser.add_argument("--unit-id", type=int, required=True)
    parser.add_argument("--year",    type=int, required=True)
    parser.add_argument("--budget",  type=int, default=8000,
                        help="Token budget (default 8000)")
    parser.add_argument("--json",    action="store_true",
                        help="Dump full context as JSON")
    args = parser.parse_args()

    req = StoryPackRequest(
        unit_id=args.unit_id,
        year=args.year,
        context_budget_tokens=args.budget,
    )

    try:
        ctx = assemble_context(req)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    if args.json:
        print(json.dumps(ctx, indent=2, default=str))
        return 0

    print(f"Unit {args.unit_id}  Year {args.year}")
    print(f"  Story slides:    {len(ctx['story_slides'])}")
    print(f"  Booklet pages:   {len(ctx['booklet_pages'])} "
          f"({sorted(ctx['booklet_pages'].keys())})")
    print(f"  Vocabulary:      {len(ctx['vocabulary'])} concept(s)")
    print(f"  Est. tokens:     {ctx['total_estimated_tokens']} / {args.budget}")

    if ctx["warnings"]:
        print("  Warnings:")
        for w in ctx["warnings"]:
            print(f"    - {w}")

    if ctx["story_slides"]:
        print("\n  Story slides:")
        for s in ctx["story_slides"]:
            pages = s.get("source_pages") or []
            vocab = s.get("vocabulary_notes") or []
            print(f"    slide {s['slide_key']:>3}  pages={pages}  vocab={vocab}  "
                  f"tokens={s['token_count']}")

    if ctx["vocabulary"]:
        print("\n  Vocabulary (first 5):")
        for c in ctx["vocabulary"][:5]:
            prior = len(c.get("prior_occurrences") or [])
            print(f"    {c['term']!r}  tier={c['tier']}  prior_occs={prior}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
