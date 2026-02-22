# Plan: Create Database Initialization Script

**Status:** ✓ Completed 2026-02-22

## Context

Creating the foundational database for the OWL Knowledge Map project. The database will store extracted concepts from curriculum booklets, their occurrences across years/subjects, and human-confirmed relationships between them.

Project currently has:
- CLAUDE.md specification with full schema
- Python venv with networkx and python-pptx
- Sample PPTX file: `src/sample/Y4 Spring 2 Christianity in 3 empires Booklet.pptx`
- No database or scripts yet

## Implementation Plan

### File 1: `src/init_db.py`

**Location:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py`

**Purpose:** Create SQLite database with schema for concepts, occurrences, and edges

**Implementation:**

1. Import `sqlite3` and `pathlib`
2. Define database path as `db/owl_knowledge_map.db` (relative to project root)
3. Create `db/` directory if it doesn't exist using `pathlib.Path.mkdir(parents=True, exist_ok=True)`
3. Create connection and cursor
4. Execute CREATE TABLE statements for:
   - **concepts** table: concept_id (PK), term, subject_area
   - **occurrences** table: occurrence_id (PK), concept_id (FK), subject, year, term, unit, chapter, slide_number, is_introduction, term_in_context, source_path
   - **edges** table: edge_id (PK), from_occurrence (FK), to_occurrence (FK), edge_type, edge_nature, confirmed_by, confirmed_date
5. Add indexes on:
   - occurrences.concept_id (for lookups by concept)
   - occurrences.is_introduction (for filtering introductions vs recurrences)
   - edges.from_occurrence and edges.to_occurrence (for graph traversal)
6. Commit and close connection
7. Print confirmation message with database location

**Features:**
- Check if database already exists - warn user but allow overwrite with confirmation
- Use multi-line strings for CREATE TABLE statements (readability)
- Include schema comment header with date and reference to CLAUDE.md
- Make script executable directly: `if __name__ == "__main__":`

**Schema Notes:**
- BOOLEAN in SQLite stored as INTEGER (0/1)
- TEXT fields for subjects use full names: 'History', 'Geography', 'Religion'
- Term format: 'Autumn1', 'Autumn2', 'Spring1', 'Spring2', 'Summer1', 'Summer2'
- No normalization of terms - stored exactly as authored

### File 2: `.gitignore` (update existing)

**Location:** `/Users/hassanmamdani/ai-projects/owl-knowledge-map/.gitignore`

**Purpose:** Add database files, IDE files, and OS files to existing .gitignore

**Changes:** Append to existing file:
```
# Database files
db/
*.db
*.db-journal
*.sqlite
*.sqlite3

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS files
.DS_Store
Thumbs.db

# Jupyter
.ipynb_checkpoints/

# Logs
*.log

# Test outputs
test_output/
temp/
```

**Note:** Existing .gitignore already has venv and Python cache entries

## Critical Files

- Create: `/Users/hassanmamdani/ai-projects/owl-knowledge-map/src/init_db.py`
- Update: `/Users/hassanmamdani/ai-projects/owl-knowledge-map/.gitignore`
- Reference: `/Users/hassanmamdani/ai-projects/owl-knowledge-map/CLAUDE.md` (schema source)

## Verification

After implementation:
1. Run `python src/init_db.py` from project root (or `python init_db.py` from src/)
2. Verify `db/` directory created
3. Verify `db/owl_knowledge_map.db` exists
4. Use SQLite CLI to verify schema:
   ```bash
   sqlite3 db/owl_knowledge_map.db ".schema"
   ```
5. Confirm all three tables exist with correct columns
6. Verify indexes created
7. Confirm `.gitignore` excludes `db/` directory (test with `git status`)

## Implementation Results

✓ Script executes successfully: `python3 src/init_db.py`
✓ Database created at: `db/owl_knowledge_map.db`
✓ All 3 tables created with correct schema
✓ All 4 indexes created (concept_id, is_introduction, from_occurrence, to_occurrence)
✓ Database accepts inserts and queries correctly
✓ `.gitignore` working — db/ directory excluded from git tracking

## Next Steps (Post-Implementation)

After init_db.py is working:
- Create extraction script (stage 1: single file proof of concept)
- Test extraction on sample PPTX
- Build out remaining extraction stages
