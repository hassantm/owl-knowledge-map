# GraphForm — Plotly network graph (stub until edges are confirmed)
# Created: 2026-02-26

from anvil import *
import anvil.server


class GraphForm(Form):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._build_ui()
        self._check_and_load()

    def _build_ui(self):
        self.add_component(Label(text='Knowledge Graph', bold=True, font_size=20))

        # Filters
        fr = ColumnPanel()
        opts = anvil.server.call('get_filter_options')

        self._dd_subject = DropDown(
            items=[('All Subjects', None)] + [(s, s) for s in opts['subjects']]
        )
        fr.add_component(self._dd_subject, full_width_row=False)

        years = opts.get('years', [3, 4, 5, 6])
        year_items = [(f'Year {y}', y) for y in years]

        self._dd_year_from = DropDown(items=year_items)
        if years:
            self._dd_year_from.selected_value = min(years)
        fr.add_component(Label(text='From', foreground='#64748B'), full_width_row=False)
        fr.add_component(self._dd_year_from, full_width_row=False)

        self._dd_year_to = DropDown(items=year_items)
        if years:
            self._dd_year_to.selected_value = max(years)
        fr.add_component(Label(text='To', foreground='#64748B'), full_width_row=False)
        fr.add_component(self._dd_year_to, full_width_row=False)

        self._dd_etype = DropDown(items=[
            ('All Edge Types', None),
            ('Within Subject', 'within_subject'),
            ('Cross Subject', 'cross_subject'),
        ])
        fr.add_component(self._dd_etype, full_width_row=False)

        self._btn_rebuild = Button(text='Rebuild Graph', role='primary-color', enabled=False)
        self._btn_rebuild.set_event_handler('click', self._on_rebuild)
        fr.add_component(self._btn_rebuild, full_width_row=False)
        self.add_component(fr)

        # Stub message
        self._lbl_stub = Label(
            text='The graph will appear here once edges have been confirmed. '
                 'Use Edge Review to confirm connections.',
            foreground='#94A3B8', font_size=14
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
            self._dd_subject.selected_value,
            self._dd_year_from.selected_value,
            self._dd_year_to.selected_value,
            self._dd_etype.selected_value,
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
