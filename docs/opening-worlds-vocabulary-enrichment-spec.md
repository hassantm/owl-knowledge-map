# Opening Worlds — Vocabulary Enrichment & Co-occurrence Pipeline
## Design & Functional Specification

**Project:** Opening Worlds Knowledge Map — Phase 2 Vocabulary Layer  
**Prepared for:** Claude Code implementation session  
**Status:** Ready for implementation  

---

## 1. Overview

This specification covers three interconnected components that extend the existing Opening Worlds knowledge graph (concepts, occurrences, edges tables) with a richer vocabulary layer and a derived co-occurrence graph.

### Components

| Component | Purpose |
|-----------|---------|
| **1. Schema Migration** | Add precomputed vocabulary fields to concepts table; create co_occurrences table |
| **2. Enrichment Pipeline** | Batch LLM enrichment of all concepts with review/approval workflow |
| **3. Co-occurrence Computation** | Derive co-occurrence edges from existing occurrences data |

### Guiding Architecture Principle

Store what is stable; generate what is contextual. LLM calls are used once at enrichment time to populate fixed fields (etymology, word family, register, tier, definition). At query time, the LLM receives only structured trusted data from the DB and performs synthesis, not recall.

---

## 2. Existing Schema Assumptions

The implementation assumes the following tables already exist:

```sql
-- Existing tables (do not modify structure, only add to concepts)
concepts    (id serial PK, name text, ...)
occurrences (id serial PK, concept_id int FK, subject text, 
             year_group int, unit_id int, unit_name text, 
             unit_order int, slide_id int, slide_title text)
edges       (id serial PK, concept_a_id int FK, concept_b_id int FK,
             edge_type text, edge_nature text)
```

If column names differ in the live schema, adjust the queries accordingly. All new objects are additive — nothing in the existing schema is modified or dropped.

---

## 3. Component 1: Schema Migration

### 3.1 Concepts Table — New Columns

```sql
-- File: migrations/001_add_vocabulary_enrichment.sql

ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS definition         text,
    ADD COLUMN IF NOT EXISTS etymology          text,
    ADD COLUMN IF NOT EXISTS word_family        text[],
    ADD COLUMN IF NOT EXISTS register           text
        CHECK (register IN (
            'subject-specific',
            'formal academic', 
            'technical',
            'general formal'
        )),
    ADD COLUMN IF NOT EXISTS tier               integer
        CHECK (tier IN (1, 2, 3)),
    ADD COLUMN IF NOT EXISTS enrichment_status  text
        NOT NULL DEFAULT 'pending'
        CHECK (enrichment_status IN (
            'pending',
            'generated',
            'approved',
            'rejected'
        )),
    ADD COLUMN IF NOT EXISTS enrichment_notes   text,
    ADD COLUMN IF NOT EXISTS enriched_at        timestamptz,
    ADD COLUMN IF NOT EXISTS enriched_by        text DEFAULT 'claude-batch';
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `definition` | text | Curriculum-appropriate definition for a KS2 teacher. 1–2 sentences. |
| `etymology` | text | Language of origin, root meaning, approximate entry into English. 1–2 sentences. |
| `word_family` | text[] | Related word forms — e.g. `['empire', 'imperial', 'imperialism', 'emperor']` |
| `register` | text | One of four controlled values (see CHECK constraint) |
| `tier` | int | Beck & Beck vocabulary tier: 1 = everyday, 2 = cross-subject academic, 3 = subject-specific technical |
| `enrichment_status` | text | State machine field controlling the pipeline workflow |
| `enrichment_notes` | text | Free-text reviewer notes added during review (edits made, concerns flagged, source referenced) |
| `enriched_at` | timestamptz | Timestamp of last LLM enrichment run for this concept |
| `enriched_by` | text | Source of enrichment — defaults to `'claude-batch'`; set to reviewer initials on manual approval |

### 3.2 Enrichment Status State Machine

```
pending ──► generated ──► approved
                │
                └──► rejected ──► pending  (re-queued for next batch run)
```

- `pending`: Initial state for all concepts; also state after rejection
- `generated`: LLM has written fields, awaiting human review
- `approved`: Reviewer has confirmed (with or without edits); safe to use in application
- `rejected`: Reviewer rejected; concept returns to `pending` for re-enrichment

### 3.3 Co-occurrences Table

```sql
-- File: migrations/002_create_co_occurrences.sql

CREATE TABLE IF NOT EXISTS co_occurrences (
    id              serial PRIMARY KEY,
    concept_a_id    integer NOT NULL REFERENCES concepts(id),
    concept_b_id    integer NOT NULL REFERENCES concepts(id),
    subject_a       text    NOT NULL,
    subject_b       text    NOT NULL,
    granularity     text    NOT NULL
        CHECK (granularity IN ('lesson', 'unit', 'year_group')),
    weight          integer NOT NULL CHECK (weight > 0),
    is_cross_subject boolean GENERATED ALWAYS AS (subject_a != subject_b) STORED,
    computed_at     timestamptz NOT NULL DEFAULT now(),

    -- Prevent duplicate pairs at the same granularity
    CONSTRAINT co_occurrences_unique
        UNIQUE (concept_a_id, concept_b_id, subject_a, subject_b, granularity),

    -- Enforce canonical ordering (a < b) to prevent mirrored duplicates
    CONSTRAINT concept_ordering
        CHECK (concept_a_id < concept_b_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_co_occ_concept_a
    ON co_occurrences(concept_a_id);

CREATE INDEX IF NOT EXISTS idx_co_occ_concept_b
    ON co_occurrences(concept_b_id);

CREATE INDEX IF NOT EXISTS idx_co_occ_cross_subject
    ON co_occurrences(is_cross_subject)
    WHERE is_cross_subject = true;

CREATE INDEX IF NOT EXISTS idx_co_occ_granularity
    ON co_occurrences(granularity);
```

---

## 4. Component 2: Enrichment Pipeline

### 4.1 File Structure

```
enrichment/
├── enrich.py          # Main batch runner
├── review.py          # CLI review interface
├── prompts.py         # Prompt construction
├── db.py              # DB connection and queries
└── requirements.txt   # anthropic, psycopg2-binary, python-dotenv
```

### 4.2 Environment

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/opening_worlds
ANTHROPIC_API_KEY=sk-...
```

### 4.3 Enrichment Prompt

```python
# prompts.py

def build_enrichment_prompt(
    concept_name: str,
    subjects: list[str],
    year_groups: list[int]
) -> str:
    subjects_str   = ', '.join(subjects)
    year_groups_str = ', '.join(map(str, sorted(year_groups)))

    return f"""You are enriching a vocabulary database for a KS2 humanities curriculum \
(ages 7–11) grounded in Core Knowledge principles (E.D. Hirsch). The curriculum \
covers history and geography with a knowledge-rich, academically rigorous approach \
for primary school children in England.

CONCEPT: "{concept_name}"
SUBJECT CONTEXT: {subjects_str}
YEAR GROUPS WHERE IT APPEARS: {year_groups_str}

Return ONLY a valid JSON object with exactly these fields. No preamble, no markdown \
fences, no trailing commas. The JSON must be parseable with json.loads():

{{
    "definition": "A clear, curriculum-appropriate definition written for a KS2 \
class teacher (not the pupil). 1–2 sentences. Should reflect the concept's meaning \
in the subject context given.",

    "etymology": "The word's origin — language it derives from, root meaning, and \
approximately when it entered English. 1–2 sentences. Accessible to a non-linguist.",

    "word_family": ["array", "of", "related", "word", "forms"],

    "register": "Exactly one of: subject-specific, formal academic, technical, \
general formal",

    "tier": 2
}}

Tier guidance:
- 1: Everyday conversational language (unlikely in this curriculum)
- 2: General academic vocabulary that appears across multiple subjects and \
disciplines (e.g. 'evidence', 'significant', 'process')
- 3: Subject-specific technical vocabulary tied to history or geography \
(e.g. 'irrigation', 'dynasty', 'contour')
"""
```

### 4.4 DB Layer

```python
# db.py

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

def get_pending_concepts(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                c.id,
                c.name,
                ARRAY_AGG(DISTINCT o.subject)    AS subjects,
                ARRAY_AGG(DISTINCT o.year_group) AS year_groups
            FROM concepts c
            JOIN occurrences o ON o.concept_id = c.id
            WHERE c.enrichment_status = 'pending'
            GROUP BY c.id, c.name
            ORDER BY c.id
        """)
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
            WHERE id = %(id)s
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
            WHERE id = %(id)s
        """, {**fields, 'notes': notes, 'reviewer': reviewer, 'id': concept_id})
    conn.commit()

def set_status(conn, concept_id: int, status: str, notes: str = None):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE concepts SET
                enrichment_status = %s,
                enrichment_notes  = COALESCE(%s, enrichment_notes)
            WHERE id = %s
        """, (status, notes, concept_id))
    conn.commit()

def get_next_for_review(conn) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, definition, etymology,
                   word_family, register, tier, enrichment_notes
            FROM concepts
            WHERE enrichment_status = 'generated'
            ORDER BY id
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
```

### 4.5 Batch Enrichment Runner

```python
# enrich.py

import json
import time
import argparse
import anthropic
from db import get_connection, get_pending_concepts, write_generated, get_enrichment_summary
from prompts import build_enrichment_prompt

client = anthropic.Anthropic()

REQUIRED_FIELDS = {'definition', 'etymology', 'word_family', 'register', 'tier'}
VALID_REGISTERS = {'subject-specific', 'formal academic', 'technical', 'general formal'}
VALID_TIERS     = {1, 2, 3}

def validate_enrichment(data: dict) -> tuple[bool, str]:
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        return False, f"Missing fields: {missing}"
    if data['register'] not in VALID_REGISTERS:
        return False, f"Invalid register: '{data['register']}'"
    if data['tier'] not in VALID_TIERS:
        return False, f"Invalid tier: {data['tier']}"
    if not isinstance(data['word_family'], list):
        return False, "word_family must be a list"
    return True, ""

def enrich_concept(concept: dict) -> dict | None:
    prompt = build_enrichment_prompt(
        concept['name'],
        list(concept['subjects']),
        list(concept['year_groups'])
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()

        # Strip markdown fences if model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        valid, reason = validate_enrichment(data)

        if not valid:
            print(f"  ✗ Validation failed for '{concept['name']}': {reason}")
            return None

        return data

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON parse failed for '{concept['name']}': {e}")
        return None
    except Exception as e:
        print(f"  ✗ API error for '{concept['name']}': {e}")
        return None

def run_batch(batch_size: int = 50, delay: float = 0.5, dry_run: bool = False):
    conn = get_connection()

    # Print current state
    summary = get_enrichment_summary(conn)
    print("\nCurrent enrichment status:")
    for status, count in summary.items():
        print(f"  {status}: {count}")
    print()

    concepts = get_pending_concepts(conn)
    total_pending = len(concepts)

    if total_pending == 0:
        print("No concepts pending enrichment.")
        return

    concepts = concepts[:batch_size]
    print(f"Processing {len(concepts)} of {total_pending} pending concepts\n")

    success, failed = 0, 0

    for i, concept in enumerate(concepts, 1):
        print(f"[{i}/{len(concepts)}] '{concept['name']}'...", end=" ", flush=True)

        enrichment = enrich_concept(concept)

        if enrichment:
            if not dry_run:
                write_generated(conn, concept['id'], enrichment)
            print("✓")
            success += 1
        else:
            failed += 1

        time.sleep(delay)

    print(f"\nDone: {success} enriched, {failed} failed")
    if failed > 0:
        print(f"Re-run to retry {failed} failed concepts (they remain 'pending')")

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch enrich vocabulary concepts")
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--delay',      type=float, default=0.5,
                        help="Seconds between API calls")
    parser.add_argument('--dry-run',    action='store_true',
                        help="Run without writing to DB")
    args = parser.parse_args()

    run_batch(
        batch_size=args.batch_size,
        delay=args.delay,
        dry_run=args.dry_run
    )
```

### 4.6 CLI Review Interface

```python
# review.py

import argparse
from db import (get_connection, get_next_for_review, write_approved,
                set_status, get_enrichment_summary)

VALID_REGISTERS = ['subject-specific', 'formal academic', 'technical', 'general formal']

def prompt_edit(field_name: str, current_value) -> any:
    print(f"\n  Editing {field_name} (press Enter to keep current):")
    print(f"  Current: {current_value}")
    new_value = input("  New value: ").strip()

    if not new_value:
        return current_value

    # Type coercion for specific fields
    if field_name == 'tier':
        return int(new_value)
    if field_name == 'word_family':
        return [w.strip() for w in new_value.split(',')]

    return new_value

def review_session(reviewer: str):
    conn = get_connection()

    summary = get_enrichment_summary(conn)
    awaiting = summary.get('generated', 0)
    print(f"\n{awaiting} concept(s) awaiting review\n")

    reviewed = 0

    while True:
        concept = get_next_for_review(conn)

        if not concept:
            print(f"\nReview complete. {reviewed} concept(s) reviewed this session.")
            break

        print(f"\n{'='*60}")
        print(f"  CONCEPT:     {concept['name']}")
        print(f"{'='*60}")
        print(f"  Definition:  {concept['definition']}")
        print(f"  Etymology:   {concept['etymology']}")
        print(f"  Word family: {', '.join(concept['word_family'] or [])}")
        print(f"  Register:    {concept['register']}")
        print(f"  Tier:        {concept['tier']}")
        if concept['enrichment_notes']:
            print(f"  Notes:       {concept['enrichment_notes']}")
        print(f"\n  [a]pprove  [e]dit & approve  [r]eject  [s]kip  [q]uit")

        choice = input("\n  > ").strip().lower()

        if choice == 'a':
            notes = input("  Notes (optional, press Enter to skip): ").strip() or None
            fields = {k: concept[k] for k in
                      ['definition', 'etymology', 'word_family', 'register', 'tier']}
            write_approved(conn, concept['id'], fields, notes, reviewer)
            print(f"  ✓ Approved")
            reviewed += 1

        elif choice == 'e':
            fields = {k: concept[k] for k in
                      ['definition', 'etymology', 'word_family', 'register', 'tier']}

            print("\n  Which field to edit?")
            print("  [1] definition  [2] etymology  [3] word_family  "
                  "[4] register  [5] tier  [6] multiple")
            field_choice = input("  > ").strip()

            field_map = {
                '1': 'definition',
                '2': 'etymology',
                '3': 'word_family',
                '4': 'register',
                '5': 'tier'
            }

            if field_choice in field_map:
                key = field_map[field_choice]
                fields[key] = prompt_edit(key, fields[key])
            elif field_choice == '6':
                for key in fields:
                    fields[key] = prompt_edit(key, fields[key])

            notes = input("\n  Reviewer notes (describe edits made): ").strip() or None
            write_approved(conn, concept['id'], fields, notes, reviewer)
            print(f"  ✓ Edited and approved")
            reviewed += 1

        elif choice == 'r':
            reason = input("  Reason for rejection (optional): ").strip() or None
            set_status(conn, concept['id'], 'rejected', reason)
            print(f"  ✗ Rejected — returned to pending queue")
            reviewed += 1

        elif choice == 's':
            # Skip without changing status — come back to it next session
            print(f"  → Skipped")

        elif choice == 'q':
            print(f"\nSession ended. {reviewed} concept(s) reviewed.")
            break

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review generated vocabulary enrichments")
    parser.add_argument('--reviewer', required=True, help="Reviewer initials or name")
    args = parser.parse_args()

    review_session(args.reviewer)
```

### 4.7 Running the Enrichment Workflow

```bash
# Step 1: Run migration
psql $DATABASE_URL -f migrations/001_add_vocabulary_enrichment.sql
psql $DATABASE_URL -f migrations/002_create_co_occurrences.sql

# Step 2: First batch (50 concepts, dry run to verify prompt output)
python enrichment/enrich.py --batch-size 5 --dry-run

# Step 3: Real run in batches
python enrichment/enrich.py --batch-size 50

# Step 4: Review session
python enrichment/review.py --reviewer HM

# Step 5: Re-run to catch rejected/failed
python enrichment/enrich.py --batch-size 50

# Repeat steps 4-5 until all concepts approved
```

---

## 5. Component 3: Co-occurrence Computation

### 5.1 File Structure

```
enrichment/
└── compute_cooccurrences.py   # Add to existing enrichment/ directory
```

### 5.2 Computation Script

```python
# compute_cooccurrences.py

import argparse
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

# ── SQL: Lesson-level co-occurrence ──────────────────────────────────────────
# Two concepts co-occur at lesson level when they both appear on the same slide.
# Weight = number of slides where the pair appear together.

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
        ON  o1.slide_id   = o2.slide_id
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(*) > 0
"""

# ── SQL: Unit-level co-occurrence ─────────────────────────────────────────────
# Two concepts co-occur at unit level when they both appear within the same unit.
# Weight = number of distinct units where the pair appear together.
# This captures cross-subject pairs that never share a slide.

UNIT_COOCCURRENCE_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'unit'                                      AS granularity,
        COUNT(DISTINCT o1.unit_id)                  AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.unit_id    = o2.unit_id
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.unit_id) > 0
"""

# ── SQL: Year-group-level co-occurrence ───────────────────────────────────────
# Two concepts co-occur at year_group level when they appear in the same year group.
# This is the loosest signal — primarily useful for identifying broad thematic clusters
# and cross-subject bridge nodes that don't share a unit.

YEAR_GROUP_COOCCURRENCE_SQL = """
    SELECT
        LEAST(o1.concept_id, o2.concept_id)         AS concept_a_id,
        GREATEST(o1.concept_id, o2.concept_id)      AS concept_b_id,
        o1.subject                                  AS subject_a,
        o2.subject                                  AS subject_b,
        'year_group'                                AS granularity,
        COUNT(DISTINCT o1.year_group)               AS weight
    FROM occurrences o1
    JOIN occurrences o2
        ON  o1.year_group = o2.year_group
        AND o1.concept_id != o2.concept_id
    GROUP BY
        LEAST(o1.concept_id, o2.concept_id),
        GREATEST(o1.concept_id, o2.concept_id),
        o1.subject,
        o2.subject
    HAVING COUNT(DISTINCT o1.year_group) > 0
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

def compute_and_insert(conn, label: str, select_sql: str, dry_run: bool = False):
    print(f"\nComputing {label} co-occurrences...", end=" ", flush=True)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(select_sql)
        rows = cur.fetchall()

    print(f"{len(rows)} pairs found")

    if dry_run:
        print(f"  [dry-run] would insert/update {len(rows)} rows")
        if rows:
            sample = rows[0]
            print(f"  Sample: concept_a={sample['concept_a_id']}, "
                  f"concept_b={sample['concept_b_id']}, "
                  f"subjects={sample['subject_a']}/{sample['subject_b']}, "
                  f"weight={sample['weight']}")
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
    print(f"  ✓ Inserted/updated {len(rows)} rows")
    return len(rows)

def run_computation(dry_run: bool = False, granularities: list[str] = None):
    conn = psycopg2.connect(os.environ['DATABASE_URL'])

    if granularities is None:
        granularities = ['lesson', 'unit', 'year_group']

    tasks = {
        'lesson':     LESSON_COOCCURRENCE_SQL,
        'unit':       UNIT_COOCCURRENCE_SQL,
        'year_group': YEAR_GROUP_COOCCURRENCE_SQL,
    }

    if not dry_run:
        print("\nTruncating co_occurrences table for full recompute...")
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE co_occurrences")
        conn.commit()

    total = 0
    for granularity in granularities:
        if granularity in tasks:
            total += compute_and_insert(conn, granularity, tasks[granularity], dry_run)

    cross_subject = _count_cross_subject(conn) if not dry_run else '(skipped in dry-run)'
    print(f"\nTotal pairs: {total}")
    print(f"Cross-subject pairs: {cross_subject}")

    conn.close()

def _count_cross_subject(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM co_occurrences WHERE is_cross_subject = true")
        return cur.fetchone()[0]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute vocabulary co-occurrence edges")
    parser.add_argument('--dry-run',       action='store_true')
    parser.add_argument('--granularities', nargs='+',
                        choices=['lesson', 'unit', 'year_group'],
                        default=['lesson', 'unit', 'year_group'])
    args = parser.parse_args()

    run_computation(dry_run=args.dry_run, granularities=args.granularities)
```

---

## 6. Analytical Queries

These queries are not part of the pipeline but should be saved as reference queries (e.g. in a `queries/` directory) for use in the knowledge map interface and for exploratory analysis.

### 6.1 Bridge Node League Table

Ranks concepts by how many distinct cross-subject pairs they connect.

```sql
-- queries/bridge_nodes.sql

SELECT
    c.id,
    c.name,
    c.tier,
    COUNT(*)                                                AS total_cross_subject_links,
    COUNT(DISTINCT co.subject_a || '-' || co.subject_b)    AS distinct_subject_pairs,
    SUM(co.weight)                                         AS cumulative_weight,
    ARRAY_AGG(DISTINCT
        CASE WHEN co.concept_a_id = c.id THEN co.subject_a
             ELSE co.subject_b END
    )                                                      AS subjects_involved
FROM concepts c
JOIN co_occurrences co
    ON  (co.concept_a_id = c.id OR co.concept_b_id = c.id)
    AND co.is_cross_subject = true
    AND co.granularity = 'lesson'   -- tightest signal; change to 'unit' for broader view
GROUP BY c.id, c.name, c.tier
ORDER BY distinct_subject_pairs DESC, cumulative_weight DESC;
```

### 6.2 Two-Hop Indirect Path Finder

Given two concepts in different subjects, finds what bridge concept connects them.

```sql
-- queries/find_bridge.sql
-- Usage: substitute concept names for :concept_a and :concept_b

WITH cross_subject AS (
    SELECT
        concept_a_id,
        concept_b_id,
        subject_a,
        subject_b,
        weight
    FROM co_occurrences
    WHERE is_cross_subject = true
      AND granularity IN ('lesson', 'unit')
)
SELECT
    c_bridge.name                          AS bridge_concept,
    c_a.name                               AS concept_a,
    c_b.name                               AS concept_b,
    left_path.subject_a                    AS subject_a,
    right_path.subject_b                   AS subject_b,
    left_path.weight + right_path.weight   AS total_path_weight
FROM cross_subject left_path
JOIN cross_subject right_path
    ON  left_path.concept_b_id  = right_path.concept_a_id
JOIN concepts c_bridge ON c_bridge.id   = left_path.concept_b_id
JOIN concepts c_a      ON c_a.id        = left_path.concept_a_id
JOIN concepts c_b      ON c_b.id        = right_path.concept_b_id
WHERE c_a.name = :concept_a
  AND c_b.name = :concept_b
ORDER BY total_path_weight DESC;
```

### 6.3 Semantic Neighbourhood Query

Used by the vocabulary tool to retrieve a concept's co-occurrence context.

```sql
-- queries/vocabulary_neighbourhood.sql

SELECT
    c2.name,
    co.subject_a,
    co.subject_b,
    co.is_cross_subject,
    co.granularity,
    co.weight
FROM co_occurrences co
JOIN concepts c2
    ON c2.id = CASE
        WHEN co.concept_a_id = :concept_id THEN co.concept_b_id
        ELSE co.concept_a_id
    END
WHERE (co.concept_a_id = :concept_id OR co.concept_b_id = :concept_id)
  AND co.granularity = 'lesson'
ORDER BY co.is_cross_subject DESC, co.weight DESC
LIMIT 10;
```

---

## 7. Execution Order

```
1.  psql -f migrations/001_add_vocabulary_enrichment.sql
2.  psql -f migrations/002_create_co_occurrences.sql
3.  python enrichment/enrich.py --batch-size 5 --dry-run     ← verify prompt output
4.  python enrichment/enrich.py --batch-size 50              ← first real batch
5.  python enrichment/review.py --reviewer HM                ← review session
6.  Repeat steps 4–5 until all concepts approved
7.  python enrichment/compute_cooccurrences.py --dry-run     ← verify row counts
8.  python enrichment/compute_cooccurrences.py               ← full computation
9.  Run bridge node query to validate cross-subject structure
```

Co-occurrence computation (step 7–8) can run at any time after the occurrences data is stable — it does not depend on enrichment being complete. It should be re-run whenever new curriculum content is ingested.

---

## 8. Notes for Claude Code

- All scripts assume a `DATABASE_URL` environment variable and an `ANTHROPIC_API_KEY` in `.env`
- The enrichment script uses `claude-opus-4-6` — adjust model string if needed
- `psycopg2.extras.execute_values` is used for bulk inserts; ensure `psycopg2-binary` is installed
- The `LEAST`/`GREATEST` pattern in the co-occurrence SQL enforces the `concept_a_id < concept_b_id` canonical ordering required by the CHECK constraint
- All co-occurrence computation is a full truncate + recompute — not incremental. This is intentional: it keeps the logic simple and the table trustworthy. Runtime on a typical KS2 curriculum dataset should be well under a minute
- The `ON CONFLICT ... DO UPDATE` in the insert handles reruns gracefully if the truncate is removed in future
