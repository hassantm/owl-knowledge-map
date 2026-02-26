# Anvil Form Reference Code

These files contain the complete Python logic for each Anvil form. They are **reference files only** — copy the code into each form in the Anvil IDE after creating the form and its designer components.

## Form inventory

| File | Form name | Purpose |
|---|---|---|
| `MainForm.py` | MainForm | Navigation shell — always visible |
| `DashboardForm.py` | DashboardForm | Stats cards + Plotly charts |
| `BrowserForm.py` | BrowserForm | Paginated corpus browser |
| `BrowserRowForm.py` | BrowserRowForm | Row template for BrowserForm repeating panel |
| `EdgeReviewForm.py` | EdgeReviewForm | Edge confirmation — the core review tool |
| `ConceptDetailForm.py` | ConceptDetailForm | Single-concept curriculum timeline |
| `OccurrenceRowForm.py` | OccurrenceRowForm | Row template for occurrence timeline |
| `EdgeRowForm.py` | EdgeRowForm | Row template for confirmed edges list |
| `GraphForm.py` | GraphForm | Plotly network graph (stub until edges confirmed) |

## How to use

1. Complete Anvil app setup (see `../20260226_anvil_app_build.md`)
2. For each form in the table above:
   a. Create the form in the Anvil IDE
   b. Add the designer components listed in the docstring at the top of each file
   c. Replace the form's `__init__.py` contents with the code from this file
3. Set up event handlers in the Anvil IDE Properties panel (listed in each file's docstring)

## Uplink functions called

| Form | Uplink functions |
|---|---|
| DashboardForm | `get_dashboard_stats`, `get_load_bearing_concepts`, `get_candidate_edges_list` |
| BrowserForm | `get_corpus`, `get_filter_options` |
| EdgeReviewForm | `get_candidate_edges_list`, `get_term_detail`, `confirm_edge`, `get_filter_options` |
| ConceptDetailForm | `get_concept_detail` |
| GraphForm | `get_graph_figure`, `get_candidate_edges_list`, `get_filter_options` |

All uplink functions are implemented in `src/uplink.py` (main branch).

## Navigation model

`MainForm` owns navigation. Sub-forms navigate by calling:
```python
get_open_form()._nav_to('target', concept_id=123)
```

Available targets: `'dashboard'`, `'browser'`, `'edge_review'`, `'concept_detail'`, `'graph'`
