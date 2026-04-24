#!/usr/bin/env python3
"""
QA Layer for Story Pack Generator

Two passes after generation:
  fact_check_story   — verifies every named claim against source booklet pages
  score_story_rubric — scores against six pedagogical dimensions (1–5)

Results are stored in generated_story_packs.fact_check_results and .rubric_scores.
"""

import json

import anthropic
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env', override=True)

client = anthropic.Anthropic()

FACTCHECK_SYSTEM_PROMPT = """
You are a fact-checking assistant for educational content.
You will be given a generated story and the booklet pages it was generated from.
Identify every specific factual claim (named people, dates, places, quantities, events)
and verify whether it appears in the source pages.
Return a JSON array. Each item: {"claim": str, "verified": bool, "source_page": int|null}.
Flag anything not directly supported as verified: false.
Return ONLY the JSON array. No preamble.
""".strip()


def fact_check_story(story_text: str, booklet_pages: dict) -> list[dict]:
    source_text = "\n\n".join(
        f"Page {num}:\n{page['text']}"
        for num, page in sorted(booklet_pages.items())
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=FACTCHECK_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"SOURCE PAGES:\n{source_text}\n\nGENERATED STORY:\n{story_text}",
        }],
    )
    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return [{"claim": "parse error", "verified": False, "source_page": None}]


RUBRIC_DIMENSIONS = [
    ("causal_chain",
     "Does each event cause or directly lead to the next, "
     "or is it sequential facts joined by 'and then'?"),
    ("vocabulary_integration",
     "Are pre-taught vocabulary words woven in naturally at appropriate density?"),
    ("dramatic_structure",
     "Is there a clear hook, building tension, and revelation moment?"),
    ("knowledge_fidelity",
     "Does the story stay within the source pages without inferring unsupported details?"),
    ("register",
     "Is the language appropriate for the specified year group?"),
    ("performance_architecture",
     "Does annotation structure include PAUSE, VOICE, PACE, FEEL, GESTURE at appropriate "
     "moments, with slide markers in the right places?"),
]

RUBRIC_SYSTEM_PROMPT = """
You score a teacher story pack against pedagogical criteria.
For each dimension, give a score 1–5 and a one-sentence justification.
Return ONLY a JSON object: {"dimension_key": {"score": int, "justification": str}, ...}.
""".strip()


def score_story_rubric(story_text: str, context: dict) -> dict:
    dimensions_text = "\n".join(
        f"{key}: {description}"
        for key, description in RUBRIC_DIMENSIONS
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=RUBRIC_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Year group: {context['year']}\n\n"
                f"SCORING DIMENSIONS:\n{dimensions_text}\n\n"
                f"STORY PACK TO SCORE:\n{story_text}"
            ),
        }],
    )
    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {"parse_error": {"score": 0, "justification": "Failed to parse rubric response"}}
