"""
MainForm — Navigation shell for OWL Knowledge Map Anvil app.

DESIGNER SETUP (do in Anvil IDE before pasting this code):
  Form type: ColumnPanel (use "Blank Panel" template)

  Add these components and name them exactly as shown:

  Layout: use two side-by-side ColumnPanels (set column widths 2/10 or use CSS)
    sidebar_panel   : ColumnPanel  (col=2, background='#1e293b')
    content_panel   : ColumnPanel  (col=10)

  Inside sidebar_panel:
    lbl_app_title   : Label   text='OWL Knowledge Map', bold=True, foreground='white'
    lbl_username    : Label   text='', foreground='#94A3B8', font_size=10
    btn_dashboard   : Button  text='Dashboard',  role='secondary-color'
    btn_browser     : Button  text='Browse',     role='secondary-color'
    btn_edge_review : Button  text='Edge Review', role='secondary-color'
    btn_graph       : Button  text='Graph',       role='secondary-color'
    btn_signout     : Button  text='Sign out',    role='secondary-color'

  Event handlers to wire up (in the Properties panel → Events):
    btn_dashboard   → click → btn_dashboard_click
    btn_browser     → click → btn_browser_click
    btn_edge_review → click → btn_edge_review_click
    btn_graph       → click → btn_graph_click
    btn_signout     → click → btn_signout_click

Created: 2026-02-26
"""

from ._anvil_designer import MainFormTemplate
from anvil import *
import anvil.server
import anvil.users


class MainForm(MainFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Require login
        if not anvil.users.get_user():
            anvil.users.login_with_form()

        user = anvil.users.get_user()
        if not user:
            # Login was cancelled — nothing to show
            return

        self.lbl_username.text = user['email']
        role = user.get('role', 'teacher')
        self.btn_edge_review.visible = (role == 'reviewer')

        # Default to Dashboard on load
        self._nav_to('dashboard')

    # -------------------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------------------

    def _nav_to(self, target: str, **kwargs):
        """Replace content_panel with the requested form."""
        self.content_panel.clear()

        if target == 'dashboard':
            from .DashboardForm import DashboardForm
            self.content_panel.add_component(DashboardForm())

        elif target == 'browser':
            from .BrowserForm import BrowserForm
            self.content_panel.add_component(BrowserForm())

        elif target == 'edge_review':
            from .EdgeReviewForm import EdgeReviewForm
            self.content_panel.add_component(EdgeReviewForm())

        elif target == 'concept_detail':
            from .ConceptDetailForm import ConceptDetailForm
            self.content_panel.add_component(
                ConceptDetailForm(concept_id=kwargs.get('concept_id'))
            )

        elif target == 'graph':
            from .GraphForm import GraphForm
            self.content_panel.add_component(GraphForm())

    # -------------------------------------------------------------------------
    # Nav button handlers
    # -------------------------------------------------------------------------

    def btn_dashboard_click(self, **event_args):
        self._nav_to('dashboard')

    def btn_browser_click(self, **event_args):
        self._nav_to('browser')

    def btn_edge_review_click(self, **event_args):
        self._nav_to('edge_review')

    def btn_graph_click(self, **event_args):
        self._nav_to('graph')

    def btn_signout_click(self, **event_args):
        anvil.users.logout()
        open_form('MainForm')
