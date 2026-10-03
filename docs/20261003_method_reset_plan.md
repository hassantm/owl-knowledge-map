# Plan: reset the knowledge-map method and rebuild the core map

**Date:** 2026-10-03
**Status:** Phases 1–3 applied 2026-10-03 (see §6). Phases 4–5 next.
**Related:** [recurrence gap-fill session](20261002_recurrence_gap_fill_session.md) · [consolidation plan](20260831_owl_consolidation_plan.md) · [ingest matcher fix plan](20260830_ingest_matcher_fix_plan.md) · `CLAUDE.md` ("Method and intent")

---

## 1. Why this plan exists

Hassan asked whether the project had been approached correctly from the start. The review covered all code, all docs and the live `owl` database. Its conclusion: **the core idea was sound, but three founding choices were never revisited as the project grew.** Together they explain why the numbers have not felt right.

| Founding choice | What went wrong | Evidence (2026-10-03) |
|---|---|---|
| Recurrence treated as secondary to extraction | Bold extraction cannot see recurrences, which are by definition unbolded. Gap-fill was added later and covered only 33 of 64 units until 2026-10-03. Everything derived from reuse (edges, co-occurrences, dashboard density, story context) was built on half the corpus, skewed by subject. | `co_occurrences` computed 2026-04-30; all 176 edges date from March; the 17 story packs are from April. |
| "Store terms exactly as authored" also used as the matching rule | "empire" ≠ "empires"; duplicates that differ only by case; truncated terms ("lexandria", "hurch") can never match. Words with several meanings are counted without a sense check. | 13 case-only duplicates; 58 singular/plural pairs split across two concepts. |
| Human confirmation of every edge between individual occurrences | Never finishable, and it spends expert time confirming a mechanical fact instead of the judgement. | About 22,500 candidate pairs; 176 confirmed. |

The review also found that **nothing defines which occurrences count as data**. The dashboard API, uplink and graph code count only rows with `validation_status = 'confirmed'`, a leftover flag from the February audit. Other consumers count everything:

- **3,645 rows have no status at all**, including all 3,458 recurrences added on 2026-10-03. The dashboard cannot see them.
- **162 Geography rows were relabelled `matched`** by `validate_md_vocabs.py`, so they drop out of the confirmed-only views.
- **`co_occurrences` and story context apply no filter.**

The bold-text premise itself was corrected early, by the vocab-first decision of 26 Feb. That decision was right.

## 2. Decided method (interview with Hassan, 2026-10-03)

**Intent**
- **Audience:** classroom teachers.
- **Use moments, all in scope:**
  - preparing a lesson;
  - planning a unit or term;
  - getting to know OWL / CPD;
  - catching up pupils who missed a unit.
- **Claim:** none in particular; the map is exploratory. It should show knowledge building, cross-subject connections, and load-bearing versus dropped concepts.
- **"Good enough for teachers" means all three of:**
  1. accurate per unit;
  2. flagship trajectories fully judged and well presented;
  3. endorsed by Christine Counsell and Steve Mastin.

**Method**

| Question | Decision |
|---|---|
| What is a concept? | An entry on a unit's **core vocab list**. Nothing else; bold extraction is retired. |
| Which list entries are in scope? | **All of them, tagged by type**: transferable concept, proper noun, or unit-specific. Views filter on the tag. |
| What is a recurrence? | Same concept, **same sense**, from the point of introduction onward. **Inflections and word-family forms count.** |
| How is sense checked? | Only for terms flagged as **ambiguous** (e.g. sacked, court, state, temple). Other matches are trusted. |
| Use before formal introduction? | **Ignored.** "Before" means earlier in curriculum order (year, then term). |
| Which occurrences count? | **One inclusion rule**, used by every consumer. |
| Edge judgement | A **model drafts `edge_nature`** from the two contexts and **Hassan checks it**. Christine and Steve sign off a selection, at least the flagship trajectories, before anything reaches teachers. |
| Unit of judgement | **Consecutive steps in a concept's trajectory**, not every pair of occurrences. That is about 5,900 steps in total, about 4,300 of them for the 511 concepts appearing in 5 or more units. |
| Priority | The core map comes first. Enrichment, story packs and CPD integration are paused until the map is accurate per unit. |

## 3. Plan

Each phase has a gate. Every phase that writes to the database follows the working rules in `CLAUDE.md`:
- take a `pg_dump -Fc` into `backups/` first;
- record the high-water mark;
- make the script dry-run by default;
- get Hassan's approval before running `--write`.

### Phase 1: one inclusion rule
- Create a view, e.g. `v_occurrences`, with labels joined from `units`, that defines the occurrences that count:
  - list introductions;
  - gap-fill recurrences from the introduction point onward;
  - excluding known junk.
- Point at it everything that currently filters on `validation_status`:
  - dashboard API `routes/stats.py`, `concepts.py` and `semantic.py`;
  - `graph_builder.py`;
  - `story_context.py`;
  - `compute_cooccurrences.py`.
- Stop using the copied subject/year/term/unit columns on `occurrences`, since 153 rows disagree with `units`.
- **Gate:** the dashboard and the database report the same counts; the 2026-10-03 recurrences are visible.

### Phase 2: concept hygiene and matching
- **Check introductions against the lists.** Verify the 113 introductions that don't come from a vocab list (24 `bold_extraction`, 89 with NULL source) and decide each one.
- **Fix bad concept rows:**
  - repair truncated terms ("roynes", "lexandria", "urret", "ontemporaries", "hurch", "uddha", …);
  - remove phrase fragments ("worn on", "ran the headline");
  - delete the junk concepts `–` (3516) and probably `ik` (3512);
  - merge the 13 duplicates that differ only by case.
- **Add a match key** alongside `concepts.term`: a normalised form plus a variant list for inflections and the word family. Keep `term` exactly as authored. `concepts.word_family` from enrichment is a possible seed, but check it first.
- **Change the gap-fill cut-off** from `intro_year <= unit_year` to curriculum order (year, then term).
- **Gate:** spot-check known concepts (empire, trade, worship, kingdom, mountains) against the booklets; no truncated terms remain.

### Phase 3: rebuild recurrences and derived tables
- Rerun the cleaned gap-fill with the new matching. Dry-run first, then review a sample, especially inflection-only matches.
- Remove existing recurrences that now fall before the introduction in curriculum order.
- Recompute `co_occurrences`. Fix the double-counting in the year_group SQL before enabling that granularity.
- **Gate:** row counts move as expected; no subject is under-represented relative to its unit count.

### Phase 4: concept-type tags and the ambiguous-term list
- **Tag every concept** as transferable concept, proper noun or unit-specific. Have a model draft the tags and Hassan check them. Yesterday's decisions in `output/transferable_concepts_decisions.csv` cover the single-unit terms already.
- **Flag ambiguous terms**, have a model check sense for their recurrences, and have Hassan review the flagged mismatches.
- **Gate:** every concept tagged; all ambiguous-term recurrences sense-checked.

### Phase 5: trajectory review
- Build trajectories: for each concept, its occurrences in curriculum order. Each consecutive pair is one step.
- A model drafts `edge_nature` (reinforcement, extension or application) for each step, with a short rationale citing both contexts.
- **Hassan's review queue** lists the steps, starting with concepts spread widely across units and subjects.
- **Re-check the 176 March edges** against the rebuilt occurrences, re-pointing them where the occurrence has changed.
- **Pick flagship trajectories** (candidates: empire, trade, worship, kingdom) and prepare them for Christine and Steve to sign off.
- **Gate:** flagships signed off; "accurate per unit" spot-checked across all three subjects.

### After this plan
- Resume story packs: regenerate the 17, after fixing `story_context.py`'s same-year "prior" bug and the destructive `--force --dry-run` order in `batch_generate.py`.
- Resume enrichment and CPD integration (`cpd.vocabulary_items`).
- The repo consolidation plan (2026-08-31) can run in parallel, but no earlier than Phase 1, which touches both repos.

## 4. Hazards to fix along the way

- `batch_generate.py --force --dry-run` deletes story packs, approved ones included, before it checks for dry-run.
- The `--dry-run` flags in `content_ingestion.py` and `enrich.py` still call the Anthropic API.
- `uplink.py` and `graph_builder.py` ignore `.env` and fall back to a hard-coded DSN. The uplink also logs that string, password included.
- `occurrences` has no unique constraint. Add one on `(concept_id, unit_id, slide_number)` or similar, once duplicates are resolved.
- The Anthropic API key was printed into a session transcript on 2026-10-02. **Rotate it.**

## 5. Open questions

1. Where should the concept-type tag live: a new `concepts.concept_type` column (migration 007), or alongside `geo_scope`?
2. Should inflection matching use a hand-reviewed variant list (precise, slow) or a lemmatiser plus review of the matches (faster, may over-match)?
3. When Christine and Steve sign off, do they use the dashboard, or a static document prepared from it?

## 6. Progress (2026-10-03)

### Phase 1 — one inclusion rule: done
`v_occurrences` (migration 007) is read by the pipeline and every dashboard route. The four conflicting `validation_status` filters are gone.

### Phase 2 — concept hygiene and matching: done
- **Cleanup:** 24 bold-only introductions and 17 fragment concepts from the 2 Oct Sikhism 1 extraction removed; 6 truncated terms repaired and 4 merged.
- **Base-form merges:** 132 concepts merged into 126 base-form concepts (migration 008: `concept_forms`, `merged_into`, `authored_term`). 8 groups with different senses kept separate.
- **List alignment:** every unit's current list fetched from Dropbox and the database aligned to it (`align_vocab_lists.py`, migration 009). Earlier introductions had come from older list versions and hand-made copies. Result: +60 introductions (51 new concepts, e.g. Qur'an, Jew, market, Mughal Empire), −25 no longer listed, zero drift in all 64 units.
- **Inflections:** 483 lemminflect forms reviewed; 409 approved, 74 rejected as another word or sense (bore → born, grind → ground, wells → well).
- **Gap-fill:** cut-off now in curriculum order; matches every approved form; apostrophes interchangeable; picture credits stripped.

### Phase 3 — rebuild: done
- **Pruning:** 373 rows outside the inclusion rule removed (2 edge-referenced rows kept).
- **Gap-fill:** +881 recurrences; idempotent on rerun.
- **Co-occurrences:** 706,716 pairs (was 270,367).
- **Map now:** 2,844 concepts; 9,070 occurrences (3,068 introductions, 6,002 recurrences); Geography 110, History 167, Religion 150 occurrences per unit.
- **Recurrence share by year:** Y3 37%, Y4 60%, Y5 73%, Y6 76%.

### Carried into Phase 4
- **Ambiguous-term list:** start with bank, fast, source, lock, plus authored polysemous terms (court, state, order, spring, mine, iron, line, pass, power, scale, might, mind, grave, yard, vessel, bound, Waves).
- **Concept-type tags** for all 2,844 concepts. The 51 new concepts also need enrichment.

### Carried into Phase 5
- **Edges to re-check:** 4 edges now have one end that is a recurrence rather than an introduction: Ethiopia (Geography Ethiopia), Christ (Ancient Egypt), surrender (Persia and Greece), prayer (Islam Arabia).

### Questions for Christine and Steve
1. **"worship"** is on no current unit list: Rama and Sita's current list dropped it. Should it be listed somewhere?
2. **Roman Empire:** the docx list says "height", the PDF of the same date says "at the height of". Which is final?
3. **More Hindu Stories:** the Dec 2023 slide version appears to lack "Mahabharata" and "versions" (possibly inside an image). Are they still on the list?
4. **Islam Arabia** and **Life and Teaching of Jesus:** the only list files sit in "prep" folders; **Agriculture's** only in "older". Are these the current lists?
5. **Typos in lists:** "Gaugalmela", "unleavened bred", "veni, vedi, vici" (kept as authored; matched by the correct spelling too).
