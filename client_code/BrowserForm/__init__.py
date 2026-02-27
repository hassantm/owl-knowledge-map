# BrowserForm — Paginated corpus browser
# Updated: 2026-02-27 — M3 components + Chip badges

from anvil import *
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server
import m3.components as m3
from anvil_extras.components import Chip


class BrowserForm(Form):
    def __init__(self, **properties):
        self.init_components(**properties)
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
        self.add_component(m3.Label(text='Browse Corpus', bold=True, font_size=20))

        fr = ColumnPanel()

        self._dd_subject = m3.DropdownMenu(placeholder='All Subjects')
        self._dd_subject.set_event_handler('change', self._on_subject)
        fr.add_component(self._dd_subject, full_width_row=False)

        self._dd_year = m3.DropdownMenu(placeholder='All Years')
        self._dd_year.set_event_handler('change', self._on_year)
        fr.add_component(self._dd_year, full_width_row=False)

        self._dd_term = m3.DropdownMenu(placeholder='All Terms')
        self._dd_term.set_event_handler('change', self._on_term)
        fr.add_component(self._dd_term, full_width_row=False)

        self._tb_search = m3.TextBox(placeholder='Search term…')
        self._tb_search.set_event_handler('lost_focus', self._on_search)
        self._tb_search.set_event_handler('pressed_enter', self._on_search)
        fr.add_component(self._tb_search, full_width_row=False)

        self.add_component(fr)

        self._results = ColumnPanel()
        self.add_component(self._results)

        pg = ColumnPanel()
        self._btn_prev = m3.Button(text='← Prev', role='outlined-button', enabled=False)
        self._btn_prev.set_event_handler('click', self._on_prev)
        pg.add_component(self._btn_prev, full_width_row=False)

        self._lbl_pg = m3.Label(text='')
        pg.add_component(self._lbl_pg, full_width_row=False)

        self._btn_next = m3.Button(text='Next →', role='outlined-button', enabled=False)
        self._btn_next.set_event_handler('click', self._on_next)
        pg.add_component(self._btn_next, full_width_row=False)

        self.add_component(pg)

    def _load_filters(self):
        opts = anvil.server.call('get_filter_options')
        self._dd_subject.items = [(s, s) for s in opts['subjects']]
        self._dd_year.items = [(f'Year {y}', y) for y in opts['years']]
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
        self._lbl_pg.text = f"Page {self._page + 1}  ·  {start}–{end} of {total}" if total else "No results"
        self._btn_prev.enabled = self._page > 0
        self._btn_next.enabled = end < total

    def _on_subject(self, **e): self._subject = self._dd_subject.value; self._page = 0; self._load()
    def _on_year(self, **e): self._year = self._dd_year.value; self._page = 0; self._load()
    def _on_term(self, **e): self._term = self._dd_term.value; self._page = 0; self._load()
    def _on_search(self, **e):
        q = (self._tb_search.text or '').strip() or None
        if q != self._search:
            self._search = q; self._page = 0; self._load()
    def _on_prev(self, **e): self._page -= 1; self._load()
    def _on_next(self, **e): self._page += 1; self._load()


class _BrowserRow(ColumnPanel):
    """Inline row — Chip badge + term link + location."""

    def __init__(self, item):
        super().__init__(background='white')
        self._item = item

        is_intro = bool(item.get('is_introduction'))
        self.add_component(
            Chip(
                text='INTRO' if is_intro else 'recur',
                background='#22C55E' if is_intro else '#94A3B8',
                foreground='white',
            ),
            full_width_row=False
        )

        lnk = Link(text=item.get('term', ''), bold=True)
        lnk.set_event_handler('click', self._on_click)
        self.add_component(lnk, full_width_row=False)

        self.add_component(
            m3.Label(
                text=(f"Y{item.get('year')} {item.get('term_period')}  ·  "
                      f"{item.get('subject')}  ·  {item.get('unit', '')}"),
                foreground='#64748B', font_size=11
            ),
            full_width_row=False
        )

    def _on_click(self, **e):
        cid = self._item.get('concept_id')
        if cid:
            get_open_form()._nav_to('concept_detail', concept_id=cid)
