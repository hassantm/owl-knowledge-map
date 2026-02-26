"""
GraphForm — Plotly network diagram (Phase B; stub until edges are confirmed).

DESIGNER SETUP:
  Form type: ColumnPanel

  Filter row:
    dd_subject      : DropDown
    dd_year_from    : DropDown
    dd_year_to      : DropDown
    dd_edge_type    : DropDown
    btn_rebuild     : Button  text='Rebuild Graph', role='primary-color'

  Status label (shown when no edges confirmed):
    lbl_no_edges    : Label   foreground='#94A3B8', font_size=13

  Graph panel (hidden until edges confirmed):
    panel_graph     : ColumnPanel
    plot_graph      : Plot   (from Toolbox → Add-ons → Plot)

  Event handlers:
    btn_rebuild     → click → btn_rebuild_click
    plot_graph      → click → plot_graph_click

NOTE: The Plot component requires the Plotly service to be enabled.
      Enable it in the Anvil IDE: Settings → Add-ons → Plotly.

Created: 2026-02-26
"""

from ._anvil_designer import GraphFormTemplate
from anvil import *
import anvil.server


class GraphForm(GraphFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._setup_filters()
        self._check_edges_and_load()

    # -------------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------------

    def _setup_filters(self):
        opts = anvil.server.call('get_filter_options')
        self.dd_subject.items = (
            [('All Subjects', None)] + [(s, s) for s in opts['subjects']]
        )
        year_items = [(f'Year {y}', y) for y in opts['years']]
        self.dd_year_from.items = year_items
        self.dd_year_to.items = year_items
        if opts['years']:
            self.dd_year_from.selected_value = min(opts['years'])
            self.dd_year_to.selected_value = max(opts['years'])
        self.dd_edge_type.items = [
            ('All Edge Types', None),
            ('Within Subject', 'within_subject'),
            ('Cross Subject', 'cross_subject'),
        ]

    def _check_edges_and_load(self):
        """Show stub message or build graph depending on confirmed edges."""
        result = anvil.server.call(
            'get_candidate_edges_list',
            None, None, True, 0, 10
        )
        has_confirmed = any(
            r.get('already_confirmed') for r in result.get('rows', [])
        )

        if not has_confirmed:
            self.lbl_no_edges.text = (
                'The knowledge graph will appear here once edges have been confirmed. '
                'Use Edge Review to start confirming edges.'
            )
            self.lbl_no_edges.visible = True
            self.panel_graph.visible = False
            self.btn_rebuild.enabled = False
        else:
            self.lbl_no_edges.visible = False
            self.panel_graph.visible = True
            self.btn_rebuild.enabled = True
            self._build_graph()

    # -------------------------------------------------------------------------
    # Graph building
    # -------------------------------------------------------------------------

    def _build_graph(self):
        fig = anvil.server.call(
            'get_graph_figure',
            self.dd_subject.selected_value,
            self.dd_year_from.selected_value,
            self.dd_year_to.selected_value,
            self.dd_edge_type.selected_value,
        )
        if fig:
            self.plot_graph.figure = fig
        else:
            self.lbl_no_edges.text = 'No graph data returned. Check filters.'
            self.lbl_no_edges.visible = True

    def btn_rebuild_click(self, **event_args):
        self._build_graph()

    def plot_graph_click(self, points, **event_args):
        """Node click → ConceptDetailForm."""
        if not points:
            return
        # customdata contains concept_id (set in get_graph_figure)
        concept_id = points[0].get('customdata') if isinstance(points[0], dict) else None
        if concept_id is not None:
            get_open_form()._nav_to('concept_detail', concept_id=int(concept_id))
