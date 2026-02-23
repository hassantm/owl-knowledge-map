# Batch Processing Guide

Created: 2026-02-23

## Overview

The batch processing script (`src/batch_process.py`) enables extraction and database persistence for multiple booklet files across the curriculum corpus. It includes filtering, resume capability, and error resilience.

## Usage

### Basic Command Structure

```bash
cd /Users/hassanmamdani/ai-projects/owl-knowledge-map
source venv/bin/activate
cd src

# Set Dropbox root for convenience
DROPBOX_ROOT="/Users/hassanmamdani/Library/CloudStorage/Dropbox/Haringey Counsell Shared Items"

python3 batch_process.py <root_dir> [options]
```

### Common Operations

#### Dry Run (discover files without processing)
```bash
# Year 4 History
python3 batch_process.py "$DROPBOX_ROOT/HEP History" --year 4 --dry-run

# All History
python3 batch_process.py "$DROPBOX_ROOT/HEP History" --dry-run

# All Geography
python3 batch_process.py "$DROPBOX_ROOT/HEP Geography" --dry-run
```

#### Process Files
```bash
# Year 4 History only
python3 batch_process.py "$DROPBOX_ROOT/HEP History" --year 4

# All History (Years 3-6)
python3 batch_process.py "$DROPBOX_ROOT/HEP History"

# All Geography
python3 batch_process.py "$DROPBOX_ROOT/HEP Geography"

# All Religion
python3 batch_process.py "$DROPBOX_ROOT/HEP Religion"
```

#### Resume After Interruption
```bash
# Skip files already in database
python3 batch_process.py "$DROPBOX_ROOT/HEP History" --year 4 --resume
```

### Command-Line Options

- `--db PATH` - Database path (default: `../db/owl_knowledge_map.db`)
- `--output PATH` - CSV output directory (default: `../output`)
- `--subject {History,Geography,Religion}` - Filter by subject
- `--year {3,4,5,6}` - Filter by year
- `--dry-run` - Discover files without processing
- `--resume` - Skip files already in database

## Implementation Summary

### What Was Built

1. **Enhanced Metadata Parsing** (`extract_stage2.py`)
   - Handles full corpus directory structure: `.../Y4 Hist Autumn 1 Unit/Y4 Autumn 1 Unit Booklet/file.pptx`
   - Falls back to sample file pattern for compatibility
   - New `expand_subject_abbreviation()` helper function

2. **Batch Processing Script** (`batch_process.py`)
   - File discovery using `rglob('**/*Booklet/*.pptx')`
   - Subject and year filtering
   - Resume capability (queries database for processed files)
   - Error resilience (individual failures don't stop batch)
   - Comprehensive reporting

### Verification Results

**Test: Year 4 History (5 booklets)**
- Files discovered: 5
- Files processed: 5
- Files failed: 0
- Success rate: 100%
- Total concepts created: 247
- Total occurrences created: 342

**Database verification:**
```sql
-- 331 total concepts (includes sample file)
SELECT COUNT(*) FROM concepts;

-- 428 total occurrences
SELECT COUNT(*) FROM occurrences;

-- 5 Year 4 units covered
SELECT DISTINCT term, unit FROM occurrences WHERE year = 4;
```

**Corpus coverage:**
- Year 3 History: 6 booklets
- Year 4 History: 5 booklets
- Year 5 History: 5 booklets
- Year 6 History: 4 booklets
- Total: 20 History booklets discovered

## Next Steps

### Immediate Options

1. **Process Full History Corpus** (~20 files)
   ```bash
   python3 batch_process.py "$DROPBOX_ROOT/HEP History"
   ```

2. **Process Geography and Religion** (~20 files each)
   ```bash
   python3 batch_process.py "$DROPBOX_ROOT/HEP Geography"
   python3 batch_process.py "$DROPBOX_ROOT/HEP Religion"
   ```

3. **Full Corpus Processing** (~60 files total)
   Process all three subjects sequentially

### Future Enhancements (Not Yet Implemented)

- Parallel processing with `multiprocessing.Pool`
- Progress bar with `tqdm` library
- HTML report generation
- Validation against Vocab List CSVs

## Error Handling

The batch processor:
- Wraps each file in try/except
- Accumulates errors without stopping batch
- Reports errors in final summary
- Enables investigation of failed files

## Resume Capability

Resume mode (`--resume`) queries the database for already-processed files:
```sql
SELECT DISTINCT source_path FROM occurrences;
```

Files whose absolute path matches are skipped, enabling:
- Recovery after interruption
- Incremental corpus updates
- Re-running batch operations safely

## Architecture

- **Single-file processing**: Handled by `extract_stage2.process_file()`
- **Batch orchestration**: New `batch_process.py` script
- **Separation of concerns**: Stage 2 functions reused without modification
- **Per-file commits**: Natural transaction boundaries, enables resume
- **Individual CSV exports**: Preserves human review workflow
