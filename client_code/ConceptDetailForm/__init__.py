# ConceptDetailForm — Curriculum timeline for a single concept
# _OccurrenceRow and _EdgeRow are inline helper classes, no separate forms needed.
# Created: 2026-02-26

from anvil import *
import anvil.server

NATURE_COLOURS = {
    'reinforcement': '#22C55E',
    'extension': '#3B82F6',
    'cross_subject_application': '#F59E0B',
}
SUBJECT_COLOURS = {'History': '#3B82F6', 'Geography': '#22C55E', 'Religion': '#EF4444'}


class ConceptDetailForm(Form):
    def __init__(self, concept_id=None, **properties):
        self.init_components(**properties)

        # Back button
        btn_back = Button(text='← Back to Browse', role='secondary-color')
        btn_back.set_event_handler('click', lambda **e: get_open_form()._nav_to('browser'))
        self.add_component(btn_back)

        if concept_id is None:
            self.add_component(Label(text='No concept selected.', foreground='#94A3B8'))
            return

        self._load(concept_id)

    def _load(self, concept_id):
        data = anvil.server.call('get_concept_detail', concept_id)
        if not data:
            self.add_component(Label(text=f'Concept {concept_id} not found.'))
            return

        concept = data['concept']
        occurrences = data['occurrences']
        edges = data['edges']

        # Header
        subj_colour = SUBJECT_COLOURS.get(concept.get('subject_area', ''), '#6366F1')
        self.add_component(Label(text=concept['term'], bold=True, font_size=24))
        self.add_component(
            Label(text=concept.get('subject_area') or 'All subjects',
                  foreground=subj_colour, font_size=13, bold=True)
        )
        self.add_component(Label(
            text=f"{len(occurrences)} occurrence(s)  ·  "
                 f"Y{concept.get('first_year', '')}–Y{concept.get('last_year', '')}",
            foreground='#64748B', font_size=12
        ))

        # Occurrence timeline
        self.add_component(Label(text='Curriculum Timeline', bold=True, font_size=16))
        for occ in occurrences:
            self.add_component(_OccurrenceRow(occ))

        # Confirmed edges
        if edges:
            self.add_component(Label(text=f'Confirmed Edges ({len(edges)})', bold=True, font_size=16))
            for edge in edges:
                self.add_component(_EdgeRow(edge))
        else:
            self.add_component(
                Label(text='No confirmed edges yet — use Edge Review to confirm connections.',
                      foreground='#94A3B8', font_size=12)
            )


class _OccurrenceRow(ColumnPanel):
    def __init__(self, item):
        super().__init__(background='#F8FAFC')
        is_intro = bool(item.get('is_introduction'))

        row = ColumnPanel()
        row.add_component(
            Label(text='INTRO' if is_intro else 'recur', bold=True,
                  foreground='white',
                  background='#22C55E' if is_intro else '#94A3B8'),
            full_width_row=False
        )
        row.add_component(
            Label(text=f"Y{item.get('year')} {item.get('term')}  ·  "
                       f"{item.get('subject')}  ·  {item.get('unit', '')}",
                  bold=True),
            full_width_row=False
        )
        row.add_component(
            Label(text=item.get('chapter') or '', foreground='#94A3B8', font_size=11),
            full_width_row=False
        )
        self.add_component(row)

        ctx = item.get('term_in_context') or ''
        if ctx:
            preview = (ctx[:220] + '…') if len(ctx) > 220 else ctx
            self.add_component(Label(text=preview, italic=True, foreground='#475569', font_size=12))


class _EdgeRow(ColumnPanel):
    def __init__(self, item):
        super().__init__()
        nature = item.get('edge_nature') or ''
        colour = NATURE_COLOURS.get(nature, '#6366F1')

        row = ColumnPanel()
        row.add_component(
            Label(text=f"Y{item.get('from_year')} {item.get('from_term_period')}  ·  "
                       f"{item.get('from_unit', '')}"),
            full_width_row=False
        )
        row.add_component(Label(text='→', bold=True, font_size=16), full_width_row=False)
        row.add_component(
            Label(text=f"Y{item.get('to_year')} {item.get('to_term_period')}  ·  "
                       f"{item.get('to_unit', '')}"),
            full_width_row=False
        )
        row.add_component(
            Label(text=nature.replace('_', ' ').title(), bold=True, foreground=colour),
            full_width_row=False
        )
        self.add_component(row)

        confirmed_by = item.get('confirmed_by') or ''
        confirmed_date = item.get('confirmed_date') or ''
        if confirmed_by:
            self.add_component(
                Label(text=f"Confirmed by {confirmed_by} on {confirmed_date}",
                      foreground='#94A3B8', font_size=11)
            )
