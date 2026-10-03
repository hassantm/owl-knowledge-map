# OWL Knowledge Map — Project Context

> **Status of this file (2026-10-03):** rewritten to describe the system as it actually is.
> The previous version described the February 2026 SQLite/Anvil design and is in git history.
> Method and intent were re-decided with the owner on 2026-10-03 (see "Method and intent").
> **[UNDER REVIEW]** markers show where current behaviour differs from that decided method.

## Overview

This project analyses the Opening Worlds Ltd (OWL) Key Stage 2 humanities curriculum (History,
Geography, Religion; Years 3–6; 64 units). The curriculum was written by Christine Counsell and
Steve Mastin. The aim is to make its knowledge architecture visible to teachers: which concepts
are introduced where, and how they recur and build across units, years and subjects.

The project has three strands that share one database:
1. **Knowledge map:** concepts, occurrences, co-occurrences and human-judged edges.
2. **Vocabulary enrichment:** definitions, etymology, word family, register and tier for each concept.
3. **Story packs:** LLM-generated teacher storytelling resources, assembled from unit content and gated by human approval.

---

## System as built

### Repositories (siblings under `/home/htmadmin/dev/`)
| Repo | Role |
|---|---|
| `owl-knowledge-map` (this repo) | Pipeline: ingestion, gap-fill, enrichment, co-occurrences, story packs. System of record for the schema. |
| `owl-knowledge-map-dashboard` | FastAPI (`api/routes/`) + React/Vite front end over the same DB. Its `.env` is a symlink to this repo's `.env`. Start with `start_api.sh` (port 8000). |
| `owl-geo-scope` | Loose scripts that add `geo_scope*` columns to `public.concepts` and classify concepts. Its migration is not in `migrations/`. |
| `owl-knowledge-map-frontend` | The old Anvil app. **Superseded and dead**; do not extend it. |
| `owl-cpd-platform` | A separate product (Next.js/Prisma) using schema `cpd` in the same `owl` DB. |

A plan to consolidate the first three into one repo is in `docs/20260831_owl_consolidation_plan.md`. It has not been executed.

### Database: PostgreSQL `owl` on localhost
- Connection is set by `DATABASE_URL` in `.env`, read by `src/db.py` and `enrichment/db.py`.
- **Exceptions:** `src/uplink.py` and `src/graph_builder.py` read `OWL_DB_URL` instead, and fall back to a hard-coded DSN. `uplink.py` never loads `.env`.
- Never print `.env` contents. It holds `ANTHROPIC_API_KEY`.
- Schema `public` belongs to the knowledge map. Schema `cpd` belongs to the CPD platform, and `cpd.units` is unrelated to `public.units`. Always qualify table names when in doubt.
- **SQLite (`db/owl_knowledge_map.db`) is legacy.** It was migrated to Postgres on 2026-03-14 and is no longer the source of truth.
- **Schema is defined by** `src/build_db_postgres.sql`, then migrations `001`–`006`, applied by hand. There is no migration runner or version table. The `geo_scope` columns come from `owl-geo-scope/01_migrate_schema.sql`.

#### Tables (`public`)
| Table | Rows (2026-10-03) | Notes |
|---|---:|---|
| `units` | 64 | **Authoritative** for subject/year/term/unit. `booklet_content` and `lesson_content` are JSONB per-page and per-slide text. All 64 have booklet text; 22 have lesson text. |
| `concepts` | 2,946 | `term` stored exactly as authored. Enrichment columns: 2,927 approved, 19 pending. `geo_scope` is set for 887. |
| `occurrences` | 8,938 | One concept at one location. FK `unit_id`. Also holds **denormalised** subject/year/term/unit copies, of which 153 rows disagree with `units`. Always join to `units` on `unit_id` for labels. |
| `edges` | 176 | Human-confirmed links between occurrences, all made 2026-03-04 to 03-28, before the recurrence gap-fill. |
| `co_occurrences` | 270,367 | Derived concept pairs at lesson and unit granularity. **Stale**: computed 2026-04-30, before gap-fill. |
| `generated_story_packs` | 17 | All `claude-sonnet-4-6`, April 2026, none approved. |

#### Column gotchas
- `occurrences.term` is the **term period** (Autumn1…Summer2), not the word. The word is in `concepts.term`.
- `is_introduction` is an INTEGER 0/1. In practice 1 means **"on the unit's core vocab list"**, not "bold in the booklet". Only 24 introductions came from bold extraction. 63 concepts have more than one introduction.
- `vocab_source` is the vocab-list filename, `'booklet_gap_fill'` (recurrences mined from booklet text), `'bold_extraction'`, or NULL.
- `validation_status` is a leftover from the February bold-extraction audit. **It is still used as the "counts as data" filter** by the dashboard API, the uplink, `graph_builder` and `insights` (`= 'confirmed'`). That makes 3,645 rows invisible to them, most of them gap-fill recurrences including the 2026-10-03 batch. The 162 `matched` rows were overwritten by `enrichment/validate_md_vocabs.py`. `co_occurrences` and story context do not filter. **[UNDER REVIEW]** Decided: one inclusion rule for all consumers (see Method).
- `term_in_context` is a full paragraph for list-sourced rows and a ±60-character snippet for gap-fill rows.

### How data got here (history in brief)
1. **Feb 2026:** bold-run extraction from booklet PPTX (`extract_stage1/2.py`, `batch_process.py`) into SQLite, followed by noise filtering and audit.
2. **26 Feb, vocab-first decision** (`docs/20260226_vocab_first_architecture.md`): the authors' per-unit **Core vocab lists** are the authority for what counts as a concept. Bold formatting was only a proxy for that intent.
3. **Mar:** the Anvil review app. 176 edges were confirmed. Then the migration to Postgres.
4. **Apr:** migrations 001–006. Added enrichment (`enrichment/`), co-occurrences, the `units` table, content ingestion of booklet and lesson text, and story packs.
5. **Aug:** analysis docs (house style feasibility, ingest matcher fix plan, consolidation plan). The React dashboard replaced Anvil. A force-directed graph was tried and **deliberately rejected** as unreadable for primary teachers.
6. **2–3 Oct:** loaded booklet text for the 31 missing units and reran a cleaned gap-fill, adding 3,458 recurrences. Produced the single-occurrence and transferable-concept exports. See `docs/20261002_recurrence_gap_fill_session.md`.

### Scripts: current vs legacy
**Current (Postgres):**
- `src/batch_ingest.py`, `src/content_ingestion.py`: PPTX text into `units.*_content`. Needs `--dropbox-root`. There is no Dropbox mount on this host; files have been fetched through the Dropbox connector into `data/booklets/`.
- `src/gap_fill_occurrences.py`: mines booklet text for recurrences. Exact term only, case-insensitive, no plurals, and only for concepts introduced in or before the unit's year. The cleaned wrapper used in Oct is `data/booklets/gap_fill_clean.py` (gitignored).
- `enrichment/enrich.py`, `review.py`, `compute_cooccurrences.py`. Run them from inside `enrichment/`.
- `src/story_context.py`, `story_generator.py`, `story_qa.py`, `batch_generate.py`.
- `src/style_corpus_stats.py`.

**Legacy (SQLite) or broken. Do not run without reading them first:**
- SQLite-era scripts: `init_db.py`, `extract_stage1.py`, `extract_stage2.py`, `batch_process.py`, `vocab_validator.py`, `audit_terms.py`, `enrich_audit.py`, `apply_audit_decisions.py`, `vocab_first_cleanup.py`, `repair_chapters.py`, `migrate_add_audit_columns.py`, `insights.py`.
- `migrate_to_postgres.py`: would now fail, and its TRUNCATE CASCADE would wipe `co_occurrences`.
- `build_graph.py`: broken.
- `uplink.py`: Anvil only.
- **There is currently no Postgres-native path for extracting new concepts.**

### Known hazards
- `batch_generate.py --force --dry-run` **deletes** existing story packs, approved ones included, before it checks dry-run.
- `--dry-run` in `content_ingestion.py` and `enrich.py` still calls the Anthropic API.
- `story_context.py` treats later units in the same year as "prior" knowledge (`year <= year`).
- `compute_cooccurrences.py` year_group SQL double-counts cross-subject pairs. No year_group rows are currently stored.
- `occurrences` has no unique constraint, so `ON CONFLICT DO NOTHING` in gap-fill does nothing. Dedupe in code.
- Tests (`tests/`, 97) cover only enrichment and co-occurrences, against inlined schema copies. They drop tables in `TEST_DATABASE_URL`, so never point that at `owl`.
- `requirements.txt` is incomplete. It is missing `psycopg2-binary`, `python-dotenv`, `anthropic` and `pytest`.

### Working rules
- **Before any write to `owl`:** take a `pg_dump -Fc` into `backups/` and record the `max(id)` high-water mark. Make the script dry-run by default, and get the user's approval before running `--write`.
- Do not delete or regenerate story packs, edges or enrichment without explicit approval.
- `data/`, `output/` and `backups/` are gitignored, and the working files of recent sessions live there.

---

## Design decisions still standing

### Terms stored exactly as authored
No normalisation or stemming in `concepts.term`, which preserves the authors' choices.
**[UNDER REVIEW]** The code also uses this rule for *matching*, so "empire" ≠ "empires", 13 duplicates differ only by case, and truncated terms such as "lexandria" can't be matched. Decided: keep the authored term, and match on a separate key or variant list (see Method).

### Human judgement on edges
Edges carry human-assigned `edge_nature`. **[UNDER REVIEW]** Confirming each edge between individual occurrences does not scale: about 22,500 candidate pairs against 176 confirmed. Decided: model-drafted, human-checked, on consecutive trajectory steps (see Method).

### edge_type and edge_nature (decided 2026-03-01)
The two are orthogonal. Any nature can pair with any type.
- `edge_type`, the structural dimension, is auto-detected: `within_subject` | `cross_subject`.
- `edge_nature`, the pedagogical dimension, is human-assigned:
  - `reinforcement`: same concept, same kind of work.
  - `extension`: the concept gains new dimensions. Example: "empire" across the Roman, Islamic and British contexts.
  - `application`: the concept is used as a schema to understand something new, within or across subjects.

### Visualisation
Force-directed and emergent physics layouts were rejected (Aug 2026): position encodes nothing a teacher can read. Prefer static views where every position carries meaning (`ArchitectureView`, `TimelineView`, `WordAtlasView` in the dashboard).

---

## Method and intent (decided with the owner, 2026-10-03)

These decisions supersede the February design. Where the system above does not yet match them, they are the target.

### Intent
- **Primary audience: classroom teachers.** Four use moments, all in scope:
  - preparing a lesson ("which of these words has my class met before, and where?");
  - planning a unit or term ("what does this build on and set up?");
  - getting to know OWL / CPD;
  - catching up pupils who missed a unit.
- **No single headline claim.** The map is exploratory. It should show knowledge building over time, cross-subject connections, and load-bearing vs dropped concepts.
- **"Good enough for teachers" means all three of:**
  1. accurate per unit: no howlers for someone who knows the unit;
  2. a handful of flagship trajectories fully judged and well presented;
  3. endorsed by Christine and Steve.

### Method
- **Concept = an entry on a unit's core vocab list. Nothing else.** Bold extraction is retired. Rows from bold extraction or with no source need checking against the lists.
- **Every list entry stays in the map, tagged by type**, e.g. transferable concept / proper noun / unit-specific, so views can filter. `output/transferable_concepts_decisions.csv` is a first pass at this tagging for single-unit terms.
- **Recurrence = the same concept, in the same sense, from the point of introduction onward.**
  - Inflections and word-family forms count ("empire" matches "empires"). `concepts.term` stays exactly as authored; matching uses a separate key or variant list.
  - The sense check applies **only to terms flagged as ambiguous** (e.g. sacked, court, state, temple). Other matches are trusted.
  - Uses **before** the formal introduction are ignored. "Before" means earlier in curriculum order (year, then term), not just an earlier year. The current gap-fill cut-off is by year only, so it is too loose within a year.
- **One inclusion rule** for which occurrences count as data, applied identically by every consumer (pipeline, dashboard API, story context). `validation_status = 'confirmed'` is not that rule.
- **Edge judgement is model-drafted and human-checked.**
  - A model proposes `edge_nature` from the two contexts.
  - Hassan checks it.
  - Christine and Steve sign off a selection, at least the flagship trajectories, before anything reaches teachers.
  - Judge consecutive steps in a concept's trajectory, not every pair of occurrences. That is about 5,900 steps in total, about 4,300 of them for the 511 concepts spread across 5 or more units, as of 2026-10-03.

### Priority
Get the core map right ("accurate per unit") before extending enrichment, story packs or CPD integration further. The owner identified scope sprawl and tech churn as past problems.

---

## Story pack icon hashes

When running `src/batch_ingest.py` or `src/content_ingestion.py`, pass all three known story icon
hashes with `--story-icon-hash` so that all story slides are detected:

```
--story-icon-hash ccf3ec0b8550fa9acd31d8d4d5cae37e \
--story-icon-hash e0d120b4971f376a079b0a1f439969ec \
--story-icon-hash 48a024b806c0f826053b607fd36475c6
```

Identified 2026-04-29. They are visual variants of the same story icon.

## Future layers (not built)
- **Page images:** render booklet pages to images (`pymupdf`), stored on disk with paths in the DB, so an occurrence can show its actual page. `uplink.get_page_image` is a stub.
- **Context-shift analysis:** sentence embeddings over `term_in_context`, to see when a term does more sophisticated work in later years.

## People
- **Project owner:** Hassan Mamdani, COO/CFO, Opening Worlds Ltd.
- **Curriculum authors:** Christine Counsell and Steve Mastin, © 2021.
