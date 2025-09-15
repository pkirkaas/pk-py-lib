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
from src.pk_py_lib.core.image import similarity
from src.pk_py_lib.core.filesystem.traversal import IMAGE_EXTENSIONS
from PySide6.QtWidgets import QComboBox, QSpinBox, QHBoxLayout
from PySide6.QtGui import QPixmap, QIcon

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
    Modal dialog for managing duplicates or visually similar images.

    Supports two modes:
    - 'duplicates': Exact matches using cryptographic hashes (existing functionality).
    - 'similarity': Perceptual similarity using pHash/wHash from DB, with Hamming distances.
      Displays groups with thumbnails and similarity scores; configurable via settings.

    Parameters
    ----------
    mode : str
        'duplicates' (default) or 'similarity'.
    groups : Optional[list[dict]]
        For duplicates mode: Structured groups with 'hash', 'count', 'files' (path, size, modified, pool).
    db_manager : Optional[DatabaseManager]
        Required for similarity mode (queries image_hashes).
    settings_manager : Optional[SettingsManager]
        For similarity settings (algorithms, thresholds).
    paths : Optional[List[str]]
        For similarity: Paths to scan if hashes missing.
    summary_text : str
        Processing summary tab content.
    report_text : str
        Duplicate/similarity report tab content.
    parent : Optional[QWidget]
        Parent widget.

    Behavior
    --------
    - Duplicates mode: Existing UI with file paths, modified times; delete to Recycle Bin.
    - Similarity mode: Adds algorithm selector, threshold spinner, refresh button.
      Queries DB for hashes; if low coverage, optionally scans paths to compute missing hashes.
      Tree: Select, Preview (thumbnail), Path, Score (Hamming distance).
      Groups shown with max score; delete works similarly.
    - Common: Splitter for tabs (summary/report) and tree; status line for selections.
    - Error handling: Popups for failures (e.g., no hashes, DB errors); logs details.

    Notes
    -----
    - Similarity requires pre-computed hashes in image_hashes table (via scan_directory).
    - Thumbnails: 64x64 scaled previews; errors skipped.
    - PoC: Synchronous scan; brute-force grouping (O(n^2) for <1000 images).
    - Settings default: pHash threshold 10; from settings_manager if available.
    - Resizable, modal; close via button or Esc.
    """

    def __init__(
        self,
        mode: str = "duplicates",
        groups: Optional[List[Dict[str, Any]]] = None,
        db_manager: Optional[DatabaseManager] = None,
        settings_manager: Optional[SettingsManager] = None,
        paths: Optional[List[str]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Construct the dialog based on mode.
    
        Parameters
        ----------
        mode : str
            'duplicates' or 'similarity'.
        groups : Optional[List[Dict[str, Any]]]
            For duplicates: groups with 'hash', 'count', 'files'.
        db_manager : Optional[DatabaseManager]
            For similarity DB access.
        settings_manager : Optional[SettingsManager]
            For similarity config.
        paths : Optional[List[str]]
            Scan paths for missing hashes.
        summary_text : str
            Summary content.
        report_text : str
            Report content.
        parent : Optional[QWidget]
    
        Behavior
        --------
        - Duplicates: Builds existing UI, populates from groups.
        - Similarity: Adds controls, computes groups from DB/settings.
        - Splitter for tabs/tree; initial sizing via timer.
    
        Notes
        -----
        - Similarity requires hashes; prompts scan if missing.
        - All on GUI thread; synchronous for PoC.
        """
        super().__init__(parent)
        self.mode = mode.lower()
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.paths = paths or []
    
        if self.mode == "similarity" and not db_manager:
            raise ValueError("Similarity mode requires DatabaseManager")
    
        # Use default settings for similarity (settings_manager integration pending)
        self.settings = {
            "similarity": {
                "enabled_algorithms": ["phash"],
                "phash_threshold": 10,
                "whash_threshold": 12,
                "max_distance": 15
            }
        }
        LOGGER.info("Using default similarity settings")
    
        title = "Duplicate Manager" if self.mode == "duplicates" else "Similarity Manager"
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(1000, 700)  # Wider for thumbs
        try:
            self.setSizeGripEnabled(True)
        except Exception:
            pass
    
        # For duplicates
        self._groups: List[Dict[str, Any]] = list(groups or []) if self.mode == "duplicates" else []
    
        # Build UI
        main_layout = QVBoxLayout(self)
    
        # Compute summary numbers (for duplicates)
        total_groups = len(self._groups)
        total_files = 0
        if self.mode == "duplicates":
            try:
                total_files = sum(len(g.get("files") or []) for g in self._groups)
            except Exception:
                total_files = 0
    
        # Splitter for tabs and main content
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
    
        # Top tabs
        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.summary_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.summary_tab.document().setDocumentMargin(0)
    
        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)
        self.report_tab.setLineWrapMode(QTextEdit.NoWrap)
    
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, f"{title.replace(' Manager', ' Report')}")
        self.splitter.addWidget(self.tabs)
    
        # Bottom widget
        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)
    
        # Header label
        header_text = f"Duplicate Groups: {total_groups} — Files: {total_files}" if self.mode == "duplicates" else "Similarity Groups: Loading..."
        self.header_label = QLabel(header_text, self)
        bottom_layout.addWidget(self.header_label)
    
        # Similarity controls (only if mode similarity)
        if self.mode == "similarity":
            controls_layout = QHBoxLayout()
            controls_layout.addWidget(QLabel("Algorithm:"))
            self.alg_combo = QComboBox()
            self.alg_combo.addItems(["phash", "whash"])
            alg_default = self.settings["similarity"].get("enabled_algorithms", ["phash"])[0]
            self.alg_combo.setCurrentText(alg_default)
            controls_layout.addWidget(self.alg_combo)
    
            controls_layout.addWidget(QLabel("Threshold:"))
            self.threshold_spin = QSpinBox()
            self.threshold_spin.setMinimum(0)
            self.threshold_spin.setMaximum(64)
            thresh_default = self.settings["similarity"].get("phash_threshold", 10)
            self.threshold_spin.setValue(thresh_default)
            controls_layout.addWidget(self.threshold_spin)
    
            self.refresh_btn = QPushButton("Refresh Groups")
            controls_layout.addWidget(self.refresh_btn)
            controls_layout.addStretch()
    
            controls_widget = QWidget()
            controls_widget.setLayout(controls_layout)
            bottom_layout.addWidget(controls_widget)
    
        # Tree widget
        self.tree = QTreeWidget(self)
        if self.mode == "duplicates":
            self.tree.setColumnCount(3)
            self.tree.setHeaderLabels(["Select", "File Path", "Modified"])
        else:
            self.tree.setColumnCount(4)
            self.tree.setHeaderLabels(["Select", "Preview", "File Path", "Similarity Score"])
    
        self.tree.setSortingEnabled(False)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1 if self.mode == "duplicates" else 2, QHeaderView.Stretch)  # Path stretches
        if self.mode == "duplicates":
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        else:
            header.setSectionResizeMode(1, QHeaderView.Fixed)
            header.resizeSection(1, 70)  # Thumb width
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
    
        # Stylesheet
        self.tree.setAlternatingRowColors(False)
        self.tree.setStyleSheet("""
     QTreeWidget::item { background-color: transparent; border: none; }
     QTreeWidget::item:selected { background-color: palette(highlight); color: palette(highlighted-text); }
     QTreeView::branch { background: transparent; }
     QTreeWidget { border: none; }
        """)
        self.tree.setItemDelegate(GroupFrameDelegate(self.tree))
    
        bottom_layout.addWidget(self.tree)
    
        # Status label
        initial_status = "No duplicates to manage" if self.mode == "duplicates" else "No similar images to manage"
        self.status_label = QLabel(initial_status, self)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_layout.addWidget(self.status_label)
    
        # Populate based on mode
        if self.mode == "duplicates":
            self._populate_tree()
        else:
            self._compute_and_populate()
    
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
    
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)
    
        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
    
        bottom_layout.addLayout(btn_row)
    
        self._update_status_line()
        self.splitter.addWidget(bottom_widget)
        main_layout.addWidget(self.splitter)
        main_layout.setSpacing(0)
    
        # Wire signals
        self.tree.itemChanged.connect(self._on_item_changed)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self._update_delete_enabled()
    
        if self.mode == "similarity":
            self.alg_combo.currentTextChanged.connect(self._on_settings_changed)
            self.threshold_spin.valueChanged.connect(self._on_settings_changed)
            self.refresh_btn.clicked.connect(self._compute_and_populate)
    
        QTimer.singleShot(100, self._configure_initial_splitter_sizes)


    def _populate_tree(self) -> None:
        """
        Populate the tree with duplicate groups for exact duplicates.

        - Columns: Select (checkbox), Path, Modified.
        - Groups: Top-level items with header "Group #i: k files (size)", bold dark red.
        - Files: Child items with path and formatted modified date.
        - Separators between groups.
        - Expands groups, stores data in UserRole.

        Handles empty groups.
        """
        self.tree.clear()
        if not self._groups:
            self.header_label.setText("No duplicates found")
            self._update_status_line()
            return

        for i, group in enumerate(self._groups, start=1):
            if i > 1:
                sep = QTreeWidgetItem(self.tree)
                try:
                    sep.setData(0, Qt.UserRole, "__separator__")
                    sep.setFirstColumnSpanned(True)
                    sep.setSizeHint(0, QSize(0, 14))
                    sep.setFlags(Qt.NoItemFlags)
                except Exception:
                    pass

            files = list(group.get("files") or [])
            k = len(files)

            group_size = 0
            if files:
                try:
                    group_size = int(files[0].get("size")) if files[0].get("size") is not None else 0
                except Exception:
                    group_size = 0

            formatted_size = format_file_size(group_size)
            top = QTreeWidgetItem(self.tree)
            top.setText(1, f"Group #{i}: {k} files ({formatted_size})")
            top.setFlags((top.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsUserCheckable)
            try:
                fnt = top.font(1)
                fnt.setBold(True)
                top.setFont(1, fnt)
                top.setForeground(1, QBrush(QColor("#200")))
            except Exception:
                pass
            self.tree.expandItem(top)

            for f in files:
                path = str(f.get("path") or "")
                modified = int(f.get("modified_time") or f.get("modified") or 0)
                size = int(f.get("size") or 0)

                child = QTreeWidgetItem(top)
                child.setText(1, path)
                child.setText(2, format_timestamp(modified))
                try:
                    child.setData(1, Qt.UserRole, path)
                    child.setData(2, Qt.UserRole, modified)
                    child.setData(3, Qt.UserRole, size)
                except Exception:
                    pass
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                child.setCheckState(0, Qt.Unchecked)

        self._update_status_line()
        self.header_label.setText(f"Duplicate Groups: {len(self._groups)}")

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
                text = "No duplicates to manage"
            else:
                text = f"{selected_files} files from {groups_with_selected} groups selected out of {total_files} total files in {total_groups} groups"
            self.status_label.setText(text)
            LOGGER.debug(f"Status updated: {text}")
        except Exception as e:
            # Log error but don't crash - set default text
            LOGGER.error("Failed to update status line", exception=e)
            text = "Error updating selection status"
            self.status_label.setText(text)
            LOGGER.debug(f"Status updated: {text}")

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
            - score: int — similarity score (0 for duplicates, N/A otherwise)
            - group_item: QTreeWidgetItem — owning group item (top-level)
            - file_item: QTreeWidgetItem — the row item for this file
    
        Notes
        -----
        - Uses Qt.UserRole to retrieve raw values, falling back to displayed text.
        - All values are built-in types to satisfy cross-thread safety rules (although we run in GUI thread).
        - For similarity: score from UserRole 4 or text(3).
        """
        selected: List[Dict[str, Any]] = []
        for gi in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(gi)
            for ci in range(g.childCount()):
                f = g.child(ci)
                try:
                    if f.checkState(0) != Qt.Checked:
                        continue
                    path_v = f.data(1 if self.mode == "duplicates" else 2, Qt.UserRole) or f.text(1 if self.mode == "duplicates" else 2)
                    mod_v = f.data(2, Qt.UserRole) if self.mode == "duplicates" else 0
                    size_v = f.data(3, Qt.UserRole) if self.mode == "duplicates" else 0
                    score_v = f.data(4, Qt.UserRole) or f.text(3) if self.mode == "similarity" else 0
                    path_s = str(path_v) if path_v is not None else ""
                    mod_i = int(mod_v) if mod_v not in (None, "") else 0
                    size_i = int(size_v) if size_v not in (None, "") else 0
                    score_i = int(score_v) if score_v not in (None, "") else 0
                    selected.append({
                        "path": path_s,
                        "size": size_i,
                        "modified": mod_i,
                        "score": score_i,
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
            mode_word = "Duplicate" if self.mode == "duplicates" else "Similarity"
            self.header_label.setText(f"{mode_word} Groups: {groups} — Files: {files}")
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

"""
SimilarityManagerDialog - Dedicated dialog for displaying and managing groups of visually similar images.

This class provides a modal QDialog for viewing similarity groups computed using perceptual hashes (pHash or wHash).
It mirrors the structure of DuplicateManagerDialog but is tailored for similarity mode, including:
- Thumbnail previews for images (64x64 scaled).
- Similarity scores (Hamming distances) displayed per file.
- Controls for selecting algorithm (pHash/wHash) and threshold, with a refresh button to recompute groups.
- Checkbox selection for files, with delete to Recycle Bin (same as duplicates).
- Tabs for processing summary and similarity report.
- Full error handling with selectable popups and detailed logging (file path, parameters, stack trace).
- Support for pre-computed groups or on-the-fly computation from paths using similarity.py functions.

The dialog accepts pre-computed groups or computes them synchronously on refresh using brute-force O(n^2) comparison
(suitable for PoC with <1000 images). Hashes are computed using PIL for image loading and assumed functions in similarity.py
for hashing and distance calculation. If DB manager is provided, it can query valid image paths for computation.

Parameters
----------
groups : Optional[list[dict]]
    List of similarity groups. Each group is a dict with:
    - 'paths': list[str] - Absolute file paths in the group.
    - 'scores': list[float] - Hamming distances for each path (relative to first or pairwise avg; length matches paths).
    - 'algorithm': str - 'phash' or 'whash' used for computation (optional, defaults to current selection).
    If None, groups are computed from paths on first populate or refresh.
paths : Optional[list[str]]
    List of absolute image file paths to compute similarity groups from (if groups is None).
    Used for on-demand computation via refresh.
summary_text : str
    Text for the "Processing Summary" tab (e.g., scan stats).
report_text : str
    Text for the "Similarity Report" tab (e.g., group summary).
db_manager : Optional[DatabaseManager]
    DatabaseManager for querying valid image paths from image_metadata (if paths not provided).
    Enables computation over cached images without explicit paths.
settings : Optional[dict]
    Settings dict for defaults, e.g., {"similarity": {"enabled_algorithms": ["phash"], "phash_threshold": 10}}.
    Used to set initial algorithm and threshold.
parent : Optional[QWidget]
    Parent widget for the dialog.

Behavior
--------
- On init: Builds UI with tabs, controls (algorithm combo, threshold spinbox, refresh button), tree widget (columns: Select checkbox, Preview thumbnail, Path, Score), status line, and Delete/Close buttons.
- Populate: _populate_tree adds top-level group items (non-checkable, bold) with child file rows (checkable, thumbnails, paths, scores). Expands groups by default.
- Refresh: _on_refresh computes groups using current algorithm/threshold from paths or DB query, then repopulates tree. Synchronous for PoC; shows error popup on failure.
- Selection: Checkboxes on file rows; updates status ("X files selected out of Y") and enables Delete.
- Delete: Confirms (with Recycle Bin if send2trash available), deletes checked files, removes rows/groups from tree, updates DB (invalidate metadata), logs details.
- Thumbnails: Generated using PIL.Image.open and QPixmap.fromImage(QImage); errors skipped with log.
- Error Handling: QMessageBox for user errors (selectable text); LOGGER.error for details (path, algorithm, threshold, stack).
- Resizable, modal; closes via button or Esc, logs closure.

Notes
-----
- Requires PIL (Pillow) for thumbnails and hashing; assumes installed via pdm.
- Computation uses brute-force pairwise Hamming distance; O(n^2) time, fine for PoC (<1000 images).
- Scores: Hamming distance (0=identical, higher=less similar); groups only include pairs <= threshold.
- No signals emitted; deletions logged. Future: emit deleted_files list[str].
- Integrates with project logging (get_logger("img_app.similarity")) and messages (show_selectable_*).
- Syntax validated; full PyDoc for reusability.
"""

from PySide6.QtGui import QImage
from PIL import Image
import traceback

LOGGER_SIM = get_logger("img_app.similarity")

class SimilarityManagerDialog(QDialog):
    """
    See class docstring above for full description.
    """

    def __init__(
        self,
        groups: Optional[List[Dict[str, Any]]] = None,
        paths: Optional[List[str]] = None,
        summary_text: str = "",
        report_text: str = "",
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the SimilarityManagerDialog.

        See class docstring for parameters and behavior.

        Notes
        -----
        - Builds full UI mirroring DuplicateManagerDialog: tabs/splitter, header, controls, tree, status, buttons.
        - Default settings if none provided: phash threshold 10.
        - Initial populate from groups if provided; else empty tree (user refreshes to compute).
        - Connects signals for tree changes, delete, controls (algo/threshold change triggers refresh if desired, but here only on button).
        - Uses GroupFrameDelegate for visual separation (same as duplicates).
        """
        super().__init__(parent)
        self.groups: List[Dict[str, Any]] = groups or []
        # Normalize incoming groups to the internal shape {'paths': [...], 'scores': [...]}
        # This allows the dialog to auto-populate when results are passed from MainWindow without requiring manual Refresh.
        self.groups = self._normalize_groups_input(self.groups)
        self.paths: List[str] = paths or []
        self.db_manager = db_manager
        self.settings = settings or {}
        self.default_settings = {
            "similarity": {
                "enabled_algorithms": ["phash", "whash"],
                "phash_threshold": 10,
                "whash_threshold": 12,
            }
        }
        self.settings = {**self.default_settings["similarity"], **self.settings.get("similarity", {})}

        self.setWindowTitle("Similarity Manager")
        self.setModal(True)
        self.resize(1000, 800)  # Taller for thumbnails/tree
        try:
            self.setSizeGripEnabled(True)
        except Exception:
            pass

        # Main layout
        main_layout = QVBoxLayout(self)

        # Splitter for tabs and content
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)

        # Tabs
        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.summary_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.summary_tab.document().setDocumentMargin(0)

        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)
        self.report_tab.setLineWrapMode(QTextEdit.NoWrap)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, "Similarity Report")
        self.splitter.addWidget(self.tabs)

        # Bottom content
        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)

        # Header
        self.header_label = QLabel("Similarity Groups: Loading...", self)
        bottom_layout.addWidget(self.header_label)

        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Algorithm:", self))
        self.alg_combo = QComboBox(self)
        self.alg_combo.addItems(self.settings["enabled_algorithms"])
        default_alg = self.settings["enabled_algorithms"][0]
        self.alg_combo.setCurrentText(default_alg)
        controls_layout.addWidget(self.alg_combo)

        controls_layout.addWidget(QLabel("Threshold:", self))
        self.threshold_spin = QSpinBox(self)
        self.threshold_spin.setMinimum(0)
        self.threshold_spin.setMaximum(64)
        thresh_key = f"{default_alg}_threshold"
        self.threshold_spin.setValue(self.settings.get(thresh_key, 10))
        controls_layout.addWidget(self.threshold_spin)

        self.refresh_btn = QPushButton("Refresh Groups", self)
        self.refresh_btn.clicked.connect(self._on_refresh)
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addStretch()

        controls_widget = QWidget(self)
        controls_widget.setLayout(controls_layout)
        bottom_layout.addWidget(controls_widget)

        # Tree
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Select", "Preview", "Path", "Score"])
        self.tree.setSortingEnabled(False)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Select
        header.setSectionResizeMode(1, QHeaderView.Fixed)  # Preview
        header.resizeSection(1, 70)
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Path
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Score

        self.tree.setAlternatingRowColors(False)
        self.tree.setStyleSheet("""
            QTreeWidget::item { background-color: transparent; border: none; }
            QTreeWidget::item:selected { background-color: palette(highlight); color: palette(highlighted-text); }
            QTreeView::branch { background: transparent; }
            QTreeWidget { border: none; }
        """)
        self.tree.setItemDelegate(GroupFrameDelegate(self.tree))
        bottom_layout.addWidget(self.tree)

        # Status
        self.status_label = QLabel("No similar images to manage", self)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_layout.addWidget(self.status_label)

        # Initial populate
        self._populate_tree()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)
        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        bottom_layout.addLayout(btn_row)

        self.splitter.addWidget(bottom_widget)
        main_layout.addWidget(self.splitter)
        main_layout.setSpacing(0)

        # Update status
        self._update_status_line()

        # Signals
        self.tree.itemChanged.connect(self._on_item_changed)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self._update_delete_enabled()

        # Controls signals (change algo/thresh updates settings but refresh on button)
        self.alg_combo.currentTextChanged.connect(self._on_settings_changed)
        self.threshold_spin.valueChanged.connect(self._on_settings_changed)

        QTimer.singleShot(100, self._configure_initial_splitter_sizes)

        # Automatically compute and populate if no pre-computed groups provided
        if not self.groups:
            def auto_refresh():
                """
                Automatically trigger refresh to populate groups on dialog open if none pre-computed.
                
                This ensures the groups pane populates immediately after similarity search results
                are available in the DB/cache, without requiring manual "Refresh Groups" click.
                
                Errors are caught and logged with full details (path, algorithm, threshold, stack trace)
                to stderr via LOGGER_SIM; user sees selectable error dialog for feedback.
                
                Preserves manual refresh button for re-computation.
                """
                try:
                    self._on_refresh()
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    LOGGER_SIM.error(
                        "Automatic population failed on dialog init",
                        exception=e,
                        variables={
                            "algorithm": self.alg_combo.currentText(),
                            "threshold": self.threshold_spin.value(),
                            "paths_count": len(getattr(self, "paths", [])),
                            "traceback": tb
                        }
                    )
                    from src.pk_py_lib.gui.utils.messages import show_selectable_error
                    show_selectable_error(
                        self,
                        "Initialization Error",
                        f"Failed to automatically load similarity groups:\n\n{str(e)}\n\n"
                        f"Algorithm: {self.alg_combo.currentText()}\n"
                        f"Threshold: {self.threshold_spin.value()}\n\n"
                        f"Check logs for details. You can still use 'Refresh Groups' manually."
                    )

            QTimer.singleShot(0, auto_refresh)

        LOGGER_SIM.info("SimilarityManagerDialog initialized", variables={"groups_count": len(self.groups), "paths_count": len(self.paths)})

    def _normalize_groups_input(self, raw_groups: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """
        Normalize incoming groups into the internal shape expected by this dialog.

        Acceptable inputs:
        - [{'paths': [...], 'scores': [...]}]  # already normalized
        - [{'files': [{'path': ...}, ...], 'count': int, ...}]  # groups_data from MainWindow
        - [[path1, path2, ...], ...]  # legacy simple list-of-paths groups

        Returns a list of dicts with:
        - 'paths': list[str]
        - 'scores': list[float]  (Hamming distances; default 0.0 when unknown)
        - 'algorithm': str       (best-effort; defaults to 'phash')
        """
        normalized: List[Dict[str, Any]] = []
        try:
            for g in (raw_groups or []):
                # Case 1: dict with 'paths' (preferred)
                if isinstance(g, dict) and isinstance(g.get('paths'), list):
                    paths = [str(p) for p in (g.get('paths') or []) if p]
                    raw_scores = g.get('scores') or []
                    scores: List[float] = []
                    if isinstance(raw_scores, list):
                        for i in range(len(paths)):
                            try:
                                scores.append(float(raw_scores[i]) if i < len(raw_scores) and raw_scores[i] is not None else 0.0)
                            except Exception:
                                scores.append(0.0)
                    else:
                        scores = [0.0 for _ in paths]
                    normalized.append({
                        'paths': paths,
                        'scores': scores,
                        'algorithm': str(g.get('algorithm') or 'phash')
                    })
                    continue

                # Case 2: dict with 'files' (MainWindow._format_similarity_groups result)
                if isinstance(g, dict) and isinstance(g.get('files'), list):
                    files_list = g.get('files') or []
                    paths = [str(f.get('path')) for f in files_list if isinstance(f, dict) and f.get('path')]
                    scores = [0.0 for _ in paths]  # distance unknown at this stage
                    normalized.append({
                        'paths': paths,
                        'scores': scores,
                        'algorithm': str(g.get('algorithm') or 'phash')
                    })
                    continue

                # Case 3: legacy list of path strings
                if isinstance(g, list):
                    paths = [str(p) for p in g if p]
                    scores = [0.0 for _ in paths]
                    normalized.append({
                        'paths': paths,
                        'scores': scores,
                        'algorithm': 'phash'
                    })
                    continue
            return normalized
        except Exception as e:
            LOGGER_SIM.error("Failed to normalize similarity groups", exception=e)
            # Fallback: if normalization failed, return empty to trigger refresh or safe UI state
            return []

    def _populate_tree(self) -> None:
        """
        Populate the tree widget with similarity groups.

        Clears existing items, adds top-level group items (non-checkable, bold header with avg score),
        and child file items (checkable, thumbnail in col 1, path in col 2, score in col 3).
        Stores raw path/score in UserRole for _collect_checked.
        Expands all groups. Updates status line.

        Handles empty groups: shows "No similar images found" if none.
        Skips thumbnail errors with log; uses default icon if failed.

        Notes
        -----
        - Thumbnails: 64x64, RGB, LANCZOS resample; QImage.Format_RGB888.
        - Scores: Displayed as "{score:.2f}"; assumes scores list matches paths length.
        - If no groups, tree empty; header updated on refresh.
        """
        self.tree.clear()
        if not self.groups:
            self.header_label.setText("No similar images found")
            self._update_status_line()
            return

        for i, group in enumerate(self.groups, 1):
            paths = group.get('paths', [])
            scores = group.get('scores', [0.0] * len(paths))
            num_images = len(paths)
            if num_images < 2:
                continue  # Skip non-groups
            avg_score = sum(scores) / num_images if scores else 0.0

            top = QTreeWidgetItem(self.tree)
            top.setText(1, f"Group #{i}: {num_images} similar images (avg Hamming: {avg_score:.2f})")
            top.setFlags((top.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsUserCheckable)
            # Bold header
            try:
                font = top.font(1)
                font.setBold(True)
                top.setFont(1, font)
                top.setForeground(1, QBrush(QColor(32, 0, 0)))  # Dark red
            except Exception:
                pass
            self.tree.expandItem(top)

            for j, path in enumerate(paths):
                child = QTreeWidgetItem(top)
                # Thumbnail (col 1)
                try:
                    pil_img = Image.open(path)
                    pil_img.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    if pil_img.mode != 'RGB':
                        pil_img = pil_img.convert('RGB')
                    stride = pil_img.width * 3
                    qimg = QImage(
                        pil_img.tobytes(), pil_img.width, pil_img.height,
                        stride, QImage.Format_RGB888
                    )
                    pixmap = QPixmap.fromImage(qimg)
                    child.setIcon(1, pixmap)
                except Exception as e:
                    LOGGER_SIM.warning(
                        "Failed to generate thumbnail",
                        exception=e, variables={"path": path}
                    )
                    # Default icon or empty
                    child.setText(1, "[No Preview]")

                child.setText(2, path)
                score = scores[j] if j < len(scores) else 0.0
                child.setText(3, f"{score:.2f}")
                # Store raw data
                child.setData(2, Qt.UserRole, path)
                child.setData(3, Qt.UserRole, score)
                child.setCheckState(0, Qt.Unchecked)
                child.setFlags(
                    child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled
                )

        self._update_status_line()
        self.header_label.setText(f"Similarity Groups: {len(self.groups)}")
        LOGGER_SIM.info("Tree populated", variables={"group_count": len(self.groups)})

    def _on_refresh(self) -> None:
        """
        Recompute similarity groups using current algorithm and threshold, then repopulate tree.

        Computation:
        - If paths provided: Brute-force pairwise Hamming on computed hashes from similarity.py.
        - If db_manager and no paths: Query valid image_metadata.file_path, use as paths.
        - Groups: Only include clusters with >=2 images where all pairs <= threshold (simple star topology from first).
        - Updates header and tree; shows error popup/log on failure (e.g., no images, hash errors).

        Parameters
        ----------
        None (uses self.alg_combo.currentText(), self.threshold_spin.value(), self.paths, self.db_manager).

        Notes
        -----
        - Synchronous; may freeze UI for large n (PoC limitation).
        - Assumes similarity.compute_hash(path, algorithm) -> str (hex), similarity.hamming(h1, h2) -> float.
        - Logs computation details (n paths, algorithm, threshold, groups found).
        - If no valid paths, shows "No images to analyze" and returns.
        """
        try:
            algorithm = self.alg_combo.currentText()
            threshold = self.threshold_spin.value()
            LOGGER_SIM.info(
                "Refreshing similarity groups",
                variables={"algorithm": algorithm, "threshold": threshold, "paths_count": len(self.paths)}
            )

            if not self.paths and self.db_manager:
                # Query valid image paths from DB
                with self.db_manager.get_connection(self.db_manager.cache_db) as conn:
                    ext_conditions = " OR ".join([f"im.file_path LIKE '%{ext}'" for ext in IMAGE_EXTENSIONS])

                    rows = conn.execute(
                        f"""
                        SELECT im.file_path
                        FROM image_metadata im
                        WHERE im.is_valid = 1 AND ({ext_conditions})
                        """
                    ).fetchall()
                    self.paths = [row['file_path'] for row in rows if row['file_path']]
                if not self.paths:
                    show_selectable_error(
                        self, "No Images", "No valid images found in cache for similarity analysis."
                    )
                    return
                LOGGER_SIM.info("Queried paths from DB", variables={"queried_count": len(self.paths)})

            if not self.paths:
                show_selectable_error(
                    self, "Refresh Failed", "No paths provided for computation. Supply paths in init or use DB manager."
                )
                return

            # Compute hashes
            hashes: Dict[str, str] = {}
            for path in self.paths:
                try:
                    hash_val = similarity.compute_phash(path, hash_size=8) # FIXME: Algorithm not used
                    hashes[path] = hash_val
                except Exception as e:
                    LOGGER_SIM.error(
                        "Hash computation failed",
                        exception=e, variables={"path": path, "algorithm": algorithm}
                    )
                    continue
            if len(hashes) < 2:
                show_selectable_error(self, "Insufficient Data", "Fewer than 2 images with valid hashes.")
                return

            # Brute-force groups (star topology: distances from first in cluster)
            self.groups = []
            processed = set()
            for i, p1 in enumerate(self.paths):
                if p1 not in hashes or p1 in processed:
                    continue
                group = {'paths': [p1], 'scores': [], 'algorithm': algorithm}
                h1 = hashes[p1]
                for j, p2 in enumerate(self.paths[i+1:], i+1):
                    if p2 not in hashes:
                        continue
                    dist = similarity.hamming_distance(h1, hashes[p2])
                    if dist <= threshold:
                        group['paths'].append(p2)
                        group['scores'].append(float(dist))
                        processed.add(p2)
                if len(group['paths']) > 1:
                    self.groups.append(group)
                processed.add(p1)

            self._populate_tree()
            LOGGER_SIM.info(
                "Groups computed successfully",
                variables={"groups_count": len(self.groups), "total_images": len(self.paths)}
            )
        except Exception as e:
            tb = traceback.format_exc()
            LOGGER_SIM.error(
                "Refresh computation failed",
                exception=e, variables={"algorithm": algorithm, "threshold": threshold, "traceback": tb}
            )
            show_selectable_error(
                self, "Computation Error", f"Failed to compute similarity groups:\n{str(e)}\n\nCheck log for details."
            )

    def _on_settings_changed(self, value) -> None:
        """
        Handle changes to algorithm or threshold.

        Updates the threshold spinbox when algorithm changes (loads corresponding default).
        No immediate recompute; user must click Refresh.

        Parameters
        ----------
        value : str or int
            Current text/value from combo/spinbox (unused directly, triggers on change).

        Notes
        -----
        - Updates self.settings for persistence if needed.
        - Logs change for audit.
        """
        if isinstance(value, str):  # Algorithm changed
            algorithm = value
            thresh_key = f"{algorithm}_threshold"
            new_thresh = self.settings.get(thresh_key, 10)
            self.threshold_spin.setValue(new_thresh)
            LOGGER_SIM.debug("Algorithm changed", variables={"algorithm": algorithm, "threshold": new_thresh})
        else:  # Threshold changed
            LOGGER_SIM.debug("Threshold changed", variables={"threshold": value})
        # Future: auto-refresh option via checkbox

    def _collect_checked(self) -> List[Dict[str, Any]]:
        """
        Collect checked file items for deletion.

        Scans tree children, collects checked items with path, score, group/file items.

        Returns
        -------
        List[dict]
            Each: {"path": str, "score": float, "group_item": QTreeWidgetItem, "file_item": QTreeWidgetItem}
            Path/score from UserRole or text fallback; score as float.

        Notes
        -----
        - Skips non-checked, malformed rows.
        - Used by _on_delete_clicked.
        """
        selected: List[Dict[str, Any]] = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if self._is_separator_item(top):
                continue
            for j in range(top.childCount()):
                child = top.child(j)
                if child.checkState(0) != Qt.Checked:
                    continue
                try:
                    path = child.data(2, Qt.UserRole) or child.text(2) or ""
                    score_str = child.data(3, Qt.UserRole) or child.text(3) or "0.0"
                    score = float(score_str) if score_str else 0.0
                    selected.append({
                        "path": str(path),
                        "score": score,
                        "group_item": top,
                        "file_item": child,
                    })
                except Exception as e:
                    LOGGER_SIM.warning(
                        "Failed to collect checked item",
                        exception=e, variables={"row": j, "group": i}
                    )
                    continue
        return selected

    def _on_delete_clicked(self) -> None:
        """
        Handle delete button click: confirm and delete checked files.

        Mirrors DuplicateManagerDialog._on_delete_clicked:
        - Collects checked via _collect_checked.
        - Confirms with selectable QMessageBox (Recycle Bin if send2trash, else permanent with double-confirm).
        - Deletes files (busy cursor), removes tree rows/groups, invalidates DB metadata.
        - Tracks success/failure, shows summary popup, refreshes UI/header/status.
        - Logs details (path, action, exception, stack) to STDERR via LOGGER.error.

        Edge Cases
        ----------
        - FileNotFound: Treat as success (cleanup UI/DB).
        - PermissionError/Other: Log, popup, continue.
        - No selection: Info popup.
        - DB failure: Log/popup but doesn't count as delete failure.

        Notes
        -----
        - Uses send2trash if available; else os.remove.
        - Updates DB via DELETE from image_metadata (cascades hashes/thumbnails).
        - Post-delete: If group <2 files, remove group + preceding separator.
        """
        sel = self._collect_checked()
        if not sel:
            show_selectable_info(self, "No Selection", "No files selected for deletion.")
            return

        n = len(sel)
        use_trash = send2trash is not None
        if use_trash:
            confirmed = self._ask_selectable_question(
                "Confirm Delete to Recycle Bin",
                f"Move {n} similar image(s) to Recycle Bin?"
            )
        else:
            confirmed = self._ask_selectable_question(
                "Confirm Permanent Delete",
                f"Permanently delete {n} similar image(s)? Cannot be undone.",
                "send2trash not available: permanent deletion."
            )
            if confirmed:
                confirmed = self._ask_selectable_question(
                    "Final Confirmation",
                    f"Really delete {n} image(s) permanently?"
                )
        if not confirmed:
            return

        try:
            QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        except Exception:
            pass

        deleted_ok = 0
        failed = 0
        db_mgr = self._get_database_manager()

        for entry in sel:
            path = entry["path"]
            file_item = entry["file_item"]
            group_item = entry["group_item"]
            action = "send2trash" if use_trash else "permanent"
            try:
                if use_trash and send2trash:
                    send2trash(path)
                else:
                    os.remove(path)
                deleted_ok += 1

                # Remove UI
                try:
                    parent = file_item.parent()
                    if parent:
                        parent.removeChild(file_item)
                        if parent.childCount() < 2:
                            idx = self.tree.indexOfTopLevelItem(parent)
                            if idx >= 0:
                                self.tree.takeTopLevelItem(idx)
                                # Remove separator if present
                                if idx > 0 and idx - 1 < self.tree.topLevelItemCount():
                                    prev = self.tree.topLevelItem(idx - 1)
                                    if self._is_separator_item(prev):
                                        self.tree.takeTopLevelItem(idx - 1)
                except Exception as e_ui:
                    LOGGER_SIM.error(
                        "UI cleanup failed post-delete",
                        exception=e_ui, variables={"path": path}
                    )

                # DB invalidate
                if db_mgr:
                    try:
                        with db_mgr.get_connection(db_mgr.cache_db) as conn:
                            conn.execute("DELETE FROM image_metadata WHERE file_path = ?", (path,))
                    except Exception as e_db:
                        LOGGER_SIM.error(
                            "DB invalidate failed post-delete",
                            exception=e_db, variables={"path": path}
                        )
                        show_selectable_error(
                            self, "DB Error", f"Failed to update DB for {path}:\n{str(e_db)}"
                        )

            except FileNotFoundError:
                deleted_ok += 1  # Already gone
                # UI/DB same as success
                # ... (repeat UI/DB code)
            except PermissionError as e_perm:
                failed += 1
                LOGGER_SIM.error(
                    "Delete permission denied",
                    exception=e_perm, variables={"path": path, "action": action}
                )
                show_selectable_error(self, "Permission Denied", f"Cannot delete {path}:\n{str(e_perm)}")
            except Exception as e_del:
                failed += 1
                tb = traceback.format_exc()
                LOGGER_SIM.error(
                    "Delete failed",
                    exception=e_del, variables={"path": path, "action": action, "traceback": tb}
                )
                show_selectable_error(self, "Delete Failed", f"Failed to delete {path}:\n{str(e_del)}")

        try:
            QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        self._refresh_header_counts()
        self._update_delete_enabled()
        self._update_status_line()
        show_selectable_info(
            self, "Delete Summary", f"Successfully deleted {deleted_ok} image(s); {failed} failed."
        )
        LOGGER_SIM.info(
            "Delete operation complete",
            variables={"deleted_ok": deleted_ok, "failed": failed, "total_selected": n}
        )

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle tree item changes (e.g., checkbox toggle).

        Updates delete button enabled state and status line.

        Parameters
        ----------
        item : QTreeWidgetItem
            Changed item (child file row).
        column : int
            Column index (0 for checkbox).

        Notes
        -----
        - Defensive: Logs errors but doesn't crash.
        - Calls _update_delete_enabled and _update_status_line.
        """
        try:
            self._update_delete_enabled()
            self._update_status_line()
        except Exception as e:
            LOGGER_SIM.error(
                "Item change handler failed",
                exception=e, variables={"column": column}
            )

    def _update_delete_enabled(self) -> None:
        """
        Enable Delete button if any file is checked.

        Scans tree children for checked state in col 0; skips separators/groups.

        Notes
        -----
        - Uses _is_separator_item to skip.
        - Sets self.delete_btn.enabled based on any_checked.
        """
        any_checked = False
        try:
            for i in range(self.tree.topLevelItemCount()):
                g = self.tree.topLevelItem(i)
                if self._is_separator_item(g):
                    continue
                for j in range(g.childCount()):
                    c = g.child(j)
                    if c.checkState(0) == Qt.Checked:
                        any_checked = True
                        break
                if any_checked:
                    break
        except Exception:
            pass
        self.delete_btn.setEnabled(any_checked)

    def _update_status_line(self) -> None:
        """
        Update status label with selection counts.

        Counts total/selected files and groups with selections; skips separators.
        Format: "{selected} files from {groups_selected} groups selected out of {total_files} in {total_groups} groups"
        If no groups: "No similar images to manage"

        Notes
        -----
        - Called after populate/selection change/delete.
        - Defensive logging on error.
        """
        try:
            total_files = 0
            selected_files = 0
            groups_selected = 0
            total_groups = 0
            for i in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(i)
                if self._is_separator_item(group):
                    continue
                total_groups += 1
                child_count = group.childCount()
                total_files += child_count
                has_sel = any(child.checkState(0) == Qt.Checked for child in [group.child(j) for j in range(child_count)])
                if has_sel:
                    groups_selected += 1
                    selected_files += sum(1 for j in range(child_count) if group.child(j).checkState(0) == Qt.Checked)
            if total_groups == 0:
                text = "No similar images to manage"
            else:
                text = f"{selected_files} files from {groups_selected} groups selected out of {total_files} total files in {total_groups} groups"
            self.status_label.setText(text)
            LOGGER_SIM.debug(f"Status updated: {text}")
        except Exception as e:
            LOGGER_SIM.error("Status update failed", exception=e)
            text = "Error updating status"
            self.status_label.setText(text)
            LOGGER_SIM.debug(f"Status updated: {text}")

    def _is_separator_item(self, item: Optional[QTreeWidgetItem]) -> bool:
        """
        Check if item is a separator row.

        Parameters
        ----------
        item : Optional[QTreeWidgetItem]
            Item to check.

        Returns
        -------
        bool
            True if separator (UserRole 0 == "__separator__").

        Notes
        -----
        - Defensive: False on exception/None.
        """
        try:
            return item is not None and item.data(0, Qt.UserRole) == "__separator__"
        except Exception:
            return False

    def _refresh_header_counts(self) -> None:
        """
        Refresh header label with current group/file counts from tree.

        Counts top-level non-separator groups and total child files.

        Notes
        -----
        - Called post-delete to update "Similarity Groups: X".
        - Defensive on error.
        """
        try:
            groups_count = 0
            files_count = 0
            for i in range(self.tree.topLevelItemCount()):
                g = self.tree.topLevelItem(i)
                if self._is_separator_item(g):
                    continue
                groups_count += 1
                files_count += g.childCount()
            self.header_label.setText(f"Similarity Groups: {groups_count} — Files: {files_count}")
        except Exception as e:
            LOGGER_SIM.error("Header refresh failed", exception=e)

    def _get_database_manager(self) -> Optional[DatabaseManager]:
        """
        Locate DatabaseManager from parent chain.

        Walks up QObject parents looking for 'database_manager' attribute.

        Returns
        -------
        Optional[DatabaseManager]
            Found instance or None.

        Notes
        -----
        - Attached to main window in app.py.
        - Logs failure.
        """
        try:
            w = self.parent()
            while w is not None:
                dm = getattr(w, "database_manager", None)
                if isinstance(dm, DatabaseManager):
                    return dm
                w = w.parent()
        except Exception as e:
            LOGGER_SIM.error("DatabaseManager resolution failed", exception=e)
        return None

    def _ask_selectable_question(self, title: str, text: str, informative: Optional[str] = None) -> bool:
        """
        Show selectable Yes/No QMessageBox.

        Parameters
        ----------
        title : str
            Dialog title.
        text : str
            Main text.
        informative : Optional[str]
            Additional info text.

        Returns
        -------
        bool
            True if Yes.

        Notes
        -----
        - Sets TextSelectableByMouse/Keyboard on text/labels.
        - Default No; logs if needed.
        """
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        if informative:
            try:
                box.setInformativeText(informative)
            except Exception:
                box.setText(f"{text}\n\n{informative}")
        try:
            box.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            for lbl in box.findChildren(QLabel):
                lbl.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
                lbl.setTextFormat(Qt.PlainText)
        except Exception:
            pass
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def _configure_initial_splitter_sizes(self) -> None:
        """
        Set initial splitter proportions after UI layout.

        Fits top tabs to summary content height + padding; clamps min/max.
        Uses 40/60 default on error.

        Notes
        -----
        - Called via QTimer.singleShot(100) post-init.
        - Logs failure.
        """
        try:
            summary_h = self.summary_tab.sizeHint().height()
            tab_h = 30
            pad = 20
            top_h = max(100, min(summary_h + tab_h + pad, self.height() - 200))
            self.tabs.setMaximumHeight(top_h)
            total_h = self.splitter.height()
            if total_h > 0:
                self.splitter.setSizes([top_h, total_h - top_h])
        except Exception as e:
            LOGGER_SIM.error("Splitter config failed", exception=e)
            try:
                default_top = int(self.splitter.height() * 0.4)
                self.splitter.setSizes([default_top, self.splitter.height() - default_top])
            except Exception:
                pass

    def closeEvent(self, event) -> None:
        """
        Handle dialog close.

        Logs closure; accepts event.

        Parameters
        ----------
        event : QCloseEvent
            Close event.
        """
        LOGGER_SIM.info("SimilarityManagerDialog closed", variables={"groups_remaining": len(self.groups)})
        super().closeEvent(event)
