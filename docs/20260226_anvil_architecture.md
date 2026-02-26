# Anvil Front-End Architecture — OWL Knowledge Map
**Date:** 2026-02-26
**Status:** Approved for implementation
**Context:** 3,442 occurrences, 3,153 concepts in SQLite. Extraction pipeline complete. Audit CSV ready for human review.

---

## Overview

Three implementation phases, each building on the previous:

| Phase | Name | Trigger |
|-------|------|---------|
| A | Audit Review Interface | Now — replaces CSV workflow |
| B | Graph Visualisation | After edges confirmed |
| C | Page View | After graph stable |

---

## Architecture

```
SQLite (local)  ←→  Uplink Process (local Python)  ←→  Anvil Web App (cloud)
                              │
                        File system (PNG pages, Phase C)
```

**Rules:**
- Anvil Server Modules are thin — they proxy calls to the uplink only
- All business logic (SQL, graph construction, image loading) lives in the uplink process
- Anvil DataTables are NOT used — SQLite is the single source of truth throughout
- Uplink script: `src/uplink.py` — must be running locally for the web app to function

---

## Database Changes (added 2026-02-26)

Two new columns added to `occurrences` via migration script `src/migrate_add_audit_columns.py`:

```sql
ALTER TABLE occurrences ADD COLUMN audit_decision TEXT;
-- Values: 'keep', 'delete', 'add', 'skip', NULL (unreviewed)

ALTER TABLE occurrences ADD COLUMN audit_notes TEXT;
-- Optional reviewer notes
```

These store decisions in-DB instead of in the CSV, making the Anvil app the authoritative review interface. The existing CSV workflow (`apply_audit_decisions.py`) remains as a fallback.

---

## Phase A — Audit Review Interface

### Purpose
Replace the `term_audit_enriched.csv` workflow with a usable web interface. 737 rows require decisions. Christine Counsell or Steve Mastin may be involved — the UI must be usable by curriculum experts, not just technical users.

### Anvil App Structure

```
MainForm
├── Sidebar navigation: Queue | Stats | Graph (stub)
├── AuditQueueForm   — issue list with filters
└── TermDetailForm   — single-term decision view
```

**AuditQueueForm**
- Filter bar: Subject | Year | Term | Issue Type
- Stats header: total issues | reviewed | pending
- Repeating Panel rows showing: issue type badge, term (bold), Subject/Year/Unit/Slide, decision dropdown, "Detail →" button

**TermDetailForm**
- Term displayed prominently (large, bold)
- `term_in_context` — full paragraph text
- For `missed_from_extraction`: `unbolded_context` alongside
- For `potential_noise` / `high_priority_review`: vocab source info
- Decision controls: DropDown (keep/delete/add/skip) + optional notes TextBox + Save button
- ← Previous | Next → navigation

### Uplink Functions (Phase A)

```python
@anvil.server.callable
def get_audit_queue(subject=None, year=None, term=None, issue_type=None, page=0, page_size=50):
    """
    Returns paginated list of dicts for review queue.
    Queries occurrences JOIN concepts WHERE needs_review=1
    OR validation_status IN ('potential_noise', 'high_priority_review').
    Filters as SQL WHERE clauses. Includes audit_decision so reviewed rows
    can be shown differently.
    """

@anvil.server.callable
def get_audit_stats():
    """
    Returns dict: total_issues, reviewed, pending, by_issue_type counts.
    """

@anvil.server.callable
def get_term_detail(occurrence_id):
    """
    Returns full occurrence record + concept term + vocab fields.
    """

@anvil.server.callable
def save_audit_decision(occurrence_id, decision, notes=None):
    """
    Writes audit_decision and audit_notes to occurrences table.
    No CSV intermediary — DB is the record.
    """

@anvil.server.callable
def apply_pending_decisions():
    """
    Executes the apply-decisions logic against DB-stored decisions.
    Returns summary counts dict: deleted, confirmed, added, skipped, errors.
    """
```

### Decision Logic in apply_pending_decisions

| `audit_decision` | `issue_type` | Action |
|------------------|-------------|--------|
| `keep` | noise / hp | SET `validation_status = 'confirmed'` |
| `delete` | noise / hp | DELETE occurrence; clean orphan concepts |
| `add` | missed | INSERT new occurrence (`is_introduction=0`, `vocab_match_type='manual_add'`) |
| `skip` | any | no action |

---

## Phase B — Graph Visualisation

### Trigger
After Phase A decisions applied and edges are being confirmed. The `edges` table is currently empty.

### Anvil App Additions

```
MainForm
├── GraphForm       — interactive network diagram
└── ConceptDetailForm — single concept trajectory
```

**GraphForm**
- Plotly network graph (Plot component)
  - Nodes sized by occurrence count; coloured by subject (History=blue, Geography=green, Religion=red)
  - Directed edges (confirmed only)
  - Hover: term, year, subject, unit
  - Click: opens ConceptDetailForm
- Filter panel: Subject | Year range | Edge type
- "Rebuild graph" button

**ConceptDetailForm**
- Concept term + subject_area
- Occurrence timeline (Plotly or table), sorted by year/term
- Each row: unit | chapter | slide | context | is_introduction badge
- Edge list with edge_nature
- "View Page" button → Phase C

### Uplink Functions (Phase B)

```python
@anvil.server.callable
def get_graph_figure(subject=None, year_from=None, year_to=None, edge_type=None):
    """
    Queries concepts + occurrences + edges from SQLite.
    Builds nx.DiGraph. Applies kamada_kawai_layout.
    Converts to Plotly JSON figure dict.
    Returns dict for Anvil Plot component.
    """

@anvil.server.callable
def get_concept_detail(concept_id):
    """
    Returns concept + all occurrences + all edges involving those occurrences.
    """
```

### NetworkX → Plotly Pattern

```python
import networkx as nx, plotly.graph_objects as go

G = nx.DiGraph()
# add nodes (concepts) and edges
pos = nx.kamada_kawai_layout(G)

edge_x, edge_y = [], []
for u, v in G.edges():
    x0, y0 = pos[u]; x1, y1 = pos[v]
    edge_x += [x0, x1, None]; edge_y += [y0, y1, None]

edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines',
                        line=dict(width=1, color='#888'))
node_trace = go.Scatter(x=node_x, y=node_y, mode='markers+text',
                        marker=dict(size=node_sizes, color=node_colours))
fig = go.Figure(data=[edge_trace, node_trace])
```

---

## Phase C — Page View

### Purpose
Show the actual booklet page when a reviewer or teacher drills into an occurrence — layout, images, surrounding narrative.

### Implementation (Option A — rendered PNG images)

**One-off build script `src/render_pages.py`:**
```
For each booklet PDF in Dropbox:
  1. Open with fitz.open(pdf_path)
  2. For each page: page.get_pixmap(dpi=150).save(png_path)
  3. Store: output/pages/{subject}/{year}_{term}_{unit}/page_{n}.png
  4. Insert png_path into occurrences.page_image_path (new column, added when ready)
```

**PDFs exist in Dropbox** — no LibreOffice conversion needed. `pymupdf` (`fitz`) handles rendering directly.

**Uplink function:**
```python
@anvil.server.callable
def get_page_image(occurrence_id):
    """
    Look up page_image_path from occurrences table.
    Return anvil.media.from_file(path, 'image/png').
    """
```

**Anvil display:**
```python
page_img = anvil.server.call('get_page_image', self.occurrence_id)
self.image_component.source = page_img
```

### Note
Phase C is additive — no schema changes to existing tables, only a new `page_image_path` column added to `occurrences`. The location metadata already in the DB (subject, year, term, unit, slide_number) is the join key between the graph and the page store.

---

## Files Created / Modified

| File | Action | Phase |
|------|---------|-------|
| `src/uplink.py` | **Create** | A, B stubs |
| `src/migrate_add_audit_columns.py` | **Create** | A |
| `src/render_pages.py` | **Create** | C |
| `src/init_db.py` | **Modify** | A — add new columns to schema |
| Anvil web app | **Create in Anvil IDE** | A, B, C |

---

## Build Sequence

1. Run `src/migrate_add_audit_columns.py` — adds `audit_decision`, `audit_notes` to live DB
2. Run `src/uplink.py` — confirm uplink connects (Anvil shows "connected")
3. In Anvil IDE: create MainForm + AuditQueueForm + TermDetailForm
4. Test end-to-end: reviewer uses UI, decisions write to DB, `apply_pending_decisions()` runs
5. Add Phase B graph functions to uplink once edges exist
6. In Anvil IDE: add GraphForm + ConceptDetailForm
7. Build `render_pages.py` and Phase C once graph is stable

---

## Verification Checklist

**Phase A:**
- [ ] `python src/uplink.py` → uplink connects
- [ ] `get_audit_queue()` → 737 rows returned
- [ ] Test decision saved in UI → `occurrences.audit_decision` updated in SQLite
- [ ] `apply_pending_decisions()` → counts match expected

**Phase B:**
- [ ] Click concept node → `get_concept_detail()` returns correct data
- [ ] Graph renders with correct node colours and edge directions

**Phase C:**
- [ ] Click "View Page" → PNG loads correctly in Image component

---

## Anvil Access Control

Anvil cloud hosting makes apps publicly accessible by default. Restrict access via Anvil's built-in user management before sharing with Christine Counsell or Steve Mastin. Determine reviewer list before deploying.
