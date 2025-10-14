"""
src/pk_py_lib/gui/settings_manager/dialog.py

Reusable master-detail Settings Manager dialog (PySide6).

Features
--------
- Left pane: search + profiles list with actions: Create, Rename, Duplicate, Delete, Set Active
- Right pane: metadata editor (name/description) with live validation + key/value table (add/edit/remove)
- Footer buttons: OK (apply & close), Cancel (discard), Apply (apply without closing)
- Dirty-state tracking and save/discard prompts when switching profiles or closing
- Error mapping via controller (Validation, AlreadyExists, NotFound, Concurrency/Storage)
- Empty state handling: prompts to create a profile when none exist

Design
------
- All persistence and validation flows through the controller (SettingsManagerController),
  which in turn delegates to SettingsProfilesAPI.
- GUI code is library-reusable: no app-specific imports or globals.

Note: Syntax validation was performed using Python's ast module per project rules.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import inspect
import sys
import traceback

# Defensive import for PySide6 to keep library importable in headless environments
try:
    from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QRegularExpression, QSize
    from PySide6.QtGui import QKeySequence, QAction
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QSplitter,
        QLineEdit,
        QListView,
        QAbstractItemView,
        QLabel,
        QPushButton,
        QDialogButtonBox,
        QMessageBox,
        QToolBar,
        QStyle,
        QFormLayout,
        QGridLayout,
        QFrame,
    )
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for SettingsManagerDialog")

    QApplication = QDialog = QWidget = QVBoxLayout = QHBoxLayout = QSplitter = QLineEdit = QListView = QAbstractItemView = QLabel = QPushButton = QDialogButtonBox = QMessageBox = QToolBar = QStyle = QAction = QFormLayout = QGridLayout = QFrame = QSortFilterProxyModel = QModelIndex = QRegularExpression = QKeySequence = Qt = _Missing()  # type: ignore


from pk_py_lib.gui.settings_manager.models import ProfilesListModel
from pk_py_lib.gui.settings_manager.editor_widget import SettingsProfileEditorWidget
from pk_py_lib.gui.settings_manager.controller import SettingsManagerController
from pk_py_lib.api import ErrorCodes
from pk_py_lib.gui.utils.messages import show_selectable_error, show_selectable_info, handle_gui_error, gui_error_handler, gui_error_context
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.core.logging.decorators import log_errors
logger = get_logger(__name__)


class _NamePromptDialog(QDialog):
    """
    Minimal reusable prompt dialog for entering a name (with live validation message).

    The caller is responsible for performing final API calls. This dialog focuses on
    collecting the text value with inline validator message support.
    """

    def __init__(self, title: str, label: str, initial: str = "", parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for _NamePromptDialog")
        try:
            super().__init__(parent)
            self.setWindowTitle(title)
            layout = QVBoxLayout(self)
            form = QFormLayout()
            layout.addLayout(form)
            self.inp = QLineEdit(initial)
            form.addRow(label, self.inp)
            self.lbl_error = QLabel("")
            self.lbl_error.setStyleSheet("color:#c00; font-size:12px;")
            form.addRow("", self.lbl_error)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
            btns.accepted.connect(self.accept)
            btns.rejected.connect(self.reject)
            layout.addWidget(btns)
        except Exception as e:
            logger.error(
                f"Error initializing _NamePromptDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_NamePromptDialog.__init__",
                parameters={"title": title, "label": label, "initial": initial},
                stack_trace=traceback.format_exc()
            )
            raise

    def text(self) -> str:
        try:
            return (self.inp.text() or "").strip()
        except Exception as e:
            logger.error(
                f"Error getting text from _NamePromptDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_NamePromptDialog.text",
                stack_trace=traceback.format_exc()
            )
            return ""

    def set_error(self, msg: Optional[str]) -> None:
        try:
            self.lbl_error.setText(msg or "")
        except Exception as e:
            logger.error(
                f"Error setting error in _NamePromptDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_NamePromptDialog.set_error",
                parameters={"msg": msg},
                stack_trace=traceback.format_exc()
            )


class SettingsManagerDialog(QDialog):
    """
    Master-detail dialog to manage settings profiles and their key/value items.

    Workflow
    --------
    - Select a profile in the list or create/duplicate/rename/delete/set active
    - Edit metadata and items on the right
    - Apply changes or OK to save; Cancel to discard

    Keyboard shortcuts
    ------------------
    - Ctrl+N: Create profile
    - F2: Rename profile
    - Ctrl+D: Duplicate profile
    - Del: Delete profile
    - Ctrl+Return: Set Active
    - Ctrl+S: Apply
    - Esc: Cancel

    Usage
    -----
    This dialog may be launched via the helper function `settings_manager_dialog(...)`.
    """

    def __init__(self, parent: Optional[QWidget] = None, controller: Optional[SettingsManagerController] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for SettingsManagerDialog")
        try:
            super().__init__(parent)
            self.setWindowTitle("Settings Manager")
            self.setModal(True)

            # Controller (API access)
            self.controller = controller or SettingsManagerController()

            # Left models: list + filter proxy
            self._profiles_model = ProfilesListModel(self)
            self._filter = QSortFilterProxyModel(self)
            self._filter.setSourceModel(self._profiles_model)
            self._filter.setFilterCaseSensitivity(Qt.CaseInsensitive)
            self._filter.setFilterKeyColumn(0)  # display text (name)

            # Track current selection id for change navigation
            self._current_profile_id: Optional[str] = None

            self._build_ui()
            # Ensure an active/default profile exists
            self.controller.ensure_default()
            # Initial load
            self._refresh_profiles(select_active=True)
        except Exception as e:
            logger.error(
                f"Error initializing SettingsManagerDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="SettingsManagerDialog.__init__",
                parameters={"parent": parent, "controller": controller},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=parent,
                error=e,
                title="Initialization Error",
                component_name="SettingsManagerDialog"
            )
            raise

    # ------------------------------------------------------------------ UI ----
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _build_ui(self) -> None:
        try:
            main = QVBoxLayout(self)

            splitter = QSplitter(self)
            splitter.setOrientation(Qt.Horizontal)
            main.addWidget(splitter, 1)

            self.profile_dropdown = QComboBox(self)
            self.profile_dropdown.currentIndexChanged.connect(self._on_profile_selected)
            main.addWidget(self.profile_dropdown, 0)

            # Right: editor
            self.editor = SettingsProfileEditorWidget(api=self.controller.api, parent=self)
            if hasattr(self.editor, "dirtyChanged"):
                self.editor.dirtyChanged.connect(self._on_dirty_changed)  # type: ignore[attr-defined]
            splitter.addWidget(self.editor)
            splitter.setStretchFactor(1, 1)

            # Footer buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel, parent=self)
            buttons.accepted.connect(self._on_ok)
            buttons.rejected.connect(self._on_cancel)
            # Find the Apply button and wire to handler
            btn_apply = buttons.button(QDialogButtonBox.Apply)
            if btn_apply:
                btn_apply.clicked.connect(self._on_apply)
            main.addWidget(buttons)

            self._update_action_states()
        except Exception as e:
            logger.error(
                f"Error building UI in SettingsManagerDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_build_ui",
                stack_trace=traceback.format_exc()
            )
            raise

    # ------------------------------------------------------------ Data Flow ----
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _refresh_profiles(self, select_active: bool = False, preserve_selection: bool = True) -> None:
        """
        Refresh profiles list from controller.

        Parameters
        ----------
        select_active : bool
            If True, attempts to select the active profile after refresh.
        preserve_selection : bool
            If True and a current id exists, tries to re-select it.
        """
        try:
            resp = self.controller.list_profiles()
            if not resp.success or resp.data is None:
                self._show_error("Failed to load profiles", resp.message, resp.code)
                self._profiles_model.set_profiles([])
                self._current_profile_id = None
                self._update_action_states()
                self._show_empty_state_hint()
                return

            self._profiles_model.set_profiles(resp.data)
            self.profile_dropdown.clear()
            for row in range(self._profiles_model.rowCount()):
                profile = self._profiles_model.profile_at(row)
                self.profile_dropdown.addItem(profile.name, profile.id)
            if self._current_profile_id:
                idx = self.profile_dropdown.findData(self._current_profile_id)
                if idx >= 0:
                    self.profile_dropdown.setCurrentIndex(idx.row())
            # Determine selection target
            target_id: Optional[str] = None
            if select_active:
                act = self.controller.get_active()
                if act.success and act.data:
                    target_id = act.data.get("id")
            if not target_id and preserve_selection and self._current_profile_id:
                target_id = self._current_profile_id

            if target_id:
                row = self._profiles_model.index_of_id(target_id)
                if row >= 0:
                    src_idx = self._profiles_model.index(row, 0)  # type: ignore[attr-defined]
                    idx = self._filter.mapFromSource(src_idx)
                    if idx.isValid():
                        self.profile_dropdown.setCurrentIndex(idx.row())
                        self._current_profile_id = target_id
                        self._load_profile(target_id)
                        self._update_action_states()
                        return

            # If no selection found, select first if present
            if self._profiles_model.rowCount() > 0:
                idx = self._filter.index(0, 0)  # type: ignore[attr-defined]
                self.profile_dropdown.setCurrentIndex(0)
                pid = self._profiles_model.profile_at(0).id  # type: ignore[union-attr]
                self._current_profile_id = pid
                self._load_profile(pid)
            else:
                self._current_profile_id = None
                # Clear editor state
                self.editor.load_profile({"id": "", "name": "", "description": None}, {})
                self._show_empty_state_hint()
            self._update_action_states()
        except Exception as e:
            logger.error(
                f"Error refreshing profiles in SettingsManagerDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_refresh_profiles",
                parameters={"select_active": select_active, "preserve_selection": preserve_selection},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Refresh Error",
                component_name="SettingsManagerDialog._refresh_profiles"
            )
            raise

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _load_profile(self, profile_id: str) -> None:
        try:
            resp = self.controller.get_profile_with_values(profile_id)
            if not resp.success or not resp.data:
                self._show_error("Failed to load profile", resp.message, resp.code)
                return
            prof = resp.data.get("profile") or {}
            vals = resp.data.get("values") or {}
            self.editor.load_profile(prof, vals)
        except Exception as e:
            logger.error(
                f"Error loading profile in SettingsManagerDialog: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_load_profile",
                parameters={"profile_id": profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Load Profile Error",
                component_name="SettingsManagerDialog._load_profile",
                profile_id=profile_id
            )
            raise

    # --------------------------------------------------------------- Events ----
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_search_changed(self, text: str) -> None:
        try:
            txt = (text or "").strip()
            re = QRegularExpression(txt) if txt else QRegularExpression()
            self._filter.setFilterRegularExpression(re)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(
                f"Warning in _on_search_changed: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_search_changed",
                parameters={"text": text},
                stack_trace=traceback.format_exc()
            )
            # Fallback to fixed string filter if regex fails
            try:
                self._filter.setFilterFixedString(txt)  # type: ignore[attr-defined]
            except Exception as fallback_e:
                logger.error(
                    f"Fallback failed in _on_search_changed: {type(fallback_e).__name__}: {fallback_e}",
                    file_path=__file__,
                    line_number=inspect.currentframe().f_lineno,
                    func_name="_on_search_changed",
                    parameters={"text": text},
                    stack_trace=traceback.format_exc()
                )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_list_selection_changed(self) -> None:
        try:
            # Handle dirty prompt before switching
            new_idx = self.list.currentIndex()
            if not new_idx.isValid():
                return
            src_idx = self._filter.mapToSource(new_idx)
            p_dict = self._profiles_model.data(src_idx, self._profiles_model.ROLE_PROFILE_DICT)  # type: ignore[attr-defined]
            if not isinstance(p_dict, dict):
                return
            new_id = str(p_dict.get("id", "")) if p_dict else ""
            if not new_id or new_id == self._current_profile_id:
                return

            if self._maybe_prompt_save_discard_cancel() is False:
                # Revert selection
                self._reselect_current()
                return

            self._current_profile_id = new_id
            self._load_profile(new_id)
            self._update_action_states()
        except Exception as e:
            logger.error(
                f"Error in _on_list_selection_changed: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_list_selection_changed",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Selection Error",
                component_name="SettingsManagerDialog._on_list_selection_changed"
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_dirty_changed(self, dirty: bool) -> None:
        try:
            self._update_action_states()
        except Exception as e:
            logger.error(
                f"Error in _on_dirty_changed: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_dirty_changed",
                parameters={"dirty": dirty},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Dirty State Error",
                component_name="SettingsManagerDialog._on_dirty_changed",
                dirty=dirty
            )

    # -------------------------------------------------------------- Actions ----
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_create(self) -> None:
        try:
            dlg = _NamePromptDialog("Create Profile", "Name:", parent=self)
            # Suggest "New Profile" or increment until unique
            sugg = self.controller.suggest_unique_name("New Profile")
            if sugg.success and sugg.data:
                dlg.inp.setText(sugg.data)
            while dlg.exec() == dlg.Accepted:
                name = dlg.text()
                if not name:
                    dlg.set_error("Name is required")
                    continue
                v = self.controller.validate_name(name)
                if not v.success:
                    dlg.set_error(v.message or "Invalid name")
                    continue
                c = self.controller.create_profile(name=name, description=None, make_active=False)
                if c.success and c.data:
                    self._refresh_profiles(select_active=False, preserve_selection=False)
                    # Select newly created by id
                    new_id = c.data.get("id")
                    if new_id:
                        self._select_by_id(new_id)
                    return
                # Handle error (uniqueness conflict etc.)
                if c.code == ErrorCodes.INVALID_CONFIG.value:
                    # Try to suggest alternative
                    alt = self.controller.suggest_unique_name(name)
                    dlg.set_error(c.message or "Name conflict")
                    if alt.success and alt.data:
                        dlg.inp.setText(alt.data)
                else:
                    self._show_error("Create failed", c.message, c.code)
                    return
        except Exception as e:
            logger.error(
                f"Error in _on_create: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_create",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Create Profile Error",
                component_name="SettingsManagerDialog._on_create"
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_rename(self) -> None:
        try:
            pid = self._current_profile_id
            if not pid:
                return
            # Prefill current name
            row = self._current_row()
            cur_name = self._profiles_model.profile_at(row).name if row >= 0 else ""  # type: ignore[union-attr]
            dlg = _NamePromptDialog("Rename Profile", "New name:", initial=cur_name, parent=self)
            while dlg.exec() == dlg.Accepted:
                new = dlg.text()
                if not new or new == cur_name:
                    dlg.set_error("Enter a different name")
                    continue
                v = self.controller.validate_name(new)
                if not v.success:
                    dlg.set_error(v.message or "Invalid name")
                    continue
                r = self.controller.rename_profile(pid, new)
                if r.success:
                    self._refresh_profiles(select_active=False, preserve_selection=False)
                    self._select_by_id(pid)
                    return
                if r.code == ErrorCodes.INVALID_CONFIG.value:
                    dlg.set_error(r.message or "Name conflict")
                    continue
                self._show_error("Rename failed", r.message, r.code)
                return
        except Exception as e:
            logger.error(
                f"Error in _on_rename: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_rename",
                parameters={"pid": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Rename Profile Error",
                component_name="SettingsManagerDialog._on_rename",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_duplicate(self) -> None:
        try:
            pid = self._current_profile_id
            if not pid:
                return
            # Get current name to base suggestion
            row = self._current_row()
            base = self._profiles_model.profile_at(row).name if row >= 0 else "Copy"  # type: ignore[union-attr]
            sugg = self.controller.suggest_unique_name(base)
            initial = sugg.data if (sugg.success and sugg.data) else f"{base} (copy)"
            dlg = _NamePromptDialog("Duplicate Profile", "New name:", initial=initial, parent=self)
            while dlg.exec() == dlg.Accepted:
                new = dlg.text()
                if not new:
                    dlg.set_error("Name is required")
                    continue
                v = self.controller.validate_name(new)
                if not v.success:
                    dlg.set_error(v.message or "Invalid name")
                    continue
                d = self.controller.duplicate_profile(pid, new_name=new, description=None, make_active=False)
                if d.success and d.data:
                    self._refresh_profiles(select_active=False, preserve_selection=False)
                    self._select_by_id(d.data.get("id", ""))
                    return
                if d.code == ErrorCodes.INVALID_CONFIG.value:
                    alt = self.controller.suggest_unique_name(new)
                    dlg.set_error(d.message or "Name conflict")
                    if alt.success and alt.data:
                        dlg.inp.setText(alt.data)
                    continue
                self._show_error("Duplicate failed", d.message, d.code)
                return
        except Exception as e:
            logger.error(
                f"Error in _on_duplicate: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_duplicate",
                parameters={"pid": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Duplicate Profile Error",
                component_name="SettingsManagerDialog._on_duplicate",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_delete(self) -> None:
        try:
            pid = self._current_profile_id
            if not pid:
                return
            # Confirm
            row = self._current_row()
            name = self._profiles_model.profile_at(row).name if row >= 0 else "this profile"  # type: ignore[union-attr]
            resp = QMessageBox.question(
                self,
                "Delete Profile",
                f"Delete profile '{name}'?\n\nIf it is Active, a replacement will be selected automatically.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
            r = self.controller.delete_profile(pid)
            if not r.success:
                self._show_error("Delete failed", r.message, r.code)
                return
            # Refresh and select active
            self._refresh_profiles(select_active=True, preserve_selection=False)
        except Exception as e:
            logger.error(
                f"Error in _on_delete: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_delete",
                parameters={"pid": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Delete Profile Error",
                component_name="SettingsManagerDialog._on_delete",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_set_active(self) -> None:
        try:
            pid = self._current_profile_id
            if not pid:
                return
            r = self.controller.set_active(pid)
            if not r.success:
                self._show_error("Set Active failed", r.message, r.code)
                return
            # Refresh list to reflect active marker
            self._refresh_profiles(select_active=True, preserve_selection=False)
        except Exception as e:
            logger.error(
                f"Error in _on_set_active: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_set_active",
                parameters={"pid": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Set Active Error",
                component_name="SettingsManagerDialog._on_set_active",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_apply(self) -> None:
        try:
            if not self._current_profile_id:
                return
            name, desc, set_values, remove_keys = self.editor.gather_changes()
            if not any([name is not None, desc is not None, set_values, remove_keys]):
                return  # nothing to do
            r = self.controller.apply_changes(self._current_profile_id, name=name, description=desc, set_values_map=set_values, remove_keys=remove_keys)
            if not r.success:
                # Provide specific guidance for common codes
                if r.code == ErrorCodes.INVALID_CONFIG.value:
                    self._show_error("Validation failed", r.message, r.code)
                elif r.code == ErrorCodes.LOCKED_DB.value:
                    self._show_error("Database is locked", "Please retry the operation.", r.code)
                else:
                    self._show_error("Apply failed", r.message, r.code)
                return
            # Refresh editor and list (item counts may have changed)
            self.editor.reset_dirty()
            self._refresh_profiles(select_active=False, preserve_selection=True)
        except Exception as e:
            logger.error(
                f"Error in _on_apply: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_apply",
                parameters={"profile_id": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Apply Changes Error",
                component_name="SettingsManagerDialog._on_apply",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_ok(self) -> None:
        try:
            if self.editor.is_dirty():
                result = self._prompt_save_discard_cancel("You have unsaved changes. Apply them before closing?")
                if result == "save":
                    self._on_apply()
                    if self.editor.is_dirty():
                        # Apply failed or still dirty; do not close
                        return
                elif result == "cancel":
                    return
                else:
                    # discard
                    pass
            self.accept()
        except Exception as e:
            logger.error(
                f"Error in _on_ok: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_ok",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="OK Button Error",
                component_name="SettingsManagerDialog._on_ok"
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_cancel(self) -> None:
        try:
            if self.editor.is_dirty():
                result = self._prompt_save_discard_cancel("Discard changes and close?")
                if result == "cancel":
                    return
                if result == "save":
                    self._on_apply()
                    if self.editor.is_dirty():
                        return
            self.reject()
        except Exception as e:
            logger.error(
                f"Error in _on_cancel: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_cancel",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Cancel Button Error",
                component_name="SettingsManagerDialog._on_cancel"
            )

    # -------------------------------------------------------------- Helpers ----
    @log_errors(include_args=True, include_traceback=True)
    def _current_row(self) -> int:
        try:
            idx = self.list.currentIndex()
            if not idx.isValid():
                return -1
            src = self._filter.mapToSource(idx)
            return src.row()
        except Exception as e:
            logger.warning(
                f"Warning in _current_row: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_current_row",
                stack_trace=traceback.format_exc()
            )
            return -1

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _select_by_id(self, profile_id: str) -> None:
        try:
            row = self._profiles_model.index_of_id(profile_id)
            if row >= 0:
                sidx = self._profiles_model.index(row, 0)  # type: ignore[attr-defined]
                vidx = self._filter.mapFromSource(sidx)
                if vidx.isValid():
                    self.profile_dropdown.setCurrentIndex(vidx.row())
                    self._current_profile_id = profile_id
                    self._load_profile(profile_id)
        except Exception as e:
            logger.error(
                f"Error in _select_by_id: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_select_by_id",
                parameters={"profile_id": profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Selection Error",
                component_name="SettingsManagerDialog._select_by_id",
                profile_id=profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _reselect_current(self) -> None:
        try:
            if not self._current_profile_id:
                return
            self._select_by_id(self._current_profile_id)
        except Exception as e:
            logger.error(
                f"Error in _reselect_current: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_reselect_current",
                parameters={"profile_id": self._current_profile_id},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Reselection Error",
                component_name="SettingsManagerDialog._reselect_current",
                profile_id=self._current_profile_id
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _update_action_states(self) -> None:
        try:
            has_sel = self._current_profile_id is not None
            self.act_rename.setEnabled(has_sel)
            self.act_duplicate.setEnabled(has_sel)
            self.act_delete.setEnabled(has_sel)
            self.act_set_active.setEnabled(has_sel)
            # Apply enablement mirrors editor dirty state (if apply button exists)
            # DialogButtonBox apply is wired via clicked signal; no direct enable toggle here.
        except Exception as e:
            logger.error(
                f"Error in _update_action_states: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_update_action_states",
                parameters={"has_sel": self._current_profile_id is not None},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Action State Error",
                component_name="SettingsManagerDialog._update_action_states"
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _show_error(self, title: str, message: Optional[str], code: Optional[str]) -> None:
        try:
            """Show error using centralized error handler with detailed logging."""
            msg = str(message) if message is not None else "An unexpected error occurred."
            if code:
                msg += f"\n\nCode: {code}"

            handle_gui_error(
                parent=self,
                error=msg,
                title=title,
                component_name="SettingsManagerDialog",
                error_code=code
            )
        except Exception as e:
            logger.error(
                f"Error in _show_error: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_show_error",
                parameters={"title": title, "message": message, "code": code},
                stack_trace=traceback.format_exc()
            )
            # Fallback to standard QMessageBox if handle_gui_error fails
            try:
                show_selectable_error(self, title, msg)
            except Exception as fallback_e:
                logger.error(
                    f"Fallback error dialog failed: {type(fallback_e).__name__}: {fallback_e}",
                    file_path=__file__,
                    line_number=inspect.currentframe().f_lineno,
                    func_name="_show_error",
                    stack_trace=traceback.format_exc()
                )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _show_empty_state_hint(self) -> None:
        try:
            # If there are no profiles, hint user to Create
            if self._profiles_model.rowCount() == 0:
                show_selectable_info(self, "No Profiles", "No profiles exist. Click 'Create' to add one.")
        except Exception as e:
            logger.error(
                f"Error in _show_empty_state_hint: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_show_empty_state_hint",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Hint Display Error",
                component_name="SettingsManagerDialog._show_empty_state_hint"
            )

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _prompt_save_discard_cancel(self, question: str) -> str:
        """
        Prompt the user to save/discard/cancel. Returns 'save' | 'discard' | 'cancel'.
        """
        try:
            mb = QMessageBox(self)
            mb.setWindowTitle("Unsaved Changes")
            mb.setText(question)
            btn_save = mb.addButton("Save", QMessageBox.AcceptRole)
            btn_discard = mb.addButton("Discard", QMessageBox.DestructiveRole)
            btn_cancel = mb.addButton("Cancel", QMessageBox.RejectRole)
            mb.setDefaultButton(btn_save)
            mb.exec()
            clicked = mb.clickedButton()
            if clicked == btn_save:
                return "save"
            if clicked == btn_discard:
                return "discard"
            return "cancel"
        except Exception as e:
            logger.error(
                f"Error in _prompt_save_discard_cancel: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_prompt_save_discard_cancel",
                parameters={"question": question},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Prompt Error",
                component_name="SettingsManagerDialog._prompt_save_discard_cancel",
                question=question
            )
            return "cancel"  # Safe default

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _maybe_prompt_save_discard_cancel(self) -> bool:
        """
        If editor has unsaved changes, prompt the user. Returns True to proceed, False to abort.
        """
        try:
            if not self.editor.is_dirty():
                return True
            result = self._prompt_save_discard_cancel("Apply changes to the current profile before switching?")
            if result == "save":
                self._on_apply()
                return not self.editor.is_dirty()
            if result == "discard":
                return True
            return False
        except Exception as e:
            logger.error(
                f"Error in _maybe_prompt_save_discard_cancel: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_maybe_prompt_save_discard_cancel",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Prompt Error",
                component_name="SettingsManagerDialog._maybe_prompt_save_discard_cancel"
            )
            return False  # Abort on error
    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SettingsManagerDialog")
    def _on_profile_selected(self, index: int) -> None:
        try:
            if index < 0:
                return
            profile_id = self.profile_dropdown.itemData(index)
            if profile_id is not None:
                self._load_profile(profile_id)
        except Exception as e:
            logger.error(
                f"Error in _on_profile_selected: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="_on_profile_selected",
                parameters={"index": index},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                parent=self,
                error=e,
                title="Profile Selection Error",
                component_name="SettingsManagerDialog._on_profile_selected",
                index=index
            )


@log_errors(include_args=True, include_traceback=True)
@gui_error_handler(component_name="settings_manager_dialog")
def settings_manager_dialog(parent: Optional[QWidget] = None, modal: bool = True) -> Optional[Dict[str, Any]]:
    """
    Create and display the Settings Manager dialog.

    Parameters
    ----------
    parent : Optional[QWidget]
        Parent widget.
    modal : bool
        Whether the dialog should be modal.

    Returns
    -------
    Optional[Dict[str, Any]]
        Active profile dictionary on accept; None on cancel.
    """
    try:
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for settings_manager_dialog")

        dlg = SettingsManagerDialog(parent=parent)
        dlg.setModal(bool(modal))
        # Show dialog and block
        result = dlg.exec()
        if result == dlg.Accepted:
            # Return the active profile at close time
            ctrl = dlg.controller
            active = ctrl.get_active()
            return active.data if active.success else None
        return None
    except Exception as e:
        logger.error(
            f"Error in settings_manager_dialog: {type(e).__name__}: {e}",
            file_path=__file__,
            line_number=inspect.currentframe().f_lineno,
            func_name="settings_manager_dialog",
            parameters={"parent": parent, "modal": modal},
            stack_trace=traceback.format_exc()
        )
        handle_gui_error(
            parent=parent,
            error=e,
            title="Dialog Launch Error",
            component_name="settings_manager_dialog"
        )
        return None


__all__ = ["SettingsManagerDialog", "settings_manager_dialog"]
