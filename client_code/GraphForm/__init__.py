# GraphForm — Plotly network graph (stub until edges are confirmed)
# Updated: 2026-02-27 — M3 components

from anvil import *
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server
import m3.components as m3


class GraphForm(Form):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._build_ui()
        self._check_and_load()

    def _build_ui(self):
        self.add_component(m3.Label(text='Knowledge Graph', bold=True, font_size=20))

        # Filters
        fr = ColumnPanel()
        opts = anvil.server.call('get_filter_options')

        self._dd_subject = m3.DropdownMenu(
            items=[('All Subjects', None)] + [(s, s) for s in opts['subjects']],
            placeholder='All Subjects',
        )
        fr.add_component(self._dd_subject, full_width_row=False)

        years = opts.get('years', [3, 4, 5, 6])
        year_items = [(f'Year {y}', y) for y in years]

        self._dd_year_from = m3.DropdownMenu(items=year_items, placeholder='Year from')
        if years:
            self._dd_year_from.value = min(years)
        fr.add_component(m3.Label(text='From', foreground='#64748B'), full_width_row=False)
        fr.add_component(self._dd_year_from, full_width_row=False)

        self._dd_year_to = m3.DropdownMenu(items=year_items, placeholder='Year to')
        if years:
            self._dd_year_to.value = max(years)
        fr.add_component(m3.Label(text='To', foreground='#64748B'), full_width_row=False)
        fr.add_component(self._dd_year_to, full_width_row=False)

        self._dd_etype = m3.DropdownMenu(
            items=[
                ('All Edge Types', None),
                ('Within Subject', 'within_subject'),
                ('Cross Subject', 'cross_subject'),
            ],
            placeholder='All Edge Types',
        )
        fr.add_component(self._dd_etype, full_width_row=False)

        self._btn_rebuild = m3.Button(text='Rebuild Graph', role='filled-button', enabled=False)
        self._btn_rebuild.set_event_handler('click', self._on_rebuild)
        fr.add_component(self._btn_rebuild, full_width_row=False)
        self.add_component(fr)

        # Stub message
        self._lbl_stub = m3.Label(
            text='The graph will appear here once edges have been confirmed. '
                 'Use Edge Review to confirm connections.',
            foreground='#94A3B8', font_size=14,
        )
        self.add_component(self._lbl_stub)

        # Plot
        self._plot = Plot()
        self._plot.visible = False
        self._plot.set_event_handler('click', self._on_plot_click)
        self.add_component(self._plot)

    def _check_and_load(self):
        result = anvil.server.call('get_candidate_edges_list', None, None, True, 0, 10)
        has_confirmed = any(r.get('already_confirmed') for r in result.get('rows', []))
        if has_confirmed:
            self._lbl_stub.visible = False
            self._plot.visible = True
            self._btn_rebuild.enabled = True
            self._build_graph()

    def _build_graph(self):
        fig = anvil.server.call(
            'get_graph_figure',
            self._dd_subject.value,
            self._dd_year_from.value,
            self._dd_year_to.value,
            self._dd_etype.value,
        )
        if fig:
            self._plot.figure = fig

    def _on_rebuild(self, **e):
        self._build_graph()

    def _on_plot_click(self, points, **e):
        if not points:
            return
        pt = points[0]
        concept_id = pt.get('customdata') if isinstance(pt, dict) else None
        if concept_id is not None:
            get_open_form()._nav_to('concept_detail', concept_id=int(concept_id))
