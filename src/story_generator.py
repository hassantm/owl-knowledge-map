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
import re
import sys

import anthropic
import psycopg2.extras
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env', override=True)

from db import get_connection
from story_context import StoryPackRequest, assemble_context
from story_qa import fact_check_story, score_story_rubric

client = anthropic.Anthropic()

# v2: outputs structured JSON for rich dashboard rendering.
# Performance annotations sourced from Steve Mastin's twelve-point storytelling
# checklist (docs/1. Humanities Training session 9.pptx, slides 8/9/16/26).
OWL_STORY_SYSTEM_PROMPT = """
You are generating annotated teacher story packs for the Opening Worlds KS2 humanities curriculum.
This curriculum is grounded in Core Knowledge principles (E.D. Hirsch) and developed by Christine Counsell and Steve Mastin.

FACTUAL GROUNDING
- Use only named people, dates, places and events that appear verbatim in the provided booklet pages.
- If a detail is not in the provided pages, omit it — do not infer.
- Flag any claim you cannot directly ground as [[UNVERIFIED]] for human review.

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
Encode inline annotations throughout the story text using double-bracket format: [[TYPE: content]]
The annotation type is the first word; content follows after a colon or em dash.

1. VARIES THE PACE — [[PACE: slow down]] or [[PACE: quicken]] at shifts in narrative energy.
2. DELIBERATELY PAUSES — [[PAUSE]] or [[PAUSE — brief note]] at moments of revelation or before key names. Silence is the most powerful tool.
3. INVOLVES HAND GESTURES — [[GESTURE: e.g. spread arms wide]] — make geography and scale physical.
4. VARIES THE TONE — [[VOICE: hushed]] or [[VOICE: commanding, wondering]] when the emotional register shifts.
5. REPEATS WORDS AND NAMES — [[REPEAT: word]] signals say it twice, letting it land.
6. INVOLVES THE FACE — [[FEEL: look amazed]] or [[FEEL: show disbelief]] — the teacher's face assigns emotional weight.
7. CHANGES THE VOLUME — [[VOICE: drop to a whisper]] or [[VOICE: rise to full voice]] — volume change signals importance.
8. NEVER HURRIES — [[PACE: hold — do not rush]] at revelation moments.
9. EYEBALLS THE AUDIENCE — [[EYE CONTACT: look around the room]] — pupils must feel personally addressed here.
10. PLAYS ON EMOTIONS — [[FEEL: let this land]] or [[FEEL: feel the weight of this]] — name the desired emotional response.
11. ENCOURAGES PARTICIPATION — [[PARTICIPATE: invite quiet echo of key word]] — use sparingly, no open questions mid-story.
12. HERALDS WHAT IS COMING — [[HERALD: brief foreshadowing phrase]] — build anticipation before each slide turn.

Annotation density: at least one annotation per paragraph. Every slide transition must carry a [[HERALD: ...]] before it.

VOCABULARY WORD MARKING
Wrap each pre-taught vocabulary word (from the vocabulary list) in curly braces when it appears in the story body: {ziggurat}, {overseer}, {cuneiform}. This causes it to display underlined in gold in the rendered output. Use the grammatically correct inflected form for the sentence — e.g. write {voting} or {vote} rather than forcing {voted} when it does not fit the grammar. The word inside the braces must read naturally in context; do not use a form that produces ungrammatical English.

OUTPUT FORMAT — JSON ONLY
Respond with a single valid JSON object. No markdown fences. No preamble. No commentary after the JSON.
The JSON must conform exactly to this schema:

{
  "title": "A short evocative story title (not the unit name)",
  "subtitle": "Story pack for: [unit name from the input]",
  "source_grounding": "One sentence stating which booklet pages this story is drawn from and that every fact is sourced there.",
  "vocabulary": [
    {
      "word": "Term as it appears in the pre-teach list",
      "pronunciation": "Phonetic breakdown e.g. zig-oo-rat",
      "definition": "Clear definition pitched at the year group. One or two sentences.",
      "example": "A sentence showing the word used in the story's context, in quotes."
    }
  ],
  "story_sections": [
    {
      "slide_marker": "Slide N — Booklet page N [optional teacher note]",
      "title": "Part N: Evocative section title",
      "body_paragraphs": [
        "Paragraph text with [[PAUSE]], [[VOICE: quiet]], [[PACE: slow]], [[FEEL: emotion]], [[GESTURE: action]], and {vocab_word} inline markers."
      ],
      "connector": "▼ continue without pause — turn to slide N"
    }
  ],
  "emphasis_points": [
    {
      "heading": "Short bold instruction for the teacher",
      "body": "One or two sentences explaining why this matters and how to land it."
    }
  ]
}

Rules:
- story_sections must have one entry per story slide in the input.
- The last story_section should have connector set to null.
- emphasis_points must have exactly three entries.
- All strings must be valid JSON (escape any quotes inside strings).
- Do not include any text outside the JSON object.
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
        "Generate a complete story pack as a single JSON object. "
        "Include a vocabulary pre-teach block, a story section per slide with inline performance annotations, "
        "and three emphasis points. Output ONLY the JSON — no fences, no preamble."
    )

    return "\n".join(parts)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _extract_json(text: str) -> dict | None:
    """Parse JSON from model response, stripping markdown fences if present."""
    fence = _JSON_FENCE_RE.search(text)
    candidate = fence.group(1) if fence else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def generate_story_pack(request: StoryPackRequest, max_tokens: int = 8000,
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

    story_text  = response.content[0].text
    story_data  = _extract_json(story_text)

    fact_check = fact_check_story(story_text, context["booklet_pages"]) if run_qa else []
    rubric     = score_story_rubric(story_text, context) if run_qa else {}

    result = {
        "story_pack_text":    story_text,
        "story_pack_data":    story_data,
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
                     story_pack_text, story_pack_data,
                     fact_check_results, rubric_scores,
                     context_metadata, input_tokens, output_tokens, warnings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                request.unit_id,
                request.year,
                request.model,
                result["story_pack_text"],
                psycopg2.extras.Json(result["story_pack_data"]),
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
    parser.add_argument("--max-tokens", type=int, default=8000,
                        help="Max output tokens (default 4000)")
    parser.add_argument("--model",      default="claude-opus-4-7")
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
    print(f"JSON parsed: {'yes' if result['story_pack_data'] else 'no — raw text stored only'}")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())
