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


from .models import ProfilesListModel
from .editor_widget import SettingsProfileEditorWidget
from .controller import SettingsManagerController
from ...api import ErrorCodes
from ..utils.messages import show_selectable_error, show_selectable_info


class _NamePromptDialog(QDialog):
    """
    Minimal reusable prompt dialog for entering a name (with live validation message).

    The caller is responsible for performing final API calls. This dialog focuses on
    collecting the text value with inline validator message support.
    """

    def __init__(self, title: str, label: str, initial: str = "", parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for _NamePromptDialog")
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

    def text(self) -> str:
        return (self.inp.text() or "").strip()

    def set_error(self, msg: Optional[str]) -> None:
        self.lbl_error.setText(msg or "")


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

    # ------------------------------------------------------------------ UI ----
    def _build_ui(self) -> None:
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

    # ------------------------------------------------------------ Data Flow ----
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
                    self.list.setCurrentIndex(idx.row())
                    self._current_profile_id = target_id
                    self._load_profile(target_id)
                    self._update_action_states()
                    return

        # If no selection found, select first if present
        if self._profiles_model.rowCount() > 0:
            idx = self._filter.index(0, 0)  # type: ignore[attr-defined]
            self.list.setCurrentIndex(idx.row())
            pid = self._profiles_model.profile_at(0).id  # type: ignore[union-attr]
            self._current_profile_id = pid
            self._load_profile(pid)
        else:
            self._current_profile_id = None
            # Clear editor state
            self.editor.load_profile({"id": "", "name": "", "description": None}, {})
            self._show_empty_state_hint()
        self._update_action_states()

    def _load_profile(self, profile_id: str) -> None:
        resp = self.controller.get_profile_with_values(profile_id)
        if not resp.success or not resp.data:
            self._show_error("Failed to load profile", resp.message, resp.code)
            return
        prof = resp.data.get("profile") or {}
        vals = resp.data.get("values") or {}
        self.editor.load_profile(prof, vals)

    # --------------------------------------------------------------- Events ----
    def _on_search_changed(self, text: str) -> None:
        txt = (text or "").strip()
        try:
            re = QRegularExpression(txt) if txt else QRegularExpression()
            self._filter.setFilterRegularExpression(re)  # type: ignore[attr-defined]
        except Exception:
            # Fallback to fixed string filter if regex fails
            self._filter.setFilterFixedString(txt)  # type: ignore[attr-defined]

    def _on_list_selection_changed(self) -> None:
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

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._update_action_states()

    # -------------------------------------------------------------- Actions ----
    def _on_create(self) -> None:
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

    def _on_rename(self) -> None:
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

    def _on_duplicate(self) -> None:
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

    def _on_delete(self) -> None:
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

    def _on_set_active(self) -> None:
        pid = self._current_profile_id
        if not pid:
            return
        r = self.controller.set_active(pid)
        if not r.success:
            self._show_error("Set Active failed", r.message, r.code)
            return
        # Refresh list to reflect active marker
        self._refresh_profiles(select_active=True, preserve_selection=False)

    def _on_apply(self) -> None:
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

    def _on_ok(self) -> None:
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

    def _on_cancel(self) -> None:
        if self.editor.is_dirty():
            result = self._prompt_save_discard_cancel("Discard changes and close?")
            if result == "cancel":
                return
            if result == "save":
                self._on_apply()
                if self.editor.is_dirty():
                    return
        self.reject()

    # -------------------------------------------------------------- Helpers ----
    def _current_row(self) -> int:
        idx = self.list.currentIndex()
        if not idx.isValid():
            return -1
        src = self._filter.mapToSource(idx)
        return src.row()

    def _select_by_id(self, profile_id: str) -> None:
        row = self._profiles_model.index_of_id(profile_id)
        if row >= 0:
            sidx = self._profiles_model.index(row, 0)  # type: ignore[attr-defined]
            vidx = self._filter.mapFromSource(sidx)
            if vidx.isValid():
                self.list.setCurrentIndex(vidx.row())
                self._current_profile_id = profile_id
                self._load_profile(profile_id)

    def _reselect_current(self) -> None:
        if not self._current_profile_id:
            return
        self._select_by_id(self._current_profile_id)

    def _update_action_states(self) -> None:
        has_sel = self._current_profile_id is not None
        self.act_rename.setEnabled(has_sel)
        self.act_duplicate.setEnabled(has_sel)
        self.act_delete.setEnabled(has_sel)
        self.act_set_active.setEnabled(has_sel)
        # Apply enablement mirrors editor dirty state (if apply button exists)
        # DialogButtonBox apply is wired via clicked signal; no direct enable toggle here.

    def _show_error(self, title: str, message: Optional[str], code: Optional[str]) -> None:
        msg = str(message) if message is not None else "An unexpected error occurred."
        if code:
            msg += f"\n\nCode: {code}"
        show_selectable_error(self, title, msg)

    def _show_empty_state_hint(self) -> None:
        # If there are no profiles, hint user to Create
        if self._profiles_model.rowCount() == 0:
            show_selectable_info(self, "No Profiles", "No profiles exist. Click 'Create' to add one.")

    def _prompt_save_discard_cancel(self, question: str) -> str:
        """
        Prompt the user to save/discard/cancel. Returns 'save' | 'discard' | 'cancel'.
        """
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

    def _maybe_prompt_save_discard_cancel(self) -> bool:
        """
        If editor has unsaved changes, prompt the user. Returns True to proceed, False to abort.
        """
        if not self.editor.is_dirty():
            return True
        result = self._prompt_save_discard_cancel("Apply changes to the current profile before switching?")
        if result == "save":
            self._on_apply()
            return not self.editor.is_dirty()
        if result == "discard":
            return True
    def _on_profile_selected(self, index: int) -> None:
        if index < 0:
            return
        profile_id = self.profile_dropdown.itemData(index)
        if profile_id is not None:
            self._load_profile(profile_id)


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


__all__ = ["SettingsManagerDialog", "settings_manager_dialog"]