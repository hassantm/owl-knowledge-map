"""
EdgeReviewForm — Edge confirmation tool (core reviewer workflow).

DESIGNER SETUP:
  Form type: ColumnPanel

  Header row:
    lbl_header        : Label  text='Edge Review', bold=True, font_size=16

  Filter row:
    dd_edge_type      : DropDown
    dd_subject        : DropDown

  Progress row:
    lbl_progress      : Label   text=''
    progress_bar      : ProgressBar  value=0

  Main two-column review panel (ColumnPanel, col=12):
    panel_review      : ColumnPanel  (only shown when there are edges to review)

    Inside panel_review, two side-by-side ColumnPanels (col=5 each):

    LEFT column:
      lbl_from_heading  : Label  text='FROM', bold=True, foreground='#64748B'
      lbl_from_term     : Label  bold=True, font_size=18
      lbl_from_location : Label  foreground='#64748B'
      lbl_from_chapter  : Label  foreground='#94A3B8', font_size=11
      lbl_from_context  : Label  (block-quote style — italic, indented)

    Middle column (col=2, centred):
      lbl_edge_type     : Label  text='→', bold=True, font_size=20 (coloured in code)

    RIGHT column (same structure as left):
      lbl_to_heading    : Label  text='TO', bold=True, foreground='#64748B'
      lbl_to_term       : Label  bold=True, font_size=18
      lbl_to_location   : Label  foreground='#64748B'
      lbl_to_chapter    : Label  foreground='#94A3B8', font_size=11
      lbl_to_context    : Label  (italic)

  Decision panel:
    tb_reviewer         : TextBox  placeholder='Your name…'
    btn_reinforcement   : Button   text='Reinforcement',         role='primary-color'
    btn_extension       : Button   text='Extension',             role='primary-color'
    btn_cross_subject   : Button   text='Cross-subject Application', role='primary-color'
    btn_skip            : Button   text='Skip →',                role='secondary-color'

  Navigation:
    btn_prev_edge       : Button  text='← Prev'
    btn_next_edge       : Button  text='Next →'

  Event handlers:
    dd_edge_type        → change    → dd_edge_type_change
    dd_subject          → change    → dd_subject_change
    btn_reinforcement   → click     → btn_reinforcement_click
    btn_extension       → click     → btn_extension_click
    btn_cross_subject   → click     → btn_cross_subject_click
    btn_skip            → click     → btn_skip_click
    btn_prev_edge       → click     → btn_prev_edge_click
    btn_next_edge       → click     → btn_next_edge_click

Created: 2026-02-26
"""

from ._anvil_designer import EdgeReviewFormTemplate
from anvil import *
import anvil.server


class EdgeReviewForm(EdgeReviewFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)
        self._all_edges = []         # all unconfirmed candidates
        self._filtered_edges = []    # after filter applied
        self._current_index = 0
        self._total_candidates = 0   # total incl. confirmed (for progress)
        self._confirmed_count = 0
        self._edge_type_filter = None
        self._subject_filter = None
        self._current_edge = None

        self._setup_filters()
        self._initial_load()

    # -------------------------------------------------------------------------
    # Setup
    # -------------------------------------------------------------------------

    def _setup_filters(self):
        self.dd_edge_type.items = [
            ('All Types', None),
            ('Within Subject', 'within_subject'),
            ('Cross Subject', 'cross_subject'),
        ]
        opts = anvil.server.call('get_filter_options')
        self.dd_subject.items = (
            [('All Subjects', None)]
            + [(s, s) for s in opts['subjects']]
        )

    def _initial_load(self):
        """Load all candidates (confirmed + unconfirmed) once for progress tracking."""
        result_all = anvil.server.call(
            'get_candidate_edges_list',
            None, None,   # subject, edge_type
            True,         # include_confirmed
            0, 300        # generous page size
        )
        all_rows = result_all.get('rows', [])
        self._total_candidates = result_all.get('total', 0)
        self._confirmed_count = sum(1 for r in all_rows if r.get('already_confirmed'))
        self._all_edges = [r for r in all_rows if not r.get('already_confirmed')]
        self._apply_filters()

    # -------------------------------------------------------------------------
    # Filtering and display
    # -------------------------------------------------------------------------

    def _apply_filters(self):
        edges = list(self._all_edges)
        if self._edge_type_filter:
            edges = [e for e in edges if e['edge_type'] == self._edge_type_filter]
        if self._subject_filter:
            edges = [
                e for e in edges
                if e['from_subject'] == self._subject_filter
                or e['to_subject'] == self._subject_filter
            ]
        self._filtered_edges = edges
        self._current_index = 0
        self._display_current()

    def _display_current(self):
        total_filtered = len(self._filtered_edges)
        pct = (
            (self._confirmed_count / self._total_candidates * 100)
            if self._total_candidates > 0 else 0
        )
        self.progress_bar.value = pct

        if total_filtered == 0:
            self.lbl_header.text = (
                f"Edge Review — {self._confirmed_count}/{self._total_candidates} confirmed. "
                "No unconfirmed edges match current filters."
            )
            self.lbl_progress.text = f"{self._confirmed_count} of {self._total_candidates} confirmed"
            self.panel_review.visible = False
            return

        self.panel_review.visible = True
        idx = self._current_index
        self.lbl_header.text = (
            f"Edge Review — {self._confirmed_count}/{self._total_candidates} confirmed  ·  "
            f"Showing {idx + 1} of {total_filtered}"
        )
        self.lbl_progress.text = (
            f"{self._confirmed_count} confirmed · {len(self._all_edges)} remaining"
        )

        edge = self._filtered_edges[idx]
        self._current_edge = edge

        # Load full context for both sides
        from_detail = anvil.server.call('get_term_detail', edge['from_occurrence_id'])
        to_detail = anvil.server.call('get_term_detail', edge['to_occurrence_id'])

        # FROM side
        self.lbl_from_term.text = from_detail['term'] if from_detail else ''
        self.lbl_from_location.text = self._format_location(from_detail)
        self.lbl_from_chapter.text = (from_detail or {}).get('chapter') or ''
        self.lbl_from_context.text = (
            (from_detail or {}).get('term_in_context') or '(no context captured)'
        )

        # Edge type badge
        etype = edge.get('edge_type', '')
        self.lbl_edge_type.text = '→\n' + etype.replace('_', ' ')
        self.lbl_edge_type.background = (
            '#3B82F6' if etype == 'within_subject' else '#F59E0B'
        )
        self.lbl_edge_type.foreground = 'white'

        # TO side
        self.lbl_to_term.text = to_detail['term'] if to_detail else ''
        self.lbl_to_location.text = self._format_location(to_detail)
        self.lbl_to_chapter.text = (to_detail or {}).get('chapter') or ''
        self.lbl_to_context.text = (
            (to_detail or {}).get('term_in_context') or '(no context captured)'
        )

        # Navigation button states
        self.btn_prev_edge.enabled = idx > 0
        self.btn_next_edge.enabled = idx < total_filtered - 1

    @staticmethod
    def _format_location(detail: dict | None) -> str:
        if not detail:
            return ''
        return (
            f"{detail['subject']}  ·  "
            f"Y{detail['year']} {detail['term_period']}  ·  "
            f"{detail['unit']}"
        )

    # -------------------------------------------------------------------------
    # Decision buttons
    # -------------------------------------------------------------------------

    def btn_reinforcement_click(self, **event_args):
        self._confirm('reinforcement')

    def btn_extension_click(self, **event_args):
        self._confirm('extension')

    def btn_cross_subject_click(self, **event_args):
        self._confirm('cross_subject_application')

    def btn_skip_click(self, **event_args):
        self._advance()

    def _confirm(self, edge_nature: str):
        reviewer = self.tb_reviewer.text.strip() if self.tb_reviewer.text else ''
        if not reviewer:
            alert('Please enter your name before confirming an edge.')
            return

        edge = self._current_edge
        if not edge:
            return

        result = anvil.server.call(
            'confirm_edge',
            edge['from_occurrence_id'],
            edge['to_occurrence_id'],
            edge_nature,
            reviewer,
        )

        if result.get('ok'):
            Notification(
                f"Confirmed: {edge_nature.replace('_', ' ')}",
                style='success',
                timeout=2,
            ).show()
            # Remove confirmed edge from local list; update counts
            self._confirmed_count += 1
            self._all_edges = [
                e for e in self._all_edges
                if not (
                    e['from_occurrence_id'] == edge['from_occurrence_id']
                    and e['to_occurrence_id'] == edge['to_occurrence_id']
                )
            ]
            self._apply_filters()
        else:
            alert(f"Error confirming edge:\n{result.get('message')}")

    def _advance(self):
        """Move to the next edge without confirming."""
        if self._current_index < len(self._filtered_edges) - 1:
            self._current_index += 1
            self._display_current()

    # -------------------------------------------------------------------------
    # Navigation buttons
    # -------------------------------------------------------------------------

    def btn_prev_edge_click(self, **event_args):
        if self._current_index > 0:
            self._current_index -= 1
            self._display_current()

    def btn_next_edge_click(self, **event_args):
        self._advance()

    # -------------------------------------------------------------------------
    # Filter handlers
    # -------------------------------------------------------------------------

    def dd_edge_type_change(self, **event_args):
        self._edge_type_filter = self.dd_edge_type.selected_value
        self._apply_filters()

    def dd_subject_change(self, **event_args):
        self._subject_filter = self.dd_subject.selected_value
        self._apply_filters()
