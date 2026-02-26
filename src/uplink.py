#!/usr/bin/env python3
"""
Anvil Uplink Server — OWL Knowledge Map

Persistent local process that exposes SQLite data to the Anvil web app via
the Anvil Uplink protocol. All business logic lives here; Anvil Server Modules
are thin proxies only.

Usage:
    python src/uplink.py

Requirements:
    pip install anvil-uplink

Set ANVIL_UPLINK_KEY environment variable (or edit UPLINK_KEY below) to the
key from: Anvil IDE → Settings → Uplink.

Created: 2026-02-26
"""

import logging
import os
import sqlite3
from pathlib import Path

import anvil.server

# =============================================================================
# CONFIGURATION
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "db" / "owl_knowledge_map.db"

# Uplink key — set via environment variable or replace the fallback string
UPLINK_KEY = os.environ.get("ANVIL_UPLINK_KEY", "YOUR_UPLINK_KEY_HERE")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger(__name__)


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def get_conn() -> sqlite3.Connection:
    """Open a read/write connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Issue types that appear in the audit queue — mirrors audit_terms.py categories
AUDIT_ISSUE_TYPES = ('missed_from_extraction', 'potential_noise', 'high_priority_review')


# =============================================================================
# PHASE A — AUDIT REVIEW FUNCTIONS
# =============================================================================

@anvil.server.callable
def get_audit_queue(
    subject: str = None,
    year: int = None,
    term: str = None,
    issue_type: str = None,
    page: int = 0,
    page_size: int = 50
) -> dict:
    """
    Return a paginated list of occurrences requiring review.

    Includes:
      - needs_review = 1 rows (noise / hp review candidates)
      - validation_status IN ('potential_noise', 'high_priority_review')

    Filters: subject, year, term (curriculum period), issue_type.
    Returns dict with keys: rows (list of dicts), total, page, page_size.

    Created: 2026-02-26
    """
    conditions = []
    params: list = []

    # Base filter — items that need review
    conditions.append(
        "(o.needs_review = 1 OR o.validation_status IN ('potential_noise', 'high_priority_review'))"
    )

    if subject:
        conditions.append("o.subject = ?")
        params.append(subject)
    if year is not None:
        conditions.append("o.year = ?")
        params.append(int(year))
    if term:
        conditions.append("o.term = ?")
        params.append(term)
    if issue_type:
        # Map issue_type to DB filter
        if issue_type == 'potential_noise':
            conditions.append("o.validation_status = 'potential_noise'")
        elif issue_type == 'high_priority_review':
            conditions.append("o.validation_status = 'high_priority_review'")
        elif issue_type == 'missed_from_extraction':
            # Missed rows: needs_review=1 but no occurrence_id in the noise categories
            # These are stored with vocab_match_type = 'manual_add' or similar
            # For now surface all needs_review rows not in noise/hp
            conditions.append(
                "o.needs_review = 1 AND o.validation_status NOT IN ('potential_noise', 'high_priority_review')"
            )

    where_clause = " AND ".join(conditions)

    count_sql = f"""
        SELECT COUNT(*) FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE {where_clause}
    """
    select_sql = f"""
        SELECT
            o.occurrence_id,
            c.term,
            o.subject,
            o.year,
            o.term        AS term_period,
            o.unit,
            o.chapter,
            o.slide_number,
            o.is_introduction,
            o.term_in_context,
            o.needs_review,
            o.review_reason,
            o.validation_status,
            o.vocab_confidence,
            o.vocab_match_type,
            o.vocab_source,
            o.audit_decision,
            o.audit_notes
        FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE {where_clause}
        ORDER BY o.subject, o.year, o.term, o.unit, c.term
        LIMIT ? OFFSET ?
    """

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]

        cursor.execute(select_sql, params + [page_size, page * page_size])
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    log.info("get_audit_queue: returned %d/%d rows (page %d)", len(rows), total, page)
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


@anvil.server.callable
def get_audit_stats() -> dict:
    """
    Return summary counts for the audit queue.

    Returns: total_issues, reviewed, pending, by_validation_status dict.

    Created: 2026-02-26
    """
    sql = """
        SELECT
            COUNT(*)                                                        AS total_issues,
            COUNT(CASE WHEN audit_decision IS NOT NULL THEN 1 END)          AS reviewed,
            COUNT(CASE WHEN audit_decision IS NULL THEN 1 END)              AS pending,
            COUNT(CASE WHEN validation_status = 'potential_noise' THEN 1 END)     AS potential_noise,
            COUNT(CASE WHEN validation_status = 'high_priority_review' THEN 1 END) AS high_priority_review,
            COUNT(CASE WHEN needs_review = 1
                        AND validation_status NOT IN ('potential_noise', 'high_priority_review')
                        THEN 1 END)                                         AS missed_from_extraction
        FROM occurrences
        WHERE needs_review = 1
           OR validation_status IN ('potential_noise', 'high_priority_review')
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        row = dict(cursor.fetchone())
    finally:
        conn.close()

    log.info("get_audit_stats: total=%d reviewed=%d pending=%d",
             row['total_issues'], row['reviewed'], row['pending'])
    return row


@anvil.server.callable
def get_term_detail(occurrence_id: int) -> dict | None:
    """
    Return full occurrence record + concept term for a single occurrence.

    Created: 2026-02-26
    """
    sql = """
        SELECT
            o.occurrence_id,
            c.concept_id,
            c.term,
            c.subject_area,
            o.subject,
            o.year,
            o.term        AS term_period,
            o.unit,
            o.chapter,
            o.slide_number,
            o.is_introduction,
            o.term_in_context,
            o.needs_review,
            o.review_reason,
            o.validation_status,
            o.vocab_confidence,
            o.vocab_match_type,
            o.vocab_source,
            o.audit_decision,
            o.audit_notes,
            o.source_path
        FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE o.occurrence_id = ?
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (occurrence_id,))
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        log.warning("get_term_detail: occurrence_id %d not found", occurrence_id)
        return None

    return dict(row)


@anvil.server.callable
def save_audit_decision(occurrence_id: int, decision: str, notes: str = None) -> dict:
    """
    Write audit_decision and audit_notes to the occurrences table.

    Valid decisions: 'keep', 'delete', 'add', 'skip'.
    Passing decision=None clears the decision (marks as unreviewed).

    Returns dict with 'ok' bool and 'message'.

    Created: 2026-02-26
    """
    valid_decisions = {'keep', 'delete', 'add', 'skip', None}
    if decision not in valid_decisions:
        return {'ok': False, 'message': f"Invalid decision '{decision}'. Use: keep, delete, add, skip."}

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT occurrence_id FROM occurrences WHERE occurrence_id = ?",
            (occurrence_id,)
        )
        if not cursor.fetchone():
            return {'ok': False, 'message': f"Occurrence {occurrence_id} not found."}

        cursor.execute(
            "UPDATE occurrences SET audit_decision = ?, audit_notes = ? WHERE occurrence_id = ?",
            (decision, notes, occurrence_id)
        )
        conn.commit()
    finally:
        conn.close()

    log.info("save_audit_decision: occurrence_id=%d decision=%s", occurrence_id, decision)
    return {'ok': True, 'message': f"Decision '{decision}' saved for occurrence {occurrence_id}."}


@anvil.server.callable
def apply_pending_decisions() -> dict:
    """
    Execute apply-decisions logic against DB-stored audit_decision values.

    Processes all occurrences where audit_decision IS NOT NULL:
      'keep'   → SET validation_status = 'confirmed'
      'delete' → DELETE occurrence; clean orphan concepts
      'add'    → Not applicable here (adds come from missed_from_extraction via CSV);
                 log as skipped with note
      'skip'   → no action

    Returns summary counts dict.

    Created: 2026-02-26
    """
    conn = get_conn()
    # Use a non-row-factory connection for write operations
    write_conn = sqlite3.connect(DB_PATH)
    write_cursor = write_conn.cursor()

    counts = {'deleted': 0, 'kept': 0, 'skipped': 0, 'errors': 0, 'orphans_cleaned': 0}

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.occurrence_id, o.audit_decision, o.validation_status,
                   c.term, o.subject, o.year, o.unit
            FROM occurrences o
            JOIN concepts c ON o.concept_id = c.concept_id
            WHERE o.audit_decision IS NOT NULL
        """)
        rows = cursor.fetchall()

        for row in rows:
            occ_id = row[0]
            decision = row[1]

            try:
                if decision == 'keep':
                    write_cursor.execute(
                        "UPDATE occurrences SET validation_status = 'confirmed' WHERE occurrence_id = ?",
                        (occ_id,)
                    )
                    counts['kept'] += 1

                elif decision == 'delete':
                    write_cursor.execute(
                        "DELETE FROM occurrences WHERE occurrence_id = ?",
                        (occ_id,)
                    )
                    counts['deleted'] += 1

                elif decision in ('skip', 'add'):
                    # 'add' for missed terms is handled separately via CSV workflow;
                    # 'skip' is a no-op
                    counts['skipped'] += 1

            except Exception as e:
                counts['errors'] += 1
                log.error("apply_pending_decisions: error on occurrence_id=%d: %s", occ_id, e)

        # Clean orphan concepts once after all deletes
        if counts['deleted'] > 0:
            write_cursor.execute("""
                DELETE FROM concepts
                WHERE concept_id NOT IN (SELECT DISTINCT concept_id FROM occurrences)
            """)
            counts['orphans_cleaned'] = write_cursor.rowcount

        write_conn.commit()

    finally:
        conn.close()
        write_conn.close()

    log.info(
        "apply_pending_decisions: deleted=%d kept=%d skipped=%d orphans=%d errors=%d",
        counts['deleted'], counts['kept'], counts['skipped'],
        counts['orphans_cleaned'], counts['errors']
    )
    return counts


# =============================================================================
# PHASE A — NAVIGATION HELPERS
# =============================================================================

@anvil.server.callable
def get_adjacent_occurrence_ids(occurrence_id: int) -> dict:
    """
    Return prev/next occurrence_ids in the review queue for navigation.

    Returns dict: {'prev': int|None, 'next': int|None}

    Created: 2026-02-26
    """
    sql = """
        SELECT occurrence_id FROM occurrences o
        JOIN concepts c ON o.concept_id = c.concept_id
        WHERE o.needs_review = 1
           OR o.validation_status IN ('potential_noise', 'high_priority_review')
        ORDER BY o.subject, o.year, o.term, o.unit, c.term
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        ids = [r[0] for r in cursor.fetchall()]
    finally:
        conn.close()

    if occurrence_id not in ids:
        return {'prev': None, 'next': None}

    idx = ids.index(occurrence_id)
    return {
        'prev': ids[idx - 1] if idx > 0 else None,
        'next': ids[idx + 1] if idx < len(ids) - 1 else None
    }


@anvil.server.callable
def get_filter_options() -> dict:
    """
    Return distinct values for filter dropdowns: subjects, years, terms.

    Created: 2026-02-26
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT DISTINCT subject FROM occurrences ORDER BY subject")
        subjects = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT year FROM occurrences ORDER BY year")
        years = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT term FROM occurrences ORDER BY term")
        terms = [r[0] for r in cursor.fetchall()]

    finally:
        conn.close()

    return {
        'subjects': subjects,
        'years': years,
        'terms': terms,
        'issue_types': list(AUDIT_ISSUE_TYPES)
    }


# =============================================================================
# PHASE B — GRAPH FUNCTIONS (stubs; build when edges table has data)
# =============================================================================

@anvil.server.callable
def get_graph_figure(
    subject: str = None,
    year_from: int = None,
    year_to: int = None,
    edge_type: str = None
) -> dict:
    """
    Build a Plotly network graph figure from SQLite concepts + occurrences + edges.

    Returns a Plotly figure as a JSON-serialisable dict for the Anvil Plot component.

    NOTE: Stub — returns empty figure until edges table is populated.

    Created: 2026-02-26
    """
    try:
        import networkx as nx
        import plotly.graph_objects as go
    except ImportError:
        log.error("get_graph_figure: networkx or plotly not installed")
        return {}

    conn = get_conn()
    try:
        cursor = conn.cursor()

        # Node query
        node_sql = """
            SELECT c.concept_id, c.term, c.subject_area, COUNT(o.occurrence_id) AS occ_count
            FROM concepts c
            JOIN occurrences o ON c.concept_id = o.concept_id
            WHERE 1=1
        """
        node_params: list = []
        if subject:
            node_sql += " AND o.subject = ?"
            node_params.append(subject)
        if year_from is not None:
            node_sql += " AND o.year >= ?"
            node_params.append(int(year_from))
        if year_to is not None:
            node_sql += " AND o.year <= ?"
            node_params.append(int(year_to))
        node_sql += " GROUP BY c.concept_id"

        cursor.execute(node_sql, node_params)
        nodes = [dict(r) for r in cursor.fetchall()]

        # Edge query
        edge_sql = """
            SELECT e.from_occurrence, e.to_occurrence, e.edge_type, e.edge_nature,
                   ofrom.concept_id AS from_concept, oto.concept_id AS to_concept
            FROM edges e
            JOIN occurrences ofrom ON e.from_occurrence = ofrom.occurrence_id
            JOIN occurrences oto ON e.to_occurrence = oto.occurrence_id
            WHERE e.confirmed_by IS NOT NULL
        """
        edge_params: list = []
        if edge_type:
            edge_sql += " AND e.edge_type = ?"
            edge_params.append(edge_type)

        cursor.execute(edge_sql, edge_params)
        edges = [dict(r) for r in cursor.fetchall()]

    finally:
        conn.close()

    if not nodes:
        return {}

    # Build NetworkX graph
    G = nx.DiGraph()
    subject_colours = {'History': '#3B82F6', 'Geography': '#22C55E', 'Religion': '#EF4444'}

    node_ids = {n['concept_id'] for n in nodes}
    for n in nodes:
        G.add_node(n['concept_id'], term=n['term'], subject_area=n['subject_area'],
                   occ_count=n['occ_count'])

    for e in edges:
        if e['from_concept'] in node_ids and e['to_concept'] in node_ids:
            G.add_edge(e['from_concept'], e['to_concept'],
                       edge_type=e['edge_type'], edge_nature=e['edge_nature'])

    if len(G.nodes) == 0:
        return {}

    pos = nx.kamada_kawai_layout(G) if len(G.nodes) > 1 else {list(G.nodes)[0]: (0, 0)}

    # Edge trace
    edge_x, edge_y = [], []
    for u, v in G.edges():
        x0, y0 = pos[u]; x1, y1 = pos[v]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode='lines',
        line=dict(width=1, color='#888'), hoverinfo='none'
    )

    # Node traces by subject (one trace per colour for legend)
    node_traces = []
    for subj, colour in subject_colours.items():
        subj_nodes = [n for n in nodes if n.get('subject_area') == subj and n['concept_id'] in G.nodes]
        if not subj_nodes:
            continue
        nx_vals = [pos[n['concept_id']][0] for n in subj_nodes]
        ny_vals = [pos[n['concept_id']][1] for n in subj_nodes]
        sizes = [max(8, min(30, n['occ_count'] * 3)) for n in subj_nodes]
        texts = [n['term'] for n in subj_nodes]
        hover = [f"{n['term']}<br>{subj}<br>{n['occ_count']} occurrences" for n in subj_nodes]
        cids = [n['concept_id'] for n in subj_nodes]

        node_traces.append(go.Scatter(
            x=nx_vals, y=ny_vals, mode='markers+text',
            name=subj,
            marker=dict(size=sizes, color=colour, line=dict(width=1, color='white')),
            text=texts, textposition='top center',
            hovertext=hover, hoverinfo='text',
            customdata=cids
        ))

    fig = go.Figure(
        data=[edge_trace] + node_traces,
        layout=go.Layout(
            title='OWL Knowledge Map',
            showlegend=True,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    )

    log.info("get_graph_figure: %d nodes, %d edges", len(G.nodes), len(G.edges))
    return fig.to_dict()


@anvil.server.callable
def get_concept_detail(concept_id: int) -> dict | None:
    """
    Return concept + all occurrences + all confirmed edges for a concept.

    Created: 2026-02-26
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()

        # Concept
        cursor.execute("SELECT * FROM concepts WHERE concept_id = ?", (concept_id,))
        concept_row = cursor.fetchone()
        if not concept_row:
            return None
        concept = dict(concept_row)

        # Occurrences, sorted by curriculum order
        term_order = "CASE o.term WHEN 'Autumn1' THEN 1 WHEN 'Autumn2' THEN 2 WHEN 'Spring1' THEN 3 WHEN 'Spring2' THEN 4 WHEN 'Summer1' THEN 5 WHEN 'Summer2' THEN 6 ELSE 7 END"
        cursor.execute(f"""
            SELECT o.*
            FROM occurrences o
            WHERE o.concept_id = ?
            ORDER BY o.year, {term_order}, o.slide_number
        """, (concept_id,))
        occurrences = [dict(r) for r in cursor.fetchall()]

        occ_ids = [o['occurrence_id'] for o in occurrences]

        # Edges involving this concept's occurrences
        if occ_ids:
            placeholders = ','.join('?' * len(occ_ids))
            cursor.execute(f"""
                SELECT e.*, c_from.term AS from_term, c_to.term AS to_term,
                       ofrom.year AS from_year, ofrom.term AS from_term_period, ofrom.unit AS from_unit,
                       oto.year AS to_year, oto.term AS to_term_period, oto.unit AS to_unit
                FROM edges e
                JOIN occurrences ofrom ON e.from_occurrence = ofrom.occurrence_id
                JOIN occurrences oto ON e.to_occurrence = oto.occurrence_id
                JOIN concepts c_from ON ofrom.concept_id = c_from.concept_id
                JOIN concepts c_to ON oto.concept_id = c_to.concept_id
                WHERE e.from_occurrence IN ({placeholders})
                   OR e.to_occurrence IN ({placeholders})
            """, occ_ids + occ_ids)
            edges = [dict(r) for r in cursor.fetchall()]
        else:
            edges = []

    finally:
        conn.close()

    return {'concept': concept, 'occurrences': occurrences, 'edges': edges}


@anvil.server.callable
def get_load_bearing_concepts(min_occurrences: int = 2) -> list[dict]:
    """
    Return concepts with min_occurrences or more, sorted by occurrence count.

    These are the entry points for the edge confirmation workflow.
    Each row includes: concept_id, term, subject_area, occ_count,
    subjects (comma-separated), first_year, last_year.

    Created: 2026-02-26
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.concept_id, c.term, c.subject_area,
                   COUNT(*) AS occ_count,
                   GROUP_CONCAT(DISTINCT o.subject)  AS subjects,
                   MIN(o.year) AS first_year,
                   MAX(o.year) AS last_year
            FROM concepts c
            JOIN occurrences o ON c.concept_id = o.concept_id
            WHERE o.validation_status = 'confirmed'
            GROUP BY c.concept_id
            HAVING COUNT(*) >= ?
            ORDER BY occ_count DESC, c.term
        """, (min_occurrences,))
        rows = [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

    log.info(
        "get_load_bearing_concepts: %d concepts with >= %d occurrences",
        len(rows), min_occurrences
    )
    return rows


@anvil.server.callable
def get_candidate_edges_list(
    subject: str = None,
    edge_type: str = None,
    include_confirmed: bool = False,
    page: int = 0,
    page_size: int = 50
) -> dict:
    """
    Return paginated candidate edges for the edge confirmation review workflow.

    Filters:
      subject          — match on either from_subject or to_subject
      edge_type        — 'within_subject' or 'cross_subject'
      include_confirmed — if True, include already-confirmed pairs

    Imports graph_builder on first call (adds ~50 ms once).

    Returns dict: rows, total, page, page_size.

    Created: 2026-02-26
    """
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).parent))
    from graph_builder import get_candidate_edges

    candidates = get_candidate_edges(DB_PATH)

    if not include_confirmed:
        candidates = [c for c in candidates if not c['already_confirmed']]
    if subject:
        candidates = [
            c for c in candidates
            if c['from_subject'] == subject or c['to_subject'] == subject
        ]
    if edge_type:
        candidates = [c for c in candidates if c['edge_type'] == edge_type]

    total = len(candidates)
    paged = candidates[page * page_size: (page + 1) * page_size]

    log.info(
        "get_candidate_edges_list: %d/%d (page %d)", len(paged), total, page
    )
    return {'rows': paged, 'total': total, 'page': page, 'page_size': page_size}


@anvil.server.callable
def confirm_edge(
    from_occurrence_id: int,
    to_occurrence_id: int,
    edge_nature: str,
    confirmed_by: str,
    edge_type: str = None,
) -> dict:
    """
    Write a confirmed edge to the edges table.

    edge_nature: 'reinforcement' | 'extension' | 'cross_subject_application'
    confirmed_by: reviewer's name (required)
    edge_type: auto-detected from subject match if not supplied

    Idempotent — updates existing edge if the pair already exists.

    Returns dict: {'ok': bool, 'edge_id': int|None, 'message': str}

    Created: 2026-02-26
    """
    from datetime import date

    valid_natures = {'reinforcement', 'extension', 'cross_subject_application'}
    if edge_nature not in valid_natures:
        return {
            'ok': False,
            'message': (
                f"Invalid edge_nature '{edge_nature}'. "
                f"Use: reinforcement, extension, cross_subject_application"
            ),
        }
    if not confirmed_by or not confirmed_by.strip():
        return {'ok': False, 'message': "confirmed_by must not be empty."}

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # Validate occurrences exist and get their subjects
        cursor.execute(
            "SELECT occurrence_id, subject FROM occurrences WHERE occurrence_id = ?",
            (from_occurrence_id,)
        )
        fr_row = cursor.fetchone()
        cursor.execute(
            "SELECT occurrence_id, subject FROM occurrences WHERE occurrence_id = ?",
            (to_occurrence_id,)
        )
        to_row = cursor.fetchone()

        if not fr_row:
            return {'ok': False, 'message': f"from_occurrence_id {from_occurrence_id} not found."}
        if not to_row:
            return {'ok': False, 'message': f"to_occurrence_id {to_occurrence_id} not found."}

        if not edge_type:
            edge_type = (
                'within_subject' if fr_row[1] == to_row[1] else 'cross_subject'
            )

        today = date.today().isoformat()

        # Idempotent upsert
        cursor.execute(
            "SELECT edge_id FROM edges WHERE from_occurrence=? AND to_occurrence=?",
            (from_occurrence_id, to_occurrence_id)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE edges
                SET edge_type=?, edge_nature=?, confirmed_by=?, confirmed_date=?
                WHERE edge_id=?
            """, (edge_type, edge_nature, confirmed_by.strip(), today, existing[0]))
            edge_id = existing[0]
            action = 'updated'
        else:
            cursor.execute("""
                INSERT INTO edges (
                    from_occurrence, to_occurrence,
                    edge_type, edge_nature, confirmed_by, confirmed_date
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                from_occurrence_id, to_occurrence_id,
                edge_type, edge_nature, confirmed_by.strip(), today
            ))
            edge_id = cursor.lastrowid
            action = 'inserted'

        conn.commit()
    finally:
        conn.close()

    log.info(
        "confirm_edge: %s edge_id=%d %d→%d nature=%s by=%s",
        action, edge_id, from_occurrence_id, to_occurrence_id,
        edge_nature, confirmed_by,
    )
    return {
        'ok': True,
        'edge_id': edge_id,
        'message': f"Edge {action} (id={edge_id}): {edge_nature} [{edge_type}]",
    }


# =============================================================================
# PHASE C — PAGE VIEW (stub; build when render_pages.py has run)
# =============================================================================

@anvil.server.callable
def get_page_image(occurrence_id: int):
    """
    Return the rendered booklet page as an Anvil media object.

    Requires occurrences.page_image_path to be populated by render_pages.py.
    Returns None if not yet available.

    Created: 2026-02-26
    """
    import anvil.media

    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT page_image_path FROM occurrences WHERE occurrence_id = ?",
            (occurrence_id,)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    # Column may not exist yet (render_pages.py not yet run)
    if not row:
        log.warning("get_page_image: occurrence_id %d not found", occurrence_id)
        return None

    page_image_path = row[0] if row[0] else None
    if not page_image_path:
        log.info("get_page_image: no page_image_path for occurrence_id %d (run render_pages.py)", occurrence_id)
        return None

    img_path = Path(page_image_path)
    if not img_path.exists():
        log.warning("get_page_image: file not found at %s", img_path)
        return None

    return anvil.media.from_file(str(img_path), 'image/png')


# =============================================================================
# ENTRY POINT
# =============================================================================

def main() -> None:
    if UPLINK_KEY == "YOUR_UPLINK_KEY_HERE":
        print("ERROR: Set ANVIL_UPLINK_KEY environment variable before starting the uplink.")
        print("  export ANVIL_UPLINK_KEY='your-key-here'")
        print("  python src/uplink.py")
        return

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run: python src/init_db.py")
        return

    log.info("Connecting to Anvil uplink...")
    log.info("Database: %s", DB_PATH)
    anvil.server.connect(UPLINK_KEY)
    log.info("Uplink connected. Waiting for calls...")
    anvil.server.wait_forever()


if __name__ == "__main__":
    main()
