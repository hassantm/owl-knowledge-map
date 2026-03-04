# owl_pages.py — All page form classes in one importable client module.
# MainForm imports from here. Forms (DashboardForm etc.) in the IDE are unused stubs.
# Created: 2026-03-03 — consolidated to avoid cross-form import errors in Classic.

from anvil import *
import anvil.users
import anvil.server

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SUBJECT_COLOURS = {
    'History': '#3B82F6',
    'Geography': '#22C55E',
    'Religion': '#EF4444',
}
NATURE_COLOURS = {
    'reinforcement': '#22C55E',
    'extension': '#3B82F6',
    'application': '#F59E0B',
}
EDGE_TYPE_COLOURS = {'within_subject': '#3B82F6', 'cross_subject': '#F59E0B'}


def _chip(text, background='#888', foreground='white'):
    lbl = Label(background=background, foreground=foreground, font_size=11, bold=True)
    lbl.text = ' ' + text + ' ' if text else ''
    return lbl


# ---------------------------------------------------------------------------
# DashboardForm
# ---------------------------------------------------------------------------

class DashboardForm(ColumnPanel):
    def __init__(self, **properties):
        super().__init__(**properties)
        self.add_component(Label(text='Dashboard', bold=True, font_size=20))
        self._load()

    def _load(self):
        stats = anvil.server.call('get_dashboard_stats')
        load_bearing = anvil.server.call('get_load_bearing_concepts', 2)
        candidates = anvil.server.call('get_candidate_edges_list', None, None, True, 0, 200)
        words_per_year = anvil.server.call('get_words_per_year')
        all_rows = candidates.get('rows', [])
        pending = sum(1 for r in all_rows if not r.get('already_confirmed'))

        # --- Stat cards ---
        stat_row = ColumnPanel()
        for label, value, colour in [
            ('Concepts', stats['concepts'], '#3B82F6'),
            ('Occurrences', stats['occurrences'], '#22C55E'),
            ('Edges Confirmed', stats['confirmed_edges'], '#6366F1'),
            ('Pending Review', pending, '#F59E0B'),
        ]:
            card = ColumnPanel(background='#F8FAFC')
            card.add_component(Label(text=str(value), bold=True, font_size=32, foreground=colour))
            card.add_component(Label(text=label, foreground='#64748B', font_size=12))
            stat_row.add_component(card, full_width_row=False)
        self.add_component(stat_row)

        # --- Chart: occurrences by subject ---
        by_subject = stats.get('by_subject', {})
        plot1 = Plot()
        plot1.data = [{
            'type': 'bar',
            'x': list(by_subject.keys()),
            'y': list(by_subject.values()),
            'marker': {'color': [SUBJECT_COLOURS.get(s, '#6366F1') for s in by_subject]},
        }]
        plot1.layout = {
            'title': 'Occurrences by Subject', 'height': 300,
            'margin': {'t': 40, 'b': 40, 'l': 50, 'r': 20},
            'plot_bgcolor': 'white',
        }
        self.add_component(plot1, full_width_row=False)

        # --- Chart: top 15 load-bearing concepts ---
        top15 = list(reversed(load_bearing[:15]))
        plot2 = Plot()
        plot2.data = [{
            'type': 'bar', 'orientation': 'h',
            'x': [r['occ_count'] for r in top15],
            'y': [r['term'] for r in top15],
            'marker': {'color': '#6366F1'},
        }]
        plot2.layout = {
            'title': 'Top 15 Load-Bearing Concepts', 'height': 320,
            'margin': {'t': 40, 'b': 20, 'l': 170, 'r': 20},
            'plot_bgcolor': 'white',
        }
        self.add_component(plot2, full_width_row=False)

        # --- Chart: edge type breakdown ---
        within = sum(1 for r in all_rows if r.get('edge_type') == 'within_subject')
        cross = sum(1 for r in all_rows if r.get('edge_type') == 'cross_subject')
        plot3 = Plot()
        plot3.data = [{
            'type': 'pie', 'hole': 0.35,
            'labels': ['Within Subject', 'Cross Subject'],
            'values': [within, cross],
            'marker': {'colors': ['#3B82F6', '#F59E0B']},
        }]
        plot3.layout = {
            'title': 'Candidate Edge Types', 'height': 300,
            'margin': {'t': 40, 'b': 20, 'l': 20, 'r': 20},
        }
        self.add_component(plot3, full_width_row=False)

        # --- Chart: new vocabulary introduced per year, by subject ---
        years = [3, 4, 5, 6]
        plot4 = Plot()
        plot4.data = [
            {
                'type': 'bar',
                'name': subj,
                'x': ['Year ' + str(y) for y in years],
                'y': [words_per_year.get(subj, {}).get(y, 0) for y in years],
                'marker': {'color': SUBJECT_COLOURS.get(subj, '#888')},
            }
            for subj in ['History', 'Geography', 'Religion']
        ]
        plot4.layout = {
            'title': 'New Vocabulary Introduced per Year',
            'height': 320,
            'barmode': 'group',
            'margin': {'t': 40, 'b': 40, 'l': 50, 'r': 20},
            'plot_bgcolor': 'white',
        }
        self.add_component(plot4, full_width_row=False)

        # --- Review CTA (reviewer only) ---
        user = anvil.users.get_user()
        if user and user['role'] == 'reviewer':
            btn = Button(text='Start Edge Review ->', role='primary-color')
            btn.set_event_handler('click', lambda **e: get_open_form()._nav_to('edge_review'))
            self.add_component(btn)


# ---------------------------------------------------------------------------
# BrowserForm
# ---------------------------------------------------------------------------

class BrowserForm(ColumnPanel):
    def __init__(self, **properties):
        super().__init__(**properties)
        self._page = 0
        self._page_size = 50
        self._subject = None
        self._year = None
        self._term = None
        self._search = None
        self._build_ui()
        self._load_filters()
        self._load()

    def _build_ui(self):
        self.add_component(Label(text='Browse Corpus', bold=True, font_size=20))

        fr = ColumnPanel()
        self._dd_subject = DropDown(include_placeholder=True, placeholder='All Subjects')
        self._dd_subject.set_event_handler('change', self._on_subject)
        fr.add_component(self._dd_subject, full_width_row=False)

        self._dd_year = DropDown(include_placeholder=True, placeholder='All Years')
        self._dd_year.set_event_handler('change', self._on_year)
        fr.add_component(self._dd_year, full_width_row=False)

        self._dd_term = DropDown(include_placeholder=True, placeholder='All Terms')
        self._dd_term.set_event_handler('change', self._on_term)
        fr.add_component(self._dd_term, full_width_row=False)

        self._tb_search = TextBox(placeholder='Search term...')
        self._tb_search.set_event_handler('lost_focus', self._on_search)
        self._tb_search.set_event_handler('pressed_enter', self._on_search)
        fr.add_component(self._tb_search, full_width_row=False)
        self.add_component(fr)

        self._results = ColumnPanel()
        self.add_component(self._results)

        pg = ColumnPanel()
        self._btn_prev = Button(text='<- Prev', role='secondary-color', enabled=False)
        self._btn_prev.set_event_handler('click', self._on_prev)
        pg.add_component(self._btn_prev, full_width_row=False)

        self._lbl_pg = Label(text='')
        pg.add_component(self._lbl_pg, full_width_row=False)

        self._btn_next = Button(text='Next ->', role='secondary-color', enabled=False)
        self._btn_next.set_event_handler('click', self._on_next)
        pg.add_component(self._btn_next, full_width_row=False)
        self.add_component(pg)

    def _load_filters(self):
        opts = anvil.server.call('get_filter_options')
        self._dd_subject.items = [(s, s) for s in opts['subjects']]
        self._dd_year.items = [('Year ' + str(y), y) for y in opts['years']]
        self._dd_term.items = [(t, t) for t in opts['terms']]

    def _load(self):
        result = anvil.server.call(
            'get_corpus', self._subject, self._year, self._term,
            self._search, self._page, self._page_size
        )
        self._results.clear()
        for row in result['rows']:
            self._results.add_component(_BrowserRow(row))

        total = result['total']
        start = self._page * self._page_size + 1
        end = min((self._page + 1) * self._page_size, total)
        if total:
            self._lbl_pg.text = ('Page ' + str(self._page + 1)
                                 + '  |  ' + str(start) + '-' + str(end)
                                 + ' of ' + str(total))
        else:
            self._lbl_pg.text = 'No results'
        self._btn_prev.enabled = self._page > 0
        self._btn_next.enabled = end < total

    def _on_subject(self, **e):
        self._subject = self._dd_subject.selected_value
        self._page = 0
        self._load()

    def _on_year(self, **e):
        self._year = self._dd_year.selected_value
        self._page = 0
        self._load()

    def _on_term(self, **e):
        self._term = self._dd_term.selected_value
        self._page = 0
        self._load()

    def _on_search(self, **e):
        q = (self._tb_search.text or '').strip() or None
        if q != self._search:
            self._search = q
            self._page = 0
            self._load()

    def _on_prev(self, **e):
        self._page -= 1
        self._load()

    def _on_next(self, **e):
        self._page += 1
        self._load()


class _BrowserRow(ColumnPanel):
    def __init__(self, item):
        super().__init__(background='white')
        self._item = item
        is_intro = bool(item.get('is_introduction'))
        self.add_component(
            _chip('INTRO' if is_intro else 'recur',
                  background='#22C55E' if is_intro else '#94A3B8'),
            full_width_row=False
        )
        lnk = Link(text=item.get('term', ''), bold=True)
        lnk.set_event_handler('click', self._on_click)
        self.add_component(lnk, full_width_row=False)
        self.add_component(
            Label(
                text=('Y' + str(item.get('year')) + ' ' + str(item.get('term_period', ''))
                      + '  |  ' + str(item.get('subject', ''))
                      + '  |  ' + str(item.get('unit', ''))),
                foreground='#64748B', font_size=11
            ),
            full_width_row=False
        )

    def _on_click(self, **e):
        cid = self._item.get('concept_id')
        if cid:
            get_open_form()._nav_to('concept_detail', concept_id=cid)


# ---------------------------------------------------------------------------
# EdgeReviewForm
# ---------------------------------------------------------------------------

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

    def _build_ui(self):
        self._lbl_header = Label(text='Edge Review', bold=True, font_size=18)
        self.add_component(self._lbl_header)

        fr = ColumnPanel()
        self._dd_etype = DropDown(
            items=[('All Types', None), ('Within Subject', 'within_subject'), ('Cross Subject', 'cross_subject')],
        )
        self._dd_etype.set_event_handler('change', self._on_etype_filter)
        fr.add_component(self._dd_etype, full_width_row=False)

        opts = anvil.server.call('get_filter_options')
        self._dd_subj = DropDown(
            items=[('All Subjects', None)] + [(s, s) for s in opts['subjects']],
        )
        self._dd_subj.set_event_handler('change', self._on_subj_filter)
        fr.add_component(self._dd_subj, full_width_row=False)
        self.add_component(fr)

        self._lbl_progress = Label(text='', foreground='#64748B')
        self.add_component(self._lbl_progress)

        self._panel_review = ColumnPanel()
        review_cols = ColumnPanel()

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

        mid = ColumnPanel()
        mid.add_component(Label(text='->', bold=True, font_size=22))
        self._lbl_edge_badge = Label(text='', bold=True, font_size=11, foreground='white')
        mid.add_component(self._lbl_edge_badge)
        review_cols.add_component(mid, full_width_row=False)

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

        dec = ColumnPanel()
        self._tb_reviewer = TextBox(placeholder='Your name...')
        dec.add_component(self._tb_reviewer, full_width_row=False)

        btn_r = Button(text='Reinforcement', role='primary-color', background='#22C55E')
        btn_r.set_event_handler('click', self.btn_reinforcement_click)
        dec.add_component(btn_r, full_width_row=False)

        btn_e = Button(text='Extension', role='primary-color', background='#3B82F6')
        btn_e.set_event_handler('click', self.btn_extension_click)
        dec.add_component(btn_e, full_width_row=False)

        btn_c = Button(text='Application', role='primary-color', background='#F59E0B')
        btn_c.set_event_handler('click', self.btn_cross_subject_click)
        dec.add_component(btn_c, full_width_row=False)

        btn_skip = Button(text='Skip ->', role='secondary-color')
        btn_skip.set_event_handler('click', self.btn_skip_click)
        dec.add_component(btn_skip, full_width_row=False)
        self._panel_review.add_component(dec)

        nav = ColumnPanel()
        self._btn_prev = Button(text='<- Prev', role='secondary-color', enabled=False)
        self._btn_prev.set_event_handler('click', self.btn_prev_click)
        nav.add_component(self._btn_prev, full_width_row=False)
        self._btn_next = Button(text='Next ->', role='secondary-color', enabled=False)
        self._btn_next.set_event_handler('click', self.btn_next_click)
        nav.add_component(self._btn_next, full_width_row=False)
        self._panel_review.add_component(nav)

        self.add_component(self._panel_review)

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
            Notification('Confirmed: ' + edge_nature.replace('_', ' '),
                         style='success', timeout=2).show()
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
        self._confirm('application')

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


# ---------------------------------------------------------------------------
# ConceptDetailForm
# ---------------------------------------------------------------------------

class ConceptDetailForm(ColumnPanel):
    def __init__(self, concept_id=None, **properties):
        super().__init__(**properties)

        btn_back = Button(text='<- Back to Browse', role='secondary-color')
        btn_back.set_event_handler('click', lambda **e: get_open_form()._nav_to('browser'))
        self.add_component(btn_back)

        if concept_id is None:
            self.add_component(Label(text='No concept selected.', foreground='#94A3B8'))
            return

        self._load(concept_id)

    def _load(self, concept_id):
        data = anvil.server.call('get_concept_detail', concept_id)
        if not data:
            self.add_component(Label(text='Concept ' + str(concept_id) + ' not found.'))
            return

        concept = data['concept']
        occurrences = data['occurrences']
        edges = data['edges']

        subj_colour = SUBJECT_COLOURS.get(concept.get('subject_area', ''), '#6366F1')
        self.add_component(Label(text=concept['term'], bold=True, font_size=24))
        self.add_component(_chip(
            text=concept.get('subject_area') or 'All subjects',
            background=subj_colour,
        ))
        first_year = str(concept.get('first_year', ''))
        last_year = str(concept.get('last_year', ''))
        self.add_component(Label(
            text=str(len(occurrences)) + ' occurrence(s)  |  Y' + first_year + '-Y' + last_year,
            foreground='#64748B', font_size=12
        ))

        self.add_component(Label(text='Curriculum Timeline', bold=True, font_size=16))
        for occ in occurrences:
            self.add_component(_OccurrenceRow(occ))

        if edges:
            self.add_component(Label(
                text='Confirmed Edges (' + str(len(edges)) + ')',
                bold=True, font_size=16
            ))
            for edge in edges:
                self.add_component(_EdgeRow(edge))
        else:
            self.add_component(Label(
                text='No confirmed edges yet -- use Edge Review to confirm connections.',
                foreground='#94A3B8', font_size=12,
            ))


class _OccurrenceRow(ColumnPanel):
    def __init__(self, item):
        super().__init__(background='#F8FAFC')
        is_intro = bool(item.get('is_introduction'))

        row = ColumnPanel()
        row.add_component(
            _chip('INTRO' if is_intro else 'recur',
                  background='#22C55E' if is_intro else '#94A3B8'),
            full_width_row=False
        )
        row.add_component(
            Label(
                text=('Y' + str(item.get('year')) + ' ' + str(item.get('term'))
                      + '  |  ' + str(item.get('subject'))
                      + '  |  ' + str(item.get('unit', ''))),
                bold=True,
            ),
            full_width_row=False
        )
        row.add_component(
            Label(text=item.get('chapter') or '', foreground='#94A3B8', font_size=11),
            full_width_row=False
        )
        self.add_component(row)

        ctx = item.get('term_in_context') or ''
        if ctx:
            preview = (ctx[:220] + '...') if len(ctx) > 220 else ctx
            self.add_component(Label(text=preview, italic=True, foreground='#475569', font_size=12))


class _EdgeRow(ColumnPanel):
    def __init__(self, item):
        super().__init__()
        nature = item.get('edge_nature') or ''
        colour = NATURE_COLOURS.get(nature, '#6366F1')

        row = ColumnPanel()
        row.add_component(
            Label(text=('Y' + str(item.get('from_year')) + ' ' + str(item.get('from_term_period'))
                        + '  |  ' + str(item.get('from_unit', '')))),
            full_width_row=False
        )
        row.add_component(Label(text='->', bold=True, font_size=16), full_width_row=False)
        row.add_component(
            Label(text=('Y' + str(item.get('to_year')) + ' ' + str(item.get('to_term_period'))
                        + '  |  ' + str(item.get('to_unit', '')))),
            full_width_row=False
        )
        row.add_component(
            _chip(text=nature.replace('_', ' ').title(), background=colour),
            full_width_row=False
        )
        self.add_component(row)

        confirmed_by = item.get('confirmed_by') or ''
        confirmed_date = item.get('confirmed_date') or ''
        if confirmed_by:
            self.add_component(Label(
                text='Confirmed by ' + confirmed_by + ' on ' + confirmed_date,
                foreground='#94A3B8', font_size=11,
            ))


# ---------------------------------------------------------------------------
# GraphForm
# ---------------------------------------------------------------------------

class GraphForm(ColumnPanel):
    def __init__(self, **properties):
        super().__init__(**properties)
        self._build_ui()
        self._check_and_load()

    def _build_ui(self):
        self.add_component(Label(text='Knowledge Graph', bold=True, font_size=20))

        fr = ColumnPanel()
        opts = anvil.server.call('get_filter_options')

        self._dd_subject = DropDown(
            items=[('All Subjects', None)] + [(s, s) for s in opts['subjects']],
        )
        fr.add_component(self._dd_subject, full_width_row=False)

        years = opts.get('years', [3, 4, 5, 6])
        year_items = [('Year ' + str(y), y) for y in years]

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

        self._dd_etype = DropDown(
            items=[
                ('All Edge Types', None),
                ('Within Subject', 'within_subject'),
                ('Cross Subject', 'cross_subject'),
            ],
        )
        fr.add_component(self._dd_etype, full_width_row=False)

        self._btn_rebuild = Button(text='Rebuild Graph', role='primary-color', enabled=False)
        self._btn_rebuild.set_event_handler('click', self._on_rebuild)
        fr.add_component(self._btn_rebuild, full_width_row=False)
        self.add_component(fr)

        self._lbl_stub = Label(
            text='The graph will appear here once edges have been confirmed. '
                 'Use Edge Review to confirm connections.',
            foreground='#94A3B8', font_size=14,
        )
        self.add_component(self._lbl_stub)

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
