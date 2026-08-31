# Plan: consolidate the OWL codebase and remediate the dashboard

**Date:** 2026-08-31
**Status:** Plan for review — nothing moved, nothing deleted. Execution deferred at your request (2026-08-31): read the three documents and decide sequencing first.
**Related:** [house style feasibility](20260830_house_style_guide_feasibility.md) · [ingest fix plan](20260830_ingest_matcher_fix_plan.md)

---

## 1. What is going on

Five GitHub repositories carry the OWL name. They are not five projects.

| Repository | Commits | Last commit | What it actually is |
|---|---:|---|---|
| `owl-knowledge-map` | 50 | 2026-08-31 | Extraction pipeline, enrichment, graph builder, story packs. **The system of record.** |
| `owl-knowledge-map-dashboard` | 28 | 2026-08-30 | FastAPI backend + React frontend over the same database. **The read layer of the same system.** |
| `owl-geo-scope` | 3 | 2026-08-30 | Four loose files: one migration that `ALTER`s `public.concepts`, one classifier script. **A feature of the pipeline, not a project.** |
| `owl-knowledge-map-frontend` | 24 | 2026-03-04 | Anvil app. Superseded by the React dashboard. **Dead for six months.** |
| `owl-cpd-platform` | 4 | 2026-08-30 | Next.js + Prisma teacher-CPD product. **A genuinely separate product.** |

So: **one system split across three repositories, one corpse, and one unrelated product.**

### The evidence that the first three are one system

**They share a constant by copy-paste.** `TERM_ORDER` — the six-term academic ordering — is independently defined in **seven files across two repositories**: `src/build_graph.py`, `src/graph_builder.py`, `src/insights.py`, `api/db.py`, `api/concepts.py`, `api/graph.py`, `api/occurrences.py`. Change the term scheme and you must find all seven.

**They disagree about how to reach the database.** Three conventions for one Postgres instance:

| Location | Variable | Form | Failure mode |
|---|---|---|---|
| `owl-knowledge-map/src/db.py` | `DATABASE_URL` | libpq URL, **required** | `KeyError` if unset |
| `dashboard/api/db.py` | `OWL_DB_URL` | keyword string, **defaults with `password=dev` inline** | silently connects to a default |
| `owl-geo-scope/02_classify_batch.py` | its own | third style | — |

**The filesystem coupling is already documented.** The dashboard README states the backend "requires the `owl-knowledge-map` repo in `../owl-knowledge-map`", and `dashboard/.env` is a **symlink** to `owl-knowledge-map/.env`. Two repos that can only run as siblings, sharing one secrets file by symlink, are one repo wearing two hats.

**`owl-geo-scope` mutates the other repo's schema.** `01_migrate_schema.sql` adds `geo_scope`, `geo_scope_confidence` and `geo_scope_notes` to `public.concepts` — a table owned by `owl-knowledge-map`'s migrations. That migration lives outside the migration sequence that governs the table, so `owl-knowledge-map/migrations/` no longer describes its own schema.

### The thing I did not expect: the CPD platform shares the database

`owl-cpd-platform/.env` points Prisma at **`postgresql://cpd:…@localhost:5432/owl?schema=cpd`** — the same database instance as the knowledge map, isolated by schema.

```
owl (database)
├── public  — 6 tables   — knowledge map (units, concepts, occurrences, edges, …)
└── cpd     — 15 tables  — CPD platform (users, modules, blocks, progress, …)
```

This is defensible and I am not proposing to change it, but three things follow:

1. **Name collision.** `public.units` is a *curriculum* unit (subject/year/term). `cpd.units` is a *training module* unit (module_id, slug, title, sort_order). Same word, unrelated meanings, one connection away from each other. Anyone querying without a schema qualifier gets whichever `search_path` decides.
2. **The intended integration is not wired up.** `cpd.vocabulary_items` has **0 rows**. The CPD platform has a table shaped to receive knowledge-map vocabulary and nothing has ever populated it. That is either a planned feature or an abandoned one — worth knowing which.
3. **Shared blast radius.** A `pg_dump`/restore, a role change, or a bad migration on one side affects both. There is currently one `pg_dump` in the ingest fix plan and it should be understood as covering both products.

### Verdict

- **Consolidate** `owl-knowledge-map` + `owl-knowledge-map-dashboard` + `owl-geo-scope` into one repository.
- **Archive** `owl-knowledge-map-frontend`.
- **Leave `owl-cpd-platform` separate.** Different product, different stack, different lifecycle. Document the shared-database coupling rather than merging it.

---

## 2. Dashboard remediation

These are worth fixing regardless of consolidation. Ordered by who gets hurt.

### 2.1 The dashboard misrepresents the curriculum (highest priority)

Concepts per unit, straight from the database:

| Subject | Booklets ingested | Concepts/unit |
|---|---|---:|
| History | 18/21 (86%) | **131.5** |
| Geography | 13/22 (59%) | **68.4** |
| Religion | 1/21 (5%) | **49.4** |

Density is monotonic with ingest coverage, because `gap_fill_occurrences.py` supplies 41% of all occurrences and can only mine units that have `booklet_content`. **History appears 2.7× conceptually denser than Religion as an artefact of the ingest bug**, and a `grep` for caveat language across `src/pages/` returns nothing.

Two fixes, in order:
1. **Now:** a coverage banner on Overview, Vocab Timeline and Word Atlas — "Vocabulary coverage is uneven: N of 64 units have booklet text. Cross-subject comparisons are not yet reliable." Drive it from a live query, not a hardcoded string, so it disappears on its own when the corpus completes.
2. **Then:** land phase 4 of the [ingest fix plan](20260830_ingest_matcher_fix_plan.md) and the distortion goes away at source.

**Until one of those is done, do not demo those three views to anyone.**

### 2.2 The README describes software that no longer exists

The largest feature section documents a 3D force-directed graph with three layout modes, and calls the semantic view "the most analytically novel part of the dashboard". In fact:

- `3d-force-graph` and `graphology` are **not in `package.json`**
- nothing imports `ForceGraph`
- there is **no `/graph` route** in `App.tsx`
- the README lists 4 features; the app ships **11 routes**, none of them the ones described
- the stack table says "Backend | FastAPI, SQLite"; `api/db.py` moved to Postgres in March and says so in its own docstring

`api/routes/semantic.py` and the `getSemanticClusters` client function still exist, but no view calls them.

**Decided 2026-08-31: leave the semantic code alone.** The README section gets rewritten to describe it as dormant rather than shipped; `api/routes/semantic.py`, the client function and `docs/semantic-analysis-report.md` all stay. Restoring the view would need the `3d-force-graph` dependency back, so the cost of keeping the endpoint is a few unused files — cheaper than deleting work whose removal was not deliberate.

### 2.3 `GET /` returns the database password

`api/main.py:52` returns `PG_CONN_STRING`, which contains `password=dev`. Beside it, `"db_exists": True` is hardcoded and tells the caller nothing. Return a version and a real connectivity check; never the DSN.

### 2.4 Eleven failing tests, all in the newest work

`WordAtlasView` (6), `VocabTimelineView` (2), `vocabHelpers.reachStyle` (3). They assert the pre-restructure tier buckets and were not updated by commit `153c61a` ("restructure tiers to 8+/4-7/2-3/1"). Three `.bak` files sit untracked alongside. Either the tier change was right and the tests are stale, or the tests encode intent the change broke — **read them before fixing them.**

Also: `pytest` is not installed in the dashboard `venv`, so the six Python API test files under `tests/` cannot have run recently.

### 2.5 Five dead API modules

`api/concepts.py`, `graph.py`, `stats.py`, `edges.py`, `occurrences.py` are shadowed by `api/routes/` equivalents and imported by **zero** files. The trap is real: three of them contain a stale copy of `TERM_ORDER`, so the next person to fix a term-ordering bug has a 50% chance of editing a file that never runs.

### 2.6 Lint and information architecture

Ten `react-hooks/preserve-manual-memoization` errors. The build itself is clean (6.8s, 436 KB main chunk).

Ten flat nav items with no grouping, mixing teacher lesson-prep (`Prepare`) with curriculum analysis (`Overview`, `Word Atlas`) as peers. Those serve different people asking different questions. Not urgent while the tool is private; the first thing to rethink if it becomes audience-facing.

---

## 3. Target structure

```
owl/                              # renamed from owl-knowledge-map
├── README.md                     # one honest entry point
├── CLAUDE.md
├── pyproject.toml                # single Python project
├── docs/
├── migrations/                   # ALL schema changes, geo_scope included
├── packages/
│   └── owl_core/                 # the shared layer that does not exist today
│       ├── db.py                 #   one connection convention
│       └── curriculum.py         #   TERM_ORDER, subject normalisation — defined ONCE
├── pipeline/                     # was src/
│   ├── ingest/                   #   batch_ingest, content_ingestion
│   ├── enrich/                   #   enrichment/ + owl-geo-scope's classifier
│   ├── graph/
│   └── analysis/                 #   insights.py, style_corpus_stats.py
├── api/                          # was dashboard/api — routes/ only, dead modules gone
├── web/                          # was dashboard/src — React app
└── tests/
    ├── pipeline/
    └── api/
```

The one genuinely new thing is `packages/owl_core`. Everything else is a move. `owl_core` is what makes the consolidation worth doing rather than cosmetic: it is where `TERM_ORDER` stops being copied seven times and where the three connection conventions become one.

**`owl-cpd-platform` stays where it is**, with a section added to its README documenting the shared `owl` database and the `cpd` schema boundary.

---

## 4. Execution plan

Preserving history matters here — `owl-knowledge-map` has 50 commits and the dashboard 28, including the provenance of the vocabulary work. `git subtree` keeps it; a fresh `git init` throws it away.

| # | Phase | Action | Gate |
|---|---|---|---|
| 0 | **Safety** | `pg_dump owl` (both schemas). Push every repo to its remote so nothing lives only on the Pi | Dump restores to a scratch DB; `git status` clean everywhere |
| 1 | **Land pending work** | Merge or close `docs/house-style-feasibility`. Commit or delete the 3 `.bak` files | No unpushed work anywhere |
| 2 | **Dashboard fixes in place** | §2.2–2.5 in `owl-knowledge-map-dashboard`, committed there | Tests green, README true, `GET /` clean |
| 3 | **Absorb the dashboard** | `git subtree add --prefix=web-tmp <dashboard> main` into `owl-knowledge-map`, then move into `api/` and `web/` | Both histories present in `git log`; app still builds |
| 4 | **Absorb geo-scope** | Move `01_migrate_schema.sql` → `migrations/006_geo_scope.sql`; classifier → `pipeline/enrich/` | Migration sequence describes the real schema |
| 5 | **Extract `owl_core`** | Create `packages/owl_core`; move `TERM_ORDER` and subject normalisation there; delete all seven copies; unify on `DATABASE_URL` | Full test suite green; API and pipeline both start |
| 6 | **Restructure** | Apply §3 layout. Update imports, `start_api.sh`, `vite.config.ts` | `npm run build`, `npm test`, pytest, and one pipeline dry-run all pass |
| 7 | **Rename** | Rename repo to `owl` on GitHub and locally. Rewrite the README | Clone-and-run from the README works in a clean directory |
| 8 | **Archive** | Archive `owl-knowledge-map-frontend` and `owl-geo-scope` on GitHub (do not delete) | Archived, not gone |

**Phases 0–2 are worth doing whatever you decide about consolidation.** Phase 5 is where the value is; phases 3–4 exist to make it possible.

### Rollback

Every phase is a git operation on a pushed branch, so revert is `git reset --hard` to the previous tag. Tag before each of 3, 5 and 6. The only non-git step is the GitHub rename in phase 7, which is reversible and leaves redirects.

### Deliberately not doing

- **Not merging `owl-cpd-platform`.** Separate product; merging would couple two release cycles for no gain.
- **Not splitting the database.** The two-schema arrangement works. Document it.
- **Not rewriting the frontend.** The IA concern in §2.6 is a design question for when there is an audience.
- **Not `git filter-repo`.** Subtree keeps history at the cost of two roots in the log. That is a fair trade; rewriting history across two published repos is not.

---

## 5. Open questions

1. ~~Is the semantic view coming back?~~ **Answered: leave it alone** (§2.2). Still worth establishing at some point *why* it went — the endpoint, client function and analysis report all survive, so this looks like working software that got dropped rather than something abandoned mid-build.
2. **Is `cpd.vocabulary_items` a planned integration?** Zero rows against a schema shaped to receive knowledge-map vocabulary. If it is planned, `owl_core` is the natural place for the shared contract and that changes what goes in it.
3. **Does anything outside this Pi consume these repos?** The rename in phase 7 and the archives in phase 8 are safe only if nothing else clones them. The Anvil app's `uplink.py` in `owl-knowledge-map` suggests there was once a live Anvil deployment — is it gone?
4. **Where does the ingest actually run?** Still open from the ingest fix plan. No Dropbox mount exists on this host, so `batch_ingest.py` has never run here. If there is a second machine, it needs to be in scope for phase 6's import changes.
