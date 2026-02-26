"""
OccurrenceRowForm — Row template for ConceptDetailForm's rp_occurrences RepeatingPanel.

DESIGNER SETUP:
  Form type: ColumnPanel (horizontal row layout)

  Components:
    badge_type     : Label   bold=True, foreground='white'
    lbl_year_term  : Label   bold=True
    lbl_subject    : Label   foreground='#64748B'
    lbl_unit       : Label   foreground='#475569'
    lbl_chapter    : Label   foreground='#94A3B8', font_size=10
    lbl_context    : Label   foreground='#475569', font_size=11, italic=True

  Event handlers:
    Form → show → form_show

Created: 2026-02-26
"""

from ._anvil_designer import OccurrenceRowFormTemplate
from anvil import *


class OccurrenceRowForm(OccurrenceRowFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

    def form_show(self, **event_args):
        item = self.item
        if not item:
            return

        is_intro = bool(item.get('is_introduction'))
        self.badge_type.text = 'INTRO' if is_intro else 'recur'
        self.badge_type.background = '#22C55E' if is_intro else '#94A3B8'

        self.lbl_year_term.text = f"Y{item.get('year')} {item.get('term')}"
        self.lbl_subject.text = item.get('subject', '')
        self.lbl_unit.text = item.get('unit', '')
        self.lbl_chapter.text = item.get('chapter') or ''

        ctx = item.get('term_in_context') or ''
        # Trim long context for the timeline card — full text on hover/expand
        self.lbl_context.text = (ctx[:200] + '…') if len(ctx) > 200 else ctx
