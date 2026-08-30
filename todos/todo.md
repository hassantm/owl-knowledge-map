# Vocabulary Enrichment & Co-occurrence Pipeline — Todo

**Spec:** `docs/vocabulary-enrichment-functional-spec.md`  
**Database:** `owl` (PostgreSQL, localhost:5432)  
**Status:** Phase 1–6 complete. Phase 4 (enrichment run) requires ANTHROPIC_API_KEY.

---

## Phase 1: Setup ✅

- [x] Add `ANTHROPIC_API_KEY` to `.env` (placeholder set — replace with real key before running enrichment)
- [x] Install dependencies: `pip install anthropic psycopg2-binary python-dotenv`
- [x] Create directory structure: `enrichment/`, `migrations/`, `queries/`

---

## Phase 2: Migrations ✅

- [x] Create `migrations/001_add_vocabulary_enrichment.sql`
- [x] Create `migrations/002_create_co_occurrences.sql`
- [x] Run migration 001 against `owl` database
- [x] Run migration 002 against `owl` database
- [x] Verified: `concepts` table has all enrichment columns with correct types/defaults/constraints
- [x] Verified: `co_occurrences` table created with all indexes and constraints

---

## Phase 3: Enrichment Pipeline Files ✅

- [x] Create `enrichment/constants.py` — shared VALID_REGISTERS, VALID_TIERS, ENRICHMENT_FIELDS
- [x] Create `enrichment/db.py` — DB connection and query functions
- [x] Create `enrichment/prompts.py` — enrichment prompt builder
- [x] Create `enrichment/enrich.py` — batch LLM enrichment runner
- [x] Create `enrichment/review.py` — CLI review interface

---

## Phase 4: Enrichment Run ⏳ (requires ANTHROPIC_API_KEY)

- [ ] Replace placeholder in `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
- [ ] Dry run (2 concepts): `cd enrichment && python enrich.py --batch-size 2 --dry-run`
- [ ] First real batch: `python enrich.py --batch-size 50`
- [ ] Review session: `python review.py --reviewer HM`
- [ ] Repeat review → enrich cycle until all 3,001 concepts are `approved`
  - Estimated: ~30 min API time at 50 concepts/batch with 0.5s delay

---

## Phase 5: Co-occurrence Computation ✅

- [x] Create `enrichment/compute_cooccurrences.py`
- [x] Dry run verified: lesson=3,453 pairs, unit=88,384 pairs, year_group=2,055,254 pairs
- [x] Full computation complete: 2,147,091 total pairs, 1,623,988 cross-subject
- [x] Verified cross-subject count in database

---

## Phase 6: Analytical Queries ✅

- [x] Create `queries/bridge_nodes.sql` — cross-subject bridge node league table
- [x] Create `queries/find_bridge.sql` — two-hop indirect path finder
- [x] Create `queries/vocabulary_neighbourhood.sql` — semantic neighbourhood query
- [x] Bridge node query validated — top result: 'urban' (3,372 cross-subject links across all 3 subjects)
- [x] Note: cross-subject pairs only appear at `year_group` granularity (lesson/unit joins are within-subject by definition); `bridge_nodes.sql` updated to use `year_group`

---

## Phase 7: Anvil Integration (future)

- [ ] Expose enrichment fields via `uplink.py` for teacher-facing vocabulary tool
- [ ] Add `get_vocabulary_neighbourhood(concept_id)` endpoint
- [ ] Add `get_bridge_nodes(min_links)` endpoint
- [ ] Surface `tier` and `register` in concept detail view

---

## Notes

- Co-occurrence computation can run independently of enrichment — re-run after any new curriculum content is ingested
- Lesson SQL uses `o1.concept_id < o2.concept_id` (not `!=`) to avoid double-counting pairs
- Lesson/unit granularities are always within-subject; cross-subject analysis uses year_group
- 3,001 concepts at 50/batch ≈ 60 batches; ~30 min at 0.5s/concept API delay
