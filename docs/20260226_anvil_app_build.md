# Anvil App Build Guide — OWL Knowledge Map

**Date:** 2026-02-26
**Status:** Phase A — Core review and browse forms

---

## Overview

The Anvil app is a single web application serving two audiences:
- **Reviewers** — confirm edges between concept occurrences (the core Phase A task)
- **Teachers** — explore the completed knowledge graph (Phase B+)

Role-based navigation: `reviewer` role sees all forms; `teacher` sees everything except Edge Review.

---

## Part 1 — Account and App Setup (user completes once)

### 1.1 Create account and app

1. Go to **anvil.works** → sign up / sign in
2. Create a new app → name: **OWL Knowledge Map**
3. Choose **Blank Panel** as the base template (not a themed template)

### 1.2 Enable the Uplink

1. In the Anvil IDE: **Settings → Uplink → Enable Uplink**
2. Copy the uplink key
3. Add to your local environment:
   ```bash
   export ANVIL_UPLINK_KEY='your-key-here'
   ```
4. Add to CLAUDE.md (App URL section) — **do not commit the key to git**

### 1.3 Enable the Users service

1. In the Anvil IDE: **Settings → Users**
2. Enable email/password login
3. Uncheck "Allow signup" — accounts are created manually
4. In the Users table schema, add a new column:
   - Name: `role`, Type: `text`
5. Create accounts manually for each reviewer:
   - **Anvil IDE → Data → users → Add Row**
   - Set `email`, `password_hash` (or use the "Send password reset email" button), `role = reviewer`

### 1.4 Connect to GitHub

1. **Settings → Version History → Connect to GitHub**
2. Select repo: `hassantm/owl-knowledge-map`
3. Select branch: **`anvil-app`**
4. Anvil will push the current (empty) app structure to the branch
5. The worktree at `~/ai-projects/owl-anvil-app` will reflect this after `git pull`

### 1.5 Note the App URL

Format: `your-app-name.anvil.app`
Add to CLAUDE.md under `## Anvil App`.

---

## Part 2 — Verify Uplink Connection

1. Start the uplink:
   ```bash
   cd ~/ai-projects/owl-knowledge-map
   export ANVIL_UPLINK_KEY='your-key-here'
   python src/uplink.py
   ```
2. In the Anvil IDE: **Settings → Uplink** — should show green "Connected"
3. Test a call in the Anvil Python console:
   ```python
   anvil.server.call('get_dashboard_stats')
   # Expected: {'concepts': 2736, 'occurrences': 2922, 'confirmed_edges': 0, 'by_subject': {...}}
   ```

---

## Part 3 — Build Each Form

Forms are created in this sequence. Create each form shell in the Anvil IDE, add the designer components listed in each `.py` file's docstring, then paste in the Python code from `docs/anvil_forms/`.

Reference code is in: `docs/anvil_forms/`
Navigation model: `MainForm._nav_to('target')` — all routing goes through MainForm.

### Build order

1. **MainForm** — navigation shell (must be first; all other forms are loaded into it)
2. **BrowserRowForm** — row template (needed before BrowserForm)
3. **OccurrenceRowForm** — row template (needed before ConceptDetailForm)
4. **EdgeRowForm** — row template (needed before ConceptDetailForm)
5. **DashboardForm**
6. **BrowserForm** — set `repeating_panel.item_template = BrowserRowForm`
7. **EdgeReviewForm**
8. **ConceptDetailForm** — set `rp_occurrences.item_template = OccurrenceRowForm`, `rp_edges.item_template = EdgeRowForm`
9. **GraphForm** (stub — shows placeholder until edges confirmed)

### Setting MainForm as the startup form

In the Anvil IDE: **Settings → Startup Form → MainForm**

---

## Part 4 — Designer Components Reference

Each form file (`docs/anvil_forms/`) contains a detailed component list in its docstring. The table below gives the key layout pattern per form.

### MainForm layout
```
ColumnPanel (full width)
├── sidebar_panel (ColumnPanel, col=2, background='#1e293b')
│   ├── lbl_app_title
│   ├── lbl_username
│   ├── btn_dashboard
│   ├── btn_browser
│   ├── btn_edge_review  ← hidden for 'teacher' role
│   ├── btn_graph
│   └── btn_signout
└── content_panel (ColumnPanel, col=10)   ← forms load here
```

### DashboardForm layout
```
ColumnPanel
├── Row: [lbl_stat_concepts] [lbl_stat_occurrences] [lbl_stat_edges] [lbl_stat_pending]
├── Row: [plot_by_subject (col=4)] [plot_top_concepts (col=5)] [plot_edge_types (col=3)]
└── btn_start_review
```

### EdgeReviewForm layout (most important)
```
ColumnPanel
├── lbl_header
├── Row: [dd_edge_type] [dd_subject]
├── Row: [lbl_progress] [progress_bar]
└── panel_review (ColumnPanel)
    ├── Row: [LEFT col=5] [MIDDLE col=2] [RIGHT col=5]
    │   ├── LEFT: lbl_from_heading / lbl_from_term / lbl_from_location / lbl_from_chapter / lbl_from_context
    │   ├── MIDDLE: lbl_edge_type (arrow + type)
    │   └── RIGHT: lbl_to_heading / lbl_to_term / lbl_to_location / lbl_to_chapter / lbl_to_context
    ├── Row: [tb_reviewer] [btn_reinforcement] [btn_extension] [btn_cross_subject] [btn_skip]
    └── Row: [btn_prev_edge] [btn_next_edge]
```

---

## Part 5 — End-to-End Test Checklist

After building all forms:

- [ ] Log in as `reviewer` → Edge Review nav item visible
- [ ] Log in as `teacher` → Edge Review nav item hidden
- [ ] Dashboard loads with stats: 2,736 concepts, 2,922 occurrences, 0 edges
- [ ] Browser shows 2,922 rows; filter by subject works; click row → ConceptDetail
- [ ] ConceptDetail shows occurrence timeline for a concept
- [ ] Edge Review loads 169 candidate edges; confirm one edge with your name
- [ ] After confirming: `SELECT COUNT(*) FROM edges;` in SQLite shows 1
- [ ] Dashboard re-loads: confirmed edges = 1
- [ ] Graph form shows stub message (no confirmed edges initially)

---

## Part 6 — Build Phases

### Phase A (current) — Core review + browse

All forms except GraphForm are functional. EdgeReviewForm is the primary tool.

### Phase B — Graph visualisation

After a significant number of edges are confirmed:
1. GraphForm becomes functional (no code changes needed — uplink already implements `get_graph_figure`)
2. Node click on graph → ConceptDetailForm (already wired)

### Phase C — Page images

After `src/render_pages.py` is written and run:
1. Add "View page" button to OccurrenceRowForm
2. Wire to `anvil.server.call('get_page_image', occurrence_id)` (stub already in uplink)

---

## Part 7 — Uplink Management

The uplink must be running for the Anvil app to work. It runs as a foreground process.

```bash
# Terminal 1 — keep running while using the app
export ANVIL_UPLINK_KEY='your-key-here'
python src/uplink.py

# Logs:
# 2026-02-26T10:00:00 [INFO] Connecting to Anvil uplink...
# 2026-02-26T10:00:01 [INFO] Uplink connected. Waiting for calls...
```

If the uplink disconnects, restart it. The Anvil app will show "Connection lost" errors until it reconnects.

---

## Part 8 — Git Workflow (reminder)

```
main      — backend: uplink.py, graph_builder.py, batch scripts
anvil-app — UI: Anvil forms (auto-pushed by Anvil IDE after GitHub sync)
```

Backend changes → branch from `main` → PR to `main`
UI changes → Anvil IDE pushes to `anvil-app` automatically

Worktrees:
- `~/ai-projects/owl-knowledge-map` (main branch)
- `~/ai-projects/owl-anvil-app` (anvil-app branch — Anvil UI code)
