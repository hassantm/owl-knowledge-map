# EdgeReviewForm — Edge confirmation workflow (core reviewer tool)
# Updated: 2026-02-27 — removed anvil_extras and LinearProgress; separate confirm handlers

from anvil import *
import anvil.server

NATURE_COLOURS = {
    'reinforcement': '#22C55E',
    'extension': '#3B82F6',
    'cross_subject_application': '#F59E0B',
}
EDGE_TYPE_COLOURS = {'within_subject': '#3B82F6', 'cross_subject': '#F59E0B'}


def _chip(text, background='#888', foreground='white'):
    lbl = Label(background=background, foreground=foreground, font_size=11, bold=True)
    lbl.text = ' ' + text + ' ' if text else ''
    return lbl


class EdgeReviewForm(ColumnPanel):
    def __init__(self, **properties):
        super().__init__(**properties)
        self._all_edges = []
        self._filtered = []
        self._idx = 0
        self._confirmed_count = 0
        self._total_candidates = 0
        self._edge_type_filter = None
        self._subject_filter = None
        self._current_edge = None
        self._build_ui()
        self._initial_load()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------

    def _build_ui(self):
        self._lbl_header = Label(text='Edge Review', bold=True, font_size=18)
        self.add_component(self._lbl_header)

        # Filters
        fr = ColumnPanel()
        self._dd_etype = DropDown(
            items=[('All Types', None), ('Within Subject', 'within_subject'), ('Cross Subject', 'cross_subject')],
            include_placeholder=True, placeholder='All Types',
        )
        self._dd_etype.set_event_handler('change', self._on_etype_filter)
        fr.add_component(self._dd_etype, full_width_row=False)

        opts = anvil.server.call('get_filter_options')
        self._dd_subj = DropDown(
            items=[('All Subjects', None)] + [(s, s) for s in opts['subjects']],
            include_placeholder=True, placeholder='All Subjects',
        )
        self._dd_subj.set_event_handler('change', self._on_subj_filter)
        fr.add_component(self._dd_subj, full_width_row=False)
        self.add_component(fr)

        # Progress label (replaces LinearProgress which is unavailable in Classic)
        self._lbl_progress = Label(text='', foreground='#64748B')
        self.add_component(self._lbl_progress)

        # Review panel: from | arrow+badge | to
        self._panel_review = ColumnPanel()
        review_cols = ColumnPanel()

        # LEFT — from occurrence
        self._left = ColumnPanel(background='#F8FAFC')
        self._lbl_from_heading = Label(text='FROM', bold=True, foreground='#64748B', font_size=11)
        self._lbl_from_term = Label(text='', bold=True, font_size=20)
        self._lbl_from_loc = Label(text='', foreground='#64748B')
        self._lbl_from_ch = Label(text='', foreground='#94A3B8', font_size=11)
        self._lbl_from_ctx = Label(text='', italic=True, foreground='#475569', font_size=12)
        for c in [self._lbl_from_heading, self._lbl_from_term,
                  self._lbl_from_loc, self._lbl_from_ch, self._lbl_from_ctx]:
            self._left.add_component(c)
        review_cols.add_component(self._left, full_width_row=False)

        # MIDDLE — arrow + edge-type badge
        mid = ColumnPanel()
        mid.add_component(Label(text='->', bold=True, font_size=22))
        self._lbl_edge_badge = Label(text='', bold=True, font_size=11, foreground='white')
        mid.add_component(self._lbl_edge_badge)
        review_cols.add_component(mid, full_width_row=False)

        # RIGHT — to occurrence
        self._right = ColumnPanel(background='#F8FAFC')
        self._lbl_to_heading = Label(text='TO', bold=True, foreground='#64748B', font_size=11)
        self._lbl_to_term = Label(text='', bold=True, font_size=20)
        self._lbl_to_loc = Label(text='', foreground='#64748B')
        self._lbl_to_ch = Label(text='', foreground='#94A3B8', font_size=11)
        self._lbl_to_ctx = Label(text='', italic=True, foreground='#475569', font_size=12)
        for c in [self._lbl_to_heading, self._lbl_to_term,
                  self._lbl_to_loc, self._lbl_to_ch, self._lbl_to_ctx]:
            self._right.add_component(c)
        review_cols.add_component(self._right, full_width_row=False)

        self._panel_review.add_component(review_cols)

        # Decision row — one handler per button, no .tag needed
        dec = ColumnPanel()
        self._tb_reviewer = TextBox(placeholder='Your name...')
        dec.add_component(self._tb_reviewer, full_width_row=False)

        btn_r = Button(text='Reinforcement', role='primary-color', background='#22C55E')
        btn_r.set_event_handler('click', self.btn_reinforcement_click)
        dec.add_component(btn_r, full_width_row=False)

        btn_e = Button(text='Extension', role='primary-color', background='#3B82F6')
        btn_e.set_event_handler('click', self.btn_extension_click)
        dec.add_component(btn_e, full_width_row=False)

        btn_c = Button(text='Cross-subject Application', role='primary-color', background='#F59E0B')
        btn_c.set_event_handler('click', self.btn_cross_subject_click)
        dec.add_component(btn_c, full_width_row=False)

        btn_skip = Button(text='Skip ->', role='secondary-color')
        btn_skip.set_event_handler('click', self.btn_skip_click)
        dec.add_component(btn_skip, full_width_row=False)
        self._panel_review.add_component(dec)

        # Navigation
        nav = ColumnPanel()
        self._btn_prev = Button(text='<- Prev', role='secondary-color', enabled=False)
        self._btn_prev.set_event_handler('click', self.btn_prev_click)
        nav.add_component(self._btn_prev, full_width_row=False)
        self._btn_next = Button(text='Next ->', role='secondary-color', enabled=False)
        self._btn_next.set_event_handler('click', self.btn_next_click)
        nav.add_component(self._btn_next, full_width_row=False)
        self._panel_review.add_component(nav)

        self.add_component(self._panel_review)

    # -------------------------------------------------------------------------
    # Data loading
    # -------------------------------------------------------------------------

    def _initial_load(self):
        result = anvil.server.call('get_candidate_edges_list', None, None, True, 0, 300)
        all_rows = result.get('rows', [])
        self._total_candidates = result.get('total', 0)
        self._confirmed_count = sum(1 for r in all_rows if r.get('already_confirmed'))
        self._all_edges = [r for r in all_rows if not r.get('already_confirmed')]
        self._apply_filters()

    def _apply_filters(self):
        edges = list(self._all_edges)
        if self._edge_type_filter:
            edges = [e for e in edges if e['edge_type'] == self._edge_type_filter]
        if self._subject_filter:
            edges = [e for e in edges
                     if e['from_subject'] == self._subject_filter
                     or e['to_subject'] == self._subject_filter]
        self._filtered = edges
        self._idx = 0
        self._display()

    def _display(self):
        total = len(self._filtered)
        pct = (self._confirmed_count / self._total_candidates * 100) if self._total_candidates else 0
        self._lbl_progress.text = (
            str(self._confirmed_count) + ' confirmed  |  '
            + str(len(self._all_edges)) + ' remaining  |  '
            + str(int(pct)) + '%'
        )

        if total == 0:
            self._lbl_header.text = (
                'Edge Review -- ' + str(self._confirmed_count) + '/'
                + str(self._total_candidates)
                + ' confirmed. No unconfirmed edges match filters.'
            )
            self._panel_review.visible = False
            return

        self._panel_review.visible = True
        edge = self._filtered[self._idx]
        self._current_edge = edge

        self._lbl_header.text = (
            'Edge Review  |  '
            + str(self._confirmed_count) + '/' + str(self._total_candidates) + ' confirmed  |  '
            + str(self._idx + 1) + ' of ' + str(total)
        )

        fr = anvil.server.call('get_term_detail', edge['from_occurrence_id'])
        to = anvil.server.call('get_term_detail', edge['to_occurrence_id'])

        def loc(d):
            if not d:
                return ''
            return (str(d['subject']) + '  |  Y' + str(d['year']) + ' ' + str(d['term_period'])
                    + '  |  ' + str(d['unit']))

        self._lbl_from_term.text = (fr or {}).get('term', '')
        self._lbl_from_loc.text = loc(fr)
        self._lbl_from_ch.text = (fr or {}).get('chapter') or ''
        self._lbl_from_ctx.text = (fr or {}).get('term_in_context') or '(no context)'

        etype = edge.get('edge_type', '')
        self._lbl_edge_badge.text = ' ' + etype.replace('_', ' ') + ' '
        self._lbl_edge_badge.background = EDGE_TYPE_COLOURS.get(etype, '#888')

        self._lbl_to_term.text = (to or {}).get('term', '')
        self._lbl_to_loc.text = loc(to)
        self._lbl_to_ch.text = (to or {}).get('chapter') or ''
        self._lbl_to_ctx.text = (to or {}).get('term_in_context') or '(no context)'

        self._btn_prev.enabled = self._idx > 0
        self._btn_next.enabled = self._idx < total - 1

    # -------------------------------------------------------------------------
    # Confirm handlers — one per edge_nature, no .tag dependency
    # -------------------------------------------------------------------------

    def _confirm(self, edge_nature):
        reviewer = (self._tb_reviewer.text or '').strip()
        if not reviewer:
            alert('Enter your name before confirming.')
            return
        edge = self._current_edge
        result = anvil.server.call(
            'confirm_edge',
            edge['from_occurrence_id'], edge['to_occurrence_id'],
            edge_nature, reviewer
        )
        if result.get('ok'):
            Notification(
                'Confirmed: ' + edge_nature.replace('_', ' '),
                style='success', timeout=2
            ).show()
            self._confirmed_count += 1
            self._all_edges = [
                e for e in self._all_edges
                if not (e['from_occurrence_id'] == edge['from_occurrence_id']
                        and e['to_occurrence_id'] == edge['to_occurrence_id'])
            ]
            self._apply_filters()
        else:
            alert('Error: ' + str(result.get('message')))

    def btn_reinforcement_click(self, **e):
        self._confirm('reinforcement')

    def btn_extension_click(self, **e):
        self._confirm('extension')

    def btn_cross_subject_click(self, **e):
        self._confirm('cross_subject_application')

    def btn_skip_click(self, **e):
        if self._idx < len(self._filtered) - 1:
            self._idx += 1
            self._display()

    def btn_prev_click(self, **e):
        if self._idx > 0:
            self._idx -= 1
            self._display()

    def btn_next_click(self, **e):
        self.btn_skip_click(**e)

    def _on_etype_filter(self, **e):
        self._edge_type_filter = self._dd_etype.selected_value
        self._apply_filters()

    def _on_subj_filter(self, **e):
        self._subject_filter = self._dd_subj.selected_value
        self._apply_filters()
