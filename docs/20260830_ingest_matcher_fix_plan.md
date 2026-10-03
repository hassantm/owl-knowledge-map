# Plan: fix the ingest matcher and complete the units corpus

**Date:** 2026-08-30
**Status:** Plan for review — nothing executed.
**Related:** [`20260830_house_style_guide_feasibility.md`](20260830_house_style_guide_feasibility.md) §5, which diagnoses the fault.

---

## 1. Why this matters more than the style guide

The immediate trigger was the house style guide needing Religion booklets. But the impact is wider, and the vocabulary concern you raised is real — just not in the way it first appears.

**The core vocabulary lists are not missing.** Every one of the 64 units has occurrences recorded, sourced from per-unit `Core vocab.docx` files. All 21 Religion units have vocabulary. That pipeline is independent of the PPTX booklet ingest and it ran fine.

**What is missing is the booklet gap-fill.** `src/gap_fill_occurrences.py` mines each unit's `booklet_content` for vocabulary terms that appear in the text but were not in the core list. It can only run where booklet text exists:

| Units | Count | Occurrences | Avg/unit | From gap-fill |
|---|---:|---:|---:|---:|
| **With** booklet text | 32 | 3,654 | **114.2** | 2,151 |
| **Without** booklet text | 32 | 1,648 | **51.5** | **0** |

Units with booklet text carry **2.2× the occurrence density**. Gap-fill accounts for 41% of all occurrences and 100% of it sits in the with-booklet half.

The consequence is that `co_occurrences` (270,367 rows) and `edges` are built on a corpus where half the units are systematically under-represented. Any question of the form "where else does this concept appear?" or "what connects to what?" currently gets a biased answer, and the bias correlates almost perfectly with subject — Religion is nearly invisible. **This is a knowledge-map integrity problem, not just a style-guide inconvenience.**

---

## 2. What is actually wrong

Three defects in [`src/batch_ingest.py`](../src/batch_ingest.py), plus a fourth in the data itself.

### 2.1 The folder regex demands a subject token

```python
_UNIT_FOLDER_RE = re.compile(
    r"^Y(\d+)\s+(Hist(?:ory)?|Geog(?:raphy)?|Relig(?:ion)?|RE)\s+(Autumn|Spring|Summer)\s+(\d+)\s+(.+)$",
    re.IGNORECASE,
)
```

History and Geography folders include the subject (`Y5 Hist Autumn 1 Baghdad`). Religion largely does not. Two sub-failures:

- **No subject token** — all of Year 4 (`Y4 Summer 2  Islam 1  Ramadan`) and most of Year 6 (`Y6 Summer 1 Reason and revelation`).
- **`Year N` instead of `YN`** — all of Year 5 (`Year 5 Autumn 1 Islam 2 Stories of the Prophets`). The pattern requires digits immediately after `Y`.

Non-matching folders are dropped by `find_unit_folders` before anything else runs, so **these units never appear in the run at all** — no error, no warning, no line in the report. That silence is why the gap went unnoticed.

### 2.2 The database lookup is exact-match only, via `ILIKE`

```python
cur.execute("... WHERE year=%s AND subject=%s AND term=%s AND unit ILIKE %s", ...)
```

Where the folder *does* parse, the trailing unit name must equal the database `unit` value exactly. Across Religion it almost never does. Two further problems with this line:

- **No fuzzy fallback and no diagnostic** — a miss returns `None` and the unit is skipped quietly.
- **`ILIKE` treats `_` and `%` as wildcards.** Folder names contain underscores (`Hindu Stories_I`, `Christianity 8 Art and text_2`) and so do database values (`Christ 1_Family of Jesus`, `Vikings 1_Aethelflaed`). An unescaped `_` matches any single character, so this can silently bind content to the **wrong unit**. It has not misfired yet, but it is a live correctness hazard in the statement that decides where content gets written.

### 2.3 `find_booklet` is too strict and non-deterministic

```python
booklet_dirs = [p for p in unit_dir.iterdir() if p.is_dir() and "booklet" in p.name.lower()]
if not booklet_dirs:
    return None
matches = list(booklet_dirs[0].glob("*.pptx"))
return matches[0] if len(matches) == 1 else None
```

- `booklet_dirs[0]` takes whichever directory `iterdir()` yields first — **unsorted, filesystem-dependent**. Units with both a `… Booklets/` and a `… Work in Progress/` folder get a coin toss.
- `len(matches) == 1` returns `None` when a folder holds two or more PPTX files, rather than choosing or reporting.

This is the likely cause of several non-Religion gaps. Y4 Geography Population has `lesson_content` but no `booklet_content`, and its booklet files are split across `Y4 Autumn 2 Population Booklets/` and `Y4 Autumn 2 Population Work in Progress/`.

### 2.4 The `units` table itself has errors — found while tracing this

Comparing the Dropbox tree against `units` surfaced metadata faults that a matcher fix alone will not resolve. **These need a decision from you, not just a code change:**

| unit_id | Database says | Dropbox says | Issue |
|---|---|---|---|
| 60 | Y5 **Summer1** Buddhism 2 | `Year 5 Summer 2 Buddhism 2 …` | Wrong term — collides with Buddhism 1, also Summer1 |
| 61 | Y5 **Summer2** Sikhism 1 | `Y6 Autumn 1 Sikhism 1 The teaching of the gurus` | Wrong **year and term** |
| — | *absent* | `Y6 Summer 2 Christianity 8 Art and text_2 Christian creatives` | Unit missing from the database entirely |

Note that units 59 and 60 both sit at Y5 Summer1, which the `units_unique(subject,year,term,unit)` constraint permits but the curriculum does not. Correcting 61 to Y6 Autumn1 also fills a hole — the database currently has no Y6 Autumn1 Religion unit.

Two Dropbox folders are **not** units and must stay excluded: `Year 5 Spring 2 Religious site visit guidance` and `Y6 Spring 1 Religious site visit guidance`. The database correctly has no rows for those slots.

---

## 3. Design of the fix

Five changes, smallest blast radius first. The guiding principle: **make the pipeline loud rather than clever.** Every change below either widens what is recognised or reports what was rejected. None introduces silent guessing.

### 3.1 Report unmatched folders (do this first, alone)

Add `--report-unmatched` to `batch_ingest.py`. Have `find_unit_folders` return both matched and rejected candidates, and print every rejected folder with the reason (`regex miss`, `no unit_id`, `no booklet pptx`, `ambiguous booklet dir`).

This is a pure-diagnostic change and it is the highest-value item in the plan. **Ship and run it before touching anything else** — it converts guesswork into a definitive worklist, and it is the control that stops this recurring.

### 3.2 Widen `_UNIT_FOLDER_RE`

```python
_UNIT_FOLDER_RE = re.compile(
    r"^Y(?:ear)?\s*(\d+)\s+"                                   # Y5 / Y 5 / Year 5
    r"(?:(Hist(?:ory)?|Geog(?:raphy)?|Relig(?:ion)?|RE)\s+)?"  # subject now OPTIONAL
    r"(Autumn|Spring|Summer)\s+(\d+)\s+(.+)$",
    re.IGNORECASE,
)
```

When the subject group is absent, infer it from the nearest `HEP <Subject>` ancestor directory. Fail loudly if neither is available — never default.

Making the subject optional slightly widens what parses; the ancestor-directory check keeps it anchored, and 3.1's reporting makes any over-match visible.

### 3.3 Add an explicit folder→unit alias map

For the cases where the folder name and the curriculum name genuinely differ, **do not fuzzy-match.** Fuzzy matching on 64 units with names like `Buddhism 1` / `Buddhism 2` and `Islam 1` / `Islam 2` / `Islam 3` is exactly where a near-miss silently writes a booklet to the wrong unit.

Prefer a `units.source_folder_name TEXT` column (migration `005`), populated by hand, with a unique index. It makes the mapping visible in the database, reviewable in one query, and self-documenting. Lookup becomes: exact `source_folder_name` match → else exact `lower(unit)` match → else report as unmatched.

The 20 Religion mappings to populate:

| Dropbox folder | → unit_id |
|---|---|
| `Y3 Religion Autumn 1 Hindu Stories_I Rama and Sita` | 44 |
| `Y3 Religion Autumn 2 More Hindu Stories_II` | 45 |
| `Y3 Religion Spring 1 Living Hindu Traditions` | 46 *(already ingested)* |
| `Y3 Religion Spring 2 Judaism Abraham, Isaac and Jacob` | 47 |
| `Y3 Religion Summer 1 Judaism Joseph, Moses and the Exodus` | 48 |
| `Y3 Religion Summer 2 Judaism The kings, the temple and living as a Jew` | 49 |
| `Y4 Autumn 1  Christianity 1  The Family of Jesus` | 50 |
| `Y4 Autumn 2 Christianity 2  The Birth of Jesus` | 51 |
| `Y4 Spring 1  Christianity 3  Life and teaching of Jesus` | 52 |
| `Y4 Spring 2 Christianity 4  Death and Resurrection of Jesus` | 53 |
| `Y4 Summer 1 Christianity 5 The message of Jesus spreads` | 54 |
| `Y4 Summer 2  Islam 1  Ramadan` | 55 |
| `Year 5 Autumn 1 Islam 2 Stories of the Prophets` | 56 |
| `Year 5 Autumn 2 Islam 3 Living Muslim Traditions` | 57 |
| `Year 5 Spring 1 Christianity 6 Living Christian traditions` | 58 |
| `Year 5 Summer 1 Buddhism 1 The prince who became the Buddha` | 59 |
| `Year 5 Summer 2 Buddhism 2 Buddhist stories & teachings` | 60 *(after term fix)* |
| `Y6 Autumn 1 Sikhism 1 The teaching of the gurus` | 61 *(after year/term fix)* |
| `Y6 Autumn 2 Sikhism 2 Living Sikh traditions` | 62 |
| `Y6 Spring 2 Stories which point to truth` | 63 |
| `Y6 Summer 1 Reason and revelation` | 64 |
| `Y6 Summer 2 Christianity 8 Art and text_2 Christian creatives` | *new row needed* |

Note that several folder names contain **double spaces** (`Y4 Summer 2  Islam 1  Ramadan`). Normalise whitespace on both sides of the comparison, and store the folder name verbatim.

### 3.4 Fix the `ILIKE` hazard

Replace `unit ILIKE %s` with `lower(trim(unit)) = lower(trim(%s))`. Equality, no wildcard semantics, no escaping to get wrong. If a genuine prefix search is ever wanted, escape `_` and `%` explicitly.

### 3.5 Make `find_booklet` deterministic and vocal

- Sort candidate directories; prefer an exact `*Booklet*` name over `*Work in Progress*`.
- On multiple PPTX files, prefer the one whose stem best matches the unit folder name; if still ambiguous, **report** the candidates rather than returning `None`.
- Skip `_output.pdf`-style artefacts and print-run subfolders.

---

## 4. Execution plan

Seven phases with a verification gate at each. **Do not batch these** — the value is in checking after each.

| # | Phase | Action | Gate before proceeding |
|---|---|---|---|
| 0 | **Back up** | `pg_dump owl > owl_pre_ingest_$(date +%F).sql` | Dump restores into a scratch database |
| 1 | **Diagnose** | Ship 3.1. Run `--dry-run --report-unmatched` over all three subject roots | Rejected-folder list reviewed by you; matches the 32 known gaps |
| 2 | **Correct metadata** | Migration for §2.4: fix units 60 and 61, insert the missing Y6 Summer 2 unit | You confirm the curriculum placements are right |
| 3 | **Widen matcher** | Ship 3.2, 3.4, 3.5 + migration 005 for `source_folder_name`; populate Religion aliases | Re-run dry-run: every Religion unit resolves to the **correct** unit_id. Eyeball all 21 |
| 4 | **Ingest Religion** | Live run, Religion root only | Page counts plausible (23–43); spot-check 2 booklets' text against the PDFs |
| 5 | **Ingest the rest** | Live run, History + Geography roots | 64/64 units have `booklet_content`, or a documented reason why not |
| 6 | **Re-run gap-fill** | `python src/gap_fill_occurrences.py --dry-run`, review, then live | Occurrence density for previously-empty units approaches ~114/unit |
| 7 | **Rebuild graph** | Recompute `co_occurrences` and `edges` | Row counts move as expected; Religion no longer under-represented |

**Phase 4 is the natural stopping point for the style guide.** Religion alone takes the corpus from 32 to 53 units and removes the single-booklet caveat that currently undermines the Religion pitch band. Phases 5–7 can follow at their own pace.

### Rollback

Phases 2–5 write to `units`; phase 6 inserts into `occurrences`; phase 7 rewrites `co_occurrences` and `edges`. The phase-0 dump covers all of it. Additionally, `booklet_content_extracted_at` timestamps every write, so a bad run is identifiable and reversible with a single `UPDATE … SET booklet_content = NULL WHERE booklet_content_extracted_at > …`.

### Cost — smaller than I previously suggested

I flagged token cost as a concern in the feasibility note. That was wrong, and your point about the PPTX files explains why. `extract_booklet_content` uses `python-pptx` to pull **text only**; the images that make these files 385 MB are never parsed or sent anywhere. The only API usage is `messages.count_tokens` per page — roughly 1,100 calls for the whole 32-unit backlog, on a counting endpoint.

The real constraint is **I/O**: `python-pptx` must read each multi-hundred-megabyte file, which for Dropbox means a full download per booklet. Budget for bandwidth and wall-clock, not for tokens. Worth confirming the files are locally synced rather than online-only placeholders before starting phase 4.

---

## 5. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Alias maps a booklet to the **wrong** unit | Low but high impact | Manual alias table, not fuzzy matching; phase-3 gate reviews all 21 before any write |
| Widened regex over-matches non-unit folders | Medium | `Religious site visit guidance` folders are known; §3.1 reporting surfaces any others; they fail at unit lookup anyway |
| Re-ingest overwrites good existing content | Low | `is_already_ingested` skips unless `--force`; do not pass `--force` in phases 4–5 |
| Gap-fill introduces spurious occurrences | Medium | It is substring mining over booklet text. Dry-run first; sample-review new occurrences for a Religion unit before the full run |
| Metadata corrections invalidate existing occurrences | Low | Units 60/61 keep their `unit_id`; only `year`/`term` change, and occurrences join on `unit_id` |
| Dropbox files are online-only placeholders | Medium | Check sync status before phase 4; the ingest host had no Dropbox mount when I looked |

---

## 6. Open questions

1. **Where does the ingest actually run?** There is no Dropbox mount on this machine (`/home/htmadmin` has `onedrive` but no Dropbox), so the original run happened elsewhere. Phases 4–5 need that environment identified.
2. **Confirm the three metadata corrections** in §2.4 — particularly moving Sikhism 1 from Y5 Summer2 to Y6 Autumn1. That is a curriculum judgement, not a data one, and I would rather not guess.
3. **Is `Y6 Summer 2 Christianity 8 Art and text_2 Christian creatives` a live unit** that should be added, or something in development?
4. **Are there other subject roots** beyond `HEP History`, `HEP Geography`, `HEP Religion`? The `2023 - Flipbook project all x 76` folder mentions 76 booklets against 64 database units, and contains Science titles (`Year 3 Spring 2 Science Animals including Humans Booklet.pdf`) that are not in the curriculum table at all.

**On question 4** — that discrepancy of 76 versus 64 is worth a look on its own. It may be nothing (older editions, retired units), or it may mean the `units` table is itself incomplete in ways this exercise has not yet surfaced.
