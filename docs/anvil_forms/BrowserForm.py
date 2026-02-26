"""
BrowserForm — Paginated, filterable corpus browser.

DESIGNER SETUP:
  Form type: ColumnPanel

  Filter row (ColumnPanel with row layout):
    dd_subject     : DropDown   (include_placeholder=True, placeholder='All Subjects')
    dd_year        : DropDown   (include_placeholder=True, placeholder='All Years')
    dd_term        : DropDown   (include_placeholder=True, placeholder='All Terms')
    tb_search      : TextBox    placeholder='Search term…'

  Results:
    repeating_panel : RepeatingPanel  item_template=BrowserRowForm

  Pagination row:
    btn_prev       : Button  text='← Prev'
    lbl_pagination : Label   text=''
    btn_next       : Button  text='Next →'

  Event handlers:
    dd_subject     → change → dd_subject_change
    dd_year        → change → dd_year_change
    dd_term        → change → dd_term_change
    tb_search      → lost_focus → tb_search_lost_focus
    tb_search      → pressed_enter → tb_search_lost_focus
    btn_prev       → click → btn_prev_click
    btn_next       → click → btn_next_click

NOTE: BrowserRowForm must be created separately (see BrowserRowForm.py).

Created: 2026-02-26
"""

from ._anvil_designer import BrowserFormTemplate
from anvil import *
import anvil.server


class BrowserForm(BrowserFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._page = 0
        self._page_size = 50
        self._subject = None
        self._year = None
        self._term = None
        self._search = None
        self._load_filters()
        self._load()

    # -------------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------------

    def _load_filters(self):
        opts = anvil.server.call('get_filter_options')
        self.dd_subject.items = (
            [('All Subjects', None)]
            + [(s, s) for s in opts['subjects']]
        )
        self.dd_year.items = (
            [('All Years', None)]
            + [(f'Year {y}', y) for y in opts['years']]
        )
        self.dd_term.items = (
            [('All Terms', None)]
            + [(t, t) for t in opts['terms']]
        )

    # -------------------------------------------------------------------------
    # Data loading
    # -------------------------------------------------------------------------

    def _load(self):
        result = anvil.server.call(
            'get_corpus',
            self._subject,
            self._year,
            self._term,
            self._search,
            self._page,
            self._page_size,
        )
        self.repeating_panel.items = result['rows']
        total = result['total']
        start = self._page * self._page_size + 1
        end = min((self._page + 1) * self._page_size, total)
        self.lbl_pagination.text = (
            f"Page {self._page + 1} · {start}–{end} of {total}"
            if total > 0 else 'No results'
        )
        self.btn_prev.enabled = self._page > 0
        self.btn_next.enabled = end < total

    # -------------------------------------------------------------------------
    # Filter handlers
    # -------------------------------------------------------------------------

    def dd_subject_change(self, **event_args):
        self._subject = self.dd_subject.selected_value
        self._page = 0
        self._load()

    def dd_year_change(self, **event_args):
        self._year = self.dd_year.selected_value
        self._page = 0
        self._load()

    def dd_term_change(self, **event_args):
        self._term = self.dd_term.selected_value
        self._page = 0
        self._load()

    def tb_search_lost_focus(self, **event_args):
        query = self.tb_search.text.strip() or None
        if query != self._search:
            self._search = query
            self._page = 0
            self._load()

    # -------------------------------------------------------------------------
    # Pagination
    # -------------------------------------------------------------------------

    def btn_prev_click(self, **event_args):
        if self._page > 0:
            self._page -= 1
            self._load()

    def btn_next_click(self, **event_args):
        self._page += 1
        self._load()
