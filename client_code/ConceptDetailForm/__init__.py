# ConceptDetailForm — Curriculum timeline for a single concept
# Updated: 2026-02-27 — removed anvil_extras; _chip() replaces Chip component

from anvil import *
import anvil.server

NATURE_COLOURS = {
    'reinforcement': '#22C55E',
    'extension': '#3B82F6',
    'cross_subject_application': '#F59E0B',
}
SUBJECT_COLOURS = {'History': '#3B82F6', 'Geography': '#22C55E', 'Religion': '#EF4444'}


def _chip(text, background='#888', foreground='white'):
    lbl = Label(background=background, foreground=foreground, font_size=11, bold=True)
    lbl.text = ' ' + text + ' ' if text else ''
    return lbl


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

        # Header
        subj_colour = SUBJECT_COLOURS.get(concept.get('subject_area', ''), '#6366F1')
        self.add_component(Label(text=concept['term'], bold=True, font_size=24))
        self.add_component(
            _chip(
                text=concept.get('subject_area') or 'All subjects',
                background=subj_colour,
            )
        )
        first_year = str(concept.get('first_year', ''))
        last_year = str(concept.get('last_year', ''))
        self.add_component(Label(
            text=str(len(occurrences)) + ' occurrence(s)  |  Y' + first_year + '-Y' + last_year,
            foreground='#64748B', font_size=12
        ))

        # Occurrence timeline
        self.add_component(Label(text='Curriculum Timeline', bold=True, font_size=16))
        for occ in occurrences:
            self.add_component(_OccurrenceRow(occ))

        # Confirmed edges
        if edges:
            self.add_component(Label(
                text='Confirmed Edges (' + str(len(edges)) + ')',
                bold=True, font_size=16
            ))
            for edge in edges:
                self.add_component(_EdgeRow(edge))
        else:
            self.add_component(
                Label(
                    text='No confirmed edges yet -- use Edge Review to confirm connections.',
                    foreground='#94A3B8', font_size=12,
                )
            )


class _OccurrenceRow(ColumnPanel):
    def __init__(self, item):
        super().__init__(background='#F8FAFC')
        is_intro = bool(item.get('is_introduction'))

        row = ColumnPanel()
        row.add_component(
            _chip(
                'INTRO' if is_intro else 'recur',
                background='#22C55E' if is_intro else '#94A3B8',
            ),
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
            self.add_component(
                Label(
                    text='Confirmed by ' + confirmed_by + ' on ' + confirmed_date,
                    foreground='#94A3B8', font_size=11,
                )
            )
