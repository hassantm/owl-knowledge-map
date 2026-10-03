# Recurrence Gap-Fill: Diagnosis and Repair

**Dates:** 2026-10-02 to 2026-10-03
**Status:** Gap-fill complete: booklet text loaded, false positives removed, and 3,458 new recurrences inserted on 2026-10-03. Step 2 (the corrected export) is still to do (see §6).

## 1. Why this work started

`single_occurrence_concepts.csv` was meant to list terms that appear in only one unit across the whole curriculum. It was wrong: "empire" had rows for 16 units and "city" for 27. The task was to diagnose the cause (Step 1) and then produce a corrected `single_occurrence_v2.csv` (Step 2). Step 2 has **not** been run yet.

## 2. Diagnosis (read-only)

### Schema notes
- There is no `owl` schema. `owl` is the **database** name, and the tables are in `public`: `concepts`, `occurrences`, `units`, `co_occurrences`, `edges` and `generated_story_packs`.
- `occurrences.term` holds the **term period** (Autumn1…Summer2), not the word. The word is only in `concepts.term`.
- `occurrences` keeps its own copies of subject/year/term/unit. **153 rows disagree with `units`**: 57 are labelled "Sikhism 1" but point at "The teaching of the gurus" (with a different year), 48 are "Living Sikh traditions" pointing at "Sikhism 2", and 48 are Buddhism 2 rows with a mismatched term period. Treat `units`, joined on `unit_id`, as authoritative. These rows have **not** been fixed.

### Cause of the bad export
The query grouped by `c.term, u.subject, u.year, u.term, u.unit` and then filtered with `HAVING COUNT(DISTINCT o.unit_id) = 1`. Because unit is in the GROUP BY, that count is always 1, so the filter did nothing and the query returned every (concept, unit) pair. Rerunning it gives exactly 5,436 rows, which equals the number of distinct `(concept_id, unit_id)` pairs. **Cause: the query (option a).**

It was **not** caused by a new concept row being created each time a term is bolded (option b). "empire" has one concept row (id 170) with 16 occurrences in 16 units: 1 bold introduction and 15 plain recurrences. 63 concepts have more than one bold introduction under the same id. There are only 13 case-only duplicate concepts, such as Desert/desert and WALES/Wales (2,946 rows, 2,946 distinct terms, 2,933 distinct `lower(trim(term))`).

### Recurrence coverage: a real gap in the data
Plain-text recurrences are stored as occurrences linked to the same concept (`is_introduction = 0`). Most were created by `src/gap_fill_occurrences.py` (`vocab_source = 'booklet_gap_fill'`). That script only scans units that have `units.booklet_content`, and **only 33 of the 64 units had it**:

| Units | Count | Bold | Plain |
|---|---|---|---|
| With booklet text | 33 | 1,457 | 2,447 |
| Without booklet text | 31 | 1,485 | 106 |

Bold extraction had run everywhere, but unbolded reuse was almost never recorded in the other 31 units. Any analysis that relies on reuse was therefore unreliable: the single-occurrence list, spread across units, intro/recurrence ratios and edges.

Where booklet text existed, capture was accurate. Searching the text for empire, city, mountains, trade and pharaoh found them in exactly the recorded units.

### Decision
Bold-concept extraction does **not** need redoing. Fill the gap instead: load booklet text for the 31 missing units, then rerun gap-fill.

## 3. Loading booklet text for the 31 missing units

1. **Backup:** `backups/pre_gapfill_20261002_1859.dump` (`pg_dump -Fc` of `units` and `occurrences`), taken before any write.
2. **Source files:** the booklet `.pptx` paths came from `occurrences.source_path`. The files were downloaded from Dropbox through the Dropbox connector into `data/booklets/<unit_id>.pptx`, about 4.4 GB, and each file size was checked against Dropbox.
   - Unit 42 (Manchester Man): the folder had been renamed to `Y6 History Spring 1 Cities 1 This Manchester man`. The `.pptx` was found at the new path.
   - The scratchpad was wiped when Claude Code restarted mid-session, so the files were downloaded again into the project folder, where they persist.
3. **Extraction:** `data/booklets/extract_all.py` uses `content_ingestion.extract_booklet_content()`, the same code as the existing 33 units, to write JSON to `data/booklets/extracted/`. Booklets produced 26–59 pages and 13k–58k characters each (log in `extract.log`).
4. **Load:** `data/booklets/load_extracted.py` updated `units.booklet_content` **only where it was NULL**. 31 rows were updated, so all 64 units now have booklet text.

Note: some booklets were edited on Dropbox after the original bold-term extraction (for example, Population was modified 2026-07-18). The loaded text reflects the current versions.

## 4. Gap-fill matching review

### How `gap_fill_occurrences.py` behaves
- It matches the exact term only, case-insensitively, with letter boundaries. There is **no plural handling**: "empire" does not match "empires".
- It only searches for concepts first introduced in a year **at or before** the unit's year.
- It inserts one row per (concept, unit), skips pairs that already exist, and never deletes.

### Dry run (unmodified script)
The unmodified script would add 3,496 rows. The 33 units that already had text gained 0, except The Maya with 2. Spot checks found false positives:
- **Junk concept `–`** (id 3516, an en dash, created by the 2026-10-02 Sikhism 1 extraction). It matched every dash: 11 rows.
- **Pronunciation guides:** for example "Barabbas (ba-rab-ass)", "Krish Kandiah (can-dye-ah)" and "(ram-ad-an)".
- **Image-credit URLs and filenames:** for example "pixabay.com/…/water-lily…", "london-underground", "…exile_from_Ayodhya.jpg".

A blanket "ignore hyphenated matches" rule was rejected because it would also drop real uses such as "semi-arid", "gas-fired" and "tax-collector".

### Decision: cleaned matching
`data/booklets/gap_fill_clean.py` reuses the script's own functions (`load_units`, `load_concepts_introduced_by_year`, `find_term_in_pages`, `insert_occurrence`), so the row format is identical. Before matching, it:
- removes URLs (`http(s)://…`, `www.…`, and tokens ending in `.com`, `.co.uk`, `.org`, `.net`, `.de`, `.br` or `.htm(l)`);
- removes pronunciation guides: brackets that contain only lowercase letters, spaces and apostrophes, with at least one hyphen;
- skips concepts whose term contains no letters.

Cleaned dry run: **3,458** new rows. All 38 dropped matches were reviewed by hand, and every one was a false positive.

## 5. Clean-up of the existing gap-fill rows (done)

At the user's request, the same check was applied to the existing 2,320 `booklet_gap_fill` rows (`data/booklets/find_gapfill_fp.py`). **15 rows** had no match in their unit's cleaned booklet text. They included "pub" in "(re-pub-lick)", "bay" in "(sack-bay)", "dye" in "(dye-ah)", "status", "political", "floral" and "Asia" inside URLs, and "Harappa" found only in the image credit "Harappa.com".

- None were used in `edges`, and no concept was left with zero occurrences.
- They were deleted in one transaction that checked the expected count (exactly 15).
- The list with reasons is in `data/booklets/gapfill_false_positives.csv`. Full copies of the deleted rows are in `data/booklets/deleted_gapfill_false_positives_full.csv`.
- `occurrences` went from 5,495 rows to 5,480; gap-fill rows went from 2,320 to 2,305.

The false-positive rate in the old rows was about 0.6%.

## 6. Pending

1. ~~**Insert the new recurrences.**~~ **Done 2026-10-03** with user approval: `python3 data/booklets/gap_fill_clean.py --write`.
   - The high-water mark beforehand was `max(occurrence_id) = 6542` (saved in `data/booklets/pre_write_max_occurrence_id.txt`). To roll back: `DELETE FROM occurrences WHERE occurrence_id > 6542 AND vocab_source = 'booklet_gap_fill'`.
   - +3,458 rows (all `is_introduction = 0`) across 32 units and 1,269 concepts. `occurrences` now has 8,938 rows: 2,942 bold and 5,996 plain.
   - Checks: a dry run afterwards found 0 new rows. Units with recurrences now: empire 29 (was 16), city 55 (was 27), kingdom 37, mountains 37.
   - The 31 newly filled units average 115 plain recurrences each; the original 33 average 74. These units are mostly Y5–6, and the year cut-off means more earlier concepts are searched for in later years.
2. ~~**Step 2:**~~ **Done 2026-10-03.** Wrote `output/single_occurrence_v2.sql` (read-only `COPY … TO STDOUT`) and `output/single_occurrence_v2.csv`.
   - **Key:** lower-case, curly apostrophes converted to straight, whitespace collapsed. Units are counted across all occurrences, bold and plain, regardless of `concept_id`. Unit labels come from `units`.
   - **`term`:** the spelling with the most occurrences; ties go first to the spelling with a bold introduction, then to the lowest `concept_id`.
   - **Result:** 1,419 rows (History 575, Religion 465, Geography 379). empire, city, kingdom and mountains are all absent. 26 rows have `plural_match` filled. One false flag: refuge → refugees, because adding "-es" happens to make a different word.
   - **Comparison:** the bad export had 5,436 rows. The `~/single_occurrence_concepts.csv` on disk is a different file from 2026-10-02 15:30 with 2,054 unique terms; it was left untouched.
   - **Includes the junk term `–`** (Sikhism 1). It was kept because the export follows the spec exactly.

3. **Step 3: filter for transferable concepts. Done 2026-10-03.**
   - Each of the 1,419 single-unit terms was classified against the user's keep/strip rubric. Four agents in parallel each took about 355 rows, using the same rubric, and wrote to `output/filter_work/decisions_{1..4}.csv`. Every strip and keep decision was then reviewed by hand.
   - Three overrides moved terms to KEEP: nirvana, Seva and ex nihilo, for consistency with the rubric's "dharma" example.
   - Output: `output/transferable_concepts.csv`, with the columns term, subject, year, term_period and unit. **779 kept** (History 312, Religion 291, Geography 176) and 640 stripped. The full decision log, with category and notes, is in `output/transferable_concepts_decisions.csv`.
   - 19 kept rows have a `plural_match`, so their plural or singular form is already reused elsewhere (one false flag: refuge → refugees).

## 7. Open issues, not yet acted on

- **Truncated concept terms:** extraction cut off the first letter of some terms, for example "roynes", "lexandria", "urret", "ontemporaries" (contemporaries), "rowsing", "hurch", "uddha", "xtreme" and "renched". There are also phrase fragments such as "Guru Nanak’s first", "worn on" and "ran the headline". All were stripped as JUNK in Step 3. Truncated terms can't be found by gap-fill, so they need fixing in `concepts`.

- **Junk concepts from the Sikhism 1 extraction:** `–` (id 3516) and possibly `ik` (id 3512, a fragment of "ik onkar"). Each still has one bold occurrence.
- **153 occurrence rows** whose stored labels disagree with `units` (§2).
- **13 case-only duplicate concepts** (§2).
- **Gap-fill limits** that will still make some terms look single-unit when they aren't: no plural matching, and no matching in years before a term is first bolded.
- **70 concepts with no bold introduction.** Confirm whether this is intended (they may come from vocab lists).
- **Exposed API key:** a diagnostic `grep` of `.env` printed the Anthropic API key into the session transcript. Rotating it is recommended.

## 8. Files created

| Path | Purpose |
|---|---|
| `backups/pre_gapfill_20261002_1859.dump` | Pre-change backup of `units` and `occurrences` |
| `data/booklets/<unit_id>.pptx` | 31 source booklets (about 4.4 GB; can be deleted once no longer needed) |
| `data/booklets/extract_all.py`, `extracted/`, `extract.log` | Booklet text extraction (no DB writes) |
| `data/booklets/load_extracted.py` | Loads extracted text into `units` where it is NULL |
| `data/booklets/gapfill_dryrun.log` | Dry run of the unmodified gap-fill script |
| `data/booklets/check_hyphen.py` | Analysis of hyphen-adjacent matches |
| `data/booklets/gap_fill_clean.py` | Cleaned gap-fill (dry run by default; `--write` to insert) |
| `data/booklets/find_gapfill_fp.py`, `gapfill_false_positives.csv` | False-positive review of the existing rows |
| `data/booklets/deleted_gapfill_false_positives_full.csv` | Full copies of the 15 deleted rows |
