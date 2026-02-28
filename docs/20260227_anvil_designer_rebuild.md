# Anvil Designer Rebuild — Working Reference

**Date:** 2026-02-27 (updated 2026-02-28)
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
  DashboardForm/__init__.py     — stats + 4 Plotly charts
  BrowserForm/__init__.py       — filter bar + paginated rows
  EdgeReviewForm/__init__.py    — two-column edge confirmation
  ConceptDetailForm/__init__.py — concept trajectory timeline
  GraphForm/__init__.py         — Plotly network graph (stub)
```

---

## How to Read This Reference

This is a **code-first** app — there is no Anvil designer layout to drag-and-drop. All components are added in Python using `add_component()`. The reference below describes:

- **Component type** — the Anvil class (e.g. `Label`, `Button`, `ColumnPanel`, `Plot`)
- **Variable name** — what to call it in Python (e.g. `card`, `lbl_value`, `plot1`). Names prefixed with `self.` are stored on the form instance so they can be referenced later; others are local variables only used during construction.
- **text=** — the string that appears on screen. "Fixed" means it is set once in the constructor and never changes. "Programmatic" means it is set (or overwritten) during `_load()` from uplink data.
- **Style** — foreground colour, font_size, bold, background — set in the constructor call.

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
| Indigo (edge count) | `#6366F1` |

---

## Form Component Reference

### MainForm — Navigation Shell

**Overview:** The root form. Always visible. Contains the nav bar at the top and a content panel below where other forms are rendered. The startup form (rename Anvil's default `Form1` to `MainForm`).

**Uplink calls:** None directly. Navigation is handled via `_nav_to()`.

**Key method:** `_nav_to(target, **kwargs)` — clears `self._content`, instantiates the target form, adds it.

#### Component tree

```
self (ColumnPanel — root, inherits from ColumnPanel not Form)
  self._nav (ColumnPanel, background='#1E293B')
    title_row (ColumnPanel — inner row for title + email + sign-out)
      lbl_title  (Label)
      lbl_user   (Label)
      btn_signout (Button)
    btn_row (ColumnPanel — inner row for nav buttons)
      btn_dashboard   (Button)
      btn_browse      (Button)
      btn_edge_review (Button)   ← hidden unless user role = 'reviewer'
      btn_graph       (Button)
  self._content (ColumnPanel — forms rendered here)
```

#### Component detail

| Variable name | Type | text= | Fixed / Programmatic | Style notes |
|---|---|---|---|---|
| `self._nav` | ColumnPanel | — | — | `background='#1E293B'` |
| `title_row` | ColumnPanel | — | — | Local variable; holds title + user + sign-out in a row |
| `lbl_title` | Label | `"OWL Knowledge Map"` | Fixed | `bold=True`, `foreground='white'`, `font_size=15` |
| `lbl_user` | Label | User's email address (e.g. `"h@openingworlds.com"`) | Programmatic — set from `anvil.users.get_user()['email']` | `foreground='#94A3B8'`, `font_size=11` |
| `btn_signout` | Button | `"Sign out"` | Fixed | `role='secondary-color'` |
| `btn_row` | ColumnPanel | — | — | Local variable; holds the four nav buttons |
| `btn_dashboard` | Button | `"Dashboard"` | Fixed | Click handler: `_nav_to('dashboard')` |
| `btn_browse` | Button | `"Browse"` | Fixed | Click handler: `_nav_to('browser')` |
| `btn_edge_review` | Button | `"Edge Review"` | Fixed | Click handler: `_nav_to('edge_review')`. `visible=False` if user role ≠ `'reviewer'` |
| `btn_graph` | Button | `"Graph"` | Fixed | Click handler: `_nav_to('graph')` |
| `self._content` | ColumnPanel | — | — | Empty on load; active form added here via `_nav_to()` |

---

### DashboardForm

**Overview:** The first screen a user sees after login. Shows four summary stat cards followed by four Plotly charts giving an overview of the corpus and edge review progress.

**Uplink calls (all called in `_load()` on form open):**
- `get_dashboard_stats()` → concepts count, occurrences count, confirmed edges count, by_subject dict
- `get_load_bearing_concepts(2)` → list of concepts with 2+ occurrences, each with `term` and `occ_count`
- `get_candidate_edges_list(None, None, True, 0, 200)` → dict with keys `rows` (list of edge dicts), `total`, `page`, `page_size`. Access the list via `result['rows']`. Each row has `edge_type` and `already_confirmed`.
- `get_words_per_year()` → new vocabulary introductions (is_introduction=1) per year, broken down by subject

#### Component tree

```
self (ColumnPanel)
  lbl_heading   (Label)
  stat_row      (ColumnPanel — holds the 4 stat cards side by side)
    card_concepts       (ColumnPanel, background='#F8FAFC')
      lbl_concepts_val  (Label — the number)
      lbl_concepts_name (Label — the stat name)
    card_occurrences    (ColumnPanel, background='#F8FAFC')
      lbl_occ_val
      lbl_occ_name
    card_edges          (ColumnPanel, background='#F8FAFC')
      lbl_edges_val
      lbl_edges_name
    card_pending        (ColumnPanel, background='#F8FAFC')
      lbl_pending_val
      lbl_pending_name
  plot1  (Plot — Occurrences by Subject)
  plot2  (Plot — Top 15 Load-Bearing Concepts)
  plot3  (Plot — Candidate Edge Types)
  plot4  (Plot — New Vocabulary Introduced per Year)
  btn_start_review (Button)  ← reviewer role only
```

#### Stat cards — detailed breakdown

The four cards are built in a loop. Each card is a `ColumnPanel` with two Labels stacked vertically:
- **Top label** (`lbl_value`): the number. Large, bold, coloured. Set programmatically from uplink data.
- **Bottom label** (`lbl_name`): the human-readable stat name. Small, muted grey. Fixed text.

| Card | Variable name | lbl_value text (example) | lbl_value colour | lbl_name text (fixed) |
|---|---|---|---|---|
| Concepts | `card_concepts` / `lbl_concepts_val` / `lbl_concepts_name` | `"2736"` (count from `stats['concepts']`) | `#3B82F6` blue | `"Concepts"` |
| Occurrences | `card_occurrences` / `lbl_occ_val` / `lbl_occ_name` | `"2922"` (count from `stats['occurrences']`) | `#22C55E` green | `"Occurrences"` |
| Edges Confirmed | `card_edges` / `lbl_edges_val` / `lbl_edges_name` | `"0"` (count from `stats['confirmed_edges']`) | `#6366F1` indigo | `"Edges Confirmed"` |
| Pending Review | `card_pending` / `lbl_pending_val` / `lbl_pending_name` | `"169"` (derived from candidate edges not yet confirmed) | `#F59E0B` amber | `"Pending Review"` |

**Style for all lbl_value labels:** `bold=True`, `font_size=32`, foreground = colour above
**Style for all lbl_name labels:** `foreground='#64748B'`, `font_size=12`

In the code these are built in a for loop — there are no `self.` names. The loop iterates over:
```python
[
    ('Concepts',       stats['concepts'],       '#3B82F6'),
    ('Occurrences',    stats['occurrences'],     '#22C55E'),
    ('Edges Confirmed',stats['confirmed_edges'], '#6366F1'),
    ('Pending Review', pending,                  '#F59E0B'),
]
```
where `pending` = count of rows in `candidates['rows']` where `already_confirmed` is False. (`candidates` is the dict returned by `get_candidate_edges_list`; the list is under the `'rows'` key.)

#### Heading

| Variable name | Type | text= | Fixed / Programmatic | Style |
|---|---|---|---|---|
| `lbl_heading` | Label | `"Dashboard"` | Fixed | `bold=True`, `font_size=20` |

#### Charts

All four plots are `Plot` components. Their `.data` and `.layout` are set programmatically in `_load()`. They are local variables (`plot1` through `plot4`), not `self.` attributes.

**Plot 1 — Occurrences by Subject**
- Variable name: `plot1`
- Type: `Plot`
- Chart type: vertical bar chart
- X axis: subject names — `['Geography', 'History', 'Religion']` (from `by_subject` dict keys)
- Y axis: occurrence counts — the corresponding values from `by_subject`
- Bar colours: Geography=#22C55E, History=#3B82F6, Religion=#EF4444 (matched per subject)
- Title: `'Occurrences by Subject'`
- Height: 300px

**Plot 2 — Top 15 Load-Bearing Concepts**
- Variable name: `plot2`
- Type: `Plot`
- Chart type: horizontal bar chart (`orientation='h'`)
- Y axis: concept terms (up to 15, reversed so highest count is at top)
- X axis: occurrence counts (`occ_count`)
- Bar colour: `#6366F1` indigo (uniform — this is about volume, not subject)
- Title: `'Top 15 Load-Bearing Concepts'`
- Height: 320px, left margin 170px (to accommodate long term labels)

**Plot 3 — Candidate Edge Types**
- Variable name: `plot3`
- Type: `Plot`
- Chart type: pie/donut (`type='pie'`, `hole=0.35`)
- Labels: `['Within Subject', 'Cross Subject']`
- Values: computed from candidate_edges list — count of `edge_type == 'within_subject'` vs `'cross_subject'`
- Colours: Within Subject=#3B82F6, Cross Subject=#F59E0B
- Title: `'Candidate Edge Types'`
- Height: 300px

**Plot 4 — New Vocabulary Introduced per Year**
- Variable name: `plot4`
- Type: `Plot`
- Chart type: grouped bar chart (`barmode='group'`)
- X axis: `['Year 3', 'Year 4', 'Year 5', 'Year 6']` (fixed labels)
- Y axis: count of new vocabulary introductions (`is_introduction=1`) per year
- 3 traces, one per subject:
  - History: y=[count_y3, count_y4, count_y5, count_y6], colour `#3B82F6` blue
  - Geography: same structure, colour `#22C55E` green
  - Religion: same structure, colour `#EF4444` red
- Data source: `get_words_per_year()` → `words_per_year['History'][3]` etc.
- Title: `'New Vocabulary Introduced per Year'`
- Height: 320px

#### Review CTA button

| Variable name | Type | text= | Fixed / Programmatic | Notes |
|---|---|---|---|---|
| `btn_start_review` | Button | `"Start Edge Review →"` | Fixed | `role='primary-color'`. Only added to form if `user['role'] == 'reviewer'`. Click: `_nav_to('edge_review')` |

---

### BrowserForm

**Overview:** A filterable, paginated list of every confirmed occurrence in the corpus. Users can filter by subject, year and term, or search by term text. Clicking a term navigates to ConceptDetailForm.

**Uplink calls:**
- `get_filter_options()` → lists of subjects, years, terms (called once on load to populate dropdowns)
- `get_corpus(subject, year, term, search, page, page_size=50)` → called on load and on every filter change or page navigation

#### Component tree

```
self (ColumnPanel)
  lbl_heading    (Label)
  filter_row     (ColumnPanel — holds the four filter controls side by side)
    self._dd_subject  (DropDown)
    self._dd_year     (DropDown)
    self._dd_term     (DropDown)
    self._tb_search   (TextBox)
  self._results  (ColumnPanel — rows injected here on each load)
  pagination     (ColumnPanel — Prev/page-label/Next)
    self._btn_prev (Button)
    self._lbl_pg   (Label)
    self._btn_next (Button)
```

#### Component detail

| Variable name | Type | text= / placeholder= | Fixed / Programmatic | Notes |
|---|---|---|---|---|
| `lbl_heading` | Label | `"Browse Corpus"` | Fixed | `bold=True`, `font_size=20` |
| `self._dd_subject` | DropDown | placeholder: `"All Subjects"` | Items set programmatically from `get_filter_options()` | Change handler: `_on_filter_change()` |
| `self._dd_year` | DropDown | placeholder: `"All Years"` | Items set programmatically | Change handler: `_on_filter_change()` |
| `self._dd_term` | DropDown | placeholder: `"All Terms"` | Items set programmatically | Change handler: `_on_filter_change()` |
| `self._tb_search` | TextBox | placeholder: `"Search term..."` | User types here | Change/pressed handler: `_on_filter_change()` |
| `self._results` | ColumnPanel | — | Cleared and repopulated on every `_load_page()` call | Each row is a `_BrowserRow` ColumnPanel |
| `self._btn_prev` | Button | `"← Prev"` | Fixed | Click: `_prev_page()`. Disabled when on page 0 |
| `self._lbl_pg` | Label | e.g. `"Page 1 | 1–50 of 2922"` | Programmatic — set after each page load | `foreground='#64748B'` |
| `self._btn_next` | Button | `"Next →"` | Fixed | Click: `_next_page()`. Disabled when on last page |

#### Browser row (`_BrowserRow`)

Each row in `self._results` is a `ColumnPanel` containing:

| Component | text= | Notes |
|---|---|---|
| `_chip('INTRO')` or `_chip('recur')` | `"INTRO"` or `"recur"` | Label styled as a chip. Background: `#3B82F6` for INTRO, `#94A3B8` for recur. White foreground, small font. |
| `Link` | The concept term text (e.g. `"empire"`) | Click navigates to ConceptDetailForm passing `concept_id` |
| Location label | e.g. `"Y4 Spring 2 | History | Christianity in 3 empires"` | `foreground='#64748B'`, `font_size=12` |

---

### EdgeReviewForm

**Overview:** The human review workflow. Shows one candidate edge at a time — the FROM occurrence on the left, the TO occurrence on the right. The reviewer reads both contexts and clicks a button to confirm the edge nature (or skip).

**Uplink calls:**
- `get_candidate_edges_list(None, None, True, 0, 300)` — loads all candidate edges on open. `True` = include already-confirmed ones (so reviewer can see them). Returns a dict — store `result['rows']` in `self._all_edges` and filter locally.
- `get_term_detail(occurrence_id)` — called for each side of the current edge to get term, location, chapter, context
- `confirm_edge(from_occurrence_id, to_occurrence_id, edge_nature, reviewer_name)` — writes to SQLite edges table

#### Component tree

```
self (ColumnPanel)
  self._lbl_header   (Label)
  filters            (ColumnPanel — filter controls)
    self._dd_etype   (DropDown)
    self._dd_subj    (DropDown)
  self._lbl_progress (Label)
  self._panel_review (ColumnPanel — swapped out per edge)
    review_cols      (ColumnPanel — three-column layout)
      left_panel     (ColumnPanel — FROM side)
        lbl_from_tag
        lbl_from_term
        lbl_from_loc
        lbl_from_ch
        lbl_from_ctx
      mid_panel      (ColumnPanel — arrow + edge type badge)
        lbl_arrow
        lbl_edge_badge
      right_panel    (ColumnPanel — TO side)
        lbl_to_tag
        lbl_to_term
        lbl_to_loc
        lbl_to_ch
        lbl_to_ctx
    decision_row     (ColumnPanel — reviewer name + confirm buttons)
      self._tb_reviewer
      btn_reinforcement
      btn_extension
      btn_cross_subject
      btn_skip
    nav_row          (ColumnPanel — prev/next navigation)
      self._btn_prev
      self._btn_next
```

#### Component detail

| Variable name | Type | text= | Fixed / Programmatic | Style notes |
|---|---|---|---|---|
| `self._lbl_header` | Label | e.g. `"Edge Review | 3/169 confirmed | 12 of 166"` | Programmatic — updated after each confirm or navigation | `bold=True`, `font_size=18` |
| `self._dd_etype` | DropDown | placeholder: `"All Types"` | Items: `['All Types', 'Within Subject', 'Cross Subject']` — fixed | Change handler: `_apply_filters()` |
| `self._dd_subj` | DropDown | placeholder: `"All Subjects"` | Items: `['All Subjects', 'History', 'Geography', 'Religion']` — fixed | Change handler: `_apply_filters()` |
| `self._lbl_progress` | Label | e.g. `"3 confirmed | 166 remaining | 2%"` | Programmatic — updated after each confirm | `foreground='#64748B'` |

**FROM panel (left_panel, background='#F8FAFC'):**

| Variable name | Type | text= | Fixed / Programmatic | Style |
|---|---|---|---|---|
| `lbl_from_tag` | Label | `"FROM"` | Fixed | `foreground='#64748B'`, `font_size=11` |
| `lbl_from_term` | Label | The concept term (e.g. `"empire"`) | Programmatic — from `get_term_detail(from_occurrence_id)['term']` | `bold=True`, `font_size=20` |
| `lbl_from_loc` | Label | Location string (e.g. `"Y4 Spring 2 · History · Christianity in 3 empires"`) | Programmatic | `foreground='#64748B'` |
| `lbl_from_ch` | Label | Chapter (e.g. `"Chapter: 2. The Roman Empire"`) | Programmatic | `foreground='#94A3B8'`, `font_size=11` |
| `lbl_from_ctx` | Label | The `term_in_context` paragraph text (truncated to ~300 chars if long) | Programmatic | `italic=True`, `foreground='#475569'`, `font_size=12` |

**Middle panel (mid_panel) — the arrow and edge type indicator:**

| Variable name | Type | text= | Fixed / Programmatic | Style |
|---|---|---|---|---|
| `lbl_arrow` | Label | `"→"` | Fixed | `bold=True`, `font_size=22` |
| `lbl_edge_badge` | Label | Edge type label (e.g. `"Within Subject"` or `"Cross Subject"`) | Programmatic — derived from current edge's `edge_type` | Background = `#3B82F6` if within-subject, `#F59E0B` if cross-subject. `foreground='white'` |

**TO panel (right_panel, background='#F8FAFC'):** Mirror of FROM panel.

| Variable name | Type | text= | Fixed / Programmatic | Style |
|---|---|---|---|---|
| `lbl_to_tag` | Label | `"TO"` | Fixed | Same as `lbl_from_tag` |
| `lbl_to_term` | Label | Concept term | Programmatic from `get_term_detail(to_occurrence_id)` | Same as `lbl_from_term` |
| `lbl_to_loc` | Label | Location string | Programmatic | Same as `lbl_from_loc` |
| `lbl_to_ch` | Label | Chapter | Programmatic | Same as `lbl_from_ch` |
| `lbl_to_ctx` | Label | Context paragraph | Programmatic | Same as `lbl_from_ctx` |

**Decision row:**

| Variable name | Type | text= | Fixed / Programmatic | Style / behaviour |
|---|---|---|---|---|
| `self._tb_reviewer` | TextBox | placeholder: `"Your name..."` | Reviewer types their name — persists across edges | Checked before confirming — shows error if blank |
| `btn_reinforcement` | Button | `"Reinforcement"` | Fixed | `background='#22C55E'`, `foreground='white'`. Click: `_confirm('reinforcement')` |
| `btn_extension` | Button | `"Extension"` | Fixed | `background='#3B82F6'`, `foreground='white'`. Click: `_confirm('extension')` |
| `btn_cross_subject` | Button | `"Cross-subject Application"` | Fixed | `background='#F59E0B'`, `foreground='white'`. Click: `_confirm('cross_subject_application')` |
| `btn_skip` | Button | `"Skip →"` | Fixed | No colour override. Click: `_skip()` — advances to next edge without writing to DB |

**Navigation row:**

| Variable name | Type | text= | Fixed / Programmatic | Notes |
|---|---|---|---|---|
| `self._btn_prev` | Button | `"← Prev"` | Fixed | Click: go to previous edge in filtered list |
| `self._btn_next` | Button | `"Next →"` | Fixed | Click: go to next edge in filtered list |

**Confirm flow:** `_confirm(edge_nature)` → checks `self._tb_reviewer.text` is not blank → calls `confirm_edge(from_id, to_id, edge_nature, reviewer)` → on success, removes edge from `self._all_edges`, updates progress label, calls `_apply_filters()` to show next.

---

### ConceptDetailForm

**Overview:** Shows the full curriculum trajectory for one concept — every occurrence in chronological order, plus any confirmed edges involving it.

**Uplink call:** `get_concept_detail(concept_id)` → returns `{'concept': {...}, 'occurrences': [...], 'edges': [...]}`

#### Component tree

```
self (ColumnPanel)
  btn_back        (Button)
  lbl_term        (Label — the concept term)
  lbl_subject_chip (Label styled as chip — subject area)
  lbl_summary     (Label — occurrence count + year range)
  lbl_timeline_hd (Label — section heading)
  [_OccurrenceRow × N]  (one per occurrence, added dynamically)
  lbl_edges_hd    (Label — section heading, shown only if edges exist)
  [_EdgeRow × N]  (one per confirmed edge, added dynamically)
  lbl_no_edges    (Label — shown if no edges)
```

#### Component detail

| Variable name | Type | text= | Fixed / Programmatic | Style |
|---|---|---|---|---|
| `btn_back` | Button | `"← Back to Browse"` | Fixed | Click: `_nav_to('browser')` |
| `lbl_term` | Label | The concept term (e.g. `"empire"`) | Programmatic — from `concept['term']` | `bold=True`, `font_size=24` |
| `lbl_subject_chip` | Label (chip) | Subject area (e.g. `"History"`) | Programmatic — from `concept['subject_area']` | Background = subject colour (`#3B82F6`/`#22C55E`/`#EF4444`). `foreground='white'`, `font_size=11` |
| `lbl_summary` | Label | e.g. `"6 occurrence(s) | Year 4 – Year 6"` | Programmatic | `foreground='#64748B'` |
| `lbl_timeline_hd` | Label | `"Curriculum Timeline"` | Fixed | `bold=True`, `font_size=16` |
| `lbl_edges_hd` | Label | e.g. `"Confirmed Edges (2)"` | Programmatic — count from `edges` list | `bold=True`, `font_size=16`. Only added if `len(edges) > 0` |
| `lbl_no_edges` | Label | `"No confirmed edges yet..."` | Fixed | `foreground='#94A3B8'`. Only added if `len(edges) == 0` |

#### Occurrence row (`_OccurrenceRow`)

One row per occurrence, added dynamically. Each is a `ColumnPanel(background='#F8FAFC')` containing:

| Component | text= | Notes |
|---|---|---|
| `_chip('INTRO')` or `_chip('recur')` | `"INTRO"` or `"recur"` | Coloured chip: INTRO=#3B82F6, recur=#94A3B8 |
| Location label | e.g. `"Y4 Spring 2 | History | Christianity in 3 empires"` | `foreground='#64748B'` |
| Chapter label | e.g. `"Chapter: 2. The Roman Empire"` | `foreground='#94A3B8'`, `font_size=11` |
| Context preview label | First 220 chars of `term_in_context` (truncated with `...`) | `italic=True`, `foreground='#475569'`, `font_size=12` |

#### Edge row (`_EdgeRow`)

One row per confirmed edge. Each is a `ColumnPanel` containing:

| Component | text= | Notes |
|---|---|---|
| From location label | e.g. `"Y4 Spring 2 · History"` | `foreground='#64748B'` |
| Arrow label | `"→"` | |
| To location label | e.g. `"Y5 Autumn 1 · History"` | `foreground='#64748B'` |
| Edge nature chip | e.g. `"reinforcement"` | Background: reinforcement=#22C55E, extension=#3B82F6, cross_subject_application=#F59E0B |
| Confirmed by label | e.g. `"Confirmed by Christine on 2026-02-28"` | `foreground='#94A3B8'`, `font_size=11` |

---

### GraphForm (Phase B stub)

**Overview:** Will show a Plotly network graph of confirmed edges. Currently a stub — shows a placeholder message until edges exist. Activates automatically once confirmed edges > 0.

**Uplink calls:**
- `get_candidate_edges_list(None, None, True, 0, 10)` — called in `_check_and_load()` to detect if any confirmed edges exist
- `get_graph_figure(subject, year_from, year_to, edge_type)` — called when "Rebuild Graph" is clicked; returns a Plotly figure dict

#### Component tree

```
self (ColumnPanel)
  lbl_heading       (Label)
  filters           (ColumnPanel — filter bar)
    self._dd_subject    (DropDown)
    lbl_from            (Label)
    self._dd_year_from  (DropDown)
    lbl_to              (Label)
    self._dd_year_to    (DropDown)
    self._dd_etype      (DropDown)
    btn_rebuild         (Button)
  self._lbl_stub    (Label — placeholder)
  self._plot        (Plot — hidden until edges confirmed)
```

#### Component detail

| Variable name | Type | text= | Fixed / Programmatic | Notes |
|---|---|---|---|---|
| `lbl_heading` | Label | `"Knowledge Graph"` | Fixed | `bold=True`, `font_size=20` |
| `self._dd_subject` | DropDown | placeholder: `"All Subjects"` | Items: `['All Subjects', 'History', 'Geography', 'Religion']` — fixed | |
| `lbl_from` | Label | `"From"` | Fixed | Small label between the two year dropdowns |
| `self._dd_year_from` | DropDown | placeholder: `"Year 3"` | Items: `[3, 4, 5, 6]` — fixed | Default: minimum year (3) |
| `lbl_to` | Label | `"To"` | Fixed | |
| `self._dd_year_to` | DropDown | placeholder: `"Year 6"` | Items: `[3, 4, 5, 6]` — fixed | Default: maximum year (6) |
| `self._dd_etype` | DropDown | placeholder: `"All Edge Types"` | Items: `['All Edge Types', 'Within Subject', 'Cross Subject']` — fixed | |
| `btn_rebuild` | Button | `"Rebuild Graph"` | Fixed | `enabled=False` until confirmed edges > 0. Click: `_rebuild()` |
| `self._lbl_stub` | Label | `"Graph will appear once edges are confirmed..."` | Fixed | `foreground='#94A3B8'`. Visible while no confirmed edges. |
| `self._plot` | Plot | — | Programmatic — figure dict set by `get_graph_figure()` | `visible=False` until confirmed edges > 0. Supports node click → `_nav_to('concept_detail', concept_id=id)` |

**Stub logic:** `_check_and_load()` calls `get_candidate_edges_list` — if any row has `already_confirmed=True`, sets `self._lbl_stub.visible = False`, `self._plot.visible = True`, `btn_rebuild.enabled = True`.

**Node click:** `_on_plot_click(points)` extracts `customdata` (concept_id) from clicked node → `_nav_to('concept_detail', concept_id=id)`.

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

**Practical tip:** create all six form shells first (empty `__init__.py`), then paste code into each form in order (1–6). All forms exist before any code runs — safer than pasting as you go.

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
3. Dashboard shows 4 stat cards + 4 charts (uplink running):
   - Occurrences by Subject (bar)
   - Top 15 Load-Bearing Concepts (horizontal bar)
   - Candidate Edge Types (donut)
   - New Vocabulary Introduced per Year (grouped bar)
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

When ready, implement `src/render_pages.py` to render PPTX slides to images.
Note: `pymupdf` (`fitz`) is a **PDF** library — it cannot open `.pptx` files directly. To render PPTX slides to PNG you need a conversion step: PPTX → PDF (via LibreOffice headless), then PDF → PNG (via `pymupdf`). Alternatively use LibreOffice headless to export directly to PNG.
The `get_page_image()` uplink stub is already in `src/uplink.py`.
Add "View booklet page" buttons to `_OccurrenceRow` in ConceptDetailForm.
