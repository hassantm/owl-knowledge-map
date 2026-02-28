# Anvil Designer Rebuild — Working Reference

**Date:** 2026-02-27
**Status:** Implemented — code-first approach, Classic Anvil theme

---

## What Changed

### Problem (prior state)
The app was running on M3 Beta theme with all form code in a single `MainForm/__init__.py` mega-file. This was a workaround for Skulpt cross-form import failures caused by the M3 dependency.

### Solution
1. **Removed M3 Beta** (`4UK6WHQ6UX7AKELK`) and **Anvil Extras** (`C6ZZPAPN4YYF5NVJ`) from `anvil.yaml`
2. **Split into separate form files** — each form has its own `client_code/FormName/__init__.py`
3. **Replaced `anvil_extras.components.Chip`** with a local `_chip()` factory function (returns a styled Label)
4. **Replaced `LinearProgress`** (unavailable in Classic) with a text Label showing `N confirmed | M remaining | X%`
5. **Separate confirm handlers** in EdgeReviewForm — one method per edge_nature, no `.tag` dependency

### File Structure (after rebuild)
```
client_code/
  MainForm/__init__.py          — nav shell + cross-form imports
  DashboardForm/__init__.py     — stats + 3 Plotly charts
  BrowserForm/__init__.py       — filter bar + paginated rows
  EdgeReviewForm/__init__.py    — two-column edge confirmation
  ConceptDetailForm/__init__.py — concept trajectory timeline
  GraphForm/__init__.py         — Plotly network graph (stub)
```

---

## Skulpt Gotchas (Classic Anvil)

| Issue | Workaround |
|-------|-----------|
| `from anvil import *` does NOT export `Form` | Use `ColumnPanel` as base class |
| `self.init_components(**properties)` only works with designer templates | Use `super().__init__(**properties)` + `add_component()` |
| `{x:.2f}` format specifiers in f-strings not supported | Use `str(round(x, 2))` or `str(int(x))` |
| `spacing_above`/`spacing_below` not valid Label kwargs | Omit; use CSS or padding via role |
| `role=` in constructor only works for Button | Set `lbl.role = 'name'` post-construction for Label/ColumnPanel |
| `DropDown.value` → use `.selected_value` instead | `.selected_value` always |
| `LinearProgress` not in Classic | Use Label showing percentage text |
| `anvil_extras.components.Chip` unavailable | Use `_chip()` factory returning a styled Label |
| Cross-form imports fail with M3 Beta | Remove M3 from `anvil.yaml` |

---

## Colour Palette

| Purpose | Colour |
|---------|--------|
| Nav bar | `#1E293B` |
| Card background | `#F8FAFC` |
| Border | `#E2E8F0` |
| Text secondary | `#64748B` |
| Text muted | `#94A3B8` |
| History | `#3B82F6` (blue) |
| Geography | `#22C55E` (green) |
| Religion | `#EF4444` (red) |
| Reinforcement | `#22C55E` |
| Extension | `#3B82F6` |
| Cross-subject | `#F59E0B` (amber) |
| Within-subject edge | `#3B82F6` |
| Cross-subject edge | `#F59E0B` |

---

## Form Component Reference

### MainForm — Navigation Shell

```
ColumnPanel (root)
  ColumnPanel col_nav (background=#1e293b)
    ColumnPanel title_row
      Label  "OWL Knowledge Map"  bold, white, font_size=15
      Label  user email           foreground=#94A3B8, font_size=11
      Button "Sign out"           role=secondary-color
    ColumnPanel btn_row
      Button "Dashboard"   → _nav_to('dashboard')
      Button "Browse"      → _nav_to('browser')
      Button "Edge Review" → _nav_to('edge_review')  [reviewer only]
      Button "Graph"       → _nav_to('graph')
  ColumnPanel _content    (active form rendered here)
```

**Key method:** `_nav_to(target, **kwargs)` — clears `_content`, adds the target form.

---

### DashboardForm

```
ColumnPanel
  Label "Dashboard"  bold, font_size=20
  ColumnPanel stat_row
    ColumnPanel card × 4  (background=#F8FAFC)
      Label  value   bold, font_size=32, colour per stat
      Label  label   foreground=#64748B, font_size=12
  Plot plot1  — bar: occurrences by subject (height=300)
  Plot plot2  — horizontal bar: top 15 load-bearing concepts (height=320)
  Plot plot3  — pie/donut: within vs cross-subject edges (height=300)
  Button "Start Edge Review →"  [reviewer only]
```

**Uplink calls:** `get_dashboard_stats`, `get_load_bearing_concepts(2)`, `get_candidate_edges_list(None,None,True,0,200)`

---

### BrowserForm

```
ColumnPanel
  Label "Browse Corpus"  bold, font_size=20
  ColumnPanel filter_row
    DropDown _dd_subject   placeholder='All Subjects'
    DropDown _dd_year      placeholder='All Years'
    DropDown _dd_term      placeholder='All Terms'
    TextBox  _tb_search    placeholder='Search term...'
  ColumnPanel _results     (rows added per page)
  ColumnPanel pagination
    Button _btn_prev  "<- Prev"
    Label  _lbl_pg    "Page N | start-end of total"
    Button _btn_next  "Next ->"
```

**Uplink calls:** `get_filter_options`, `get_corpus(subject, year, term, search, page, page_size)`

**_BrowserRow:** `_chip(INTRO|recur)` + `Link(term)` → click navigates to ConceptDetailForm + location label

---

### EdgeReviewForm

```
ColumnPanel
  Label _lbl_header    "Edge Review | N/total confirmed | idx of total"
  ColumnPanel filters
    DropDown _dd_etype   All Types / Within Subject / Cross Subject
    DropDown _dd_subj    All Subjects / History / Geography / Religion
  Label _lbl_progress   "N confirmed | M remaining | X%"
  ColumnPanel _panel_review
    ColumnPanel review_cols
      ColumnPanel _left  (background=#F8FAFC)
        Label "FROM"      foreground=#64748B, font_size=11
        Label _lbl_from_term   bold, font_size=20
        Label _lbl_from_loc    foreground=#64748B
        Label _lbl_from_ch     foreground=#94A3B8, font_size=11
        Label _lbl_from_ctx    italic, foreground=#475569, font_size=12
      ColumnPanel mid
        Label "->"               bold, font_size=22
        Label _lbl_edge_badge    background=edge colour, foreground=white
      ColumnPanel _right  (background=#F8FAFC)
        Label "TO"        [mirror of FROM]
        Label _lbl_to_term / _lbl_to_loc / _lbl_to_ch / _lbl_to_ctx
    ColumnPanel decision
      TextBox _tb_reviewer  placeholder='Your name...'
      Button "Reinforcement"             background=#22C55E → btn_reinforcement_click
      Button "Extension"                 background=#3B82F6 → btn_extension_click
      Button "Cross-subject Application" background=#F59E0B → btn_cross_subject_click
      Button "Skip ->"                                      → btn_skip_click
    ColumnPanel nav
      Button _btn_prev  "<- Prev"
      Button _btn_next  "Next ->"
```

**Uplink calls:** `get_candidate_edges_list(None,None,True,0,300)`, `get_term_detail(occurrence_id)`, `confirm_edge(from_id, to_id, edge_nature, reviewer)`

**Confirm flow:** each button calls `_confirm(edge_nature)` → uplink → on success, removes edge from `_all_edges`, decrements remaining count, calls `_apply_filters()` to show next.

---

### ConceptDetailForm

```
ColumnPanel
  Button "<- Back to Browse"
  Label  concept term    bold, font_size=24
  Label  _chip(subject_area)   background=subject colour
  Label  "N occurrence(s) | Yfirst-Ylast"   foreground=#64748B
  Label  "Curriculum Timeline"  bold, font_size=16
  _OccurrenceRow × N
    ColumnPanel (background=#F8FAFC)
      _chip(INTRO|recur) + Label(year term | subject | unit) + Label(chapter)
      Label context preview (italic, max 220 chars)
  Label  "Confirmed Edges (N)"  bold, font_size=16  [if edges exist]
  _EdgeRow × N
    ColumnPanel
      Label from_loc + Label -> + Label to_loc + _chip(edge_nature)
      Label "Confirmed by X on YYYY-MM-DD"
  Label  "No confirmed edges yet..."  [if no edges]
```

**Uplink call:** `get_concept_detail(concept_id)` → returns `{concept, occurrences, edges}`

---

### GraphForm (Phase B stub)

```
ColumnPanel
  Label "Knowledge Graph"  bold, font_size=20
  ColumnPanel filters
    DropDown _dd_subject   All Subjects / History / Geography / Religion
    Label "From"
    DropDown _dd_year_from  Year 3/4/5/6  (default min)
    Label "To"
    DropDown _dd_year_to    Year 3/4/5/6  (default max)
    DropDown _dd_etype     All Edge Types / Within Subject / Cross Subject
    Button "Rebuild Graph"  (enabled only when confirmed edges > 0)
  Label _lbl_stub   "Graph will appear once edges confirmed..."   [foreground=#94A3B8]
  Plot  _plot       visible=False until confirmed edges > 0
```

**Stub logic:** `_check_and_load()` calls `get_candidate_edges_list(None,None,True,0,10)` — if any `already_confirmed`, hides stub, shows plot, enables Rebuild.

**Uplink call:** `get_graph_figure(subject, year_from, year_to, edge_type)` → returns Plotly figure dict

**Node click:** `_on_plot_click(points)` → extracts `customdata` (concept_id) → `_nav_to('concept_detail', concept_id=id)`

---

## Form Creation Order (new app build)

Create forms in this order — **MainForm must be last** because its code imports from all the others.

| # | Form name | Notes |
|---|-----------|-------|
| 1 | `DashboardForm` | |
| 2 | `BrowserForm` | |
| 3 | `EdgeReviewForm` | |
| 4 | `ConceptDetailForm` | |
| 5 | `GraphForm` | |
| 6 | `MainForm` | Rename the default `Form1` Anvil creates; this becomes the startup form automatically |

**Why this order:** `MainForm/__init__.py` contains:
```python
from DashboardForm import DashboardForm
from BrowserForm import BrowserForm
from EdgeReviewForm import EdgeReviewForm
from ConceptDetailForm import ConceptDetailForm
from GraphForm import GraphForm
```
If any of those forms don't exist when MainForm is saved, the imports fail on load.

**Practical tip:** create all six form shells first (no code), then paste code into each form in the same order (1–6). All forms exist before any code runs — safer than pasting as you go.

Code to paste for each form is in:
```
~/ai-projects/owl-anvil-app/client_code/FormName/__init__.py
```

---

## Starting the Uplink

```bash
export ANVIL_UPLINK_KEY='your-key-here'
python src/uplink.py
```

The uplink must be running for any server call to succeed. Anvil IDE → Settings → Uplink shows green "Connected" when active.

---

## Verification Checklist

1. App loads without Skulpt errors in browser console
2. Nav bar shows user email; Edge Review hidden for teacher role
3. Dashboard shows 4 stat cards + 3 charts (uplink running)
4. Browser filters work; clicking term navigates to ConceptDetailForm
5. EdgeReviewForm loads an edge pair; confirming writes to SQLite edges table
   - `SELECT COUNT(*) FROM edges;` in SQLite should show 1 after first confirm
6. ConceptDetailForm shows occurrence timeline for the concept
7. GraphForm shows stub until edges confirmed; once confirmed, plot becomes visible
8. `python src/build_graph.py` shows confirmed_edges count reflecting new edge

---

## Phase B — When to Implement GraphForm Fully

GraphForm is currently a stub. Enable full graph once:
- Meaningful edges have been confirmed via EdgeReviewForm (suggest 20+ edges)
- `get_graph_figure()` uplink function is already implemented — just needs confirmed edges to render

No code changes needed for Phase B — the stub logic in `_check_and_load()` will auto-detect confirmed edges and activate the plot.

---

## Phase C — Page Images (Future)

When ready, implement `src/render_pages.py` to render PPTX slides to PNG using `pymupdf`.
The `get_page_image()` uplink stub is already in `src/uplink.py`.
Add "View booklet page" buttons to `_OccurrenceRow` in ConceptDetailForm.
