# OWL Knowledge Map — Project Context

> **Status of this file (2026-10-03):** rewritten to describe the system as it actually is.
> The previous version described the February 2026 SQLite/Anvil design and is in git history.
> Method and intent were re-decided with the owner on 2026-10-03 (see "Method and intent").
> Phases 1–4 of the method reset are applied; Phase 5 (trajectory review) is next (see the plan doc).

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
- **Schema is defined by** `src/build_db_postgres.sql`, then migrations `001`–`010`, applied by hand. There is no migration runner or version table. The `geo_scope` columns come from `owl-geo-scope/01_migrate_schema.sql`.

#### Tables (`public`)
| Table | Rows (2026-10-03, after Phase 3) | Notes |
|---|---:|---|
| `units` | 64 | **Authoritative** for subject/year/term/unit. `booklet_content` and `lesson_content` are JSONB per-page and per-slide text. All 64 have booklet text; 22 have lesson text. |
| `concepts` | 2,980 (2,844 live) | `term` stored exactly as authored. `merged_into` marks the 136 concepts merged into a base-form concept (kept for traceability; exclude with `merged_into IS NULL`). New concepts from list alignment are enrichment `pending`. |
| `concept_forms` | 3,477 | Every form a concept is matched by: `authored` (the spellings on the lists) and `inflection` (lemminflect, reviewed). Only `status = 'approved'` forms are used for matching; 74 inflections are `rejected`. |
| `occurrences` | 9,072 | One concept at one location. FK `unit_id`. Denormalised subject/year/term/unit copies are stale for 153 rows: **never use them; join `units`**. `authored_term` holds the exact list wording for introductions. |
| `v_occurrences` (view) | 9,070 | **The single inclusion rule (migrations 007–009). Every consumer reads this, not `occurrences`.** Introduction = on that unit's current vocab list; recurrence = gap-fill match at or after the concept's first introduction in curriculum order. Exposes `curriculum_pos`, boolean `is_introduction`, `intro_source`, `authored_term`. |
| `edges` | 176 | Human-confirmed links between occurrences, made 2026-03-04 to 03-28. 4 now have one end demoted to a recurrence (`vocab_source = 'list_removed'`: Ethiopia, Christ, surrender, prayer) and need re-checking in Phase 5. |
| `co_occurrences` | 706,716 | Derived concept pairs at lesson and unit granularity, recomputed 2026-10-03. Both granularities are within one unit, so **cross-subject pairs are 0 by construction**; cross-subject analysis must come from trajectories. |
| `generated_story_packs` | 17 | All `claude-sonnet-4-6`, April 2026, none approved. Built on the old half-corpus; regenerate before use. |

#### Column gotchas
- `occurrences.term` is the **term period** (Autumn1…Summer2), not the word. The word is in `concepts.term`; the exact list wording in `occurrences.authored_term`.
- In `v_occurrences`, `is_introduction` is boolean and derived from `vocab_source` (list file = introduction). The raw `occurrences.is_introduction` INTEGER is kept consistent by the alignment script but is not authoritative. The dashboard casts the view's boolean back to 0/1 for the frontend.
- `vocab_source`: the current list file name (introductions), `'booklet_gap_fill'` (recurrences), or `'list_removed'` (edge-referenced row demoted to a recurrence).
- `concepts.concept_type` (transferable / proper_noun / unit_specific), `concept_category` and `concept_type_note` are the Phase 4 tags; transferable includes disciplinary TECHNICAL concepts. Tags describe the kind of word, never its spread.
- `concepts.is_ambiguous` marks polysemous concepts; `occurrences.sense_check` (same / different / unclear) records their recurrences' sense check. `different` rows are excluded by `v_occurrences` but kept.
- `validation_status` is a dead column from the February audit. Nothing reads it any more; do not reintroduce it as a filter.
- `term_in_context` is a full paragraph for older list-sourced rows and a ±60-character snippet for gap-fill and newly added rows.

### How data got here (history in brief)
1. **Feb 2026:** bold-run extraction from booklet PPTX (`extract_stage1/2.py`, `batch_process.py`) into SQLite, followed by noise filtering and audit.
2. **26 Feb, vocab-first decision** (`docs/20260226_vocab_first_architecture.md`): the authors' per-unit **Core vocab lists** are the authority for what counts as a concept. Bold formatting was only a proxy for that intent.
3. **Mar:** the Anvil review app. 176 edges were confirmed. Then the migration to Postgres.
4. **Apr:** migrations 001–006. Added enrichment (`enrichment/`), co-occurrences, the `units` table, content ingestion of booklet and lesson text, and story packs.
5. **Aug:** analysis docs (house style feasibility, ingest matcher fix plan, consolidation plan). The React dashboard replaced Anvil. A force-directed graph was tried and **deliberately rejected** as unreadable for primary teachers.
6. **2–3 Oct:** booklet text loaded for all 64 units, then the method reset (`docs/20261003_method_reset_plan.md`): Phase 1 single inclusion rule; Phase 2 concept hygiene, base-form merges, alignment of every unit with its **current** Dropbox vocab list, reviewed inflections; Phase 3 pruning, gap-fill rerun, co-occurrence recompute.

### Scripts: current vs legacy
**Current (Postgres).** All writing scripts are dry run by default; `--write` commits.
- `src/batch_ingest.py`, `src/content_ingestion.py`: PPTX text into `units.*_content`. Needs `--dropbox-root`. There is no Dropbox mount on this host; files are fetched through the Dropbox connector (large files via a temporary download link).
- `src/compare_vocab_lists.py` (read-only) and `src/align_vocab_lists.py`: compare/align every unit's introductions with its current list in `data/phase2/lists/<unit_id>_*.txt` (gitignored: OWL content; refetch from Dropbox when lists change). Shared parsing and concept resolution in `src/vocab_lists.py`.
- `src/phase2_concept_hygiene.py`: the one-off 2026-10-03 cleanup (already applied; kept for the record and as the home of shared write helpers).
- `src/generate_inflections.py`: stage lemminflect forms for review (`data/phase2/inflection_review.csv`), `--load` records decisions in `concept_forms`.
- `src/gap_fill_occurrences.py`: mines cleaned booklet text (credits, URLs, pronunciation guides stripped) for recurrences, matching every approved form, only at or after each concept's first introduction in curriculum order. Idempotent.
- `src/load_phase4.py`: loads reviewed tags, ambiguous flags and sense checks from `data/phase4/` (dry run by default).
- `src/prune_occurrences.py`: deletes rows outside the inclusion rule (never edge-referenced ones). Run after list or form changes, before gap-fill.
- `enrichment/enrich.py`, `review.py`, `compute_cooccurrences.py` (default lesson + unit). Run them from inside `enrichment/`.
- `src/story_context.py`, `story_generator.py`, `story_qa.py`, `batch_generate.py`.
- `src/style_corpus_stats.py`.

**Rebuild order after a list change:** refetch lists → `compare_vocab_lists.py` → `align_vocab_lists.py` → `generate_inflections.py` (review, `--load`) → `prune_occurrences.py` → `gap_fill_occurrences.py` → `compute_cooccurrences.py`.

**Legacy (SQLite) or broken. Do not run without reading them first:**
- SQLite-era scripts: `init_db.py`, `extract_stage1.py`, `extract_stage2.py`, `batch_process.py`, `vocab_validator.py`, `audit_terms.py`, `enrich_audit.py`, `apply_audit_decisions.py`, `vocab_first_cleanup.py`, `repair_chapters.py`, `migrate_add_audit_columns.py`, `insights.py`.
- `migrate_to_postgres.py`: would now fail, and its TRUNCATE CASCADE would wipe `co_occurrences`.
- `build_graph.py`: broken.
- `uplink.py`: Anvil only.
- `enrichment/validate_md_vocabs.py`: superseded by the list alignment; it overwrites `validation_status`.

### Known hazards
- `batch_generate.py --force --dry-run` **deletes** existing story packs, approved ones included, before it checks dry-run.
- `--dry-run` in `content_ingestion.py` and `enrich.py` still calls the Anthropic API.
- `story_context.py` treats later units in the same year as "prior" knowledge (`year <= year`); use `curriculum_pos`.
- `compute_cooccurrences.py` truncates and commits before recomputing; take a backup first.
- `occurrences` has no unique constraint. Gap-fill and the alignment dedupe in code.
- New recurrences of ambiguous concepts (`is_ambiguous`) from a future gap-fill run arrive with `sense_check` NULL and count until checked; sense-check them before relying on the numbers.
- Tests (`tests/`, 97) cover only enrichment and co-occurrences, against inlined schema copies. They drop tables in `TEST_DATABASE_URL`, so never point that at `owl`.
- `requirements.txt` is incomplete. It is missing `psycopg2-binary`, `python-dotenv`, `anthropic`, `lemminflect`, `python-pptx` and `pytest`.

### Working rules
- **Before any write to `owl`:** take a `pg_dump -Fc` into `backups/` and record the `max(id)` high-water mark. Make the script dry-run by default, and get the user's approval before running `--write`.
- Sample-check matches before writing (read ~30 random new rows with context). Every bug found in Phase 2–3 was found this way.
- Do not delete or regenerate story packs, edges or enrichment without explicit approval.
- `data/`, `output/` and `backups/` are gitignored, and the working files of recent sessions live there. The repo is public: never commit OWL list or booklet content.

---

## Design decisions still standing

### Terms stored exactly as authored
No normalisation or stemming in `concepts.term`, which preserves the authors' choices. Matching uses `concept_forms` instead: authored spellings plus reviewed inflections. Concepts that are forms of one word are merged (`merged_into`), keeping every authored spelling as a form and on its introduction (`authored_term`). 8 groups whose forms mean different things are kept separate (forced/forces, struck/strikes, clog/clogs, pit/pitted, yield/yielding, prevailing/prevailed, representative(s), demand(s)).

### Human judgement on edges
Edges carry human-assigned `edge_nature`. Confirming each occurrence pair does not scale (about 5,600 trajectory steps). Decided: model-drafted, human-checked, on consecutive trajectory steps (Phase 5).

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
