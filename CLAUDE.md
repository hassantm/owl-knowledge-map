# OWL Knowledge Map — Project Context

## Overview

This project analyses the Opening Worlds Ltd (OWL) Key Stage 2 humanities curriculum — a knowledge-based curriculum covering History, Geography and Religion for Years 3–6 (primary). The curriculum was authored by Christine Counsell and Steve Mastin, both prominent figures in knowledge-based curriculum theory (influenced heavily by E.D. Hirsch).

The goal is to extract the conceptual vocabulary deliberately embedded in the curriculum booklets, build a structured database of those concepts and their locations, and ultimately construct a directed knowledge graph showing how concepts are introduced, reinforced and built upon across subjects and years. This makes visible to teachers the curricular architecture that currently exists only in the authors' heads.

---

## Source Material

- **Format**: PowerPoint (.pptx) booklets, one per unit
- **Location**: Dropbox, mirrored locally
- **Structure**: `/{Subject}/{Year} {Subject} {Term} {Unit}/Booklet/filename.pptx`
- **Example path**: `Year 4 Hist/Y4 Hist Spring 2 Christianity in 3 empires/Y4 Hist Spring 2 Booklet.pptx`
- **Subjects**: History, Geography, Religion
- **Years**: 3, 4, 5, 6
- **Terms**: Autumn 1, Autumn 2, Spring 1, Spring 2, Summer 1, Summer 2

The folder naming convention is consistent and encodes Subject, Year and Term directly — the file path is the primary source of metadata.

Each unit folder also contains a Vocab List subfolder with a pre-curated vocabulary list. These can be used for validation against the automated bold-text extraction.

---

## Key Design Decisions

### Bold Terms as Concept Markers
In the OWL curriculum, words and phrases printed in **bold** within the booklet text represent concepts being formally introduced. They are deliberate pedagogical markers, not incidental formatting. Once introduced, these concepts recur in later units without being re-bolded — they are assumed knowledge being applied and extended.

### Terms Are Stored Exactly As Authored
No normalisation or stemming. "culture" and "cultures" are separate entries if both appear in bold, because that reflects an authorial decision. The integrity of Counsell and Mastin's vocabulary choices is preserved exactly.

### Multi-Word Phrases
Bold formatting is applied to multi-word phrases as single runs (e.g. "official religion", "three wise men", "rose from the dead"). These are captured as single concept terms, not split at word boundaries.

### Human-Confirmed Edges
Connections between occurrences (edges in the graph) are not generated automatically. A human reviewer confirms each edge and assigns an edge_nature value. This preserves scholarly judgement about whether a recurrence represents simple reinforcement or genuine conceptual extension.

---

## Database Schema (SQLite)

### Table: `concepts`
The abstract vocabulary item, independent of location.

```sql
CREATE TABLE concepts (
    concept_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    term            TEXT NOT NULL,
    subject_area    TEXT
);
```

### Table: `occurrences`
A specific instance of a concept at a location in the curriculum.

```sql
CREATE TABLE occurrences (
    occurrence_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id      INTEGER REFERENCES concepts(concept_id),
    subject         TEXT NOT NULL,      -- 'History', 'Geography', 'Religion'
    year            INTEGER NOT NULL,   -- 3, 4, 5, or 6
    term            TEXT NOT NULL,      -- 'Autumn1', 'Autumn2', 'Spring1', 'Spring2', 'Summer1', 'Summer2'
    unit            TEXT NOT NULL,      -- e.g. 'Christianity in 3 empires'
    chapter         TEXT,               -- Chapter title parsed from slide heading
    slide_number    INTEGER,
    is_introduction BOOLEAN NOT NULL,   -- TRUE if bold (formal introduction), FALSE if recurrence
    term_in_context TEXT,               -- Full paragraph text surrounding the term
    source_path     TEXT                -- Full file path to source PPTX
);
```

### Table: `edges`
Directed relationships between occurrences of the same concept.

```sql
CREATE TABLE edges (
    edge_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    from_occurrence     INTEGER REFERENCES occurrences(occurrence_id),
    to_occurrence       INTEGER REFERENCES occurrences(occurrence_id),
    edge_type           TEXT,   -- 'within_subject' or 'cross_subject'
    edge_nature         TEXT,   -- 'reinforcement', 'extension', or 'cross_subject_application'
    confirmed_by        TEXT,   -- Name of human reviewer
    confirmed_date      TEXT    -- ISO date string YYYY-MM-DD
);
```

---

## Extraction Script Design

### Core Libraries
- `python-pptx` — PPTX parsing and bold run detection
- `pathlib` — folder tree traversal
- `sqlite3` — database writes
- `re` — path parsing and term cleaning

### Execution Flow

**Stage 1 — Single file proof of concept**
- Open one PPTX
- Loop: slides → shapes → text frames → paragraphs → runs
- Capture runs where `run.font.bold == True`
- Print term and slide number to console
- Validate against known content

**Stage 2 — Metadata from file path**
- Parse folder name: `Y4 Hist Spring 2 Christianity in 3 empires`
- Extract: Year=4, Subject=History, Term=Spring2, Unit=Christianity in 3 empires
- Handle subject abbreviations: Hist→History, Geog→Geography, Relig→Religion

**Stage 3 — Chapter detection**
- Chapter headings follow the pattern: `"1. Chapter title"`, `"2. Chapter title"` etc.
- Detect by slide text matching `^\d+\.\s+` 
- Track current chapter as state variable while iterating slides

**Stage 4 — Noise filtering**
- Discard purely numeric runs (line numbers for reading scaffolding)
- Discard "Page N" patterns (table of contents entries)
- Strip trailing punctuation from terms (`.`, `,`, `?`)
- Flag short common words (len < 5 or on a stopword-adjacent list) for human review

**Stage 5 — Context capture**
- For each bold term, capture the full paragraph text as `term_in_context`
- This preserves the semantic context for later analysis (e.g. "sacked" in the context of Rome being attacked, not employment)

**Stage 6 — Scale to corpus**
- Walk the full folder tree using `pathlib.Path.rglob`
- Target files matching `*Booklet*.pptx` (excluding Powerpoints, Print resources etc.)
- Accumulate all results, write to SQLite

**Stage 7 — Output**
- Write to SQLite database using the schema above
- Also write a CSV export for human review of extracted terms
- Flag terms for review in a separate `review_queue` table or column

### Important Notes on PPTX Bold Detection
- Bold is stored as `<a:rPr b="1">` in DrawingML XML
- python-pptx exposes this as `run.font.bold`
- Bold can be inherited from paragraph or slide master — `run.font.bold` returns `None` if inherited rather than explicit. Treat `None` as not-bold; only capture `True`
- A single paragraph may contain multiple bold runs (e.g. "Goths", "Huns", "Visigoths" in the same paragraph) — each is captured separately

---

## Phase 2 — Knowledge Graph

### Tools
- **NetworkX** — graph construction, traversal and analysis (user is familiar)
- **SQLite** — source of truth for nodes and edges
- Visualisation tool TBD

### Graph Structure
- **Concept nodes** — abstract term (parent)
- **Occurrence nodes** — specific location instance (child), with metadata: subject, year, term, unit
- **Directed edges** — from earlier to later occurrence, human-confirmed
- **Edge attributes** — edge_type (within/cross subject), edge_nature (reinforcement/extension/cross_subject_application)

### Key Analytical Questions the Graph Should Answer
1. Which concepts are load-bearing — appearing most frequently across years and subjects?
2. Where do cross-subject connections occur?
3. What is the conceptual trajectory of a specific term across the curriculum?
4. Are there gaps — concepts introduced but never revisited?
5. Where does context shift occur — same term doing more sophisticated conceptual work in later years?

---

## Planned Application Stack

The project is built in four layers, all primarily Python:

**1. SQLite** — canonical data store, lives locally alongside the project. Source of truth for all extracted data, confirmed edges and review state. Never replaced or migrated — all other layers read from and write to it.

**2. Python scripts** — extraction pipeline, database writes, NetworkX graph analysis. All local, all in this project directory.

**3. Anvil Uplink** — a persistent Python process running locally that connects the SQLite database to the Anvil web app. The uplink was designed exactly for this pattern: exposing a local data source to a web front end without moving the data or changing the back end. This is the bridge layer — it should not contain business logic, only data access functions.

**4. Anvil web app** — front end for human review workflow and teacher-facing visualisation. Built entirely in Python using the Anvil framework. Anvil DataTables are NOT used as the database — SQLite via the uplink is the data store. Anvil is purely the UI layer.

### Why This Stack
- Keeps SQLite as the single source of truth — no data duplication or sync problems
- Entirely Python throughout — consistent with the project owner's skills
- Anvil uplink was purpose-built for local database access from a web app
- Separates concerns cleanly: extraction, storage, access, presentation

### Anvil Review Interface — Intended Functionality
The human review workflow is central to the project's scholarly integrity. The Anvil app should support:
- Browsing extracted concepts and occurrences by subject, year and term
- Presenting candidate concept matches across the corpus for edge confirmation
- Displaying term_in_context for both the from_occurrence and to_occurrence side by side
- Allowing the reviewer to confirm an edge, assign edge_type and edge_nature, and record their name and date
- A review queue showing unconfirmed candidate connections
- Flagged terms awaiting noise review (short words, ambiguous terms)

This interface is particularly important if Christine Counsell or Steve Mastin are involved in reviewing connections — it needs to be usable by curriculum experts, not just technical users.

---

## Future Phases

### Context Analysis
The `term_in_context` field is captured from the start to enable later semantic analysis:
- Sentence embeddings to measure context shift between introduction and recurrence
- Conceptual neighbourhood analysis (what other bold terms cluster around a term at each occurrence)
- The "empire" example illustrates why this matters: introduced as territory and power, enriched by the concept of an emperor in the Roman/Byzantine context, then deliberately complicated by the Islamic empire which is recognisably an empire but held together by something other than an emperor. That context shift is the most sophisticated pedagogical move in the curriculum and the graph should be able to surface it.

### Phase 3 — Teacher-Facing Visualisation
The Anvil app, once the review workflow is complete, can be extended to present the knowledge graph in a form accessible to teachers:
- Visual map of concept trajectories across years and subjects
- Ability to explore a single concept and trace its journey through the curriculum
- Cross-subject connection highlighting
- Potentially a publishable tool that Opening Worlds could offer alongside the booklets

### Phase 4 — Learning Resources
Development of animated story resources or condensed text summaries derived from the booklets. Requires curriculum expertise in the loop and is dependent on completing the knowledge graph phases first.

---

## Page Retrieval Layer (Future Consideration)

### The Idea
Alongside the knowledge graph, there is value in building a document retrieval layer that stores each booklet page as a retrievable unit, tagged with the same location metadata as the occurrences table (subject, year, term, unit, chapter, page/slide number). This would allow a teacher browsing the visualisation to click on any concept occurrence and see the actual booklet page — layout, images, surrounding narrative — not just the extracted text snippet.

This transforms the tool from a structural map into something closer to a navigable curriculum. The difference between reading "empire is introduced on page 7 of Y4 Spring 2" and actually seeing that page in its original visual context is significant for a teacher trying to understand authorial intent.

### Why Not SQLite
SQLite is not the right store for this layer. The booklets are image-heavy (68MB+ even compressed). Storing binary content at scale degrades SQLite performance and makes the database unwieldy. The pattern established for source PPTX files applies here too — the database holds metadata and paths, not the binary content itself.

### Two Storage Approaches

**Option A — Rendered page images**
Split each PDF into per-page PNG or JPEG files at extraction time using `pymupdf` (also called `fitz`). Store images in a predictable folder structure mirroring the existing Dropbox hierarchy. The database holds the file path and location metadata. Simple, fast to implement, works well with Anvil's image display capabilities.

**Option B — Extracted page text with full-text search**
Use `pymupdf` to extract text from each PDF page with positional data. Store in a document store such as Elasticsearch or PostgreSQL full-text search. Enables keyword search across the full corpus — not just bold terms but any word on any page across all subjects and years. More powerful but significantly more infrastructure.

### Recommended Path
Option A first — rendered page images with path references in the database. This is buildable without additional infrastructure and delivers immediate value in the Anvil visualisation. Option B is an upgrade path if full-text search across the corpus becomes a requirement.

### Key Library
**pymupdf** (`fitz`) is the best Python library for PDF work. Handles text extraction, page rendering and image export. Would do the heavy lifting for either option. Install via `pip install pymupdf`.

### Architectural Position
This is an enrichment layer on top of the core knowledge graph, not part of it. The location metadata already captured in the occurrences table (subject, year, term, unit, chapter, slide_number) is the join key between the graph and the page store. No schema changes are needed — the retrieval layer is additive.

In the Anvil app, the uplink process would handle page retrieval alongside SQLite queries, fetching the relevant image from its stored location and passing it to the front end when a teacher drills into a specific occurrence node.

### When to Build
Not during the extraction and graph phases — but design for it by ensuring location metadata in the occurrences table is precise enough to uniquely identify a page. That is already the case. Revisit when building the teacher-facing Anvil visualisation.

---

## Project Owner
Hassan Mamdani, COO/CFO, Opening Worlds Ltd  
This is an internal professional project to make the curriculum's knowledge architecture visible to teachers.

## Curriculum Authors
Christine Counsell and Steve Mastin, Opening Worlds Ltd  
© 2021 Christine Counsell and Steve Mastin
