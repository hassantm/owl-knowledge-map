# DashboardForm — Stats overview and charts
# Updated: 2026-02-27 — removed m3 components, use classic Anvil

from anvil import *
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server

SUBJECT_COLOURS = {
    'History': '#3B82F6',
    'Geography': '#22C55E',
    'Religion': '#EF4444',
}


class DashboardForm(Form):
    def __init__(self, **properties):
        self.init_components(**properties)
        self.add_component(Label(text='Dashboard', bold=True, font_size=20))
        self._load()

    def _load(self):
        stats = anvil.server.call('get_dashboard_stats')
        load_bearing = anvil.server.call('get_load_bearing_concepts', 2)
        candidates = anvil.server.call('get_candidate_edges_list', None, None, True, 0, 200)
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

        # --- Review CTA (reviewer only) ---
        user = anvil.users.get_user()
        if user and user.get('role') == 'reviewer':
            btn = Button(text='Start Edge Review →', role='primary-color')
            btn.set_event_handler('click', lambda **e: get_open_form()._nav_to('edge_review'))
            self.add_component(btn)
