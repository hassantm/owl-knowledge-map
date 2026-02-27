# MainForm — Navigation shell
# Updated: 2026-02-27 — removed m3 components, use classic Anvil

from anvil import *
import anvil.users
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.server


class MainForm(Form):
    def __init__(self, **properties):
        self.init_components(**properties)

        if not anvil.users.get_user():
            anvil.users.login_with_form()

        user = anvil.users.get_user()
        if not user:
            return

        self._build_nav(user)
        self._content = ColumnPanel()
        self.add_component(self._content)
        self._nav_to('dashboard')

    def _build_nav(self, user):
        nav = ColumnPanel(background='#1e293b')

        title_row = ColumnPanel()
        title_row.add_component(
            Label(text='OWL Knowledge Map', bold=True, foreground='white', font_size=15),
            full_width_row=False
        )
        title_row.add_component(
            Label(text=user['email'], foreground='#94A3B8', font_size=11),
            full_width_row=False
        )
        btn_out = Button(text='Sign out', role='secondary-color')
        btn_out.set_event_handler('click', self._on_signout)
        title_row.add_component(btn_out, full_width_row=False)
        nav.add_component(title_row)

        btn_row = ColumnPanel()
        nav_items = [('Dashboard', 'dashboard'), ('Browse', 'browser'), ('Graph', 'graph')]
        if user.get('role') == 'reviewer':
            nav_items.insert(2, ('Edge Review', 'edge_review'))

        for label, target in nav_items:
            btn = Button(text=label, role='secondary-color', foreground='white')
            btn.tag = target
            btn.set_event_handler('click', self._on_nav)
            btn_row.add_component(btn, full_width_row=False)

        nav.add_component(btn_row)
        self.add_component(nav)

    def _on_nav(self, sender, **event_args):
        self._nav_to(sender.tag)

    def _on_signout(self, **event_args):
        anvil.users.logout()
        open_form('MainForm')

    def _nav_to(self, target, **kwargs):
        self._content.clear()
        if target == 'dashboard':
            from .DashboardForm import DashboardForm
            self._content.add_component(DashboardForm())
        elif target == 'browser':
            from .BrowserForm import BrowserForm
            self._content.add_component(BrowserForm())
        elif target == 'edge_review':
            from .EdgeReviewForm import EdgeReviewForm
            self._content.add_component(EdgeReviewForm())
        elif target == 'concept_detail':
            from .ConceptDetailForm import ConceptDetailForm
            self._content.add_component(ConceptDetailForm(concept_id=kwargs.get('concept_id')))
        elif target == 'graph':
            from .GraphForm import GraphForm
            self._content.add_component(GraphForm())
