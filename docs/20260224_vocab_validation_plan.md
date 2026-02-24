# Plan: Vocabulary List Validation for Extraction Enhancement

## Context

**Current State:**
- ✅ Batch processing working - can process 20+ booklets in one run
- ✅ Basic noise filtering catches obvious non-concepts (page numbers, URLs, line numbers)
- ✅ Flagging system identifies low-confidence terms (short words, all-caps, low context)
- ✅ Y4 Christianity sample: 86 terms extracted, 11 flagged for review (87% need manual review)
- ⚠️ High manual review burden - most extracted terms need human verification
- ⚠️ No way to distinguish valid short terms ("code", "law") from noise

**Discovery:**
- 📁 35+ pre-curated vocabulary lists exist in Dropbox alongside booklets
- 📄 Format: .docx files organized by chapter (matching booklet structure)
- ✓ Example: Y4 Roman Britain has 56 authoritative terms across 6 chapters
- ✓ Lists created by curriculum authors (Christine Counsell/Steve Mastin)
- ✓ Multi-word phrases preserved: "placed in chains", "rose from the dead"
- ✓ Location: Each unit has "Vocab List" subfolder with "By Chapter" version

**Why This is Needed:**
- Leverage existing authoritative vocabulary to validate extractions
- Auto-approve terms that match vocab lists (reduce manual review by ~60%)
- Identify likely noise (extracted but not in vocab) for prioritized review
- Detect extraction misses (in vocab but not extracted) to improve recall
- Add confidence scoring to guide human review workflow

**This Plan Implements:**
- New validation module (`vocab_validator.py`) to parse and match against vocab lists
- Multi-tier matching algorithm (exact, normalized, fuzzy)
- Database schema extension for validation metadata
- Integration into Stage 2 pipeline as optional validation step
- Enhanced reporting showing confirmed vs. potential noise

---

## Implementation Approach

### 1. Add python-docx Dependency

**File:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/requirements.txt`

**Add:**
```
python-docx
```

**Install:**
```bash
source venv/bin/activate
pip install python-docx
```

---

### 2. Create Vocabulary Validator Module

**File:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/vocab_validator.py` (NEW)

**Core Functions:**

#### 2.1 Parse Vocabulary List (.docx)

```python
def parse_vocab_docx(docx_path: str) -> dict:
    """
    Parse vocabulary list .docx into structured data.

    Expected format:
    - Chapter headings: "Chapter 1" or "1. Chapter Title"
    - Terms: One per paragraph

    Returns:
        {
            'chapters': {
                '1': ['term1', 'term2'],
                '2': ['term3', 'term4']
            },
            'all_terms': ['term1', 'term2', ...],  # Flat list for quick lookup
            'metadata': {
                'source_path': str,
                'total_terms': int,
                'chapter_count': int
            }
        }
    """
```

**Implementation Notes:**
- Use `from docx import Document`
- Chapter detection: `r'^(Chapter\s+)?(\d+)\.?'`
- Track current chapter as state variable
- Strip whitespace, preserve multi-word phrases
- Skip empty paragraphs

#### 2.2 Locate Vocabulary List

```python
def find_vocab_list(pptx_path: str) -> str | None:
    """
    Find vocabulary list .docx for a booklet file.

    Search pattern:
    1. Get unit folder (parent.parent of pptx)
    2. Look for "Vocab List" subfolder
    3. Prefer files with "By Chapter" in name
    4. Fallback to any .docx

    Returns path or None if not found.
    """
```

**Discovery Logic:**
```
Booklet: /Year 4 Hist/Y4 Hist Autumn 1 Roman Republic/Y4 Autumn 1 Booklet/file.pptx
Vocab:   /Year 4 Hist/Y4 Hist Autumn 1 Roman Republic/Vocab List/Y4 Roman Britain By Chapter.docx
                                                        ↑ Look here
```

#### 2.3 Match Term Against Vocab

```python
def match_term(extracted: str, vocab_terms: list) -> dict:
    """
    Match extracted term against vocabulary list.

    Three-tier matching:
    1. Exact (case-insensitive): extracted.lower() == vocab.lower()
    2. Normalized: Strip punctuation, collapse whitespace
    3. Fuzzy: difflib.SequenceMatcher (90% similarity threshold)

    Returns:
        {
            'matched': bool,
            'match_type': 'exact' | 'normalized' | 'fuzzy' | 'none',
            'confidence': 0.0 to 1.0,
            'vocab_term': str (matched vocab term, or None)
        }
    """
```

**Confidence Scoring:**
- Exact match: 1.0
- Normalized match: 0.95
- Fuzzy match (>90% similar): 0.8
- No match: 0.0

**Examples:**
```
"Bethlehem" vs "Bethlehem"        → exact, 1.0
"rose from dead" vs "rose from the dead" → fuzzy, 0.8
"baptised" vs "baptized"          → fuzzy, 0.8
"Reason 1" vs vocab list          → none, 0.0
```

#### 2.4 Validate Extraction Results

```python
def validate_extraction(extraction_results: dict, vocab_path: str, unit_name: str) -> dict:
    """
    Validate extraction results against vocabulary list.

    Args:
        extraction_results: Output from extract_stage1.extract_bold_runs()
        vocab_path: Path to vocabulary .docx file
        unit_name: Curriculum unit name

    Returns:
        Enriched extraction_results with validation metadata added to each term:
        - validation_status: 'confirmed' | 'potential_noise' | 'confirmed_with_flag' | 'high_priority_review'
        - vocab_confidence: 0.0 to 1.0
        - vocab_match_type: 'exact' | 'normalized' | 'fuzzy' | 'none'
        - vocab_source: Path to vocab .docx

        Plus validation_stats:
        {
            'vocab_terms_total': int,
            'extracted_confirmed': int,
            'extracted_noise': int,
            'missed_terms': [list]  # In vocab but not extracted
        }
    """
```

**Validation Categories:**

| Category | Condition | validation_status | needs_review |
|----------|-----------|-------------------|--------------|
| Confirmed | In vocab, not flagged by Stage 1 | 'confirmed' | 0 (auto-approve) |
| Confirmed with flag | In vocab, but flagged by Stage 1 | 'confirmed_with_flag' | 1 (low priority) |
| Potential noise | Not in vocab, not flagged | 'potential_noise' | 1 (medium priority) |
| High priority review | Not in vocab + flagged by Stage 1 | 'high_priority_review' | 1 (high priority) |

**Missed Terms:**
- Terms in vocab list but NOT extracted from booklet
- Tracked separately in validation_stats['missed_terms']
- Indicates possible extraction failures (false negatives)

---

### 3. Extend Database Schema

**File:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py`

**Add to occurrences table:**

```sql
-- Add after review_reason column (line 62)
validation_status   TEXT,     -- 'confirmed', 'potential_noise', 'confirmed_with_flag', 'high_priority_review', NULL
vocab_confidence    REAL,     -- 0.0 to 1.0, NULL if no vocab validation
vocab_match_type    TEXT,     -- 'exact', 'normalized', 'fuzzy', 'none', NULL
vocab_source        TEXT      -- Path to vocab .docx used, NULL if no validation
```

**Migration for Existing Database:**

Create migration script or manual ALTER TABLE:
```sql
ALTER TABLE occurrences ADD COLUMN validation_status TEXT;
ALTER TABLE occurrences ADD COLUMN vocab_confidence REAL;
ALTER TABLE occurrences ADD COLUMN vocab_match_type TEXT;
ALTER TABLE occurrences ADD COLUMN vocab_source TEXT;
```

**Note:** Existing records will have NULL values (acceptable - indicates pre-validation extractions)

---

### 4. Integrate into Stage 2 Pipeline

**File:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage2.py`

**Modification Points:**

#### 4.1 Import Validator (top of file)

```python
# Add after existing imports
try:
    from vocab_validator import find_vocab_list, validate_extraction
    VOCAB_VALIDATION_AVAILABLE = True
except ImportError:
    VOCAB_VALIDATION_AVAILABLE = False
```

#### 4.2 Modify process_file() Function

**Insert after extraction (around line 318):**

```python
# Step 2: Extract bold terms (reuse Stage 1)
print(f"Extracting bold terms...")
extraction = extract_bold_runs(pptx_path)
results['extraction'] = extraction

# NEW STEP 2.5: Vocab validation (optional)
if VOCAB_VALIDATION_AVAILABLE:
    vocab_path = find_vocab_list(pptx_path)
    if vocab_path:
        print(f"Validating against vocab list...")
        extraction = validate_extraction(extraction, vocab_path, metadata['unit'])
        results['validation_stats'] = extraction.get('validation_stats', {})

        # Print validation summary
        vstats = results['validation_stats']
        print(f"  Vocab list: {Path(vocab_path).name}")
        print(f"  Terms in vocab: {vstats.get('vocab_terms_total', 0)}")
        print(f"  Confirmed: {vstats.get('extracted_confirmed', 0)}")
        print(f"  Potential noise: {vstats.get('extracted_noise', 0)}")
        print(f"  Missed terms: {len(vstats.get('missed_terms', []))}")
    else:
        print(f"  No vocab list found - skipping validation")

# Continue with Step 3 (database write)...
```

#### 4.3 Update insert_occurrence() Function

**Modify to accept validation metadata (around line 140):**

```python
def insert_occurrence(cursor: sqlite3.Cursor, concept_id: int, metadata: dict,
                     term_data: dict) -> int:
    """
    Insert an occurrence record.

    2026-02-24: Added validation metadata fields

    Args:
        cursor: SQLite cursor
        concept_id: Foreign key to concepts table
        metadata: File metadata (subject, year, term, unit, source_path)
        term_data: Extracted term data including:
            - slide, chapter, context, flagged, review_reason (existing)
            - validation_status, vocab_confidence, vocab_match_type, vocab_source (new)
    """
    cursor.execute("""
        INSERT INTO occurrences (
            concept_id, subject, year, term, unit, chapter,
            slide_number, is_introduction, term_in_context, source_path,
            needs_review, review_reason,
            validation_status, vocab_confidence, vocab_match_type, vocab_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        term_data.get('review_reason', None),
        # New validation fields
        term_data.get('validation_status', None),
        term_data.get('vocab_confidence', None),
        term_data.get('vocab_match_type', None),
        term_data.get('vocab_source', None)
    ))
    return cursor.lastrowid
```

#### 4.4 Update CSV Export

**File:** `extract_stage2.py` - modify `export_to_csv()` (around line 253)

**Add columns:**
```python
writer = csv.DictWriter(f, fieldnames=[
    'term', 'slide', 'chapter', 'context', 'flagged', 'review_reason',
    'subject', 'year', 'term_period', 'unit',
    # New validation columns
    'validation_status', 'vocab_confidence', 'vocab_match_type'
])
```

**Add to row writes:**
```python
writer.writerow({
    # ... existing fields ...
    'validation_status': term_data.get('validation_status', ''),
    'vocab_confidence': term_data.get('vocab_confidence', ''),
    'vocab_match_type': term_data.get('vocab_match_type', '')
})
```

---

### 5. Enhanced Reporting

#### 5.1 Console Output

**Expected output during processing:**

```
Processing: Y4 Spring 2 Christianity in 3 empires Booklet.pptx
Parsing metadata...
Extracting bold terms...
Validating against vocab list...
  Vocab list: Y4 Christianity Core Vocab By Chapter.docx
  Terms in vocab: 56
  Confirmed: 52 (60%)
  Potential noise: 34 (40%)
  Missed terms: 4

Writing to database...
Success: 86 terms extracted, 52 auto-approved, 34 flagged for review
```

#### 5.2 Missed Terms Report (Optional)

**Create separate CSV per unit:**

```python
# In vocab_validator.py
def export_missed_terms(missed_terms: list, unit_name: str, output_dir: str):
    """
    Export missed terms (in vocab but not extracted) to CSV.

    CSV format:
    unit, chapter, missed_term, vocab_chapter
    """
```

**Filename:** `output/{unit_name}_missed_terms.csv`

---

## Critical Files

**New files:**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/vocab_validator.py` - Core validation module (~300 lines)

**Modified files:**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/requirements.txt` - Add python-docx
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py` - Add validation columns to schema
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage2.py` - Integrate validation, update DB writes and CSV export

**Reference files (read-only):**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage1.py` - Understand extraction data structure
- Sample vocab list: `/Users/hassanmamdani/Library/CloudStorage/Dropbox/Haringey Counsell Shared Items/HEP History/Year 4 Hist/Y4 Hist Spring 1 Roman Britain/Y4 Spring 1 Roman Britain Vocab List/*.docx`

---

## Verification & Testing

### Phase 1: Install Dependencies & Initialize DB

```bash
cd /Users/hassanmamdani/ai-projects/owl-knowledge-map
source venv/bin/activate

# Install python-docx
pip install python-docx

# Reinitialize database with new schema
# WARNING: This will delete existing data
python src/init_db.py
# Type 'y' to confirm
```

**Expected:** Database recreated with 4 new validation columns

### Phase 2: Test Vocab List Parsing

```python
# Python REPL test
source venv/bin/activate
cd src
python3

from vocab_validator import parse_vocab_docx, find_vocab_list

# Test finding vocab list
pptx_path = "/Users/hassanmamdani/Library/CloudStorage/Dropbox/Haringey Counsell Shared Items/HEP History/Year 4 Hist/Y4 Hist Spring 1 Roman Britain/Y4 Spring 1 Roman Britain Booklet/Y4 Spring 1 Roman Britain Booklet.pptx"
vocab_path = find_vocab_list(pptx_path)
print(f"Found: {vocab_path}")

# Test parsing
vocab_data = parse_vocab_docx(vocab_path)
print(f"Chapters: {list(vocab_data['chapters'].keys())}")
print(f"Total terms: {len(vocab_data['all_terms'])}")
print(f"Chapter 1 terms: {vocab_data['chapters']['1'][:5]}")  # First 5 terms
```

**Expected:**
- Vocab list found
- 56 total terms parsed
- 6 chapters identified
- Terms correctly extracted

### Phase 3: Test Single File with Validation

```bash
# Process Y4 Christianity (has vocab list)
cd /Users/hassanmamdani/ai-projects/owl-knowledge-map
source venv/bin/activate
cd src

python3 extract_stage2.py
```

**Expected Output:**
```
Processing: Y4 Spring 2 Christianity in 3 empires Booklet.pptx
Extracting bold terms...
Validating against vocab list...
  Vocab list: Y4 Christianity Core Vocab By Chapter.docx
  Terms in vocab: 56
  Confirmed: 52
  Potential noise: 34
  Missed terms: 4

Success: 86 terms extracted
```

**Verification Queries:**

```bash
sqlite3 db/owl_knowledge_map.db "
SELECT validation_status, COUNT(*)
FROM occurrences
GROUP BY validation_status;
"

# Expected:
# confirmed|52
# potential_noise|30
# confirmed_with_flag|4
```

### Phase 4: Check CSV Export

```bash
ls -lh output/Y4\ Spring\ 2\ Christianity*_extracted.csv
head -20 output/Y4\ Spring\ 2\ Christianity*_extracted.csv
```

**Expected:**
- CSV has validation_status, vocab_confidence, vocab_match_type columns
- Confirmed terms have confidence 0.8-1.0
- Noise terms have confidence 0.0

### Phase 5: Batch Processing Test

```bash
# Clear database
python src/init_db.py  # Type 'y'

# Process Year 4 History with validation
DROPBOX_ROOT="/Users/hassanmamdani/Library/CloudStorage/Dropbox/Haringey Counsell Shared Items"
python src/batch_process.py "$DROPBOX_ROOT/HEP History" --year 4
```

**Expected:**
- 5 files processed
- Validation stats shown for each unit
- Some units may not have vocab lists (validation skipped)
- Database populated with validation metadata

**Validation Query:**

```sql
SELECT
    unit,
    COUNT(*) as total_terms,
    SUM(CASE WHEN validation_status = 'confirmed' THEN 1 ELSE 0 END) as confirmed,
    SUM(CASE WHEN validation_status LIKE '%noise%' THEN 1 ELSE 0 END) as noise
FROM occurrences
WHERE year = 4
GROUP BY unit;
```

**Expected:** 60-70% of terms confirmed by vocab lists

### Phase 6: Review Validation Quality

**Manual spot-checks:**

1. Sample confirmed terms:
```sql
SELECT term, vocab_confidence, vocab_match_type
FROM occurrences
WHERE validation_status = 'confirmed'
LIMIT 20;
```
**Verify:** Terms are legitimate curriculum concepts

2. Sample potential noise:
```sql
SELECT term, context, review_reason
FROM occurrences
WHERE validation_status = 'potential_noise'
LIMIT 20;
```
**Verify:** Mix of actual noise and possible valid variants

3. Missed terms (if generated):
```bash
cat output/*_missed_terms.csv
```
**Verify:** Terms that should have been extracted but weren't

### Success Criteria

- [ ] python-docx installed successfully
- [ ] Database schema updated with 4 validation columns
- [ ] Vocab list parsing works for .docx files
- [ ] Vocab list discovery finds files in correct folder
- [ ] Matching algorithm produces reasonable confidence scores
- [ ] Validation integrates smoothly into Stage 2 pipeline
- [ ] CSV exports include validation metadata
- [ ] Batch processing works with validation enabled
- [ ] ~60% of extracted terms confirmed by vocab lists
- [ ] Manual review burden reduced (confirmed terms auto-approved)
- [ ] Validation gracefully skips units without vocab lists

---

## Implementation Notes

**Design Philosophy:**
- Optional validation - gracefully handles missing vocab lists
- Non-destructive - preserves all Stage 1 extractions with added metadata
- Conservative matching - high fuzzy threshold (90%) to avoid false positives
- Human oversight maintained - flags for review, doesn't auto-reject
- Modular design - validator is standalone, reusable module

**Error Handling:**
- Missing vocab list → skip validation, log message
- Vocab parse error → log error, skip validation for that unit
- Multiple vocab files → prefer "By Chapter", log which used
- Unicode issues → handle gracefully with encoding fallback

**Performance:**
- Vocab parsing cached in memory during batch processing
- Matching is fast (exact: O(1), fuzzy: O(n) but rare)
- Expected overhead: ~0.5-1 second per file (negligible)

**Future Enhancements (out of scope):**
- ML confidence scoring based on review feedback
- Context-aware semantic matching with embeddings
- Cross-unit validation (flag if term appears in other subjects)
- Automated threshold tuning based on precision/recall metrics

**Dependencies:**
- python-docx: Parse .docx vocab list files
- difflib (built-in): Fuzzy string matching

**Code Conventions:**
- Follow CLAUDE.md style guidelines
- Add timestamped comments (2026-02-24)
- Preserve existing extraction logic (no breaking changes)
- Use descriptive function/variable names
- Handle errors gracefully with logging
