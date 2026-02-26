"""
ConceptDetailForm — Curriculum timeline for a single concept.

DESIGNER SETUP:
  Form type: ColumnPanel

  Header:
    btn_back          : Button  text='← Back to Browse',  role='secondary-color'
    lbl_term          : Label   bold=True, font_size=22
    lbl_subject_area  : Label   foreground='#64748B', font_size=12

  Occurrence timeline section:
    lbl_occ_heading   : Label  text='Occurrences', bold=True
    rp_occurrences    : RepeatingPanel  item_template=OccurrenceRowForm

  Confirmed edges section:
    panel_edges       : ColumnPanel  (hidden until edges exist)
    lbl_edges_heading : Label  text='Confirmed Edges', bold=True
    rp_edges          : RepeatingPanel  item_template=EdgeRowForm

  Event handlers:
    btn_back          → click → btn_back_click

NOTE: OccurrenceRowForm and EdgeRowForm must be created separately.

Created: 2026-02-26
"""

from ._anvil_designer import ConceptDetailFormTemplate
from anvil import *
import anvil.server


class ConceptDetailForm(ConceptDetailFormTemplate):
    def __init__(self, concept_id=None, **properties):
        self.init_components(**properties)
        self._concept_id = concept_id
        if concept_id is not None:
            self._load(concept_id)
        else:
            self.lbl_term.text = 'No concept selected.'

    def _load(self, concept_id: int):
        data = anvil.server.call('get_concept_detail', concept_id)

        if not data:
            self.lbl_term.text = f'Concept {concept_id} not found.'
            return

        concept = data['concept']
        occurrences = data['occurrences']
        edges = data['edges']

        # Header
        self.lbl_term.text = concept['term']
        self.lbl_subject_area.text = concept.get('subject_area') or 'All subjects'

        # Occurrence timeline (sorted by year/term/slide — already ordered by uplink)
        self.rp_occurrences.items = occurrences

        # Confirmed edges section
        if edges:
            self.lbl_edges_heading.text = f"Confirmed Edges ({len(edges)})"
            self.rp_edges.items = edges
            self.panel_edges.visible = True
        else:
            self.panel_edges.visible = False

    def btn_back_click(self, **event_args):
        get_open_form()._nav_to('browser')
