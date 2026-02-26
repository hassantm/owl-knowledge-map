# Audit Enrichment + Decision Feedback Loop

## Context
The term audit produced `output/term_audit.csv` with 737 issues. The reviewer (Hassan) needs to work through these and feed decisions back into the SQLite database. The CSV is the review medium — two scripts wrap the workflow:
1. **Enrich** the CSV so the reviewer has the information needed to make each decision
2. **Apply** decisions from the filled-in CSV back to the database

---

## Two Scripts

### Script 1: `src/enrich_audit.py`
Reads `output/term_audit.csv`, enriches it, writes `output/term_audit_enriched.csv`.

**Enrichment by issue_type:**

**`missed_from_extraction` rows (137):**
- Look up `source_path` for the unit via DB: `SELECT DISTINCT source_path FROM occurrences WHERE subject=? AND year=? AND term=? AND unit=? LIMIT 1`
- Open the PPTX and search ALL text runs (not just bold) for the term using case-insensitive word-boundary regex
- Add columns:
  - `appears_unbolded` — `True` / `False` / `No source found`
  - `unbolded_slides` — comma-separated slide numbers (e.g. `"4, 7, 12"`)
  - `unbolded_context` — full paragraph text of first match

**`potential_noise` and `high_priority_review` rows (600):**
- Look up `occurrence_id` via DB:
  ```sql
  SELECT o.occurrence_id FROM occurrences o
  JOIN concepts c ON o.concept_id = c.concept_id
  WHERE o.subject=? AND o.year=? AND o.term=? AND o.unit=?
  AND c.term=? AND o.slide_number=?
  ```
- Add `occurrence_id` column (required for delete operations)
- `appears_unbolded`, `unbolded_slides`, `unbolded_context` left blank for these rows

**All rows:**
- Add blank `decision` column (reviewer fills this in)

**Valid decision values:**
| issue_type | valid decisions |
|---|---|
| `missed_from_extraction` | `add` (only if appears_unbolded=True), `skip` |
| `potential_noise` | `keep`, `delete`, `skip` |
| `high_priority_review` | `keep`, `delete`, `skip` |

Blank = not yet reviewed (same as `skip` for apply script).

---

### Script 2: `src/apply_audit_decisions.py`
Reads `output/term_audit_enriched.csv` (after reviewer fills in `decision` column). Applies changes to DB. Idempotent — safe to re-run.

**`delete`** (noise/high_priority rows):
```sql
DELETE FROM occurrences WHERE occurrence_id = ?
```
Then orphan concept cleanup:
```sql
DELETE FROM concepts WHERE concept_id NOT IN (SELECT DISTINCT concept_id FROM occurrences)
```

**`keep`** (noise/high_priority rows):
```sql
UPDATE occurrences SET validation_status = 'confirmed' WHERE occurrence_id = ?
```

**`add`** (missed_from_extraction rows — only if appears_unbolded=True):
1. Get or create concept_id
2. Insert occurrence with `is_introduction=False` (unbolded = not formal introduction), `slide_number` and `term_in_context` from PPTX lookup, `validation_status='confirmed'`, `vocab_match_type='manual_add'`

**Output:** Summary printed to console + `output/audit_decisions_log.csv` written with timestamp, action, term, unit for audit trail.

---

## Files

| File | Action |
|---|---|
| `src/enrich_audit.py` | Create |
| `src/apply_audit_decisions.py` | Create |
| `output/term_audit_enriched.csv` | Generated (not committed) |
| `output/audit_decisions_log.csv` | Generated on apply run |

---

## PPTX Text Search

Reuse slide/shape/paragraph/run iteration from `extract_stage1.py` but capture ALL runs. Check assembled paragraph text to handle terms split across run boundaries:

```python
para_text = ''.join(run.text for run in para.runs)
pattern = re.compile(r'(?<![a-zA-Z])' + re.escape(term) + r'(?![a-zA-Z])', re.IGNORECASE)
if pattern.search(para_text):
    # record slide, chapter, context
```

---

## Verification

1. Run `python src/enrich_audit.py` — check enriched CSV has new columns, `occurrence_id` populated for noise rows
2. Spot-check 2–3 missed terms against source PPTX to verify `appears_unbolded` accuracy
3. Add test decisions, run `python src/apply_audit_decisions.py`, verify DB changes
4. Re-run `python src/audit_terms.py` — confirm deleted rows gone, kept rows show `confirmed`
