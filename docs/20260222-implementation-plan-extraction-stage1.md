# Plan: Stage 1 PPTX Extraction Script

**Date:** 2026-02-22
**Status:** Ready for implementation

## Context

The OWL Knowledge Map database is now initialized and ready to receive data. The next step is to extract conceptual vocabulary from curriculum PowerPoint booklets. The booklets use **bold text** as pedagogical markers for formal concept introductions—these aren't incidental formatting but deliberate authorial decisions by Christine Counsell and Steve Mastin.

**Current state:**
- ✅ Database schema created (concepts, occurrences, edges tables)
- ✅ Sample PPTX available: `data/sample/Y4 Spring 2 Christianity in 3 empires Booklet.pptx` (39 slides, ~75 substantive bold terms)
- ✅ Python venv with python-pptx and networkx installed
- ⏳ No extraction logic yet

**This plan implements Stage 1:** A single-file proof of concept that extracts bold terms from the sample PPTX, applies noise filtering, tracks chapters, and prints results for human validation. No database writes yet—Stage 1 is about proving the extraction logic works correctly before adding persistence.

## Implementation Approach

### File to Create: `src/extract_stage1.py`

A single Python script with 7 functions organized into three layers:

**Layer 1: Filtering & Cleaning**
- `is_noise(text)` → Filters out "Page N" patterns and pure numeric runs (line numbers)
- `clean_term(text)` → Strips trailing punctuation
- `is_short_term(text)` → Flags terms < 5 chars for human review
- `detect_chapter(text)` → Identifies chapter headings (pattern: "1. Chapter title")

**Layer 2: Extraction**
- `extract_bold_runs(pptx_path)` → Core logic: opens PPTX, iterates slides/shapes/paragraphs/runs, captures bold terms with chapter tracking and context

**Layer 3: Output**
- `format_output(results, filename)` → Prints structured console report
- `main()` → Orchestrates execution

### Key Algorithm: `extract_bold_runs()`

```
Initialize:
  - results = {terms: [], total_slides: 0, errors: []}
  - current_chapter = None

Open PPTX with python-pptx

For each slide in presentation:
  For each shape with text_frame:
    For each paragraph:

      # Check for chapter heading (scans ALL text, not just bold)
      If paragraph matches "^\d+\.\s+":
        Update current_chapter

      # Extract bold runs
      For each run where run.font.bold == True:  # Explicit True only
        If is_noise(run.text): skip

        cleaned = clean_term(run.text)
        flagged = is_short_term(cleaned)

        Append to results:
          - term: cleaned
          - slide: slide_number
          - chapter: current_chapter (or None if pre-chapter)
          - context: full paragraph.text
          - flagged: bool

Return results
```

### Critical Implementation Details

**1. Bold Detection Precision**
- Only capture `run.font.bold == True` (explicit bold)
- Ignore `run.font.bold == None` (inherited from slide master—not an authorial decision)
- python-pptx returns `True`/`False`/`None`, each means something different

**2. Noise Filtering Rules**
Based on exploration of sample file:
- **Filter out:** "Page N" patterns (table of contents), pure numeric runs like "456" or "17." (line numbers from reading scaffolds)
- **Keep but flag:** Short words (< 5 chars) like "died", "halo", "Huns" for human review
- **Clean:** Strip trailing punctuation (.,;:!?) but preserve internal punctuation in multi-word terms

**3. Chapter State Management**
- Chapter detection happens BEFORE bold run iteration (chapter headings aren't bolded)
- `current_chapter` maintained as state variable across slides
- Initialize as `None` for terms appearing before first chapter

**4. Context Capture**
- Capture full `paragraph.text` (not just the sentence)
- Paragraphs are semantic units in booklets (typically 1-3 sentences)
- Provides context for later semantic analysis (e.g., "empire" used differently in Roman vs. Islamic context)

### Output Format

Three-section console report:

```
=== EXTRACTION REPORT ===
File: Y4 Spring 2 Christianity in 3 empires Booklet.pptx
Slides processed: 39
Terms extracted: 75
Flagged for review: 12

=== EXTRACTED TERMS ===
Slide 3 | Chapter 1: To the lions! Christians in the Roman Empire
  - "official religion"
    Context: ...made Christianity the official religion of the empire...
  - "persecuted"
    Context: Christians were persecuted by Roman emperors...

Slide 4 | Chapter 1: To the lions! Christians in the Roman Empire
  [FLAGGED: SHORT] "died"
    Context: ...they died for their faith...

=== FLAGGED TERMS (for review) ===
1. "died" (4 chars) - Slide 4
2. "rose" (4 chars) - Slide 7
...
```

## Critical Files

**To create:**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/extract_stage1.py` - Complete extraction script (~250 lines)

**References (existing files):**
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/data/sample/Y4 Spring 2 Christianity in 3 empires Booklet.pptx` - Input file (39 slides)
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py` - Shows database schema for future Stage 2 integration
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/CLAUDE.md` - Defines bold term philosophy, noise filters, extraction stages
- `/Users/hassanmamdani/ai-projects/owl-knowledge-map/requirements.txt` - Confirms python-pptx available

## Verification & Testing

### Step 1: Run Script
```bash
cd /Users/hassanmamdani/ai-projects/owl-knowledge-map
python3 src/extract_stage1.py
```

**Expected output:**
- Summary showing ~75 terms extracted from 39 slides
- Terms grouped by slide and chapter
- 10-15 short terms flagged for review
- No errors (or only minor shape-related warnings)

### Step 2: Count Validation
```bash
python3 src/extract_stage1.py > /tmp/extraction_output.txt
grep '  - "' /tmp/extraction_output.txt | wc -l
```
**Expected:** ~75 lines (one per term)

### Step 3: Spot Check Known Terms
Based on "Christianity in 3 empires" topic, verify these appear:
```bash
grep -i "Constantine" /tmp/extraction_output.txt
grep -i "martyr" /tmp/extraction_output.txt
grep -i "official religion" /tmp/extraction_output.txt
```
**Expected:** Each term found with context

### Step 4: Noise Filter Validation
```bash
grep -E '"Page [0-9]+"' /tmp/extraction_output.txt  # Should be empty
grep -E '"[0-9]+\.?"' /tmp/extraction_output.txt     # Should be empty
```
**Expected:** No results (noise successfully filtered)

### Step 5: Chapter Tracking Validation
```bash
grep "Slide .* | [0-9]\." /tmp/extraction_output.txt
```
**Expected:** Multiple chapter headers like "Slide 3 | 1. To the lions! Christians in the Roman Empire"

### Verification Checklist
- [ ] Script runs without crashes
- [ ] Total terms extracted: ~75 (±10)
- [ ] Known terms present ("Constantine", "martyr", "official religion", "Byzantine")
- [ ] No "Page N" or pure numeric patterns in extracted terms
- [ ] Chapters correctly identified and tracked across slides
- [ ] Short terms flagged but still extracted
- [ ] Context captured for each term (paragraph text)
- [ ] Output is human-readable and scannable

## Extension Path to Stage 2

**What Stage 2 will add** (not implemented yet):
1. Filename metadata parsing (extract Year, Subject, Term, Unit from path)
2. Database writes (insert into concepts and occurrences tables)
3. CSV export for human review

**Key design advantage:** Stage 1 functions remain unchanged in Stage 2. The extraction layer (`extract_bold_runs()`, `is_noise()`, etc.) becomes reusable infrastructure. Stage 2 simply adds a persistence layer that consumes the extraction results.

All filtering and extraction logic is validated in Stage 1 before introducing database complexity.

## Implementation Notes

**Philosophy:** Keep Stage 1 observable and simple. Console output must be detailed enough to validate extraction quality by reading it. No silent failures—if something goes wrong, we want to see it.

**Testing focus:** Human verification. The output format is designed for a curriculum expert (potentially Christine Counsell or Steve Mastin) to scan and confirm we're capturing the right terms with appropriate context.

**Code style:** Follow CLAUDE.md conventions—clean Python, standard conventions, concise comments with timestamps when modified.
