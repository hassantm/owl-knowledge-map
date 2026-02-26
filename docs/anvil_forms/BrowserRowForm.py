"""
BrowserRowForm — Row template for BrowserForm's RepeatingPanel.

In Anvil, set BrowserForm's repeating_panel → item_template = BrowserRowForm.

DESIGNER SETUP:
  Form type: ColumnPanel (narrow, horizontal row layout)

  Components:
    badge_type     : Label   text='INTRO', bold=True, foreground='white'
                             (set background colour in code)
    lbl_term       : Label   bold=True
    lbl_location   : Label   foreground='#64748B', font_size=11
    lbl_chapter    : Label   foreground='#94A3B8', font_size=10

  Make the whole row clickable by adding an event handler on the form itself:
    Form → show → form_show
    Form → click → row_click  (or add a transparent Button over the row)

  Alternatively, add a link or button with the concept term text and wire to click.

Created: 2026-02-26
"""

from ._anvil_designer import BrowserRowFormTemplate
from anvil import *


class BrowserRowForm(BrowserRowFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

    def form_show(self, **event_args):
        item = self.item
        if not item:
            return

        is_intro = bool(item.get('is_introduction'))
        self.badge_type.text = 'INTRO' if is_intro else 'recur'
        self.badge_type.background = '#22C55E' if is_intro else '#94A3B8'
        self.badge_type.foreground = 'white'

        self.lbl_term.text = item.get('term', '')
        self.lbl_location.text = (
            f"Y{item.get('year')} {item.get('term_period')}  ·  "
            f"{item.get('subject')}  ·  {item.get('unit', '')}"
        )
        self.lbl_chapter.text = item.get('chapter') or ''

    def row_click(self, **event_args):
        concept_id = self.item.get('concept_id') if self.item else None
        if concept_id:
            get_open_form()._nav_to('concept_detail', concept_id=concept_id)
