# Architectural Decision: Vocab-First Pipeline

**Date:** 2026-02-26
**Status:** Adopted
**Implemented by:** `src/vocab_first_cleanup.py`

---

## The Core Question

Should the pipeline start from bold text extraction (current approach) and verify against vocab lists — or start from vocab lists (authoritative) and search the PPTX to recover metadata?

---

## Decision

**Vocab-first is the correct architecture.**

The bold-first approach uses formatting as a proxy for authorial intent. The vocab lists *are* the intent. Starting from the proxy and checking against the source is architecturally inverted.

---

## Why Vocab Lists Are Authoritative

The vocab lists are not just a flat list of terms. They are:

- **Per booklet (per unit):** Scoped to the exact unit where terms are introduced
- **By chapter:** The chapter breakdown maps directly to the chapter of first introduction

This means vocab list structure IS the introduction map. A term appearing in Chapter 3 of the Y4 Spring 2 vocab list was introduced in Chapter 3 of that unit — by the authors themselves (Christine Counsell and Steve Mastin).

**What the vocab list provides without any PPTX access:**
- Term (exactly as authored)
- `is_introduction = True` (implicit — the vocab list is the record of what was introduced)
- Chapter of introduction
- Unit, subject, year, term (from file path, same as current approach)

**What still requires PPTX text search:**
- `slide_number` — precise location within the booklet
- `term_in_context` — surrounding paragraph text
- Bold check — now a verification/sanity check, not the primary signal

---

## Problem with the Bold-First Approach

### Extraction counts (pre-cleanup)

| Status | Count |
|---|---|
| confirmed (bold + in vocab) | 2,556 |
| confirmed_with_flag (bold + in vocab, flagged) | 193 |
| potential_noise (bold, NOT in vocab) | 316 |
| high_priority_review (bold, NOT in vocab, flagged) | 284 |
| NULL (pre-validation rows) | 93 |
| **Total** | **3,442** |
| Missed (in vocab, NOT extracted) | 137 |

The 600 noise candidates (potential_noise + high_priority_review) are the direct cost of using bold as the primary signal. Inspection confirmed these are formatting accidents: quote attributions, inline headings, speaker names — not editorial vocabulary decisions.

The 737-item human review queue is the downstream cost of this inversion.

---

## Vocab-First Logic

```
Vocab list terms + chapter → search PPTX for slide/context → is_introduction already known
```

- Every term confirmed by definition (authors wrote the lists)
- `is_introduction = True` for all vocab list entries; chapter already known
- PPTX search adds slide number and context
- The 600 noise candidates are never generated
- The 137 missed terms are found via full-text PPTX search

---

## Implementation: Pragmatic Cleanup of Existing DB

Rather than rebuild from scratch, `vocab_first_cleanup.py` brings the existing DB to a vocab-first state in four steps.

### Step 1 — Delete noise

```sql
DELETE FROM occurrences
WHERE validation_status IN ('potential_noise', 'high_priority_review');

DELETE FROM concepts
WHERE concept_id NOT IN (SELECT DISTINCT concept_id FROM occurrences);
```

Removes ~600 rows. Leaves confirmed occurrences grounded in vocab list membership.

### Step 2 — Promote confirmed_with_flag

193 rows are in the vocab list AND flagged by Stage 1. Vocab list membership overrides the flag.

```sql
UPDATE occurrences SET validation_status = 'confirmed'
WHERE validation_status = 'confirmed_with_flag';
```

### Step 3 — Update chapters from vocab lists

For surviving occurrences where chapter is NULL or empty, populate from vocab list chapter structure. Where DB chapter number conflicts with vocab list chapter, the conflict is logged but not overwritten (to avoid replacing full chapter titles like `'1. The Roman Empire'` with bare `'2'`).

### Step 4 — Recover missed vocab terms

For the ~137 missed terms: search full PPTX text (not just bold) for each. Those found (expected ~81) are inserted as confirmed occurrences with `is_introduction=0`. Those not found in the PPTX text at all (~56) are supplementary vocab not used in the booklet body — no occurrence record is created.

---

## Net Result (expected)

| Status | Before | After |
|---|---|---|
| confirmed | 2,556 | ~2,830 |
| confirmed_with_flag | 193 | 0 (promoted) |
| potential_noise | 316 | 0 (deleted) |
| high_priority_review | 284 | 0 (deleted) |
| Human review queue | ~737 items | ~81 items |

---

## Future Extractions: Invert the Pipeline

New booklets added to the corpus should follow vocab-first from the outset:

1. Load vocab list → get terms + chapters
2. Search PPTX for each term → get slide, context, bold status
3. Write confirmed occurrence directly (no validation_status classification needed)

The `validation_status` field and all Stage 1 noise filters become redundant for new extractions.

---

## One Legitimate Risk

Could there be terms bolded in booklets but absent from vocab lists? Sample inspection of the 600 noise candidates (names, quote attributions, partial phrases) strongly suggests these are formatting accidents, not editorial decisions. The risk of losing valid concepts is low. The bold check can be retained as a secondary sanity check in future extractions.

---

## Scripts

| Script | Role |
|---|---|
| `src/vocab_first_cleanup.py` | One-time DB cleanup; `--dry-run` mode |
| `src/vocab_validator.py` | Vocab list discovery and parsing (unchanged) |
| `src/audit_terms.py` | Regenerate review queue after cleanup (~81 items) |
| `src/enrich_audit.py` | Enrich residual review queue (unchanged) |
| `src/apply_audit_decisions.py` | Apply residual decisions (unchanged) |
