"""
DashboardForm — Stats overview and Plotly charts.

DESIGNER SETUP:
  Form type: ColumnPanel

  Stat card labels (row of 4, use ColumnPanel with col=3 each):
    lbl_stat_concepts     : Label  large text, bold
    lbl_stat_occurrences  : Label  large text, bold
    lbl_stat_edges        : Label  large text, bold
    lbl_stat_pending      : Label  large text, bold

  Add descriptive sub-labels beneath each if desired (no event handlers needed).

  Plotly plots (add Plot components — from Toolbox → Add-ons → Plot):
    plot_by_subject       : Plot  (occurrences by subject bar)
    plot_top_concepts     : Plot  (top 15 concepts horizontal bar)
    plot_edge_types       : Plot  (within vs cross pie)

  Button (reviewer-only):
    btn_start_review      : Button  text='Start Edge Review →', role='primary-color'

  Event handlers:
    btn_start_review      → click → btn_start_review_click

Created: 2026-02-26
"""

from ._anvil_designer import DashboardFormTemplate
from anvil import *
import anvil.server
import anvil.users


class DashboardForm(DashboardFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._load()

    def _load(self):
        stats = anvil.server.call('get_dashboard_stats')
        load_bearing = anvil.server.call('get_load_bearing_concepts', 2)
        candidates = anvil.server.call(
            'get_candidate_edges_list',
            None, None,   # subject, edge_type
            True,         # include_confirmed
            0, 200        # page, page_size
        )

        # --- Stat cards ---
        self.lbl_stat_concepts.text = str(stats['concepts'])
        self.lbl_stat_occurrences.text = str(stats['occurrences'])
        self.lbl_stat_edges.text = str(stats['confirmed_edges'])

        all_rows = candidates.get('rows', [])
        pending = sum(1 for r in all_rows if not r.get('already_confirmed'))
        self.lbl_stat_pending.text = str(pending)

        # --- Plot: occurrences by subject (bar) ---
        by_subject = stats.get('by_subject', {})
        subject_colours = {
            'History': '#3B82F6',
            'Geography': '#22C55E',
            'Religion': '#EF4444',
        }
        colours = [subject_colours.get(s, '#6366F1') for s in by_subject.keys()]

        self.plot_by_subject.data = [{
            'type': 'bar',
            'x': list(by_subject.keys()),
            'y': list(by_subject.values()),
            'marker': {'color': colours},
        }]
        self.plot_by_subject.layout = {
            'title': 'Occurrences by Subject',
            'margin': {'t': 40, 'b': 60, 'l': 50, 'r': 20},
            'xaxis': {'title': ''},
            'yaxis': {'title': 'Count'},
            'plot_bgcolor': 'white',
        }

        # --- Plot: top 15 load-bearing concepts (horizontal bar) ---
        top15 = load_bearing[:15]
        reversed_top15 = list(reversed(top15))
        self.plot_top_concepts.data = [{
            'type': 'bar',
            'orientation': 'h',
            'x': [r['occ_count'] for r in reversed_top15],
            'y': [r['term'] for r in reversed_top15],
            'marker': {'color': '#6366F1'},
        }]
        self.plot_top_concepts.layout = {
            'title': 'Top 15 Load-Bearing Concepts',
            'margin': {'t': 40, 'b': 30, 'l': 180, 'r': 20},
            'xaxis': {'title': 'Occurrences'},
            'plot_bgcolor': 'white',
        }

        # --- Plot: candidate edge types (pie) ---
        within = sum(1 for r in all_rows if r.get('edge_type') == 'within_subject')
        cross = sum(1 for r in all_rows if r.get('edge_type') == 'cross_subject')
        self.plot_edge_types.data = [{
            'type': 'pie',
            'labels': ['Within Subject', 'Cross Subject'],
            'values': [within, cross],
            'marker': {'colors': ['#3B82F6', '#F59E0B']},
            'hole': 0.3,
        }]
        self.plot_edge_types.layout = {
            'title': 'Candidate Edge Types (all 169)',
            'margin': {'t': 40, 'b': 20, 'l': 20, 'r': 20},
        }

        # --- Role check for review button ---
        user = anvil.users.get_user()
        self.btn_start_review.visible = (
            user is not None and user.get('role') == 'reviewer'
        )

    def btn_start_review_click(self, **event_args):
        get_open_form()._nav_to('edge_review')
