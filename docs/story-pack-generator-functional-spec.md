# OWL Story Pack Generator — Functional Specification
## Schema-Aligned Implementation Reference

**Project:** Opening Worlds Knowledge Map — AI Teacher Tools  
**Source design doc:** `docs/OWL_AI_Design_Spec_v0.1.docx`  
**Status:** Ready for implementation  
**Last updated:** 2026-04-24 — aligned to live PostgreSQL schema (`owl` database)

> This is the implementation-ready version of the design spec. All SQL uses actual column names from the live database. See `docs/OWL_AI_Design_Spec_v0.1.docx` for the original design document with pedagogical rationale.

---

## 1. Overview

The Story Pack Generator extends the existing knowledge map pipeline with AI-assisted production of annotated teacher story packs. It operates in three layers:

| Component | Purpose |
|-----------|---------|
| **1. Schema migration** | Add content storage to `units`; create `generated_story_packs` |
| **2. Corpus ingestion extension** | Tokenise and store curriculum text per slide/page in `units.content` |
| **3. Context assembly + generation** | At generation time, query the database rather than Drive; call Claude API |

The system is additive — nothing in the existing schema is modified or dropped.

---

## 2. Existing Schema (Live PostgreSQL — `owl` database)

```
Connection: postgresql://htmadmin:dev@localhost:5432/owl
```

### Core tables

```sql
concepts (
    concept_id      serial          PRIMARY KEY,
    term            text            NOT NULL,
    subject_area    text,
    -- enrichment columns (migration 001):
    definition      text,
    etymology       text,
    word_family     text[],
    register        text,           -- CHECK: subject-specific | formal academic | technical | general formal
    tier            integer,        -- CHECK: 1 | 2 | 3
    enrichment_status text          NOT NULL DEFAULT 'pending',
    enrichment_notes  text,
    enriched_at       timestamptz,
    enriched_by       text          DEFAULT 'claude-batch'
)

occurrences (
    occurrence_id   serial      PRIMARY KEY,
    concept_id      integer     REFERENCES concepts(concept_id),
    subject         text        NOT NULL,   -- 'History', 'Geography', 'Religion'
    year            integer     NOT NULL,   -- 3, 4, 5, or 6
    term            text        NOT NULL,   -- 'Autumn1', 'Spring2', etc.
    unit            text        NOT NULL,   -- e.g. 'Christianity in 3 empires'
    unit_id         integer     NOT NULL REFERENCES units(unit_id),  -- added migration 003
    chapter         text,
    slide_number    integer,
    is_introduction integer     NOT NULL,   -- 1 = bold introduction, 0 = recurrence
    term_in_context text,
    source_path     text,
    needs_review    integer     DEFAULT 0,
    review_reason   text,
    validation_status text,
    vocab_confidence  float,
    vocab_match_type  text,
    vocab_source      text,
    audit_decision    text,
    audit_notes       text
)

edges (
    edge_id         serial  PRIMARY KEY,
    from_occurrence integer REFERENCES occurrences(occurrence_id),
    to_occurrence   integer REFERENCES occurrences(occurrence_id),
    edge_type       text,   -- 'within_subject' or 'cross_subject'
    edge_nature     text,   -- 'reinforcement', 'extension', 'application'
    confirmed_by    text,
    confirmed_date  text
)

units (
    unit_id         serial  PRIMARY KEY,
    subject         text    NOT NULL,
    year            integer NOT NULL,
    term            text    NOT NULL,
    unit            text    NOT NULL,
    vocab_list_path text,
    CONSTRAINT units_unique UNIQUE (subject, year, term, unit)
)

co_occurrences (
    id              serial  PRIMARY KEY,
    concept_a_id    integer NOT NULL REFERENCES concepts(concept_id),
    concept_b_id    integer NOT NULL REFERENCES concepts(concept_id),
    subject_a       text    NOT NULL,
    subject_b       text    NOT NULL,
    granularity     text    NOT NULL,   -- 'lesson' | 'unit' | 'year_group'
    weight          integer NOT NULL,
    is_cross_subject boolean GENERATED ALWAYS AS (subject_a != subject_b) STORED,
    computed_at     timestamptz NOT NULL DEFAULT now()
)
```

### Key schema differences from design spec

| Design spec | Live schema | Impact |
|---|---|---|
| `catalogue` table | `units` table | Content columns added to `units` in migration 004 |
| `catalogue.id` | `units.unit_id` | All FK references use `unit_id` |
| `vocabulary` table | `concepts` table | `concept_id`, `term` (not `name`) |
| `vocabulary.pronunciation` | Does not exist | Omitted from all queries |
| `vocabulary.example_sentence` | Does not exist | Omitted from all queries |
| `occurrences.vocab_id` | `occurrences.concept_id` | |
| `occurrences.slide_id` | `occurrences.slide_number` | INTEGER, resets per unit |
| `occurrences.year_group` | `occurrences.year` | INTEGER (3–6) |
| `edges` (concept→concept) | `co_occurrences` | `edges` connects occurrences; concept-level graph is `co_occurrences` |

---

## 3. Component 1: Schema Migration

### `migrations/004_add_unit_content.sql`

```sql
ALTER TABLE units
    ADD COLUMN IF NOT EXISTS content                 jsonb,
    ADD COLUMN IF NOT EXISTS content_stale           boolean     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS content_extracted_at    timestamptz,
    ADD COLUMN IF NOT EXISTS content_tokenizer_model varchar(64);

CREATE INDEX IF NOT EXISTS idx_units_content_stale
    ON units (content_stale)
    WHERE content_stale = true;
```

### `migrations/005_create_generated_story_packs.sql`

```sql
CREATE TABLE IF NOT EXISTS generated_story_packs (
    id                  serial          PRIMARY KEY,
    lesson_unit_id      integer         NOT NULL REFERENCES units(unit_id),
    booklet_unit_id     integer         NOT NULL REFERENCES units(unit_id),
    year                integer         NOT NULL,
    model               varchar(64)     NOT NULL,
    story_pack_text     text,
    fact_check_results  jsonb,
    rubric_scores       jsonb,
    context_metadata    jsonb,
    input_tokens        integer,
    output_tokens       integer,
    warnings            text[],
    human_approved      boolean         NOT NULL DEFAULT false,
    approved_by         varchar(128),
    approved_at         timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_story_packs_lesson   ON generated_story_packs(lesson_unit_id);
CREATE INDEX IF NOT EXISTS idx_story_packs_approved ON generated_story_packs(human_approved);
```

---

## 4. Component 2: Corpus Ingestion Extension

### File: `src/content_ingestion.py`

New standalone module. Integrates with the existing extraction pipeline — functions here are called from `src/batch_process.py` after PPTX/PDF extraction.

#### 4.1 JSONB content structures

**Booklet (PDF):**
```json
{
  "document_type": "booklet",
  "total_token_count": 8420,
  "tokenizer_model": "claude-sonnet-4-6",
  "extracted_at": "2026-04-24T10:00:00Z",
  "pages": {
    "3": { "text": "Just outside Ur's city walls...", "token_count": 312 },
    "4": { "text": "The brickmaker knows...", "token_count": 287 }
  }
}
```

**Lesson (PPTX):**
```json
{
  "document_type": "lesson",
  "total_token_count": 3240,
  "tokenizer_model": "claude-sonnet-4-6",
  "extracted_at": "2026-04-24T10:00:00Z",
  "slides": {
    "11": {
      "text": "Let's listen to a story.",
      "notes": "Have pupils shut the booklets. Now you tell the story...",
      "token_count": 43,
      "story_slide": true,
      "source_pages": [3]
    },
    "12": {
      "text": "Let's listen to a story.",
      "notes": "Continue the story, using Pages 4 and 5. When you reach the word 'precinct'...",
      "token_count": 89,
      "story_slide": true,
      "source_pages": [4, 5],
      "vocabulary_notes": ["precinct"],
      "animation_notes": "Remove inscription translation only when the dog's paws land on the brick."
    }
  }
}
```

#### 4.2 Helper functions

```python
import re
import json
import anthropic
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

load_dotenv()
client = anthropic.Anthropic()

STORY_SLIDE_PATTERNS = [
    r"listen to a story",
    r"tell the story",
    r"tell a story",
    r"story time",
]

def count_tokens_for_chunk(text: str, model: str = "claude-sonnet-4-6") -> int:
    response = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}]
    )
    return response.input_tokens

def detect_story_slide(title: str, notes: str) -> bool:
    combined = (title + " " + notes).lower()
    return any(re.search(p, combined) for p in STORY_SLIDE_PATTERNS)

def parse_source_pages(notes: str) -> list[int]:
    # "Pages 5 and 6" or "Page 3" or "Pages 5, 6 and 7"
    pages = []
    for m in re.finditer(r'[Pp]ages?\s+([\d,\s]+(?:and\s+\d+)?)', notes):
        raw = m.group(1)
        pages.extend(int(x) for x in re.findall(r'\d+', raw))
    return sorted(set(pages))

def parse_vocabulary_notes(notes: str) -> list[str]:
    return re.findall(r"the word[s]?\s+'([^']+)'", notes, re.IGNORECASE)

def parse_animation_notes(notes: str) -> str | None:
    m = re.search(r'(Remove|Use|Show|Hide|Click).{0,200}\.', notes)
    return m.group(0) if m else None
```

#### 4.3 Extraction functions

```python
def extract_and_store_booklet(
    pdf_path: str,
    unit_id: int,
    page_texts: dict[int, str],   # from existing PDF extraction
    model: str = "claude-sonnet-4-6"
):
    pages = {}
    total_tokens = 0
    for page_num, page_text in sorted(page_texts.items()):
        token_count = count_tokens_for_chunk(page_text, model)
        pages[str(page_num)] = {"text": page_text, "token_count": token_count}
        total_tokens += token_count

    content = {
        "document_type": "booklet",
        "total_token_count": total_tokens,
        "tokenizer_model": model,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages
    }
    _write_content(unit_id, content, model)

def extract_and_store_lesson(
    pptx_path: str,
    unit_id: int,
    extracted_slides: dict[int, dict],  # {slide_num: {text, notes}} from existing PPTX extraction
    model: str = "claude-sonnet-4-6"
):
    slides = {}
    total_tokens = 0
    for slide_num, slide_data in sorted(extracted_slides.items()):
        combined = slide_data["text"] + " " + slide_data.get("notes", "")
        token_count = count_tokens_for_chunk(combined, model)
        entry = {
            "text": slide_data["text"],
            "notes": slide_data.get("notes", ""),
            "token_count": token_count,
            "story_slide": detect_story_slide(slide_data["text"], slide_data.get("notes", "")),
            "source_pages": parse_source_pages(slide_data.get("notes", "")),
            "vocabulary_notes": parse_vocabulary_notes(slide_data.get("notes", ""))
        }
        anim = parse_animation_notes(slide_data.get("notes", ""))
        if anim:
            entry["animation_notes"] = anim
        slides[str(slide_num)] = entry
        total_tokens += token_count

    content = {
        "document_type": "lesson",
        "total_token_count": total_tokens,
        "tokenizer_model": model,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "slides": slides
    }
    _write_content(unit_id, content, model)

def _write_content(unit_id: int, content: dict, model: str):
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE units SET
                content                 = %s,
                content_stale           = false,
                content_extracted_at    = now(),
                content_tokenizer_model = %s
            WHERE unit_id = %s
        """, (json.dumps(content), model, unit_id))
    conn.commit()
    conn.close()

def check_staleness(unit_id: int) -> dict:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT content_stale, content_extracted_at, content_tokenizer_model
            FROM units WHERE unit_id = %s
        """, (unit_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}
```

---

## 5. Component 3: Context Assembly Layer

### File: `src/story_context.py`

```python
import os
import json
from dataclasses import dataclass, field
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

@dataclass
class StoryPackRequest:
    lesson_unit_id:      int
    booklet_unit_id:     int
    year:                int
    context_budget_tokens: int = 8000
    model:               str  = "claude-sonnet-4-6"

SYSTEM_PROMPT_TOKENS = 1200  # reserved estimate for system prompt
```

#### 5.1 Step 1 — Story slides

```python
def get_story_slide_data(lesson_unit_id: int) -> list[dict]:
    """Returns story slides with their source pages and notes."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                slide_key,
                slide_value->>'notes'           AS notes,
                slide_value->>'animation_notes' AS animation_notes,
                slide_value->'source_pages'     AS source_pages,
                slide_value->'vocabulary_notes' AS vocabulary_notes,
                (slide_value->>'token_count')::int AS token_count
            FROM units,
                jsonb_each(content->'slides') AS slides(slide_key, slide_value)
            WHERE unit_id = %s
              AND (slide_value->>'story_slide')::boolean = true
            ORDER BY slide_key::int ASC
        """, (lesson_unit_id,))
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

#### 5.2 Step 2 — Booklet pages

```python
def get_booklet_pages(booklet_unit_id: int, page_numbers: list[int]) -> dict[int, dict]:
    """Returns text and token counts for specific booklet pages only."""
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                page_key::int                   AS page_number,
                page_value->>'text'             AS text,
                (page_value->>'token_count')::int AS token_count
            FROM units,
                jsonb_each(content->'pages') AS pages(page_key, page_value)
            WHERE unit_id = %s
              AND page_key::int = ANY(%s)
            ORDER BY page_key::int ASC
        """, (booklet_unit_id, page_numbers))
        rows = cur.fetchall()
    conn.close()
    return {r["page_number"]: {"text": r["text"], "token_count": r["token_count"]} for r in rows}
```

#### 5.3 Step 3 — Vocabulary with prior context

Uses `concepts` (not `vocabulary`), `occurrences.concept_id` (not `vocab_id`), `occurrences.year` (not `year_group`), and `co_occurrences` for cross-subject links (not `edges`, which connects occurrences not concepts).

```python
def get_vocabulary_with_prior_context(lesson_unit_id: int, year: int) -> list[dict]:
    """
    Returns concepts for the current unit with enrichment data and prior occurrence context.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
            prior_occurrences AS (
                SELECT
                    o.concept_id,
                    o.year,
                    o.term    AS curriculum_term,
                    o.unit    AS unit_name,
                    o.subject
                FROM occurrences o
                WHERE o.concept_id IN (SELECT concept_id FROM current_unit_concepts)
                  AND o.year <= %s
                  AND o.unit_id != %s
            ),
            connected_concepts AS (
                SELECT
                    CASE
                        WHEN co.concept_a_id = cuc.concept_id THEN co.concept_a_id
                        ELSE co.concept_b_id
                    END AS source_concept_id,
                    CASE
                        WHEN co.concept_a_id = cuc.concept_id THEN co.concept_b_id
                        ELSE co.concept_a_id
                    END AS connected_concept_id,
                    c2.term    AS connected_term,
                    co.is_cross_subject,
                    co.weight
                FROM current_unit_concepts cuc
                JOIN co_occurrences co
                    ON co.concept_a_id = cuc.concept_id
                    OR co.concept_b_id = cuc.concept_id
                JOIN concepts c2
                    ON c2.concept_id = CASE
                        WHEN co.concept_a_id = cuc.concept_id THEN co.concept_b_id
                        ELSE co.concept_a_id
                    END
                WHERE co.granularity = 'unit'
                  AND co.weight >= 2
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
                )) FILTER (WHERE po.concept_id IS NOT NULL) AS prior_occurrences,
                json_agg(DISTINCT jsonb_build_object(
                    'term',            cc.connected_term,
                    'is_cross_subject', cc.is_cross_subject,
                    'weight',          cc.weight
                )) FILTER (WHERE cc.source_concept_id IS NOT NULL) AS connected_concepts
            FROM current_unit_concepts cuc
            LEFT JOIN prior_occurrences po ON cuc.concept_id = po.concept_id
            LEFT JOIN connected_concepts cc ON cuc.concept_id = cc.source_concept_id
            GROUP BY cuc.concept_id, cuc.term, cuc.definition,
                     cuc.etymology, cuc.word_family, cuc.tier
            ORDER BY cuc.concept_id
        """, (lesson_unit_id, year, lesson_unit_id))
        rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

#### 5.4 Step 4 — Budget check and assembly

```python
def assemble_context(request: StoryPackRequest) -> dict:
    from src.content_ingestion import check_staleness

    warnings = []

    staleness = check_staleness(request.lesson_unit_id)
    if staleness.get("content_stale"):
        warnings.append(
            f"Lesson content flagged stale since {staleness['content_extracted_at']}. "
            "Proceeding with cached content."
        )

    story_slides = get_story_slide_data(request.lesson_unit_id)
    all_source_pages = sorted(set(
        p for slide in story_slides
        for p in (slide["source_pages"] or [])
    ))

    booklet_pages = get_booklet_pages(request.booklet_unit_id, all_source_pages)
    vocabulary = get_vocabulary_with_prior_context(request.lesson_unit_id, request.year)

    story_slide_tokens = sum(s["token_count"] for s in story_slides)
    booklet_tokens     = sum(p["token_count"] for p in booklet_pages.values())
    vocab_tokens       = len(vocabulary) * 80  # rough estimate: 80 tokens per term

    total = SYSTEM_PROMPT_TOKENS + story_slide_tokens + booklet_tokens + vocab_tokens

    if total > request.context_budget_tokens:
        budget_for_booklet = (
            request.context_budget_tokens
            - SYSTEM_PROMPT_TOKENS
            - story_slide_tokens
            - vocab_tokens
        )
        booklet_pages = _trim_pages_to_budget(booklet_pages, budget_for_booklet)
        warnings.append("Context trimmed to fit token budget. Some booklet pages excluded.")

    return {
        "story_slides":  story_slides,
        "booklet_pages": booklet_pages,
        "vocabulary":    vocabulary,
        "year":          request.year,
        "warnings":      warnings,
        "total_estimated_tokens": total,
    }

def _trim_pages_to_budget(
    pages: dict[int, dict],
    budget: int
) -> dict[int, dict]:
    """Keep pages in order until budget is exhausted."""
    kept, running = {}, 0
    for page_num, page in sorted(pages.items()):
        if running + page["token_count"] <= budget:
            kept[page_num] = page
            running += page["token_count"]
    return kept
```

---

## 6. Component 4: Generation Engine

### File: `src/story_generator.py`

```python
import json
import os
import psycopg2
import psycopg2.extras
import anthropic
from dotenv import load_dotenv
from src.story_context import StoryPackRequest, assemble_context

load_dotenv()
client = anthropic.Anthropic()

# Version this string. Bump the version comment when changed.
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
- Terms in `vocabulary_notes` must be embedded naturally per the teacher notes guidance.
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
12. HERALDS WHAT IS COMING NEXT — mark with [HERALD: brief foreshadowing phrase] to build anticipation before each new slide or narrative turn. E.g. 'But that was not the end of the story...'

Annotation density: aim for at least one annotation per paragraph. Every slide transition must carry a [HERALD] before it and a [SLIDE N] marker.

SLIDE TRANSITION MARKERS
- Insert [SLIDE N] at the correct point in the narrative.

OUTPUT FORMAT
Produce three sections:
1. VOCABULARY PRE-TEACH BLOCK — word, definition, example sentence in the unit's context
2. ANNOTATED STORY — narrative with inline performance annotations and slide markers
3. TEACHER EMPHASIS BRIEFING — three bullet points highlighting what to land hardest
""".strip()
```

#### 6.1 User prompt

```python
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
        prior_str = ""
        prior = concept.get("prior_occurrences") or []
        if prior:
            refs = [
                f"{p['subject']} Y{p['year']} {p['unit']}"
                for p in prior if p
            ]
            prior_str = f" [Previously encountered in: {', '.join(refs)}]"
        tier_str = f" (Tier {concept['tier']})" if concept["tier"] else ""
        parts.append(f"- {concept['term']}{tier_str}: {concept['definition'] or '(no definition yet)'}{prior_str}")

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
            parts.append(f"Vocabulary to embed naturally (do not define mid-story): {', '.join(vocab_notes)}")

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
```

#### 6.2 Full pipeline

```python
def generate_story_pack(request: StoryPackRequest) -> dict:
    context    = assemble_context(request)
    user_prompt = build_user_prompt(context)

    response = client.messages.create(
        model=request.model,
        max_tokens=4000,
        system=OWL_STORY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    story_text = response.content[0].text

    fact_check = fact_check_story(story_text, context["booklet_pages"])
    rubric     = score_story_rubric(story_text, context)

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
        }
    }

    _persist_story_pack(request, result)
    return result

def _persist_story_pack(request: StoryPackRequest, result: dict):
    import json as _json
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO generated_story_packs
                (lesson_unit_id, booklet_unit_id, year, model,
                 story_pack_text, fact_check_results, rubric_scores,
                 context_metadata, input_tokens, output_tokens, warnings)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            request.lesson_unit_id,
            request.booklet_unit_id,
            request.year,
            request.model,
            result["story_pack_text"],
            _json.dumps(result["fact_check_results"]),
            _json.dumps(result["rubric_scores"]),
            _json.dumps(result["context_metadata"]),
            result["input_tokens"],
            result["output_tokens"],
            result["warnings"],
        ))
    conn.commit()
    conn.close()
```

---

## 7. Component 5: QA Layer

### File: `src/story_qa.py`

```python
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

FACTCHECK_SYSTEM_PROMPT = """
You are a fact-checking assistant for educational content.
You will be given a generated story and the booklet pages it was generated from.
Identify every specific factual claim (named people, dates, places, quantities, events) 
and verify whether it appears in the source pages.
Return a JSON array. Each item: {"claim": str, "verified": bool, "source_page": int|null}.
Flag anything not directly supported as verified: false.
Return ONLY the JSON array. No preamble.
"""

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
            "content": f"SOURCE PAGES:\n{source_text}\n\nGENERATED STORY:\n{story_text}"
        }]
    )
    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return [{"claim": "parse error", "verified": False, "source_page": None}]

RUBRIC_DIMENSIONS = [
    ("causal_chain",            "Does each event cause or directly lead to the next, or is it sequential facts joined by 'and then'?"),
    ("vocabulary_integration",  "Are pre-taught vocabulary words woven in naturally at appropriate density?"),
    ("dramatic_structure",      "Is there a clear hook, building tension, and revelation moment?"),
    ("knowledge_fidelity",      "Does the story stay within the source pages without inferring unsupported details?"),
    ("register",                "Is the language appropriate for the specified year group?"),
    ("performance_architecture","Does annotation structure include PAUSE, VOICE, PACE, FEEL, GESTURE at appropriate moments, with slide markers in the right places?"),
]

RUBRIC_SYSTEM_PROMPT = """
You score a teacher story pack against pedagogical criteria.
For each dimension, give a score 1–5 and a one-sentence justification.
Return ONLY a JSON object: {"dimension_key": {"score": int, "justification": str}, ...}.
"""

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
            )
        }]
    )
    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {"parse_error": {"score": 0, "justification": "Failed to parse rubric response"}}
```

---

## 8. Dashboard Integration

New route file: `owl-knowledge-map-dashboard/api/routes/story_packs.py`

Register in `api/main.py`: `app.include_router(story_packs.router, prefix="/api")`

### Endpoints

```
GET  /api/story-packs/
     ?lesson_unit_id=&approved_only=false&page=1&page_size=20
     → list of packs (id, lesson_unit_id, booklet_unit_id, year, model,
       human_approved, approved_by, created_at, warning count)

POST /api/story-packs/generate
     body: {lesson_unit_id, booklet_unit_id, year, model?, context_budget_tokens?}
     → triggers generate_story_pack(); returns new pack id

GET  /api/story-packs/{id}
     → full pack: story_pack_text, fact_check_results, rubric_scores,
       context_metadata, warnings, human_approved

PATCH /api/story-packs/{id}/approve
     body: {approved_by: str}
     → sets human_approved=true, approved_by, approved_at=now()
     → returns updated pack record
```

---

## 9. Design Decisions (Carried Forward from Design Spec)

- **Drive is the canonical source.** `units.content` is a cache. When in conflict, Drive wins. The `content_stale` flag exists for this reason.
- **Token counts stored at extraction time, not generation time.** Running `count_tokens` per chunk once during corpus ingestion prevents repeated API calls at generation time.
- **Tokenizer is model-specific.** If the generation model changes, stored token counts are approximate until the corpus is re-extracted. The `content_tokenizer_model` column records this.
- **No hallucination by design.** The system prompt instructs the model to use only source page content. The fact-check pass verifies this. Human approval (`human_approved`) is the final gate before delivery to schools.
- **`co_occurrences` for concept-level links.** The design spec used `edges` for concept-to-concept connections, but in the live schema `edges` connects `occurrences` (specific curriculum locations), not concepts. The concept-level graph is `co_occurrences`. The vocabulary context query uses `co_occurrences` at `granularity='unit'` to find conceptually related terms.
- **Full recompute, not incremental.** Co-occurrence computation (already in place) truncates and recomputes. The same approach applies to content ingestion — re-extract a unit by calling the extraction function again; `_write_content` overwrites the existing JSONB.

### Open questions (from design spec — not yet resolved)

1. What is the full text of Steve Mastin's twelve-point storytelling checklist? Required for `OWL_STORY_SYSTEM_PROMPT`.
2. Should human approval live only in the database (current design) or also in a dedicated review UI in the dashboard?
3. Are there units where the story moment spans the full booklet rather than specific flagged pages? If so, does the token budget approach require adjustment?
4. Should `generated_story_packs` support versioning — multiple packs per lesson with one marked current?
5. What is the target latency for story pack generation? This affects whether the QA layer (fact-check + rubric) runs synchronously in the `POST /generate` response or is deferred.

---

## 10. Execution Order

```bash
# 1. Run migrations
psql $DATABASE_URL -f migrations/004_add_unit_content.sql
psql $DATABASE_URL -f migrations/005_create_generated_story_packs.sql

# 2. Verify schema
psql owl -c "\d units"
psql owl -c "\d generated_story_packs"

# 3. Test story slide detection on a known lesson PPTX
python -c "
from src.content_ingestion import detect_story_slide, parse_source_pages, parse_vocabulary_notes
notes = \"Now you tell the story, using the information on Pages 5 and 6. When you reach the word 'precinct'...\"
print(detect_story_slide('Let\\'s listen to a story.', notes))
print(parse_source_pages(notes))
print(parse_vocabulary_notes(notes))
"

# 4. Extract content for one unit (dry run — inspect JSONB output)
# Integrate extract_and_store_lesson / extract_and_store_booklet calls
# into batch_process.py after PPTX/PDF extraction runs.
# Test against: Y5 Autumn 1 Baghdad (lesson + booklet unit_ids from units table)

# 5. Generate a story pack for the test unit
python -c "
from src.story_context import StoryPackRequest
from src.story_generator import generate_story_pack
req = StoryPackRequest(
    lesson_unit_id=<y5_baghdad_lesson_unit_id>,
    booklet_unit_id=<y5_baghdad_booklet_unit_id>,
    year=5
)
result = generate_story_pack(req)
print(result['story_pack_text'][:500])
print('Fact check items:', len(result['fact_check_results']))
print('Unverified claims:', sum(1 for r in result['fact_check_results'] if not r['verified']))
"

# 6. Repeat for Y6 Summer 1 Ur as second test case

# 7. Register story_packs router in dashboard and test endpoints
# GET /api/story-packs/ should return the two generated packs
# PATCH /api/story-packs/{id}/approve to test approval gate
```

---

## 11. Implementation Notes

- All Python scripts load `DATABASE_URL` and `ANTHROPIC_API_KEY` from `.env` via `python-dotenv`
- The `client.messages.count_tokens()` call requires `anthropic>=0.28.0` (already in requirements)
- JSONB keys for pages and slides are stored as strings (`"3"`, `"11"`) to satisfy PostgreSQL `jsonb_each`; cast to `::int` in ORDER BY clauses
- `parse_source_pages` handles both "Page N" and "Pages N and M" / "Pages N, M and P" patterns
- The `co_occurrences` table uses `concept_a_id < concept_b_id` canonical ordering — the vocabulary context query handles both directions via CASE expressions
- `enrichment_status = 'approved'` filter in the vocabulary query means concepts must have passed the enrichment review cycle before appearing in story packs; unenriched concepts are excluded
