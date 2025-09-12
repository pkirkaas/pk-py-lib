"""
img_app/img_app/widgets/duplicate_manager.py

DuplicateManagerDialog - Milestone 1 UI skeleton for managing duplicate groups (single_pool).

This dialog presents groups and files with per-file checkboxes and no actions enabled yet.

Syntax validation: This file has been reviewed with ast.parse for Python syntax correctness.
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QTimer, QRect, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QPushButton, QWidget, QSizePolicy, QSpacerItem, QMessageBox,
    QHeaderView, QTextEdit, QTabWidget, QSplitter, QStyledItemDelegate
)
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor, QBrush, QFont
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtCore import QModelIndex

from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error
from src.pk_py_lib.core.logging import get_logger
from src.pk_py_lib.core.database import DatabaseManager

# Optional send2trash import; fallback would be permanent deletion
try:
    from send2trash import send2trash  # type: ignore
except Exception:  # pragma: no cover
    send2trash = None  # type: ignore

# Module-level logger for duplicate operations within the app
LOGGER = get_logger("img_app.duplicates")


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string.
    
    Parameters
    ----------
    size_bytes : int
        File size in bytes.
        
    Returns
    -------
    str
        Formatted file size string (e.g., "3.5 MB").
        
    Examples
    --------
    >>> format_file_size(1024)
    '1.0 KB'
    >>> format_file_size(3670016)
    '3.5 MB'
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1
        
    return f"{size:.1f} {size_names[i]}"


def format_timestamp(timestamp: int) -> str:
    """
    Format Unix timestamp to "dd-MMM-yy" format.
    
    Parameters
    ----------
    timestamp : int
        Unix timestamp in seconds.
        
    Returns
    -------
    str
        Formatted date string (e.g., "09-Sep-25").
        
    Examples
    --------
    >>> format_timestamp(1725926400)  # Assuming this is Sep 9, 2025
    '09-Sep-25'
    """
    from datetime import datetime
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d-%b-%y")
    except (ValueError, OSError):
        return str(timestamp)



class GroupFrameDelegate(QStyledItemDelegate):
    """
    QStyledItemDelegate that adds visual separation to groups in a QTreeWidget by:
    - Applying a pure white background to top-level group header rows for optimal contrast with bold dark red text.
    - Drawing strong 3px horizontal lines above subsequent groups (except the first and last) to separate them, spanning full viewport width.
    - Increasing vertical spacing for header rows (font height + 10px) to provide moderate separation without excess,
      with adjusted line positioning to center the line in the reduced space closer to the last file of the previous group.

    The delegate always invokes the base delegate to paint default cell content first. It does not
    draw frames or borders around groups. Background is explicitly filled white for header rows, and lines are
    drawn only once per group boundary (when painting the first column of subsequent top-level items).

    Parameters
    ----------
    tree : QTreeWidget
        The tree view this delegate will paint for.

    Notes
    -----
    - This delegate is strictly visual; it does not modify model data or selection.
    - It assumes the tree is expanded by default for groups; lines are drawn based on current visual
      positions and do not adjust for collapsed states.
    - Vertical separation is implemented by increasing the height of top-level header rows via sizeHint().
    - Handles edge cases: no lines for single group or empty tree; lines span full viewport width using multiple thin lines for exact 3px thickness.
    - For groups with no children, line positioning remains correct relative to previous group.
    - Explicit fillRect ensures pure white background regardless of stylesheet interference.
    """

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree
        # Visual separation tuning constants (single source of truth for paint/sizeHint)
        self._sep_color = QColor(173, 216, 230)   # light blue separator
        self._sep_thickness = 2                   # 2 px for better visibility on dark themes
        self._sep_margin_top = 8                  # whitespace above the line
        self._content_gap = 12                    # whitespace between line and header text
        self._sep_row_height = 14                 # height of dedicated separator rows
        # Group header background lightening factors (percent for QColor.lighter)
        # Push lighter background further per request
        self._header_lighten_dark = 280
        self._header_lighten_light = 140
        # Near-white header background (not pure white, but very close for maximum readability)
        self._header_bg_color = QColor(245, 247, 250)  # ~#F5F7FA
        # Group header background lightening factors (percent for QColor.lighter)
        # Dark themes: brighten noticeably; Light themes: subtle lift for a pale band
        self._header_lighten_dark = 175
        self._header_lighten_light = 110

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Draw dedicated separator rows as full-width light-blue rules.
        For normal top-level group headers, fill a light, theme-appropriate
        background band to improve readability of the dark-red title.
        Child rows are painted normally.
        """
        try:
            # Separator rows are marked with "__separator__" in column 0, UserRole
            root_col0 = index.sibling(index.row(), 0)
            if root_col0.isValid() and root_col0.data(Qt.UserRole) == "__separator__":
                painter.save()
                viewport_rect = self._tree.viewport().rect()
                painter.setClipRect(viewport_rect)
                pen = QPen(self._sep_color)
                pen.setWidth(self._sep_thickness)
                painter.setPen(pen)
                y = option.rect.center().y()
                painter.drawLine(0, y, viewport_rect.width(), y)
                painter.restore()
                return
        except Exception:
            # Fall through to default painting on any issue
            pass

        # Light header background for top-level non-separator rows (near-white band)
        try:
            if not index.parent().isValid():
                bg = self._header_bg_color
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.restore()
        except Exception:
            pass

        # Default painting for normal rows (group headers and file items)
        super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Provide a small fixed height for separator rows; default size for all others.
        """
        base = super().sizeHint(option, index)
        try:
            root_col0 = index.sibling(index.row(), 0)
            if root_col0.isValid() and root_col0.data(Qt.UserRole) == "__separator__":
                return QSize(base.width(), self._sep_row_height)
        except Exception:
            pass
        return base


class DuplicateManagerDialog(QDialog):
    """
    Modal dialog listing duplicate groups and their member files for single_pool runs.

    Parameters
    ----------
    groups : list[dict]
        Structured list of duplicate groups. Each group dict must match:
          {
            "hash": str,           # content identity hash for the group
            "count": int,          # number of files in the group
            "files": [             # per-file metadata (raw values; no formatting here)
              { "path": str, "size": int, "modified": int, "pool": str },
              ...
            ]
          }
        Only groups with at least two files are expected.
    parent : Optional[QWidget]
        Optional Qt parent widget.

    Behavior
    --------
    - Header label shows summary "Duplicate Groups: N — Files: M".
    - Tree lists groups as top-level items with title "Group #i — Hash: <hash> — Files: K".
    - Child items are individual files with a checkbox in the "Select" column.
    - Columns: [Select, File Path, Modified, Size]; sorting enabled.
    - File Path column stretches; Modified and Size auto-resize to contents for readability.
    - Delete button is enabled when at least one file is checked; deletions use Recycle Bin when available, with safe fallbacks and confirmations.
    - The dialog uses a vertical QSplitter to separate the tab widget (top pane) from the duplicate management interface (bottom pane).
    - The top pane (QTabWidget) is initially sized to fit the content height of the Processing Summary tab.

    Notes
    -----
    - Timestamps (Modified) and Sizes are shown as raw integers; no humanization here.
    - The dialog is resizable and modal; it can be closed with the Close button or Esc.
    - Users can resize the splitter handle to adjust the height of the top and bottom panes.
    - The initial height of the top pane is calculated based on the content's sizeHint() to ensure it fits the text content comfortably.
    """

    def __init__(self, groups: List[Dict[str, Any]], summary_text: str = "", report_text: str = "", parent: Optional[QWidget] = None) -> None:
        """
        Construct the dialog with duplicate groups and populate the tree.

        Parameters
        ----------
        groups : List[Dict[str, Any]]
            Duplicate groups structured as described in the class docstring. Only groups
            with count >= 2 are expected, but the dialog will render whatever is provided.
        summary_text : str
            Text content for the Processing Summary tab.
        report_text : str
            Text content for the Duplicate Report tab.
        parent : Optional[QWidget]
            Optional parent widget; typically the main window.

        Behavior
        --------
        - Builds the UI with a resizable splitter separating the tab widget (top pane)
          from the duplicate management interface (bottom pane).
        - Populates group/file rows with checkboxes for file items.
        - Wires the Delete button to be enabled only when at least one file is checked.
        - Sets initial splitter position based on content height of Processing Summary tab.

        Notes
        -----
        - All UI work occurs on the GUI thread; no background threads are used.
        - The top pane (QTabWidget) is initially sized to fit the Processing Summary content.
        - Users can resize the splitter handle to adjust pane heights.
        - Syntax validation was performed with ast.parse prior to inclusion.
        """
        super().__init__(parent)
        print(f"Dialog initialized with groups={len(groups or [])}, summary_text len={len(summary_text or '')}, report_text len={len(report_text or '')}", file=sys.stderr)
        print(f"[DEBUG DuplicateManagerDialog] Initialized with {len(groups or [])} groups, summary length: {len(summary_text or '')}, report length: {len(report_text or '')}", file=sys.stderr)
        self.setWindowTitle("Duplicate Manager")
        self.setModal(True)
        self.resize(900, 600)
        try:
            self.setSizeGripEnabled(True)
        except Exception:
            pass

        # Keep a local reference to input data
        self._groups: List[Dict[str, Any]] = list(groups or [])

        # Build UI
        main_layout = QVBoxLayout(self)

        # Compute summary numbers for header
        total_groups = len(self._groups)
        total_files = 0
        try:
            total_files = sum(len(g.get("files") or []) for g in self._groups)
        except Exception:
            total_files = 0

        # Create a vertical splitter for resizable top and bottom panes
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)  # Prevent complete collapse of either pane

        # Top pane: tabs for summary and report
        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.summary_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.summary_tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Reduce vertical space in Processing Summary by setting minimal document margins for compact layout;
        # this minimizes the gap below the last line (e.g., "Errors: 0") without affecting readability,
        # ensuring the summary section ends closely above the Duplicates Groups section in the splitter.
        self.summary_tab.document().setDocumentMargin(0)

        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)
        self.report_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.report_tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, "Duplicate Report")
        self.splitter.addWidget(self.tabs)

        # Bottom pane: container for the rest of the UI elements
        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins for seamless appearance
        # Set minimal spacing in the bottom layout to keep the Duplicates Groups section compact while
        # allowing sufficient separation between elements (header, tree, status); default is small, but explicit for control.
        bottom_layout.setSpacing(5)

        # Header label (remains for group/file counts)
        self.header_label = QLabel(f"Duplicate Groups: {total_groups} — Files: {total_files}", self)
        bottom_layout.addWidget(self.header_label)

        # Tree widget with 3 columns: Select, File Path, Modified (Size removed)
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Select", "File Path", "Modified"])
        # Sorting disabled to keep dedicated separator rows correctly positioned between groups
        self.tree.setSortingEnabled(False)

        # Column sizing policies:
        # - File Path stretches
        # - Modified auto-resizes to contents for readability
        # - Select column fits to checkbox content
        try:
            header = self.tree.header()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        except Exception:
            # Defensive in case Qt platform backends vary
            pass

        # Minimal, selection-friendly stylesheet; explicitly no borders or frames to prevent visual artifacts
        self.tree.setAlternatingRowColors(False)
        self.tree.setStyleSheet("""
QTreeWidget::item { background-color: transparent; border: none; }
QTreeWidget::item:selected { background-color: palette(highlight); color: palette(highlighted-text); }
QTreeView::branch { background: transparent; }
QTreeWidget { border: none; }
""")
        # Install delegate for group separation (no frames, only backgrounds and lines)
        self.tree.setItemDelegate(GroupFrameDelegate(self.tree))
        
        bottom_layout.addWidget(self.tree)

        # Populate tree with groups and files
        # Each group is a top-level item with text in the "File Path" column (index 1)
        for i, group in enumerate(self._groups, start=1):
            # Insert a dedicated separator row between groups (after the first)
            if i > 1:
                sep = QTreeWidgetItem(self.tree)
                try:
                    sep.setData(0, Qt.UserRole, "__separator__")
                    sep.setFirstColumnSpanned(True)
                    sep.setSizeHint(0, QSize(0, 14))
                    # No interaction on separator rows
                    sep.setFlags(Qt.NoItemFlags)
                except Exception:
                    pass
            try:
                gh = str(group.get("hash") or "")
            except Exception:
                gh = ""
            files = list(group.get("files") or [])
            k = len(files)
            
            # Get file size from first file in group (all files are identical)
            group_size = 0
            if files:
                try:
                    group_size = int(files[0].get("size")) if files[0].get("size") is not None else 0
                except Exception:
                    group_size = 0

            top = QTreeWidgetItem(self.tree)
            # Place the group title in the File Path column to keep the "Select" column free for child checkboxes
            # Format: "Group #i: k files (formatted_size)" - hash removed as requested
            formatted_size = format_file_size(group_size)
            top.setText(1, f"Group #{i}: {k} files ({formatted_size})")
            # Make the group rows non-checkable
            top.setFlags((top.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsUserCheckable)
            # Header visual: bold font and dark red text on the label column only
            try:
                fnt = top.font(1)
                fnt.setBold(True)
                top.setFont(1, fnt)
                top.setForeground(1, QBrush(QColor("#200")))
            except Exception:
                pass
            # Expand groups by default for quick inspection
            self.tree.expandItem(top)

            # Add file children with a checkbox in column 0
            for f in files:
                try:
                    path = str(f.get("path") or "")
                except Exception:
                    path = ""
                try:
                    modified = int(f.get("modified")) if f.get("modified") is not None else 0
                except Exception:
                    modified = 0
                try:
                    size = int(f.get("size")) if f.get("size") is not None else 0
                except Exception:
                    size = 0

                child = QTreeWidgetItem(top)
                # Column 0 holds a checkbox; we add text to other columns
                child.setText(1, path)
                # Format modified timestamp to "dd-MMM-yy" using helper function
                child.setText(2, format_timestamp(modified))
                # Store raw values for reliable retrieval independent of display formatting
                try:
                    child.setData(1, Qt.UserRole, path)
                    child.setData(2, Qt.UserRole, modified)
                    # Store size in UserRole for potential future use, though not displayed
                    child.setData(3, Qt.UserRole, size)
                except Exception:
                    pass
                # Enable user check state on the "Select" column
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                child.setCheckState(0, Qt.Unchecked)
                # Provide numeric sort keys for Modified to ensure numeric sort when used
                try:
                    child.setData(2, Qt.UserRole, modified)
                except Exception:
                    pass

        # Status line: shows "X files selected out of Y total files"
        self.status_label = QLabel("0 files selected out of 0 total files", self)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_layout.addWidget(self.status_label)

        # Buttons row: spacer + [Delete] [Close]
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)  # Initially disabled; enabled when any file item is checked
        btn_row.addWidget(self.delete_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        bottom_layout.addLayout(btn_row)

        # Initialize status line with current counts
        self._update_status_line()

        # Add bottom widget to splitter
        self.splitter.addWidget(bottom_widget)

        # Add splitter to main layout
        main_layout.addWidget(self.splitter)
        # Minimize spacing in the main layout to reduce any gap between the splitter panes and ensure
        # the summary section ends closely above the Duplicates Groups section without unnecessary vertical space.
        main_layout.setSpacing(0)

        # Set initial splitter sizes based on content height after UI is populated
        # This is handled by the QTimer singleShot call below

        # Wire signals (after population to avoid spurious itemChanged during build)
        try:
            self.tree.itemChanged.connect(self._on_item_changed)
        except Exception:
            # Some backends might not expose itemChanged; defensive
            pass
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self._update_delete_enabled()

        # Set up single-shot timer to configure splitter after UI is fully populated
        QTimer.singleShot(100, self._configure_initial_splitter_sizes)

    def _on_item_changed(self, item: "QTreeWidgetItem", column: int) -> None:
        """
        React to any item change (primarily checkbox toggles) to update the Delete button state and status line.

        Parameters
        ----------
        item : QTreeWidgetItem
            The item that changed. For this dialog, child items represent files and expose a check state in column 0.
        column : int
            The column index that changed; the checkbox lives in column 0.

        Behavior
        --------
        - Recomputes whether any file rows are checked.
        - Enables the Delete button only when at least one file is checked.
        - Updates the status line with current selection counts.
        """
        try:
            self._update_delete_enabled()
            self._update_status_line()
        except Exception as e:
            # Defensive: never propagate errors from UI state updates
            LOGGER.error("State update after itemChanged failed", exception=e, variables={"column": column})

    def _is_separator_item(self, item: "QTreeWidgetItem" | None) -> bool:
        """
        Determine whether a top-level item is a dedicated separator row.

        A separator row is a top-level QTreeWidgetItem we insert between groups.
        It is marked by setting column 0, Qt.UserRole to the sentinel string "__separator__".
        These rows:
        - Have no children and no flags (non-interactive)
        - Must be excluded from counts and selection scans
        - Are painted by GroupFrameDelegate as a thin light-blue rule

        Parameters
        ----------
        item : QTreeWidgetItem | None
            The item to test (may be None).

        Returns
        -------
        bool
            True if item is a separator row, else False.
        """
        try:
            if item is None:
                return False
            return item.data(0, Qt.UserRole) == "__separator__"
        except Exception:
            return False

    def _update_delete_enabled(self) -> None:
        """
        Compute whether any file items are checked and toggle the Delete button accordingly.
        """
        any_checked = False
        try:
            for gi in range(self.tree.topLevelItemCount()):
                g = self.tree.topLevelItem(gi)
                if self._is_separator_item(g):
                    continue
                for ci in range(g.childCount()):
                    c = g.child(ci)
                    if c.checkState(0) == Qt.Checked:
                        any_checked = True
                        break
                if any_checked:
                    break
        except Exception:
            any_checked = False
        self.delete_btn.setEnabled(any_checked)

    def _update_status_line(self) -> None:
        """
        Update the status line with current selection and total file/group counts.
        
        Behavior
        --------
        - Counts total files across all groups.
        - Counts checked files across all groups.
        - Counts groups with at least one selected file.
        - Counts total groups.
        - Updates status label text to show "X files from Y groups selected out of Z total files in W groups".
        - If no duplicates to manage, shows "No duplicates to manage".
        """
        try:
            total_files = 0
            selected_files = 0
            groups_with_selected = 0
            total_groups = 0
            
            # Count total files, selected files, and groups with selected files (skip separator rows)
            for gi in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(gi)
                if self._is_separator_item(group):
                    continue
                total_groups += 1
                group_file_count = group.childCount()
                total_files += group_file_count
                
                # Check if this group has any selected files
                has_selected = False
                for ci in range(group_file_count):
                    file_item = group.child(ci)
                    if file_item.checkState(0) == Qt.Checked:
                        selected_files += 1
                        has_selected = True
                
                if has_selected:
                    groups_with_selected += 1
            
            # Update status label
            if total_groups == 0:
                self.status_label.setText("No duplicates to manage")
            else:
                self.status_label.setText(
                    f"{selected_files} files from {groups_with_selected} groups selected "
                    f"out of {total_files} total files in {total_groups} groups"
                )
        except Exception as e:
            # Log error but don't crash - set default text
            LOGGER.error("Failed to update status line", exception=e)
            self.status_label.setText("Error updating selection status")

    def _collect_checked_files(self) -> List[Dict[str, Any]]:
        """
        Collect all checked file rows.

        Returns
        -------
        List[dict]
            List of dictionaries for each checked file with:
            - path: str — absolute file system path
            - size: int — size in bytes (raw)
            - modified: int — last modification timestamp (raw)
            - group_item: QTreeWidgetItem — owning group item (top-level)
            - file_item: QTreeWidgetItem — the row item for this file

        Notes
        -----
        - Uses Qt.UserRole to retrieve raw values, falling back to displayed text.
        - All values are built-in types to satisfy cross-thread safety rules (although we run in GUI thread).
        """
        selected: List[Dict[str, Any]] = []
        for gi in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(gi)
            for ci in range(g.childCount()):
                f = g.child(ci)
                try:
                    if f.checkState(0) != Qt.Checked:
                        continue
                    path_v = f.data(1, Qt.UserRole) or f.text(1)
                    mod_v = f.data(2, Qt.UserRole) or f.text(2)
                    size_v = f.data(3, Qt.UserRole) or f.text(3)
                    path_s = str(path_v) if path_v is not None else ""
                    mod_i = int(mod_v) if mod_v not in (None, "") else 0
                    size_i = int(size_v) if size_v not in (None, "") else 0
                    selected.append({
                        "path": path_s,
                        "size": size_i,
                        "modified": mod_i,
                        "group_item": g,
                        "file_item": f,
                    })
                except Exception:
                    # Skip malformed rows defensively
                    continue
        return selected

    def _refresh_header_counts(self) -> None:
        """
        Refresh header label counts from the current tree contents.

        Behavior
        --------
        - Counts top-level groups still present.
        - Sums all child rows across groups as the file count.
        """
        try:
            groups = 0
            files = 0
            for gi in range(self.tree.topLevelItemCount()):
                g = self.tree.topLevelItem(gi)
                if self._is_separator_item(g):
                    continue
                groups += 1
                files += g.childCount()
            self.header_label.setText(f"Duplicate Groups: {groups} — Files: {files}")
        except Exception as e:
            LOGGER.error("Header refresh failed", exception=e)

    def _on_delete_clicked(self) -> None:
        """
        Delete the currently checked files, using the system Recycle Bin when available.

        Workflow
        --------
        - If no files are selected, shows info and returns.
        - Confirm intent:
          - If send2trash is available: "Delete N file(s) to Recycle Bin?"
          - If send2trash is not available: "Permanently delete N file(s)?" with explicit warning, followed by a second confirmation.
        - Perform deletions with a busy cursor; track successes and failures.
        - On each success:
          - Remove the file row from the tree. If the group now has fewer than 2 items, remove the entire group.
          - Attempt to mark the DB row invalid (is_valid=0, last_scanned=CURRENT_TIMESTAMP); failures are logged and surfaced but do not abort.
        - After processing, refresh header counts and show a summary info dialog.

        Edge Cases
        ----------
        - FileNotFoundError is treated as success (UI and DB update still attempted).
        - PermissionError and other exceptions are logged and reported; processing continues.

        Examples
        --------
        >>> # User selects files via checkboxes and presses Delete
        >>> # The dialog confirms and then deletes files to Recycle Bin when possible.
        """
        try:
            sel = self._collect_checked_files()
            if not sel:
                show_selectable_info(self, "Delete", "No files selected.")
                return

            n = len(sel)
            use_trash = send2trash is not None
            if use_trash:
                confirmed = self._ask_selectable_question(
                    "Confirm Deletion",
                    f"Delete {n} file(s) to the system Recycle Bin?"
                )
                if not confirmed:
                    return
            else:
                confirmed = self._ask_selectable_question(
                    "Confirm Permanent Deletion",
                    f"Permanently delete {n} file(s)? This cannot be undone.",
                    "Recycle Bin integration (send2trash) is not available on this system."
                )
                if not confirmed:
                    return
                # Second confirmation for permanent delete, as an extra safety step
                confirmed2 = self._ask_selectable_question(
                    "Confirm Permanent Deletion (Step 2)",
                    f"Really permanently delete {n} file(s)? This action cannot be undone."
                )
                if not confirmed2:
                    return

            # Busy cursor for the bulk operation
            try:
                QGuiApplication.setOverrideCursor(Qt.WaitCursor)
            except Exception:
                pass

            deleted_ok = 0
            failed = 0
            db_mgr = self._get_database_manager()

            for entry in sel:
                path = entry.get("path") or ""
                group_item = entry.get("group_item")
                file_item = entry.get("file_item")
                action = "send2trash" if use_trash else "os.remove"

                # Attempt to delete the file
                try:
                    if use_trash and send2trash is not None:
                        send2trash(path)  # type: ignore[misc]
                    else:
                        # May raise FileNotFoundError or PermissionError
                        os.remove(path)

                    # Success or file did not exist
                    deleted_ok += 1

                    # Remove UI row if it still exists
                    try:
                        if file_item is not None and getattr(file_item, "treeWidget", None) and file_item.treeWidget() is not None:
                            parent = file_item.parent()
                            if parent is not None:
                                parent.removeChild(file_item)
                            # If group now has fewer than 2 children, remove the group row
                            if parent is not None and parent.childCount() < 2:
                                top_parent = parent.parent()  # type: ignore[assignment]
                                if top_parent is None and getattr(parent, "treeWidget", None):
                                    idx = self.tree.indexOfTopLevelItem(parent)
                                    if idx >= 0:
                                        self.tree.takeTopLevelItem(idx)
                                        # Remove preceding separator if present
                                        try:
                                            if idx - 1 >= 0:
                                                prev = self.tree.topLevelItem(idx - 1)
                                                if self._is_separator_item(prev):
                                                    self.tree.takeTopLevelItem(idx - 1)
                                        except Exception:
                                            pass
                    except Exception as e_ui:
                        LOGGER.error("UI removal failed after delete", exception=e_ui, variables={"path": path})

                    # Mark DB row invalid; non-blocking on failure
                    if db_mgr is not None:
                        try:
                            with db_mgr.get_connection(db_mgr.cache_db) as conn:
                                conn.execute(
                                    "DELETE FROM image_metadata WHERE file_path = ?",
                                    (path,),
                                )
                        except Exception as e_db:
                            failed += 0  # DB failure does not count as delete failure
                            LOGGER.error(
                                "DB update failed after deletion",
                                exception=e_db,
                                variables={"path": path, "action": "db_update"}
                            )
                            show_selectable_error(self, "Database Update Failed", f"Failed to update database for:\n{path}\n\n{e_db}")

                except FileNotFoundError:
                    # Treat as success: file is already gone
                    deleted_ok += 1
                    # UI and DB handling same as success
                    try:
                        if file_item is not None and getattr(file_item, "treeWidget", None) and file_item.treeWidget() is not None:
                            parent = file_item.parent()
                            if parent is not None:
                                parent.removeChild(file_item)
                            if parent is not None and parent.childCount() < 2:
                                idx = self.tree.indexOfTopLevelItem(parent)
                                if idx >= 0:
                                    self.tree.takeTopLevelItem(idx)
                                    # Remove preceding separator if present
                                    try:
                                        if idx - 1 >= 0:
                                            prev = self.tree.topLevelItem(idx - 1)
                                            if self._is_separator_item(prev):
                                                self.tree.takeTopLevelItem(idx - 1)
                                    except Exception:
                                        pass
                    except Exception as e_ui2:
                        LOGGER.error("UI removal failed after FileNotFound", exception=e_ui2, variables={"path": path})

                    if db_mgr is not None:
                        try:
                            with db_mgr.get_connection(db_mgr.cache_db) as conn:
                                conn.execute(
                                    "UPDATE image_metadata SET is_valid = 0, last_scanned = CURRENT_TIMESTAMP WHERE file_path = ?",
                                    (path,),
                                )
                        except Exception as e_db2:
                            LOGGER.error(
                                "DB update failed after FileNotFound",
                                exception=e_db2,
                                variables={"path": path, "action": "db_update"}
                            )
                            show_selectable_error(self, "Database Update Failed", f"Failed to update database for:\n{path}\n\n{e_db2}")

                except PermissionError as e_perm:
                    failed += 1
                    LOGGER.error("Delete failed (permission)", exception=e_perm, variables={"path": path, "action": action})
                    show_selectable_error(self, "Delete Failed", f"Permission denied:\n{path}\n\n{e_perm}")

                except Exception as e_del:
                    failed += 1
                    LOGGER.error("Delete failed", exception=e_del, variables={"path": path, "action": action})
                    show_selectable_error(self, "Delete Failed", f"Failed to delete:\n{path}\n\n{e_del}")

            # End-for: restore cursor and refresh UI
            try:
                QGuiApplication.restoreOverrideCursor()
            except Exception:
                pass

            self._refresh_header_counts()
            self._update_delete_enabled()
            self._update_status_line()
            
            # Summary information
            show_selectable_info(self, "Delete Summary", f"Deleted {deleted_ok} file(s); {failed} failed.")
        except Exception as e:
            # Top-level safety: log and show error but ensure cursor is restored
            try:
                QGuiApplication.restoreOverrideCursor()
            except Exception:
                pass
            LOGGER.error("Delete operation failed", exception=e)
            show_selectable_error(self, "Delete Error", f"Delete operation failed:\n{e}")

    def _get_database_manager(self) -> Optional[DatabaseManager]:
        """
        Attempt to locate an application-provided DatabaseManager by walking up the parent chain.

        Returns
        -------
        Optional[DatabaseManager]
            The DatabaseManager instance if attached to any parent as 'database_manager', else None.

        Notes
        -----
        - The application entry point attaches managers to the main window (see app.main()).
        - If no manager is found, DB updates are skipped but deletions proceed.
        """
        try:
            w = self.parent()
            # Walk up the QObject parent chain to find an attribute 'database_manager'
            while w is not None:
                dm = getattr(w, "database_manager", None)
                if isinstance(dm, DatabaseManager):
                    return dm
                w = w.parent()  # type: ignore[assignment]
        except Exception as e:
            LOGGER.error("Failed to resolve DatabaseManager from parent chain", exception=e)
        return None

    def _ask_selectable_question(self, title: str, text: str, informative_text: Optional[str] = None) -> bool:
        """
        Show a Yes/No question dialog with selectable text.

        Parameters
        ----------
        title : str
            Window title.
        text : str
            Main question text.
        informative_text : Optional[str]
            Optional details shown below the main text.

        Returns
        -------
        bool
            True if user answered Yes; False otherwise.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        if informative_text:
            try:
                box.setInformativeText(informative_text)
            except Exception:
                try:
                    box.setText(f"{text}\n\n{informative_text}")
                except Exception:
                    pass

        # Ensure selectability per project requirements
        try:
            box.setTextInteractionFlags(  # type: ignore[attr-defined]
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
            )
        except Exception:
            pass
        try:
            # Make all labels selectable
            from PySide6.QtWidgets import QLabel  # local import to avoid top clutter
            for lbl in box.findChildren(QLabel):
                try:
                    lbl.setTextInteractionFlags(
                        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
                    )
                    lbl.setOpenExternalLinks(True)
                    lbl.setTextFormat(Qt.PlainText)
                except Exception:
                    pass
        except Exception:
            pass

        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def _configure_initial_splitter_sizes(self) -> None:
        """
        Configure initial splitter sizes based on content height after UI is fully populated.

        Behavior
        --------
        - Calculates the natural height required by the Processing Summary tab content.
        - Sets the top pane height to fit the content with appropriate padding.
        - Ensures reasonable minimum and maximum height constraints.
        - Configures the splitter to allow user resizing while providing sensible defaults.

        Edge Cases
        ----------
        - Handles empty or minimal content gracefully with minimum height constraints.
        - Prevents the top pane from consuming all available space.
        - Maintains functionality across different platform and content scenarios.
        """
        try:
            # Calculate the natural height of the Processing Summary content
            summary_height = self.summary_tab.sizeHint().height()
            
            # Add padding for tab headers, margins, and visual comfort
            tab_header_height = 30  # Approximate height of tab bar
            padding = 20  # Additional padding for comfort
            
            total_top_height = summary_height + tab_header_height + padding
            
            # Ensure we have reasonable minimum and maximum constraints
            min_top_height = 100  # Minimum sensible height for top pane
            max_top_height = self.height() - 200  # Leave room for bottom pane
            
            # Clamp the calculated height to reasonable bounds
            clamped_height = max(min_top_height, min(total_top_height, max_top_height))
            
            # Enforce maximum height on the tabs widget to prevent the top pane from growing beyond content height
            # This allows shrinking via splitter handle but caps expansion at the calculated content-fitted height
            # Ensures the pane remains shrinkable while preventing unnecessary growth during dialog resizes
            self.tabs.setMaximumHeight(clamped_height)
            
            # Set splitter sizes - using proportional approach for better cross-platform behavior
            total_height = self.splitter.height()
            if total_height > 0:
                top_ratio = clamped_height / total_height
                bottom_ratio = 1.0 - top_ratio
                self.splitter.setSizes([int(clamped_height), int(total_height * bottom_ratio)])
            
        except Exception as e:
            # Log error but don't crash the dialog - use default splitter behavior
            LOGGER.error("Failed to set initial splitter sizes", exception=e)
            # Set reasonable default split (40% top, 60% bottom)
            default_top = int(self.splitter.height() * 0.4)
            self.splitter.setSizes([default_top, self.splitter.height() - default_top])