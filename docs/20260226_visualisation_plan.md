# Knowledge Graph Visualisation Plan
_2026-02-26_

## Requirements

The graph is directed and multi-layer:
- **Concept nodes** — abstract vocabulary item (e.g. "empire")
- **Occurrence nodes** — specific curriculum location (subject / year / term / unit / slide)
- **Directed edges** — pedagogical sequence from earlier to later occurrence, with `edge_nature` label (reinforcement / extension / cross_subject_application)

The primary audience is teachers and curriculum experts (potentially Counsell/Mastin). It will be delivered inside the Anvil web app via the existing Uplink architecture. Interactivity — hover, filter, click-to-explore — is essential.

---

## Library Comparison Summary

| Library | Directed arrows | Hover | Anvil embed | Complexity | Status |
|---|---|---|---|---|---|
| NetworkX/matplotlib | Yes | No | Image only | Very low | Stable |
| Plotly | No native | Yes | Native (Plot component) | Medium | Stable |
| Pyvis | Yes | Yes (`title` attr) | IFrame via HTTP endpoint | Low | Stagnant (2021) |
| Dash + Cytoscape | Yes | Yes + Python callbacks | No (needs separate server) | High | Active |
| Bokeh | No native | Yes | IFrame via HTTP endpoint | Medium | Active |
| Gephi | Yes | Yes | No (desktop) | High | Active |

---

## Recommended Path

### Phase 1 — Developer analysis tool (now)
**Library: NetworkX/matplotlib + Gephi**

- Build the NetworkX graph from SQLite (concepts + occurrences + edges tables)
- Export to GEXF: `nx.write_gexf(G, "output/owl_graph.gexf")`
- Import into Gephi desktop for exploratory analysis: ForceAtlas2 layout, centrality metrics, community detection
- Use to answer the analytical questions from CLAUDE.md:
  - Which concepts are most load-bearing?
  - Where do cross-subject connections cluster?
  - Are there gaps (introduced but never revisited)?
- This phase is for developer/owner use only — not teacher-facing

### Phase 2 — Teacher-facing prototype (next)
**Library: Pyvis**

- `pyvis.network.Network(directed=True)` with `from_nx(G)` one-liner
- Serve generated HTML via a lightweight HTTP endpoint in the Uplink process
- Embed in Anvil via `IFrame` component pointing at the endpoint
- Nodes styled by type: concept node vs. occurrence node
- Node colour by subject (History / Geography / Religion)
- Node size by degree (load-bearing concepts appear larger)
- Edge colour by `edge_nature` (reinforcement=blue, extension=orange, cross_subject=purple)
- Hover tooltip (`title` attribute) shows: term, subject, year, term, unit, chapter
- Physics layout with `toggle_physics(False)` for a stable initial render

**Limitations to communicate to users:**
- No click-to-Python callbacks — clicking a node can't open a side panel without extra JS wiring
- Non-deterministic layout unless positions pre-computed and fixed
- Library is not actively maintained (wraps stable vis.js — functional but no new features)

### Phase 3 — Full interactive interface (future)
**Library: Dash + Cytoscape (standalone micro-app)**

When the review workflow in Anvil is complete and the graph data is mature, build a dedicated Dash app:
- Hosted separately (localhost or a simple cloud host)
- Embedded via `IFrame` in Anvil
- Cytoscape.js renders directed arrows, edge labels, compound nodes
- Python callbacks on node click → loads all occurrences for that concept from SQLite → displays side panel with `term_in_context` snippets
- Filterable by subject, year, edge_nature
- CSS stylesheet system for rich visual hierarchy
- `dagre` hierarchical layout to show Year 3 → Year 6 progression left-to-right

---

## Phase 2 Implementation Plan (Pyvis)

### 1. Build the NetworkX graph from SQLite

```python
# src/build_graph.py
import sqlite3
import networkx as nx

def build_graph(db_path, filters=None):
    """
    Build a directed NetworkX graph from the OWL SQLite database.
    Nodes: concepts and occurrences. Edges: confirmed edges table.
    filters: dict with optional keys subject, year, edge_nature
    """
    conn = sqlite3.connect(db_path)
    G = nx.DiGraph()

    # Add concept nodes
    for row in conn.execute("SELECT concept_id, term, subject_area FROM concepts"):
        G.add_node(f"c_{row[0]}", label=row[1], node_type="concept",
                   title=f"Concept: {row[1]}", group="concept")

    # Add occurrence nodes
    query = "SELECT occurrence_id, concept_id, subject, year, term, unit, chapter FROM occurrences"
    for row in conn.execute(query):
        label = f"{row[2]} Y{row[3]} {row[4]}"
        title = f"{row[2]} | Year {row[3]} | {row[4]}\n{row[5]}\n{row[6] or ''}"
        G.add_node(f"o_{row[0]}", label=label, node_type="occurrence",
                   subject=row[2], year=row[3], term=row[4],
                   unit=row[5], title=title, group=row[2])

    # Add edges
    for row in conn.execute("SELECT from_occurrence, to_occurrence, edge_type, edge_nature FROM edges"):
        G.add_edge(f"o_{row[0]}", f"o_{row[1]}",
                   edge_type=row[2], edge_nature=row[3],
                   title=row[3] or "")

    conn.close()
    return G
```

### 2. Render with Pyvis

```python
# src/render_graph.py
from pyvis.network import Network
import networkx as nx

SUBJECT_COLOURS = {
    "History": "#e07b39",
    "Geography": "#4a9b6f",
    "Religion": "#7b5ea7",
    "concept": "#cccccc"
}

EDGE_COLOURS = {
    "reinforcement": "#4477aa",
    "extension": "#ee6677",
    "cross_subject_application": "#228833"
}

def render_pyvis(G):
    net = Network(directed=True, height="750px", width="100%",
                  bgcolor="#ffffff", font_color="black")
    net.from_nx(G)

    # Post-process node colours and sizes
    for node in net.nodes:
        ntype = node.get("node_type", "occurrence")
        subject = node.get("subject", "concept")
        node["color"] = SUBJECT_COLOURS.get(subject, SUBJECT_COLOURS["concept"])
        node["size"] = 30 if ntype == "concept" else 15

    # Post-process edge colours
    for edge in net.edges:
        nature = edge.get("edge_nature", "")
        edge["color"] = EDGE_COLOURS.get(nature, "#aaaaaa")
        edge["arrows"] = "to"

    net.toggle_physics(True)
    return net.generate_html()
```

### 3. Serve from Uplink

```python
# In the Uplink process
import anvil.server
from src.build_graph import build_graph
from src.render_graph import render_pyvis

DB_PATH = "owl_knowledge_map.db"

@anvil.server.callable
def get_graph_html(filters=None):
    G = build_graph(DB_PATH, filters)
    return render_pyvis(G)
```

### 4. Embed in Anvil

```python
# Anvil client form
import anvil.server
from anvil import IFrame

class GraphView(GraphViewTemplate):
    def form_show(self, **event_args):
        html = anvil.server.call('get_graph_html')
        media = anvil.BlobMedia('text/html', html.encode(), name='graph.html')
        self.iframe_1.url = anvil.server.get_media_url(media)
```

---

## Phase 1 Implementation Plan (GEXF/Gephi)

Much simpler — just export the graph:

```python
# src/export_gexf.py
from src.build_graph import build_graph
import networkx as nx

G = build_graph("owl_knowledge_map.db")
nx.write_gexf(G, "output/owl_knowledge_graph.gexf")
print(f"Exported {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
```

In Gephi: File → Open → select `owl_knowledge_graph.gexf`. Run ForceAtlas2. Map node size to Degree. Map node colour to `group` attribute.

---

## Build Order

1. `src/build_graph.py` — NetworkX graph builder from SQLite (shared by all phases)
2. `src/export_gexf.py` — 10-line script, immediate Gephi analysis
3. `pip install pyvis` — add to requirements
4. `src/render_graph.py` — Pyvis renderer returning HTML string
5. Uplink endpoint `get_graph_html`
6. Anvil `GraphView` form with IFrame

Steps 1-2 can be built and validated immediately with current DB data (even before edges exist — the concept+occurrence nodes alone are a useful structural map).

---

## Open Questions Before Building

1. **Graph scope for initial view** — full corpus (all subjects, all years) or scoped by default to one subject? The full graph may be visually overwhelming before filtering is added.
2. **Edge data readiness** — the edges table is currently empty (edges require human confirmation). Phase 1/2 nodes-only view is still valuable; edges enhance it later.
3. **Concept-node visibility** — do teachers need to see both abstract concept nodes and occurrence nodes, or just occurrence nodes linked by shared concept? Two design options:
   - **Bipartite view**: concept node at centre, occurrence nodes fanning out — shows the full picture but is complex
   - **Occurrence-only view**: occurrence nodes linked directly, concept label inferred — simpler, better for Year 3→6 progression layout
4. **Filter controls** — subject filter and year filter in Anvil UI alongside the iframe? These would call `get_graph_html(filters={"subject": "History"})` with fresh rendering.

---

## Dependencies to Add

```
pyvis>=0.3.2
networkx>=3.0   # already in use
```

Gephi is a separate desktop download (https://gephi.org) — no pip install.
