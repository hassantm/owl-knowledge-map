#!/usr/bin/env python3
"""
graph_builder.py — OWL Knowledge Map Graph Library

Builds a NetworkX DiGraph from confirmed occurrences and confirmed edges.

Graph structure:
  - Concept nodes   : abstract vocabulary terms   ('concept_N')
  - Occurrence nodes: curriculum locations         ('occ_N')
  - Concept → Occurrence edges: membership         (relationship='has_occurrence')
  - Occurrence → Occurrence edges: confirmed curriculum connections (from edges table)

Candidate edges (unconfirmed) are NOT added to the graph. Use
get_candidate_edges() to generate them for human review.

Usage (as library):
    from graph_builder import build_graph, get_candidate_edges, graph_stats
    G = build_graph(conn_string)

Migrated from SQLite to PostgreSQL: 2026-03-14
Originally created: 2026-02-26
"""

import os
from pathlib import Path

import networkx as nx
import psycopg2
from psycopg2.extras import RealDictCursor

PG_CONN_STRING = os.environ.get(
    "OWL_DB_URL",
    "dbname=owl user=htmadmin password=dev host=localhost port=5432"
)

# =============================================================================
# CURRICULUM ORDERING
# =============================================================================

TERM_ORDER: dict[str, int] = {
    'Autumn1': 1, 'Autumn2': 2,
    'Spring1': 3, 'Spring2': 4,
    'Summer1': 5, 'Summer2': 6,
}


def curriculum_position(
    year: int,
    term: str,
    slide: int | None = None
) -> tuple[int, int, int]:
    """Return a sortable position tuple for curriculum ordering."""
    return (year, TERM_ORDER.get(term, 0), slide or 0)


# =============================================================================
# GRAPH BUILDING
# =============================================================================

def build_graph(conn_string: str = PG_CONN_STRING) -> nx.DiGraph:
    """
    Build a NetworkX DiGraph from all confirmed occurrences and edges.

    Node IDs:
      concept nodes    'concept_{concept_id}'
      occurrence nodes 'occ_{occurrence_id}'
    """
    G = nx.DiGraph()

    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Concept nodes
            cursor.execute("SELECT concept_id, term, subject_area FROM concepts")
            for row in cursor.fetchall():
                G.add_node(
                    f"concept_{row['concept_id']}",
                    type='concept',
                    concept_id=row['concept_id'],
                    term=row['term'],
                    subject_area=row['subject_area'],
                )

            # Occurrence nodes + concept→occurrence edges
            cursor.execute("""
                SELECT o.occurrence_id, o.concept_id, c.term AS concept_term,
                       o.subject, o.year, o.term AS term_period,
                       o.unit, o.chapter, o.slide_number,
                       o.is_introduction, o.term_in_context
                FROM occurrences o
                JOIN concepts c ON o.concept_id = c.concept_id
                WHERE o.validation_status = 'confirmed'
                ORDER BY o.year, o.term, o.slide_number
            """)
            for row in cursor.fetchall():
                occ_id = f"occ_{row['occurrence_id']}"
                concept_id = f"concept_{row['concept_id']}"
                pos = curriculum_position(
                    row['year'], row['term_period'], row['slide_number']
                )
                G.add_node(
                    occ_id,
                    type='occurrence',
                    occurrence_id=row['occurrence_id'],
                    concept_id=row['concept_id'],
                    concept_term=row['concept_term'],
                    subject=row['subject'],
                    year=row['year'],
                    term_period=row['term_period'],
                    unit=row['unit'],
                    chapter=row['chapter'],
                    slide_number=row['slide_number'],
                    is_introduction=bool(row['is_introduction']),
                    term_in_context=row['term_in_context'],
                    curriculum_pos=pos,
                )
                G.add_edge(concept_id, occ_id, relationship='has_occurrence')

            # Confirmed occurrence→occurrence edges
            cursor.execute("""
                SELECT edge_id, from_occurrence, to_occurrence,
                       edge_type, edge_nature, confirmed_by, confirmed_date
                FROM edges
            """)
            for row in cursor.fetchall():
                fr = f"occ_{row['from_occurrence']}"
                to = f"occ_{row['to_occurrence']}"
                if fr in G and to in G:
                    G.add_edge(
                        fr, to,
                        edge_id=row['edge_id'],
                        edge_type=row['edge_type'],
                        edge_nature=row['edge_nature'],
                        confirmed_by=row['confirmed_by'],
                        confirmed_date=row['confirmed_date'],
                    )
    finally:
        conn.close()

    return G


# =============================================================================
# CANDIDATE EDGE GENERATION
# =============================================================================

def get_candidate_edges(conn_string: str = PG_CONN_STRING) -> list[dict]:
    """
    Generate candidate occurrence→occurrence edges for human review.

    For each concept with 2+ occurrences:
    - Sort by curriculum position (year, term, slide, occurrence_id)
    - Generate sequential chain: O1→O2, O2→O3, ...
    - Skip pairs at the same curriculum position
    """
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT o.occurrence_id, o.concept_id, c.term AS concept_term,
                       o.subject, o.year, o.term AS term_period,
                       o.unit, o.chapter, o.slide_number
                FROM occurrences o
                JOIN concepts c ON o.concept_id = c.concept_id
                WHERE o.validation_status = 'confirmed'
                ORDER BY o.concept_id, o.year, o.term, o.slide_number, o.occurrence_id
            """)
            rows = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT from_occurrence, to_occurrence FROM edges")
            confirmed_pairs = {(r['from_occurrence'], r['to_occurrence']) for r in cursor.fetchall()}
    finally:
        conn.close()

    # Group by concept
    from_concept: dict[int, list[dict]] = {}
    for row in rows:
        cid = row['concept_id']
        from_concept.setdefault(cid, []).append(row)

    candidates = []
    for concept_id, occs in from_concept.items():
        if len(occs) < 2:
            continue

        occs_sorted = sorted(
            occs,
            key=lambda o: (
                curriculum_position(o['year'], o['term_period'], o['slide_number']),
                o['occurrence_id'],
            ),
        )

        for i in range(len(occs_sorted) - 1):
            fr = occs_sorted[i]
            to = occs_sorted[i + 1]

            fr_pos = curriculum_position(fr['year'], fr['term_period'], fr['slide_number'])
            to_pos = curriculum_position(to['year'], to['term_period'], to['slide_number'])
            if fr_pos == to_pos:
                continue

            edge_type = (
                'within_subject' if fr['subject'] == to['subject']
                else 'cross_subject'
            )
            candidates.append({
                'from_occurrence_id': fr['occurrence_id'],
                'to_occurrence_id':   to['occurrence_id'],
                'term':               fr['concept_term'],
                'from_subject':       fr['subject'],
                'from_year':          fr['year'],
                'from_term':          fr['term_period'],
                'from_unit':          fr['unit'],
                'from_chapter':       fr['chapter'] or '',
                'to_subject':         to['subject'],
                'to_year':            to['year'],
                'to_term':            to['term_period'],
                'to_unit':            to['unit'],
                'to_chapter':         to['chapter'] or '',
                'edge_type':          edge_type,
                'already_confirmed':  (
                    fr['occurrence_id'], to['occurrence_id']
                ) in confirmed_pairs,
            })

    return candidates


# =============================================================================
# GRAPH STATISTICS
# =============================================================================

def graph_stats(G: nx.DiGraph) -> dict:
    """Return summary statistics for the knowledge graph."""
    concept_nodes = [n for n, d in G.nodes(data=True) if d.get('type') == 'concept']
    occ_nodes     = [n for n, d in G.nodes(data=True) if d.get('type') == 'occurrence']

    confirmed_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get('edge_nature') is not None
    ]

    by_edge_type   = {}
    by_edge_nature = {}
    for _, _, d in G.edges(data=True):
        if d.get('edge_type'):
            by_edge_type[d['edge_type']] = by_edge_type.get(d['edge_type'], 0) + 1
        if d.get('edge_nature'):
            by_edge_nature[d['edge_nature']] = by_edge_nature.get(d['edge_nature'], 0) + 1

    load_bearing = [
        n for n in concept_nodes
        if G.out_degree(n) >= 2
    ]

    subjects = set(
        d.get('subject') for _, d in G.nodes(data=True)
        if d.get('type') == 'occurrence' and d.get('subject')
    )

    return {
        'concepts':              len(concept_nodes),
        'occurrences':           len(occ_nodes),
        'confirmed_edges':       len(confirmed_edges),
        'load_bearing_concepts': len(load_bearing),
        'subjects':              sorted(subjects),
        'by_edge_type':          by_edge_type,
        'by_edge_nature':        by_edge_nature,
    }
