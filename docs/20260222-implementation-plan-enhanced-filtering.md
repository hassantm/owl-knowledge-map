# Plan: Enhanced Noise Filtering (Stage 2 Refinement)

## Context

Stages 1 and 2 are complete and successfully extract bold terms from curriculum booklets. However, the initial run revealed several categories of noise that should be filtered:

**Current issues (from sample extraction):**
- ✅ 96 terms extracted, but includes noise like:
  - Slide labels: "Reason 1", "Reason 2", "Reason 3", "Source 1", "Source 2"
  - URLs: "http://www.cngcoins.com"
  - Citations: "Classical Numismatic Group, Inc"
  - Heading fragments: "The" from "The Ezana stone"
  - Picture credits (not yet tested but user reports every booklet has these)

**Why refinement now:**
- User wants to improve extraction quality before processing full corpus
- Better to iterate on filtering logic with the sample file first
- Reprocess sample to measure improvement quantitatively

**This plan implements:** Enhanced Stage 2 with improved noise filtering, schema modification to track review status, and reprocessing of sample data to validate improvements.

## Schema Enhancement

### Add review_flag to occurrences table

Currently, the `flagged` field from extraction (short terms, etc.) is only in CSV exports. To track review status in the database, add a `needs_review` column:

**File to modify:** `src/init_db.py`

Add to occurrences table (line ~58):
```sql
needs_review    INTEGER DEFAULT 0,  -- 0=no review needed, 1=needs review, 2=reviewed and approved, 3=reviewed and rejected
review_reason   TEXT                -- Why flagged: 'short_term', 'potential_heading', 'url', 'citation', etc.
```

**Migration approach:**
Since database is only used for development so far, simply:
1. Delete existing database
2. Reinitialize with new schema
3. Reprocess sample file

## Enhanced Noise Filtering

### File to modify: `src/extract_stage1.py`

The `is_noise()` function (lines 23-47) currently filters:
- "Page N" patterns
- Pure numeric runs

**Enhancements to add:**

#### 1. Noise term dictionary (inline in code for now)
Add at top of file after imports:
```python
# Noise terms dictionary - slide labels and structural text
NOISE_TERMS = {
    # Slide structural labels
    'reason 1', 'reason 2', 'reason 3', 'reason 4', 'reason 5',
    'source 1', 'source 2', 'source 3', 'source 4', 'source 5',
    'example 1', 'example 2', 'example 3',
    'task 1', 'task 2', 'task 3',

    # Generic headings
    'the', 'a', 'an',  # Only when standalone

    # Add more patterns as discovered during corpus processing
}
```

#### 2. URL detection
Add to `is_noise()`:
```python
# Filter URLs
if re.match(r'https?://', text, re.IGNORECASE):
    return True
if re.match(r'www\.', text, re.IGNORECASE):
    return True
```

#### 3. Common citation patterns
Add to `is_noise()`:
```python
# Filter common citation patterns
if re.match(r'.+(Group|Inc|Ltd|LLC|Corp|Organization|Foundation)\.?$', text):
    return True
```

#### 4. Picture Credits section detection
Modify `extract_bold_runs()` to track a "skip mode" state variable:

Add after `current_chapter = None` (line ~131):
```python
in_credits_section = False
```

Add detection before bold run extraction (line ~145):
```python
# Check if we've entered Picture Credits section
if 'picture credit' in para_text.lower():
    in_credits_section = True

# Skip all bold terms if in credits section
if in_credits_section:
    continue  # Skip this paragraph entirely
```

#### 5. Enhanced flagging for potential headings
Modify `is_short_term()` or add new `flag_for_review()` function:

```python
def flag_for_review(text: str, context: str) -> tuple[bool, str]:
    """
    Determine if term needs human review and why.

    Returns:
        (needs_review: bool, reason: str)
    """
    reasons = []

    # Short terms
    if len(text) < 5:
        reasons.append('short_term')

    # Very short context suggests heading-only
    if len(context) < 20:
        reasons.append('potential_heading')

    # Single word in all caps (except valid proper nouns)
    if text.isupper() and ' ' not in text and len(text) > 1:
        reasons.append('all_caps')

    # Ends with colon (likely a heading)
    if text.endswith(':'):
        reasons.append('heading_marker')

    if reasons:
        return True, ', '.join(reasons)
    return False, None
```

Update extraction to use new function (line ~170):
```python
# Clean and flag
cleaned = clean_term(run_text)
needs_review, review_reason = flag_for_review(cleaned, para_text)

# Store with new fields
results['terms'].append({
    'term': cleaned,
    'slide': slide_num,
    'chapter': current_chapter,
    'context': para_text,
    'flagged': needs_review,
    'review_reason': review_reason
})
```

## Stage 2 Database Integration

### File to modify: `src/extract_stage2.py`

#### Update `insert_occurrence()` function (line ~130)
Add review fields to INSERT statement:
```python
cursor.execute("""
    INSERT INTO occurrences (
        concept_id, subject, year, term, unit, chapter,
        slide_number, is_introduction, term_in_context, source_path,
        needs_review, review_reason
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    concept_id,
    metadata['subject'],
    metadata['year'],
    metadata['term'],
    metadata['unit'],
    term_data['chapter'],
    term_data['slide'],
    True,
    term_data['context'],
    metadata['source_path'],
    1 if term_data['flagged'] else 0,
    term_data.get('review_reason', None)
))
```

#### Update CSV export (line ~200)
Add review_reason column:
```python
writer = csv.DictWriter(f, fieldnames=[
    'term', 'slide', 'chapter', 'context', 'flagged', 'review_reason',
    'subject', 'year', 'term_period', 'unit'
])
```

## Critical Files

**Files to modify:**
1. `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py` - Add needs_review + review_reason columns
2. `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage1.py` - Enhanced noise filtering
3. `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage2.py` - Database and CSV updates

**Files used as reference:**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/output/Y4 Spring 2 Christianity in 3 empires Booklet_extracted.csv` - Shows current noise issues

## Verification & Testing

### Step 1: Reinitialize database with new schema
```bash
cd /Users/hassanmamdani/ai-projects/owl-knowledge-map
venv/bin/python3 src/init_db.py
# Type 'y' to confirm overwrite
```

**Expected:** Database recreated with needs_review and review_reason columns

### Step 2: Run enhanced Stage 2 extraction
```bash
venv/bin/python3 src/extract_stage2.py
```

**Expected output changes:**
- Terms extracted: Should be ~75-85 (down from 96 due to better filtering)
- Filtered out automatically: "Reason 1/2/3", "Source 1/2/3", URLs, citations
- Flagged for review: Short terms + potential headings with reasons

### Step 3: Verify database schema
```bash
sqlite3 db/owl_knowledge_map.db ".schema occurrences"
```

**Expected:** needs_review and review_reason columns present

### Step 4: Check filtered noise terms
```bash
sqlite3 db/owl_knowledge_map.db "SELECT term FROM concepts WHERE term LIKE 'Reason%' OR term LIKE 'Source%' OR term LIKE 'http%';"
```

**Expected:** Empty result (these should be filtered)

### Step 5: Verify review flagging
```bash
sqlite3 db/owl_knowledge_map.db "SELECT term, review_reason FROM occurrences WHERE needs_review = 1 LIMIT 10;"
```

**Expected:** Short terms and potential headings with reasons like "short_term", "potential_heading", "all_caps"

### Step 6: Compare term counts
```bash
# Old extraction (before refinements)
wc -l output/Y4\ Spring\ 2\ Christianity\ in\ 3\ empires\ Booklet_extracted.csv
# Should show 97 lines (96 terms + header)

# New extraction (after refinements)
# Check new CSV output
# Should show ~76-86 lines (cleaner extraction)
```

### Step 7: Spot-check CSV export
```bash
head -20 output/Y4\ Spring\ 2\ Christianity\ in\ 3\ empires\ Booklet_extracted.csv
```

**Expected:** New review_reason column populated for flagged terms

### Verification Checklist
- [ ] Database schema includes needs_review and review_reason columns
- [ ] Total terms reduced by ~10-20 (noise filtered out)
- [ ] "Reason 1", "Source 1", URLs no longer in extracted terms
- [ ] Picture credits section skipped (if present in sample)
- [ ] Flagged terms include review reasons in database and CSV
- [ ] Valid short terms like "Huns", "sins", "Pope" still extracted but flagged
- [ ] Multi-word terms like "three wise men", "official religion" still captured correctly

## Success Metrics

**Before refinements:**
- 96 terms extracted
- ~8 flagged (short terms only)
- Includes obvious noise (Reason 1, Source 1, URLs)

**After refinements (expected):**
- 75-85 terms extracted (~11-21 noise terms filtered)
- ~15-20 flagged with specific reasons
- No structural labels, URLs, or citations in results
- Review reasons help prioritize human validation

**Qualitative improvement:**
- CSV export is more focused and useful for review
- Database query for "terms needing review" is actionable
- Extraction can scale to full corpus with confidence

## Future Enhancements (not in this plan)

- **External config file:** Move NOISE_TERMS to YAML/JSON for easy editing
- **Pattern learning:** Track rejected terms during review to auto-expand noise dictionary
- **Heading detection ML:** Train classifier on context length + formatting patterns
- **Batch processing:** Process multiple files and aggregate statistics

## Implementation Notes

**Design philosophy:**
- Conservative filtering - when in doubt, flag for review rather than auto-reject
- Preserve all filtering logic in Stage 1 (extraction layer)
- Stage 2 just passes through the enhanced metadata

**Testing approach:**
- Reprocess sample file is the primary validation
- Before/after comparison shows improvement quantitatively
- Human review of flagged terms validates we're not over-filtering

**Code style:** Follow CLAUDE.md conventions - clean Python, timestamped comments for modifications
