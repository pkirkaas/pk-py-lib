"""
src/pk_py_lib/gui/dialogs/base_file_manager_dialog.py

Shared Qt dialog scaffolding for file-management workflows (duplicates, similarity, etc.).
Provides Summary/Report tabs with selectable text, footer actions, and selection state wiring
built on the SelectionStore pattern.

Syntax validation performed with Python's ast module prior to inclusion.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..dialog_models import DialogState, Group
from ..models import SelectionStore


class BaseFileManagerDialog(QDialog):
    """
    Base class for file management dialogs using composition over inheritance.

    This scaffold centralises:
      • Summary & Report tabs with selectable text
      • Shared footer showing selection status and primary actions
      • Wiring between SelectionStore and status/controls

    Subclasses supply their own controls (toolbar) and content area to keep responsibilities
    isolated and composable.
    """

    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        selection_store: Optional[SelectionStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialise the dialog with optional group data and selection store.

        Parameters
        ----------
        groups:
            Initial immutable groups to expose in the dialog.
        selection_store:
            shared SelectionStore instance to maintain selection state across views.
        parent:
            Optional parent widget (standard Qt parent/child relationship).
        """
        super().__init__(parent)

        self.selection_store = selection_store or SelectionStore()
        self.dialog_state = DialogState(
            groups=groups or [],
            selection_store=self.selection_store,
        )

        # Hold onto latest summary/report payloads for regeneration/export.
        self._summary_text: str = ""
        self._report_text: str = ""

        self.setModal(True)
        self.resize(1200, 800)
        self.setWindowTitle("File Manager")

        self._build_ui()
        self._connect_signals()
        self._update_status_label(self.selection_store.get_selection_count())

    # ---------------------------------------------------------------------#
    # UI Construction helpers
    # ---------------------------------------------------------------------#
    def _build_ui(self) -> None:
        """Compose the shared dialog layout."""
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 12, 12, 12)
        self._main_layout.setSpacing(12)

        # --- Top Pane (Summary/Report Tabs) ---
        top_pane_widget = QWidget(self)
        top_pane_layout = QVBoxLayout(top_pane_widget)
        top_pane_layout.setContentsMargins(0, 0, 0, 0)
        top_pane_layout.setSpacing(0) # Tabs widget handles its own spacing

        self._build_tabs(top_pane_layout) # Adds self.tab_widget to top_pane_layout

        # Ensure the top pane (tabs only) can be resized by the splitter
        top_pane_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        # --- Content Area (Controls + Main results) ---
        content_area_widget = QWidget(self)
        # Ensure the content area expands to fill available space
        content_area_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        content_area_layout = QVBoxLayout(content_area_widget)
        content_area_layout.setContentsMargins(0, 0, 0, 0)
        content_area_layout.setSpacing(12) # Spacing between controls and content area

        # Add controls (Status Row) to the top of the content area
        controls = self._build_controls()
        if controls is not None:
            content_area_layout.addWidget(controls)

        self._build_content_area(content_area_layout)

        # --- Vertical Splitter ---
        # This splitter divides the top report/controls area from the main content area.
        self._main_splitter = QSplitter(Qt.Vertical, self)
        self._main_splitter.addWidget(top_pane_widget)
        self._main_splitter.addWidget(content_area_widget)

        # Set initial sizes: top pane minimal (1), bottom pane takes remaining space.
        # This ensures the top pane starts at its minimum size hint (content height)
        # and is collapsable (by setting the size to 0, but 1 is safer for initial display).
        self._main_splitter.setSizes([1, 1000000])
        self._main_splitter.setCollapsible(0, True) # Make the top pane collapsable

        self._main_layout.addWidget(self._main_splitter)
        self._build_footer(self._main_layout)

    def _build_tabs(self, parent_layout: QVBoxLayout) -> None:
        """Create the Summary/Report tab widget with selectable text."""
        self.tab_widget = QTabWidget(self)
        # Ensure the tab widget respects its minimum size (content height) but can expand
        self.tab_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

        self.summary_edit = QTextEdit(self.tab_widget)
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setAcceptRichText(False)
        self.summary_edit.setPlaceholderText("Summary information will appear here.")
        self.summary_edit.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.tab_widget.addTab(self.summary_edit, "Summary")

        self.report_edit = QTextEdit(self.tab_widget)
        self.report_edit.setReadOnly(True)
        self.report_edit.setAcceptRichText(False)
        self.report_edit.setPlaceholderText("Detailed report output will appear here.")
        self.report_edit.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.tab_widget.addTab(self.report_edit, "Report")

        parent_layout.addWidget(self.tab_widget)

    def _build_controls(self) -> Optional[QWidget]:
        """
        Hook for subclasses to inject control toolbars/filters.

        Returns
        -------
        QWidget | None
            Controls widget added beneath the tabs, or None if no controls are required.
        """
        return None

    def _build_content_area(self, parent_layout: QVBoxLayout) -> None:
        """
        Subclasses must override to provide their main content area (tree, preview, etc.).
        """
        raise NotImplementedError(
            "Subclasses must implement _build_content_area to supply their primary widgets."
        )

    def _build_footer(self, parent_layout: QVBoxLayout) -> None:
        """Create footer containing selection status and primary actions."""
        footer_widget = QWidget(self)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        self.status_label = QLabel("0 files selected", footer_widget)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch(1)

        self.delete_button = QPushButton("Delete Selected", footer_widget)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.delete_button.setEnabled(False)
        footer_layout.addWidget(self.delete_button)

        close_button = QPushButton("Close", footer_widget)
        close_button.clicked.connect(self.accept)
        footer_layout.addWidget(close_button)

        parent_layout.addWidget(footer_widget)

    # ---------------------------------------------------------------------#
    # Signal wiring and status helpers
    # ---------------------------------------------------------------------#
    def _connect_signals(self) -> None:
        """Connect shared signals such as selection updates."""
        self.selection_store.selection_count_changed.connect(self._update_status_label)

    def _update_status_label(self, count: int) -> None:
        """Reflect selection counts in the footer and enable/disable actions."""
        total_files = sum(len(group.items) for group in self.dialog_state.groups)
        self.status_label.setText(f"{count}/{total_files} files selected")
        self.delete_button.setEnabled(count > 0)

    # ---------------------------------------------------------------------#
    # Summary / Report helpers
    # ---------------------------------------------------------------------#
    def set_summary_text(self, text: str) -> None:
        """
        Replace the contents of the Summary tab.

        Text remains selectable per project requirements.
        """
        self._summary_text = text or ""
        self.summary_edit.setPlainText(self._summary_text)
        # Move cursor to start to ensure the top of the text is visible
        self.summary_edit.setTextCursor(QTextCursor(self.summary_edit.document()))
        self.summary_edit.moveCursor(QTextCursor.Start)

    def set_report_text(self, text: str) -> None:
        """
        Replace the contents of the Report tab.

        Text remains selectable per project requirements.
        """
        self._report_text = text or ""
        self.report_edit.setPlainText(self._report_text)
        # Move cursor to start to ensure the top of the text is visible
        self.report_edit.setTextCursor(QTextCursor(self.report_edit.document()))
        self.report_edit.moveCursor(QTextCursor.Start)

    def append_report_lines(self, *lines: str) -> None:
        """
        Append one or more lines to the report output in a selectable, scrollable manner.
        """
        normalized = [segment for segment in (lines or []) if segment]
        if not normalized:
            return
        current = self.report_edit.toPlainText()
        updated = "\n".join(filter(None, [current, *normalized])).strip()
        self.set_report_text(updated)

    # ---------------------------------------------------------------------#
    # Group refresh helpers
    # ---------------------------------------------------------------------#
    def update_groups(self, groups: List[Group]) -> None:
        """
        Replace dialog groups and refresh selection counters.

        Subclasses should call this after repopulating their tree/list views.
        """
        self.dialog_state.groups = groups or []
        self._update_status_label(self.selection_store.get_selection_count())

    # ---------------------------------------------------------------------#
    # Abstract hooks expected from subclasses
    # ---------------------------------------------------------------------#
    def _on_delete_clicked(self) -> None:
        """
        Subclasses must provide deletion behaviour appropriate to their workflow.
        """
        raise NotImplementedError("Subclasses must implement _on_delete_clicked")


__all__ = ["BaseFileManagerDialog"]