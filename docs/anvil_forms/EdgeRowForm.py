"""
EdgeRowForm — Row template for ConceptDetailForm's rp_edges RepeatingPanel.

DESIGNER SETUP:
  Form type: ColumnPanel

  Components:
    lbl_from_loc   : Label   (from occurrence location)
    lbl_arrow      : Label   text='→', bold=True
    lbl_to_loc     : Label   (to occurrence location)
    lbl_nature     : Label   bold=True  (edge_nature, coloured)
    lbl_confirmed  : Label   foreground='#94A3B8', font_size=10  (confirmed by/date)

  Event handlers:
    Form → show → form_show

Created: 2026-02-26
"""

from ._anvil_designer import EdgeRowFormTemplate
from anvil import *

NATURE_COLOURS = {
    'reinforcement': '#22C55E',
    'extension': '#3B82F6',
    'cross_subject_application': '#F59E0B',
}


class EdgeRowForm(EdgeRowFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

    def form_show(self, **event_args):
        item = self.item
        if not item:
            return

        self.lbl_from_loc.text = (
            f"Y{item.get('from_year')} {item.get('from_term_period')} · {item.get('from_unit', '')}"
        )
        self.lbl_to_loc.text = (
            f"Y{item.get('to_year')} {item.get('to_term_period')} · {item.get('to_unit', '')}"
        )

        nature = item.get('edge_nature') or ''
        self.lbl_nature.text = nature.replace('_', ' ').title()
        self.lbl_nature.foreground = NATURE_COLOURS.get(nature, '#6366F1')

        confirmed_by = item.get('confirmed_by') or ''
        confirmed_date = item.get('confirmed_date') or ''
        self.lbl_confirmed.text = (
            f"Confirmed by {confirmed_by} on {confirmed_date}"
            if confirmed_by else ''
        )
