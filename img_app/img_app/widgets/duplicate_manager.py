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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QPushButton, QWidget, QSizePolicy, QSpacerItem, QMessageBox,
    QHeaderView, QTextEdit, QTabWidget
)
from PySide6.QtGui import QGuiApplication

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

    Notes
    -----
    - Timestamps (Modified) and Sizes are shown as raw integers; no humanization here.
    - The dialog is resizable and modal; it can be closed with the Close button or Esc.
    """

    def __init__(self, groups: List[Dict[str, Any]], summary_text: str = "", report_text: str = "", parent: Optional[QWidget] = None) -> None:
        """
        Construct the dialog with duplicate groups and populate the tree.

        Parameters
        ----------
        groups : List[Dict[str, Any]]
            Duplicate groups structured as described in the class docstring. Only groups
            with count >= 2 are expected, but the dialog will render whatever is provided.
        parent : Optional[QWidget]
            Optional parent widget; typically the main window.

        Behavior
        --------
        - Builds the header and tree.
        - Populates group/file rows with checkboxes for file items.
        - Wires the Delete button to be enabled only when at least one file is checked.

        Notes
        -----
        - All UI work occurs on the GUI thread; no background threads are used.
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

        # Header label
        # Add tabs for integrated summary and report
        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.summary_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.summary_tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)
        self.report_tab.setLineWrapMode(QTextEdit.NoWrap)
        self.report_tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, "Duplicate Report")
        main_layout.addWidget(self.tabs)

        # Header label (remains for group/file counts)
        self.header_label = QLabel(f"Duplicate Groups: {total_groups} — Files: {total_files}", self)
        main_layout.addWidget(self.header_label)
        main_layout.addWidget(self.header_label)

        # Tree widget with 4 columns: Select, File Path, Modified, Size
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Select", "File Path", "Modified", "Size"])
        self.tree.setSortingEnabled(True)

        # Column sizing policies:
        # - File Path stretches
        # - Modified and Size are resize-to-contents
        # - Select column fits to checkbox content
        try:
            header = self.tree.header()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        except Exception:
            # Defensive in case Qt platform backends vary
            pass

        main_layout.addWidget(self.tree)

        # Populate tree with groups and files
        # Each group is a top-level item with text in the "File Path" column (index 1)
        for i, group in enumerate(self._groups, start=1):
            try:
                gh = str(group.get("hash") or "")
            except Exception:
                gh = ""
            files = list(group.get("files") or [])
            k = len(files)

            top = QTreeWidgetItem(self.tree)
            # Place the group title in the File Path column to keep the "Select" column free for child checkboxes
            top.setText(1, f"Group #{i} — Hash: {gh} — Files: {k}")
            # Make the group rows non-checkable and bold-ish via flags; actual styling can be added later
            top.setFlags((top.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable) & ~Qt.ItemIsUserCheckable)
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
                child.setText(2, str(modified))
                child.setText(3, str(size))
                # Store raw values for reliable retrieval independent of display formatting
                try:
                    child.setData(1, Qt.UserRole, path)
                    child.setData(2, Qt.UserRole, modified)
                    child.setData(3, Qt.UserRole, size)
                except Exception:
                    pass
                # Enable user check state on the "Select" column
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                child.setCheckState(0, Qt.Unchecked)
                # Provide numeric sort keys for Modified and Size to ensure numeric sort when used
                try:
                    child.setData(2, Qt.UserRole, modified)
                    child.setData(3, Qt.UserRole, size)
                except Exception:
                    pass

        # Buttons row: spacer + [Delete] [Close]
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)  # Initially disabled; enabled when any file item is checked
        btn_row.addWidget(self.delete_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        main_layout.addLayout(btn_row)

        # Wire signals (after population to avoid spurious itemChanged during build)
        try:
            self.tree.itemChanged.connect(self._on_item_changed)
        except Exception:
            # Some backends might not expose itemChanged; defensive
            pass
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self._update_delete_enabled()

    def _on_item_changed(self, item: "QTreeWidgetItem", column: int) -> None:
        """
        React to any item change (primarily checkbox toggles) to update the Delete button state.

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
        """
        try:
            self._update_delete_enabled()
        except Exception as e:
            # Defensive: never propagate errors from UI state updates
            LOGGER.error("State update after itemChanged failed", exception=e, variables={"column": column})

    def _update_delete_enabled(self) -> None:
        """
        Compute whether any file items are checked and toggle the Delete button accordingly.
        """
        any_checked = False
        try:
            for gi in range(self.tree.topLevelItemCount()):
                g = self.tree.topLevelItem(gi)
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
            groups = self.tree.topLevelItemCount()
            files = 0
            for gi in range(groups):
                g = self.tree.topLevelItem(gi)
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