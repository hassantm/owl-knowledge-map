#!/usr/bin/env python3
"""
Build Graph CLI Script

Builds the OWL knowledge graph from confirmed occurrences and confirmed edges,
prints statistics, and optionally exports candidate edges for human review.

Candidate edges connect occurrences of the same concept across curriculum
positions. They require human confirmation (edge_nature assignment) before
being written to the edges table.

Usage:
    python src/build_graph.py
    python src/build_graph.py --export-candidates
    python src/build_graph.py --top N          # show top N load-bearing concepts
    python src/build_graph.py --concept "empire"   # trace a specific concept

Created: 2026-02-26
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import networkx as nx
from graph_builder import (
    TERM_ORDER,
    build_graph,
    curriculum_position,
    get_candidate_edges,
    graph_stats,
)


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def print_stats(stats: dict) -> None:
    """Print graph statistics to console. Created: 2026-02-26"""
    print("=" * 60)
    print("KNOWLEDGE GRAPH STATISTICS")
    print("=" * 60)
    print(f"Concept nodes:            {stats['concepts']}")
    print(f"Occurrence nodes:         {stats['occurrences']}")
    print(f"Confirmed edges:          {stats['confirmed_edges']}")
    print(f"Load-bearing concepts:    {stats['load_bearing_concepts']}")
    print(f"  (concepts with 2+ occurrences — have candidate edges)")
    print(f"Subjects:                 {', '.join(stats['subjects'])}")
    if stats['by_edge_type']:
        print()
        print("Confirmed edges by type:")
        for k, v in sorted(stats['by_edge_type'].items()):
            print(f"  {k:<30} {v}")
    if stats['by_edge_nature']:
        print()
        print("Confirmed edges by nature:")
        for k, v in sorted(stats['by_edge_nature'].items()):
            print(f"  {k:<30} {v}")
    print("=" * 60)


def print_top_concepts(G: nx.DiGraph, n: int) -> None:
    """
    Print the N concepts with the most occurrences.

    Created: 2026-02-26
    """
    concept_nodes = [
        (node, data)
        for node, data in G.nodes(data=True)
        if data.get('type') == 'concept'
    ]

    ranked = sorted(
        concept_nodes,
        key=lambda x: G.out_degree(x[0]),
        reverse=True
    )[:n]

    print(f"\nTop {n} load-bearing concepts (by occurrence count):")
    print(f"{'Term':<40} {'Occurrences':>12}")
    print("-" * 54)
    for node, data in ranked:
        occ_count = G.out_degree(node)
        print(f"{data['term']:<40} {occ_count:>12}")


def print_concept_trace(G: nx.DiGraph, search_term: str) -> None:
    """
    Print the curriculum trajectory of a specific concept.

    Created: 2026-02-26
    """
    # Find matching concept nodes (case-insensitive)
    matches = [
        (node, data)
        for node, data in G.nodes(data=True)
        if data.get('type') == 'concept'
        and search_term.lower() in data.get('term', '').lower()
    ]

    if not matches:
        print(f"No concept found matching '{search_term}'")
        return

    for concept_node, concept_data in matches:
        print(f"\nConcept: '{concept_data['term']}'")
        print("-" * 60)

        # Get occurrence nodes for this concept
        occ_nodes = [
            (succ, G.nodes[succ])
            for succ in G.successors(concept_node)
            if G.nodes[succ].get('type') == 'occurrence'
        ]

        if not occ_nodes:
            print("  No occurrences found")
            continue

        # Sort by curriculum position
        occ_sorted = sorted(
            occ_nodes,
            key=lambda x: x[1].get('curriculum_pos', (0, 0, 0))
        )

        for occ_id, occ_data in occ_sorted:
            intro_marker = '[INTRO]' if occ_data.get('is_introduction') else '[recur]'
            chapter = occ_data.get('chapter') or '—'
            context = occ_data.get('term_in_context') or ''
            if len(context) > 80:
                context = context[:77] + '...'
            print(
                f"  {intro_marker} Y{occ_data['year']} {occ_data['term_period']} "
                f"{occ_data['subject']:<12} | {occ_data['unit']:<35} | "
                f"Ch: {chapter}"
            )
            if context:
                print(f"           \"{context}\"")

        # Show confirmed outgoing edges from these occurrences
        confirmed = [
            (u, v, G.edges[u, v])
            for u, v in G.edges()
            if u.startswith('occ_') and v.startswith('occ_')
            and G.edges[u, v].get('edge_nature')
            and G.nodes[u].get('concept_id') == concept_data['concept_id']
        ]
        if confirmed:
            print(f"  Confirmed edges: {len(confirmed)}")


# =============================================================================
# CANDIDATE EDGE EXPORT
# =============================================================================

def export_candidates(candidates: list[dict], output_path: Path) -> None:
    """
    Write candidate edges to CSV for human review.

    Columns include a blank 'edge_nature' for the reviewer to fill in:
      reinforcement, extension, cross_subject_application

    Created: 2026-02-26
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        'term',
        'from_occurrence_id', 'from_subject', 'from_year', 'from_term',
        'from_unit', 'from_chapter',
        'to_occurrence_id', 'to_subject', 'to_year', 'to_term',
        'to_unit', 'to_chapter',
        'edge_type',
        'edge_nature',      # reviewer fills in: reinforcement / extension / cross_subject_application
        'confirmed_by',     # reviewer fills in: their name
        'already_confirmed',
        'notes',
    ]

    pending = [c for c in candidates if not c['already_confirmed']]
    already = [c for c in candidates if c['already_confirmed']]

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for c in pending + already:
            writer.writerow({**c, 'edge_nature': '', 'confirmed_by': '', 'notes': ''})

    print(f"  Candidate edges written to: {output_path}")
    print(f"  Pending review:   {len(pending)}")
    print(f"  Already confirmed: {len(already)}")


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description='Build OWL knowledge graph and report statistics.'
    )
    parser.add_argument(
        '--export-candidates', action='store_true',
        help='Export candidate edges to output/candidate_edges.csv'
    )
    parser.add_argument(
        '--top', type=int, default=0, metavar='N',
        help='Print top N load-bearing concepts'
    )
    parser.add_argument(
        '--concept', type=str, default='',
        help='Trace curriculum trajectory of a concept (partial match)'
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    db_path = project_root / "db" / "owl_knowledge_map.db"

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}")
        return 1

    print("Building knowledge graph...")
    G = build_graph(db_path)

    stats = graph_stats(G)
    print_stats(stats)

    if args.top:
        print_top_concepts(G, args.top)

    if args.concept:
        print_concept_trace(G, args.concept)

    if args.export_candidates:
        print()
        print("Generating candidate edges...")
        candidates = get_candidate_edges(db_path)

        within = sum(1 for c in candidates if c['edge_type'] == 'within_subject')
        cross  = sum(1 for c in candidates if c['edge_type'] == 'cross_subject')
        print(f"  Total candidates:    {len(candidates)}")
        print(f"  Within-subject:      {within}")
        print(f"  Cross-subject:       {cross}")

        output_path = project_root / "output" / "candidate_edges.csv"
        export_candidates(candidates, output_path)

    return 0


if __name__ == "__main__":
    exit(main())
