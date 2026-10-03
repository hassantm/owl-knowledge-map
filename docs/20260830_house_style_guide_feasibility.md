# Feasibility review: extracting an Opening Worlds house style guide from the `owl` database

**Date:** 2026-08-30
**Scope:** Review only — no extraction performed, no guide written.
**Question asked:** Is there enough text in the `owl` Postgres database to derive a style guide for writing a booklet in the Opening Worlds house style (grammar, capitalisation, writing style, sentence length, tone, pitch)?

**Short answer: yes, comfortably — for prose style.** The corpus is large enough, clean enough and internally consistent enough to support an evidence-based style guide.

**Update, same day:** all five scoping questions are now answered (§4), and the Religion coverage gap has been diagnosed (§5) — it is a folder-name matching bug in the ingest pipeline, not missing content. The source files are all present in Dropbox.

---

## 1. What is actually in the database

`units` is the relevant table. 64 rows (Geography, History, Religion × Years 3–6 × six half-terms). Two content columns matter:

| Column | Type | What it holds |
|---|---|---|
| `booklet_content` | `jsonb` | Per-page extracted booklet text: `{pages: {"1": {text, token_count}, ...}, page_count, total_token_count, document_type: "booklet"}` |
| `lesson_content` | `jsonb` | Per-slide lesson deck text **plus teacher notes**: `{slides: {"1": {text, notes, story_slide, animation_notes, ...}}}` |

Both were extracted by `claude-sonnet-4-6` (see `booklet_content_model`). Staleness flags (`booklet_content_stale`, `lesson_content_stale`) exist, so there is a refresh path.

### Corpus size — booklets

| Subject | Units with booklet text | Pages | Tokens |
|---|---:|---:|---:|
| History | 18 | 645 | 142,750 |
| Geography | 13 | 431 | 71,134 |
| Religion | **1** | 27 | 5,645 |
| **Total** | **32 of 64** | **1,103** | **219,529** |

After stripping extraction furniture (see §3), that is **~130,000 words of running prose across ~11,100 sentences**. For comparison, most published house style guides are derived from far less. This is more than sufficient.

Booklets run 23–43 pages, 3,500–13,300 tokens. `lesson_content` adds a further corpus of slide text and — more valuable — **teacher notes that state pedagogical intent in the house voice**.

---

## 2. Evidence that house style is genuinely measurable here

I ran quick quantitative passes over the cleaned prose to test whether the signal is there. It is, and it is consistent.

### Sentence length — and a clean progression by year group

| Year | Mean sentence (words) | Median | Sentences sampled |
|---|---:|---:|---:|
| Y3 | 11.2 | 10 | 3,489 |
| Y4 | 11.9 | 11 | 2,562 |
| Y5 | 12.2 | 11 | 4,395 |
| Y6 | 13.2 | 12 | 493 |

Overall mean 11.7, median 11.0. The monotonic Y3→Y6 climb is exactly the kind of finding a style guide needs — it gives a **defensible per-year target band** rather than a single global number. Unit-level means range 9.7 (Living Hindu Traditions, Y3) to 13.4 (Roman Empire, Y4), so there is also a legitimate spread to document as tolerance.

Long-word density (9+ characters) runs 4.9%–10.0% by unit and tracks year loosely — a second, independent pitch lever.

### Tone and voice markers (counts across the cleaned corpus)

- **Direct address to the reader is the dominant mode:** `you`/`You` — 913 occurrences; `we`/`We` — 560. The reader is addressed, not described. `children` appears 46 times, `pupils` 0 — i.e. the booklet never talks *about* its audience.
- **Questions to the reader: 5.8% of all sentences.** `Look at` / `Can you see` — 112; `Do you remember` — 65.
- **Exclamations: 4.8% of sentences.** This is high by adult-prose standards and is clearly deliberate house voice ("The River Indus is 3,200 kilometres long!").
- **Inclusive imperatives:** `Let's` — 63 (always curly `Let’s`), `Let us` — 9.
- **Sentence-initial conjunctions are sanctioned:** `But` — 241, `So` — 70, `Now` — 79. Formal connectives are rare by contrast: `However` — 4, `Moreover` — 3, `Indeed` — 1. That contrast is itself a strong style rule.
- **Hedging is present and deliberate:** `Perhaps` — 32.
- **Pronunciation glosses are a house convention:** 371 instances of the `Aethelberht (eth–ell–burt)` / `murti (mer-tee)` pattern.
- **First-hand voices are used:** 156 curly double-quote marks, mostly named quoted speakers (fishermen, community elders) — a recurring "listen to the people who live there" device.

### Orthography and mechanics — unambiguous

| Convention | Evidence |
|---|---|
| British spelling | `-ise`/`-our`/`-re` throughout, counting inflected forms: civilis- 62 / civiliz- 0; centre 27 / center 0; organis- 16 / organiz- 0; realis- 8 / realiz- 0; colour 29 (the 7 `color` hits are inside URLs and image credits) |
| `while` not `whilst` | while 45 / whilst 0 |
| Curly apostrophes | 1,126 curly vs 10 straight |
| En dash, never em dash | en 103 / em 0 |
| Double space after full stop | 1,890 instances — a strong (if unfashionable) house habit worth an explicit ruling |
| Serial comma | 206 `, and` instances — needs a manual check to separate true Oxford commas from clause joins |

### Structural conventions

Booklets follow a repeatable skeleton, verifiable in the data:
- Cover page (title only), then a **numbered contents page** listing 5–6 chapters with page numbers (360 numbered section headings detected).
- Chapter titles alternate between noun phrases ("The Persian Empire") and reader-facing questions ("How are volcanoes formed?", "Why do people choose to be near a dangerous volcano?").
- Page numbers on 528 of 1,103 pages; `©2021 Opening Worlds Ltd` copyright line on 36 pages.
- Margin **line numbers** on most prose pages (the `1 2 3 4…` runs in the extract) — evidence of a shared-reading design intent.
- **No glossary or word-bank pages inside booklets** (0 hits for Glossary/Contents-as-heading/Key words). Vocabulary lives separately — see `units.vocab_list_path` (`data/Vocab/*.md`) and the `concepts` table.

### Vocabulary policy is already encoded

The `concepts` table (2,929 rows) carries `tier` (Beck tiers 1–3), `register`, `definition`, `etymology`, `word_family` and `geo_scope`. Distribution:

- Tier 2: 2,041 (general formal 1,016 / formal academic 781 / subject-specific 207 / technical 37)
- Tier 3: 886 (subject-specific 834 / technical 52)

`occurrences` (5,302 rows) records where each term is **introduced** (`is_introduction`) and its `term_in_context`. This means a style guide can specify not just "define new words in context" but the actual house *pattern* for doing so, with real examples — and can state a target tier-2/tier-3 load per booklet.

### Reproducing these figures

Every number in this section comes from [`src/style_corpus_stats.py`](../src/style_corpus_stats.py):

```bash
python src/style_corpus_stats.py
```

It reads `units.booklet_content` directly, so re-running it after the corpus is completed (see the [ingest fix plan](20260830_ingest_matcher_fix_plan.md)) will refresh every figure. `--analysis size|sentences|tone|orthography|structure` runs one section; `--subject` and `--year` filter; `--json PATH` dumps the results for downstream use.

---

## 3. Limitations you should know about before commissioning the work

**(a) Extraction furniture pollutes the raw text.** 75.8% of non-empty lines are non-prose: margin line numbers, page numbers, image credits and Wikimedia URLs. This is trivially strippable with a filter (I used one for all figures above) but any extraction job must do it, or the metrics will be garbage.

**(b) Reading order is not guaranteed.** The text was pulled from what were evidently text boxes, so captions, pull-quotes and body copy sometimes appear out of visual order, and prose is interrupted by numeric markers on 123 pages. This does **not** affect sentence-level or word-level analysis — which is where most of a style guide lives. It **does** mean you cannot reliably reconstruct paragraph-to-image relationships, page rhythm, or "how a spread opens" from this data.

**(c) Coverage is uneven and Religion is effectively absent — but this is fixable.** 32 of 64 units have booklet text. Religion has exactly one booklet (Y3 Living Hindu Traditions), and it is the outlier on sentence length (9.7 words vs 11.7 corpus mean). Y6 is also thin: a single booklet (The Maya), so the Y6 pitch band currently rests on one data point. **Diagnosed in §5** — the cause is a folder-name matcher in `batch_ingest.py`, not absent source material. Fixing it should recover all 17 Religion booklets plus ~15 further History/Geography units.

**(d) No layout, typography or design evidence exists — and this is now settled as out of scope.** The database holds text only; the source files are PPTX booklets in Dropbox. Confirmed with you 2026-08-30: booklet design is deliberately non-uniform — text and images are combined in whatever way makes the teaching point most effectively — so there is no house layout to codify. The general accessibility rules that *do* apply (legible text against images, avoiding heavily textured backgrounds behind text for dyslexic readers) will be written by hand and appended, not extracted.

**(e) Descriptive ≠ prescriptive.** The corpus tells you what the booklets *do*, not what the house *wants*. The double-space-after-full-stop habit is the obvious example: real, consistent, and quite possibly something you would rule against rather than codify. Every extracted convention needs an editorial yes/no.

**(f) Provenance caveat.** The text is an LLM extraction, not an authoritative source file. It reads as faithful in every sample I checked, but for a document that will govern future writing, spot-checking a couple of booklets against the originals is cheap insurance.

---

## 4. Decisions taken (2026-08-30)

| # | Question | Decision |
|---|---|---|
| 1 | Audience | **Human writers developing booklets.** |
| 2 | Descriptive or prescriptive | **Prescriptive** — the guide is to serve as quality control for new resources. |
| 3 | Religion gap | **Extract the missing text first** so the database is complete. |
| 4 | Slicing (one guide vs per-subject/per-year) | **Undecided — let it emerge during writing.** |
| 5 | Design in scope | **Out of scope.** Booklet design is intentionally non-uniform; accessibility rules to be written manually. |

### What "prescriptive" changes

This is a bigger shift than it sounds. A descriptive guide can report a convention and move on; a prescriptive one has to **rule** on it, and be defensible when a writer disagrees. Three consequences:

- **Every rule needs a verdict, not just a count.** The corpus tells us the booklets put two spaces after a full stop (1,890 instances). A QC document has to say *do this* or *do not do this*. I will bring each contested convention to you with the evidence and a recommendation rather than silently encoding current practice.
- **Rules need to be checkable.** If it is to work as quality control, an editor must be able to hold a draft against it and reach a yes/no. That favours crisp rules ("use `while`, never `whilst`") over impressionistic ones ("aim for warmth"), and it means the voice section needs observable proxies — direct address, question rate, exclamation rate — not just adjectives.
- **Sentence-length bands need stated tolerances, not just targets.** As QC, "around 11 words in Year 3" invites a reviewer to flag a legitimate 19-word sentence. The guide must state the band, the tolerance, and that the target is a mean across a booklet — never a per-sentence limit.

Where a convention is real but weak evidence for a rule, I will mark it as guidance rather than a checkpoint, so QC does not harden a coincidence into a standard.

### On slicing (Q4)

Leaving this open is the right call and costs nothing. The evidence points to **one guide with per-year bands inside it**, because the Y3→Y6 gradient is smooth (11.2 → 13.2 words) rather than stepped, and the History/Geography difference is small (11.8 vs 12.1). The Religion outlier at 9.7 words rests on one booklet and may well disappear once the other 16 are extracted. I will draft as a single guide and split only if the completed Religion data forces it.

---

## 5. Diagnosis: why the Religion booklets are missing

You asked how the gap occurred. I traced it, and it is **entirely a folder-name matching failure in the ingest pipeline — not missing content**. The source PPTX files are present in Dropbox.

The pipeline is [`src/batch_ingest.py`](../src/batch_ingest.py), which walks the Dropbox tree and only ingests a unit when **three** conditions all hold. Religion fails at least one of them almost everywhere.

**Condition 1 — the folder name must match `_UNIT_FOLDER_RE`:**

```
^Y(\d+)\s+(Hist(?:ory)?|Geog(?:raphy)?|Relig(?:ion)?|RE)\s+(Autumn|Spring|Summer)\s+(\d+)\s+(.+)$
```

It requires a **subject token** immediately after the year. History and Geography folders have one (`Y5 Hist Autumn 1 Baghdad`, `Y4 Geog Autumn 2 Population`). **Every Year 4 Religion folder omits it:**

- `Y4 Autumn 1  Christianity 1  The Family of Jesus`
- `Y4 Autumn 2 Christianity 2  The Birth of Jesus`
- `Y4 Spring 1  Christianity 3  Life and teaching of Jesus`
- `Y4 Spring 2 Christianity 4  Death and Resurrection of Jesus`
- `Y4 Summer 1 Christianity 5 The message of Jesus spreads`
- `Y4 Summer 2  Islam 1  Ramadan`

After `Y4` comes `Autumn`, not a subject. The regex fails, `parse_unit_folder` returns `None`, and `find_unit_folders` **never even discovers the folder**. All of Year 4 Religion is invisible to the pipeline. Year 6 folders (`Y6 Summer 1 Reason and revelation`, `Y6 Spring 2 Stories which point to truth`) fail the same way. `Year 5 Summer 2 Buddhism 2 …` fails differently — it starts `Year 5`, and the pattern requires `Y` followed immediately by digits.

**Condition 2 — the parsed unit name must match the database exactly** (`lookup_unit_id` uses `unit ILIKE %s` with no fuzzy fallback). Year 3 Religion folders *do* carry the subject token, so they parse — and then fail here:

| Dropbox folder → parsed unit | Database `unit` | Match |
|---|---|---|
| `Hindu Stories_I Rama and Sita` | `Rama and Sita` | ✗ |
| `More Hindu Stories_II` | `More Hindu stories` | ✗ |
| **`Living Hindu Traditions`** | **`Living Hindu Traditions`** | **✓** |
| `Judaism Abraham, Isaac and Jacob` | `Judaism Stories 1` | ✗ |
| `Judaism Joseph, Moses and the Exodus` | `Joseph, Moses and the Exodus` | ✗ |
| `Judaism The kings, the temple and living as a Jew` | `Judaism 3` | ✗ |

**Exactly one Religion unit in the entire curriculum satisfies both conditions — and it is precisely the one in the database.** That is a complete explanation of the 1-of-17 result.

**Condition 3 — `find_booklet` requires exactly one `.pptx`** in the first subfolder whose name contains "booklet" (`matches[0] if len(matches) == 1 else None`). This is the likely cause of several *non-Religion* gaps. Y4 Geography Population has `lesson_content` but no `booklet_content`, and its booklet files are split across `Y4 Autumn 2 Population Booklets/` and `Y4 Autumn 2 Population Work in Progress/` — `booklet_dirs[0]` picks one arbitrarily (directory order is not sorted) and the count test then fails.

**The source files exist.** I confirmed the Ramadan booklet folder contains `Y4 Summer 2 Islam 1 Ramadan Booklet.pptx` (385 MB) alongside the print PDFs. Nothing needs re-authoring — only the matcher needs fixing.

### Two latent bugs worth fixing at the same time

1. **`ILIKE` treats `_` and `%` as wildcards.** Folder names contain underscores (`Hindu Stories_I`, `More Hindu Stories_II`, and in the database `Christ 1_Family of Jesus`, `Vikings 1_Aethelflaed`). An unescaped `_` matches any single character, so `lookup_unit_id` can silently match the *wrong* unit rather than none. It has not bitten yet, but it is a real correctness hazard in a lookup that decides where content is written.
2. **Unmatched folders fail silently.** `find_unit_folders` filters non-matching folders out of the list entirely, so a naming drift produces no warning — the unit simply never appears in the run report. That is why this went unnoticed. A `--report-unmatched` flag listing every folder the regex rejected would have surfaced all of Year 4 Religion on the first run.

### Recommended fix (cheapest first)

1. Make the subject token **optional** in `_UNIT_FOLDER_RE`, and accept `Year N` as well as `YN`. Infer the subject from the `HEP <Subject>` ancestor folder when the token is absent. This alone recovers most of Years 4–6.
2. Add an **alias table** (or a `units.source_folder_name` column) mapping Dropbox folder names to `unit_id`, for the ~6 Year 3 Religion cases where the folder name and the curriculum name genuinely differ. Populating it by hand is a 20-minute job and is more honest than fuzzy matching.
3. Escape `_` and `%` in the `ILIKE` parameter, or switch to `lower(unit) = lower(%s)`.
4. Add unmatched-folder reporting, then re-run `batch_ingest.py --dry-run` across all three subject roots and review the report **before** committing to a real run.
5. Relax `find_booklet`: prefer an exact `*Booklet*.pptx` name match, sort candidate directories deterministically, and report ambiguity rather than returning `None`.

Expected recovery: **17 Religion booklets** plus a further **15 History/Geography** units currently missing — taking the corpus from 32 to potentially all 64 units, and roughly doubling the evidence base before the guide is written.

**One caveat on cost:** these PPTX files are large (the Ramadan booklet alone is 385 MB) and ingestion calls the Anthropic token-counting API per page. A full re-ingest is not free in time or tokens — worth running Religion first, checking the output, then the rest.

---

## 6. What I would build

Four parts, each earning its place from a different evidence source:

1. **Mechanics** (spelling, punctuation, capitalisation, numbers, dates, names, pronunciation glosses) — rule-based counting, high confidence, each with an explicit prescriptive verdict. Presentable as a table; also the bulk of the quick-reference card.
2. **Sentence and paragraph craft** (length bands per year with stated tolerances, clause patterns, sanctioned sentence-initial connectives, question and exclamation rates) — quantitative, framed as checkable targets with worked examples.
3. **Voice and pitch** (direct address, inclusive `we`, awe-and-wonder register, use of first-hand testimony, how difficulty escalates Y3→Y6) — LLM-assisted analysis over the corpus, illustrated with real quoted exemplars and justified from the teacher notes in `lesson_content`, which state pedagogical intent in the house voice.
4. **Booklet architecture** (cover, contents, 5–6 chapters, chapter-title patterns, vocabulary introduction pattern, line numbering) — from structure detection plus the `concepts`/`occurrences` tables.

Plus a hand-written **accessibility appendix** (per decision 5) and a **one-page quick-reference card** for the writer's desk.

Every rule ships with two to three verbatim exemplars and a unit citation, so a writer can see it working and an editor can challenge it. Delivered as a draft for your editorial sign-off, not as a finished standard.

---

## 7. Recommended next steps

1. **Fix the ingest matcher** and re-run for Religion (§5). Review the dry-run report first.
2. **Re-run the corpus analysis** on the completed data — the per-year bands and the Religion figure will move, and the Y6 band currently rests on a single booklet.
3. **Draft parts 1 and 2** and review them together. These are cheap and mechanical, and they are where you will first see whether the extracted rules are ones you recognise and endorse.
4. **Then commission parts 3 and 4**, and decide the slicing question (Q4) on the evidence.

**Still open, and worth a view before drafting:** is there an existing informal style guide, editorial checklist, or set of author instructions already in use? If so, the most valuable first output may be a **diff** — where the corpus diverges from what you thought you were commissioning — rather than a guide built from scratch. For a document whose purpose is quality control, knowing where current practice has already drifted from intent is the most useful thing it could tell you.
