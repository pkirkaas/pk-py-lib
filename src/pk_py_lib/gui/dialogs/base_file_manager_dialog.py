"""
src/pk_py_lib/gui/dialogs/base_file_manager_dialog.py

Shared Qt dialog scaffolding for file-management workflows (duplicates, similarity, etc.).
Provides Summary/Report tabs with selectable text, footer actions, and selection state wiring
built on the SelectionStore pattern.

Syntax validation performed with Python's ast module prior to inclusion.
"""

from __future__ import annotations

from typing import List, Optional
from pathlib import Path

import sys
import traceback
import inspect

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from ..dialog_models import DialogState, Group
from ...core.filesystem.operations import FileOperations
from ..models import SelectionStore

from src.pk_py_lib.core.logging.decorators import log_errors
from src.pk_py_lib.core.logging.logger import get_logger


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

        self.logger = get_logger(__name__)

        self.selection_store = selection_store or SelectionStore()
        self.dialog_state = DialogState(
            groups=groups or [],
            selection_store=self.selection_store,
        )

        # Hold onto latest summary/report payloads for regeneration/export.
        self._summary_text: str = ""
        self._report_text: str = ""

        # State for the collapsible top pane
        self._is_collapsed: bool = True

        # Set window flags to enable Minimize and Maximize buttons
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        
        self.setModal(True)
        self.resize(1200, 800)
        self.setWindowTitle("File Manager")

        self._build_ui()
        self._connect_signals()
        self._update_status_label(self.selection_store.get_selection_count())

    # ---------------------------------------------------------------------#
    # UI Construction helpers
    # ---------------------------------------------------------------------#
    @log_errors()
    def _build_ui(self) -> None:
        """Compose the shared dialog layout."""
        try:
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
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "UI Build Error", f"Failed to build dialog UI: {error_msg}")
            raise

    @log_errors()
    def _build_tabs(self, parent_layout: QVBoxLayout) -> None:
        """
        Create the Summary/Report tab header and collapsible content area.

        The header contains the QTabBar and a collapse button.
        The content area is a QStackedWidget holding the Summary and Report QTextEdits.
        """
        try:
            # 1. Tab Content (Collapsible Area)
            self._tab_content_stack = QStackedWidget(self)
            # Ensure the stacked widget respects its minimum size (content height) but can expand
            self._tab_content_stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

            # Create Summary Text Edit
            self.summary_edit = QTextEdit(self._tab_content_stack)
            self.summary_edit.setReadOnly(True)
            self.summary_edit.setAcceptRichText(False)
            self.summary_edit.setPlaceholderText("Summary information will appear here.")
            self.summary_edit.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            self._tab_content_stack.addWidget(self.summary_edit) # Index 0

            # Create Report Text Edit
            self.report_edit = QTextEdit(self._tab_content_stack)
            self.report_edit.setReadOnly(True)
            self.report_edit.setAcceptRichText(False)
            self.report_edit.setPlaceholderText("Detailed report output will appear here.")
            self.report_edit.setTextInteractionFlags(
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            )
            self._tab_content_stack.addWidget(self.report_edit) # Index 1

            # 2. Tab Bar and Collapse Button (Header)
            header_widget = QWidget(self)
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(8)

            self.tab_bar = QTabBar(self)
            self.tab_bar.addTab("Summary") # Index 0
            self.tab_bar.addTab("Report")  # Index 1
            self.tab_bar.setShape(QTabBar.RoundedNorth)
            
            self._collapse_button = QToolButton(self)
            self._collapse_button.setArrowType(Qt.DownArrow) # Start collapsed
            self._collapse_button.setToolTip("Collapse/Expand Summary/Report Pane")
            self._collapse_button.clicked.connect(self._toggle_collapse)

            header_layout.addWidget(self.tab_bar)
            header_layout.addStretch(1)
            header_layout.addWidget(self._collapse_button)

            # 3. Connect Signals
            self.tab_bar.currentChanged.connect(self._tab_content_stack.setCurrentIndex)

            # 4. Add Header and Content to Parent Layout
            parent_layout.addWidget(header_widget)
            parent_layout.addWidget(self._tab_content_stack)
            
            # Start collapsed by default
            self._tab_content_stack.setVisible(False)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Tabs Build Error", f"Failed to build tabs: {error_msg}")
            raise

    @log_errors()
    def _build_controls(self) -> Optional[QWidget]:
        """
        Hook for subclasses to inject control toolbars/filters.
        """
        try:
            return None
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Controls Build Error", f"Failed to build controls: {error_msg}")
            raise

    @log_errors()
    def _toggle_collapse(self) -> None:
        """
        Toggles the visibility of the tab content area (Summary/Report) and updates the collapse button icon.
        
        When collapsed, the QStackedWidget containing the summary/report QTextEdits is hidden,
        but the QTabBar and collapse button remain visible.
        """
        try:
            self._is_collapsed = not self._is_collapsed
            self._tab_content_stack.setVisible(not self._is_collapsed)

            if self._is_collapsed:
                # Collapsed state: show down arrow
                self._collapse_button.setArrowType(Qt.DownArrow)
            else:
                # Expanded state: show up arrow
                self._collapse_button.setArrowType(Qt.UpArrow)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Collapse Toggle Error", f"Failed to toggle collapse: {error_msg}")
            # Do not re-raise to prevent dialog crash

    @log_errors()
    def _build_content_area(self, parent_layout: QVBoxLayout) -> None:
        """
        Subclasses must override to provide their main content area (tree, preview, etc.).
        """
        try:
            raise NotImplementedError(
                "Subclasses must implement _build_content_area to supply their primary widgets."
            )
        except NotImplementedError:
            # Re-raise as is, since it's expected for base class
            raise
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Content Area Error", f"Failed to build content area: {error_msg}")
            raise

    @log_errors()
    def _build_footer(self, parent_layout: QVBoxLayout) -> None:
        """Create footer containing selection status and primary actions."""
        try:
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
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Footer Build Error", f"Failed to build footer: {error_msg}")
            raise

    # ---------------------------------------------------------------------#
    # Signal wiring and status helpers
    # ---------------------------------------------------------------------#
    @log_errors()
    def _connect_signals(self) -> None:
        """Connect shared signals such as selection updates."""
        try:
            self.selection_store.selection_count_changed.connect(self._update_status_label)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Signal Connection Error", f"Failed to connect signals: {error_msg}")
            raise

    @log_errors()
    def _update_status_label(self, count: int) -> None:
        """Reflect selection counts in the footer and enable/disable actions."""
        try:
            total_files = sum(len(group.items) for group in self.dialog_state.groups)
            self.status_label.setText(f"{count}/{total_files} files selected")
            self.delete_button.setEnabled(count > 0)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Status Update Error", f"Failed to update status: {error_msg}")
            # Continue without updating to avoid crash

    # ---------------------------------------------------------------------#
    # Summary / Report helpers
    # ---------------------------------------------------------------------#
    @log_errors()
    def set_summary_text(self, text: str) -> None:
        """
        Replace the contents of the Summary tab.

        Text remains selectable per project requirements.
        """
        try:
            self._summary_text = text or ""
            self.summary_edit.setPlainText(self._summary_text)
            # Move cursor to start to ensure the top of the text is visible
            self.summary_edit.setTextCursor(QTextCursor(self.summary_edit.document()))
            self.summary_edit.moveCursor(QTextCursor.Start)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Summary Update Error", f"Failed to update summary: {error_msg}")
            # Do not re-raise to prevent dialog crash

    @log_errors()
    def set_report_text(self, text: str) -> None:
        """
        Replace the contents of the Report tab.

        Text remains selectable per project requirements.
        """
        try:
            self._report_text = text or ""
            self.report_edit.setPlainText(self._report_text)
            # Move cursor to start to ensure the top of the text is visible
            self.report_edit.setTextCursor(QTextCursor(self.report_edit.document()))
            self.report_edit.moveCursor(QTextCursor.Start)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Report Update Error", f"Failed to update report: {error_msg}")
            # Do not re-raise to prevent dialog crash

    @log_errors()
    def append_report_lines(self, *lines: str) -> None:
        """
        Append one or more lines to the report output in a selectable, scrollable manner.
        """
        try:
            normalized = [segment for segment in (lines or []) if segment]
            if not normalized:
                return
            current = self.report_edit.toPlainText()
            updated = "\n".join(filter(None, [current, *normalized])).strip()
            self.set_report_text(updated)
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Report Append Error", f"Failed to append to report: {error_msg}")
            # Do not re-raise to prevent dialog crash

    # ---------------------------------------------------------------------#
    # Group refresh helpers
    # ---------------------------------------------------------------------#
    @log_errors()
    def update_groups(self, groups: List[Group]) -> None:
        """
        Replace dialog groups and refresh selection counters.

        Subclasses should call this after repopulating their tree/list views.
        """
        try:
            self.dialog_state.groups = groups or []
            self._update_status_label(self.selection_store.get_selection_count())
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.warning(self, "Groups Update Error", f"Failed to update groups: {error_msg}")
            # Do not re-raise to prevent dialog crash

    # ---------------------------------------------------------------------#
    # Abstract hooks expected from subclasses
    # ---------------------------------------------------------------------#
    @log_errors()
    def _on_delete_clicked(self) -> None:
        """
        Handle the deletion of selected files by moving them to the system trash.

        This method performs the following steps:
        1. Retrieves the list of selected file paths from the selection store.
        2. Prompts the user for confirmation using a QMessageBox.
        3. Iterates through the paths and calls FileOperations.safe_delete(to_trash=True).
        4. Updates the report tab with the results of the operation.
        5. Emits the files_deleted signal upon completion.
        """
        try:
            selected_paths = self.selection_store.get_selected_paths()
            if not selected_paths:
                return

            # 1. Confirmation Dialog
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Confirm Deletion")
            msg_box.setText(
                f"Are you sure you want to move {len(selected_paths)} selected file(s) to the Recycle Bin/Trash?"
            )
            msg_box.setInformativeText("This operation is generally reversible via the system trash.")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            
            if msg_box.exec() != QMessageBox.Yes:
                return

            # 2. Perform Deletion
            deleted_count = 0
            failed_paths: List[Path] = []
            
            self.append_report_lines(
                f"--- Starting deletion of {len(selected_paths)} files to Trash ---"
            )

            for path_str in selected_paths:
                path = Path(path_str)
                try:
                    # Use safe_delete with to_trash=True
                    success = FileOperations.safe_delete(path, to_trash=True)
                    if success:
                        deleted_count += 1
                        self.append_report_lines(f"SUCCESS: Moved to trash: {path.name}")
                    else:
                        # Should only happen if path didn't exist, which is logged internally
                        failed_paths.append(path)
                        self.append_report_lines(f"SKIPPED: File not found or deletion failed: {path.name}")
                except (OSError, IOError) as e:
                    failed_paths.append(path)
                    error_detail = f"OSError/IOError: {str(e)}"
                    self.logger.error(
                        error_detail,
                        extra={
                            "file": __file__,
                            "line": inspect.currentframe().f_lineno,
                            "function": "_on_delete_clicked",
                            "path": str(path),
                            "traceback": traceback.format_exc(),
                            "dialog_title": self.windowTitle(),
                            "selected_paths_count": len(selected_paths),
                        }
                    )
                    self.append_report_lines(f"ERROR: Failed to delete {path.name}: {error_detail}")
                except Exception as e:
                    failed_paths.append(path)
                    exc_type = type(e).__name__
                    error_detail = f"{exc_type}: {str(e)}"
                    self.logger.error(
                        error_detail,
                        extra={
                            "file": __file__,
                            "line": inspect.currentframe().f_lineno,
                            "function": "_on_delete_clicked",
                            "path": str(path),
                            "locals": locals(),
                            "traceback": traceback.format_exc(),
                            "dialog_title": self.windowTitle(),
                            "selected_paths_count": len(selected_paths),
                        }
                    )
                    self.append_report_lines(f"ERROR: Failed to delete {path.name}: {error_detail}")

            # 3. Final Report and Cleanup
            self.append_report_lines(
                f"--- Deletion complete: {deleted_count} deleted, {len(failed_paths)} failed ---"
            )
            
            # Clear selection store for deleted items
            for path in selected_paths:
                if Path(path) not in failed_paths:
                    self.selection_store.remove_selection(path)
            
            # 4. Notify subclasses/parent to refresh their views
            self.files_deleted.emit(selected_paths)
            
            # If all selected files were deleted, show success message
            if deleted_count > 0 and len(failed_paths) == 0:
                QMessageBox.information(
                    self,
                    "Deletion Complete",
                    f"Successfully moved {deleted_count} file(s) to the Recycle Bin/Trash."
                )
        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"
            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_title": self.windowTitle(),
                }
            )
            QMessageBox.critical(self, "Deletion Error", f"Failed to process deletion: {error_msg}")
            raise
            
    # ---------------------------------------------------------------------#
    # Signals
    # ---------------------------------------------------------------------#
    files_deleted = Signal(list)


__all__ = ["BaseFileManagerDialog"]