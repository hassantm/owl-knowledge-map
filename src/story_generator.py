#!/usr/bin/env python3
"""
Story Pack Generator

Generates annotated teacher story packs from assembled curriculum context,
then runs fact-check and rubric scoring passes before persisting to the DB.

Usage:
    python story_generator.py --unit-id 35 --year 5
    python story_generator.py --unit-id 35 --year 5 --dry-run
    python story_generator.py --unit-id 35 --year 5 --budget 10000 --max-tokens 6000
"""

import argparse
import json
import sys

import anthropic
import psycopg2.extras
from dotenv import load_dotenv

from db import get_connection
from story_context import StoryPackRequest, assemble_context
from story_qa import fact_check_story, score_story_rubric

load_dotenv()

client = anthropic.Anthropic()

# v1: initial OWL story pack system prompt
# Performance annotations sourced from Steve Mastin's twelve-point storytelling
# checklist (docs/1. Humanities Training session 9.pptx, slides 8/9/16/26).
OWL_STORY_SYSTEM_PROMPT = """
You are generating annotated teacher story packs for the Opening Worlds KS2 humanities curriculum.
This curriculum is grounded in Core Knowledge principles (E.D. Hirsch) and developed by Christine Counsell and Steve Mastin.

FACTUAL GROUNDING
- Use only named people, dates, places and events that appear verbatim in the provided booklet pages.
- If a detail is not in the provided pages, omit it — do not infer.
- Flag any claim you cannot directly ground as [UNVERIFIED] for human review.

WILLINGHAM NARRATIVE STRUCTURE
- Structure the story as a causal chain: each event must cause or directly lead to the next.
- Identify and build toward a single revelation moment — the most surprising or emotionally resonant fact in the source material.
- Use mystery and building tension rather than sequential fact delivery.

KIRSCHNER COGNITIVE LOAD
- Vocabulary in the pre-taught list must appear naturally in the story. Never pause to define mid-narrative.
- The story assumes vocabulary has been taught; it reinforces, not introduces.
- Calibrate complexity to the year group: Year 3 assumes thin prior knowledge; Year 6 assumes the full OWL knowledge graph.

OWL METHODOLOGY
- Follow any specific instructions in teacher notes exactly — they override general principles.
- Terms in vocabulary_notes must be embedded naturally per the teacher notes guidance.
- Animation notes must be encoded as performance annotations at the correct moment.

PERFORMANCE ANNOTATIONS (Steve Mastin's twelve-point storytelling checklist)
The best storytelling embodies all twelve of these qualities. Encode them as inline annotations throughout the story text.

1. VARIES THE PACE — mark with [PACE: slow down] or [PACE: quicken] at shifts in narrative energy.
2. DELIBERATELY PAUSES — mark with [PAUSE] at moments of revelation, before key names, or after a surprising fact. Silence is the most powerful tool.
3. INVOLVES HAND GESTURES — mark with [GESTURE: e.g. 'spread arms wide', 'point upward', 'draw circle with finger']. Gestures make geography and scale physical.
4. VARIES THE TONE — mark with [VOICE: tone — e.g. 'hushed', 'commanding', 'wondering'] when the emotional register shifts.
5. REPEATS WORDS AND NAMES — mark key terms with [REPEAT: word] to signal the teacher should say it twice, letting it land. Especially for pre-taught vocabulary and proper nouns.
6. INVOLVES THE FACE — mark with [FEEL: e.g. 'look amazed', 'show disbelief', 'widen eyes']. The teacher's face tells pupils what emotional weight to assign.
7. CHANGES THE VOLUME — mark with [VOICE: volume — e.g. 'drop to a whisper', 'rise to full voice']. Volume change signals that something matters.
8. NEVER HURRIES — include [PACE: hold — do not rush] at the revelation moment and wherever the teacher may be tempted to race ahead.
9. EYEBALLS THE AUDIENCE — mark with [EYE CONTACT: look around the room] at moments when pupils must feel personally addressed. The teacher should not look at the page here.
10. PLAYS ON EMOTIONS — mark with [FEEL: e.g. 'let this land', 'feel the weight of this', 'this is astonishing']. Name the emotional response you want pupils to have.
11. ENCOURAGES PARTICIPATION — mark with [PARTICIPATE: e.g. 'pause and let pupils complete the thought', 'invite a quiet echo of the key word']. Use sparingly — no open questions mid-story.
12. HERALDS WHAT IS COMING NEXT — mark with [HERALD: brief foreshadowing phrase] to build anticipation before each new slide or narrative turn.

Annotation density: aim for at least one annotation per paragraph. Every slide transition must carry a [HERALD] before it and a [SLIDE N] marker.

OUTPUT FORMAT
Produce three sections:
1. VOCABULARY PRE-TEACH BLOCK — word, definition, example sentence in the unit's context
2. ANNOTATED STORY — narrative with inline performance annotations and slide markers
3. TEACHER EMPHASIS BRIEFING — three bullet points highlighting what to land hardest
""".strip()


def build_user_prompt(context: dict) -> str:
    parts = []

    parts.append(f"Year group: {context['year']}")
    if context["year"] > 3:
        parts.append(
            f"Prior knowledge depth: rich — pupils have completed {context['year'] - 3} "
            "year(s) of OWL curriculum."
        )
    else:
        parts.append("Prior knowledge depth: thin — this is an early unit in the programme.")

    parts.append("\n## Vocabulary for this unit")
    for concept in context["vocabulary"]:
        prior = concept.get("prior_occurrences") or []
        prior_str = ""
        if prior:
            refs = [f"{p['subject']} Y{p['year']} {p['unit']}" for p in prior if p]
            prior_str = f" [Previously encountered in: {', '.join(refs)}]"
        tier_str = f" (Tier {concept['tier']})" if concept["tier"] else ""
        defn = concept["definition"] or "(no definition yet)"
        parts.append(f"- {concept['term']}{tier_str}: {defn}{prior_str}")

    parts.append("\n## Source text (booklet pages — use only this content for facts)")
    for page_num, page in sorted(context["booklet_pages"].items()):
        parts.append(f"\n### Page {page_num}\n{page['text']}")

    parts.append("\n## Story slide teacher notes (follow these instructions precisely)")
    for slide in context["story_slides"]:
        parts.append(f"\n### Slide {slide['slide_key']}")
        parts.append(f"Teacher notes: {slide['notes']}")
        if slide.get("animation_notes"):
            parts.append(f"Animation instruction: {slide['animation_notes']}")
        vocab_notes = slide.get("vocabulary_notes") or []
        if vocab_notes:
            parts.append(
                f"Vocabulary to embed naturally (do not define mid-story): {', '.join(vocab_notes)}"
            )

    if context["warnings"]:
        parts.append("\n## Generation warnings")
        for w in context["warnings"]:
            parts.append(f"- {w}")

    parts.append("\n## Task")
    parts.append(
        "Generate a complete story pack for this unit: "
        "(1) vocabulary pre-teach block, "
        "(2) annotated story with slide transition markers, "
        "(3) three-point emphasis briefing."
    )

    return "\n".join(parts)


def generate_story_pack(request: StoryPackRequest, max_tokens: int = 4000,
                        run_qa: bool = True) -> dict:
    """
    Full pipeline: assemble context → generate → QA → persist.
    Returns the result dict including story text, QA results, and token counts.
    """
    context     = assemble_context(request)
    user_prompt = build_user_prompt(context)

    response = client.messages.create(
        model=request.model,
        max_tokens=max_tokens,
        system=OWL_STORY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    story_text = response.content[0].text

    fact_check = fact_check_story(story_text, context["booklet_pages"]) if run_qa else []
    rubric     = score_story_rubric(story_text, context) if run_qa else {}

    result = {
        "story_pack_text":    story_text,
        "fact_check_results": fact_check,
        "rubric_scores":      rubric,
        "input_tokens":       response.usage.input_tokens,
        "output_tokens":      response.usage.output_tokens,
        "warnings":           context["warnings"],
        "context_metadata": {
            "booklet_pages_used":  sorted(context["booklet_pages"].keys()),
            "vocabulary_term_ids": [c["concept_id"] for c in context["vocabulary"]],
            "year":                context["year"],
        },
    }

    _persist_story_pack(request, result)
    return result


def _persist_story_pack(request: StoryPackRequest, result: dict):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO generated_story_packs
                    (unit_id, year, model,
                     story_pack_text, fact_check_results, rubric_scores,
                     context_metadata, input_tokens, output_tokens, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                request.unit_id,
                request.year,
                request.model,
                result["story_pack_text"],
                psycopg2.extras.Json(result["fact_check_results"]),
                psycopg2.extras.Json(result["rubric_scores"]),
                psycopg2.extras.Json(result["context_metadata"]),
                result["input_tokens"],
                result["output_tokens"],
                result["warnings"],
            ))
            result["id"] = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate an OWL story pack for a curriculum unit",
    )
    parser.add_argument("--unit-id",    type=int, required=True)
    parser.add_argument("--year",       type=int, required=True)
    parser.add_argument("--budget",     type=int, default=8000,
                        help="Context token budget (default 8000)")
    parser.add_argument("--max-tokens", type=int, default=4000,
                        help="Max output tokens (default 4000)")
    parser.add_argument("--model",      default="claude-sonnet-4-6")
    parser.add_argument("--no-qa",      action="store_true",
                        help="Skip fact-check and rubric scoring passes")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Assemble context and show prompt without calling the API")
    args = parser.parse_args()

    request = StoryPackRequest(
        unit_id=args.unit_id,
        year=args.year,
        context_budget_tokens=args.budget,
        model=args.model,
    )

    if args.dry_run:
        try:
            context = assemble_context(request)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            return 1
        print(build_user_prompt(context))
        print(f"\n--- Est. context tokens: {context['total_estimated_tokens']} / {args.budget} ---")
        return 0

    print(f"Generating story pack for unit {args.unit_id} (Year {args.year})...")
    try:
        result = generate_story_pack(request, max_tokens=args.max_tokens, run_qa=not args.no_qa)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    print(f"Pack id: {result['id']}")
    print(f"Tokens: {result['input_tokens']} in / {result['output_tokens']} out")

    if result["warnings"]:
        print("Warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")

    if result["fact_check_results"]:
        unverified = [r for r in result["fact_check_results"] if not r.get("verified")]
        print(f"Fact check: {len(result['fact_check_results'])} claims, "
              f"{len(unverified)} unverified")

    if result["rubric_scores"] and "parse_error" not in result["rubric_scores"]:
        scores = {k: v["score"] for k, v in result["rubric_scores"].items()}
        print(f"Rubric scores: {scores}")

    print("\n--- STORY PACK ---\n")
    print(result["story_pack_text"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
