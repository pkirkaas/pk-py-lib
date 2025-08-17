"""
src/pk_py_lib/gui/settings_manager/editor_widget.py

Reusable right-side editor widget for Settings Profiles:
- Metadata form (Name with live validation, Description)
- Key/Value table with Add/Edit/Remove actions using JSON values
- Dirty-state tracking and diff computation for Apply flows

This widget is GUI-only but persistence-agnostic. Callers should:
- load_profile(profile: dict, values: dict)
- check is_dirty() and gather_changes() to apply via a controller
- call reset_dirty() after successful apply

Note: Syntax validation was performed using Python's ast module per project rules.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Defensive import for PySide6 to keep library importable in headless environments
try:
    from PySide6.QtCore import Qt, Signal, QSize
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QTableView,
        QAbstractItemView,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QMessageBox,
        QSplitter,
        QSizePolicy,
    )
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for GUI widgets")

    QWidget = QVBoxLayout = QHBoxLayout = QLabel = QLineEdit = QPlainTextEdit = QPushButton = QTableView = QAbstractItemView = QDialog = QDialogButtonBox = QFormLayout = QMessageBox = QSplitter = QSizePolicy = Signal = Qt = QIcon = _Missing()  # type: ignore


from .models import KeyValueTableModel
from .validators import ProfileNameValidator, SingleKeyValidator
from ...api.settings_profiles import SettingsProfilesAPI


class KeyValueEditDialog(QDialog):
    """
    Modal editor for a single (key, value) pair where value is arbitrary JSON.

    Parameters
    ----------
    api : SettingsProfilesAPI
        API used to validate the 'key' syntax via SingleKeyValidator.
    parent : Optional[QWidget]
        Parent widget.
    initial_key : Optional[str]
        Initial key to prefill (for edit flow).
    initial_value : Optional[Any]
        Initial Python value (will be serialized to JSON for editing).

    Usage
    -----
    >>> api = SettingsProfilesAPI()
    >>> dlg = KeyValueEditDialog(api, initial_key="alg.threshold", initial_value=0.9)
    >>> if dlg.exec() == dlg.Accepted:
    ...     k, v = dlg.result_value()
    """

    def __init__(
        self,
        api: SettingsProfilesAPI,
        parent: Optional[QWidget] = None,
        initial_key: Optional[str] = None,
        initial_value: Optional[Any] = None,
    ):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for KeyValueEditDialog")

        super().__init__(parent)
        self.setWindowTitle("Edit Item")
        self._api = api
        self._out_key: Optional[str] = None
        self._out_value: Optional[Any] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.inp_key = QLineEdit(initial_key or "")
        self.inp_key.setPlaceholderText("key (e.g., alg.threshold)")
        self._key_validator = SingleKeyValidator(self._api, self)
        self.inp_key.setValidator(self._key_validator)  # type: ignore[arg-type]
        form.addRow("Key:", self.inp_key)

        self.lbl_key_error = QLabel("")
        self.lbl_key_error.setStyleSheet("color: #c00; font-size: 12px;")
        form.addRow("", self.lbl_key_error)

        self.inp_value = QPlainTextEdit()
        self.inp_value.setPlaceholderText('JSON value (e.g., 0.9, "text", {"a":1}, [1,2])')
        self.inp_value.setMinimumHeight(120)
        self.inp_value.setTabChangesFocus(True)
        # Prefill JSON if provided
        if initial_value is not None:
            try:
                self.inp_value.setPlainText(json.dumps(initial_value, ensure_ascii=False, indent=2))
            except Exception:
                self.inp_value.setPlainText(str(initial_value))
        form.addRow("Value:", self.inp_value)

        self.lbl_value_error = QLabel("")
        self.lbl_value_error.setStyleSheet("color: #c00; font-size: 12px;")
        form.addRow("", self.lbl_value_error)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Live validation hook
        self.inp_key.textChanged.connect(self._validate_key_inline)

    def _validate_key_inline(self) -> None:
        t = self.inp_key.text()
        try:
            state = self.inp_key.validator().validate(t, len(t))[0]  # type: ignore[attr-defined]
        except Exception:
            state = None
        if hasattr(self._key_validator, "last_error"):
            msg = self._key_validator.last_error()  # type: ignore[attr-defined]
        else:
            msg = None
        self.lbl_key_error.setText("" if state == self._key_validator.Acceptable else (msg or ""))  # type: ignore[attr-defined]

    def _on_accept(self) -> None:
        key = (self.inp_key.text() or "").strip()
        if not key:
            self.lbl_key_error.setText("Key is required")
            return
        # Validate key via validator
        try:
            state = self._key_validator.validate(key, len(key))[0]  # type: ignore[index]
        except Exception:
            state = None
        if state != self._key_validator.Acceptable:  # type: ignore[attr-defined]
            self.lbl_key_error.setText(self._key_validator.last_error() or "Invalid key")  # type: ignore[attr-defined]
            return

        # Parse JSON
        raw = self.inp_value.toPlainText().strip()
        if raw == "":
            # Null-like handling: allow explicit null
            self.lbl_value_error.setText("Value is required (use null for JSON null)")
            return
        try:
            value = json.loads(raw)
        except Exception as e:
            self.lbl_value_error.setText(f"Invalid JSON: {e}")
            return

        self._out_key = key
        self._out_value = value
        self.accept()

    def result_value(self) -> Tuple[str, Any]:
        """
        Return the (key, value) after acceptance.

        Raises
        ------
        RuntimeError
            If called before acceptance.
        """
        if self._out_key is None:
            raise RuntimeError("Dialog not accepted")
        return self._out_key, self._out_value


class SettingsProfileEditorWidget(QWidget):
    """
    Composite editor for a settings profile's metadata and key/value items.

    Signals
    -------
    dirtyChanged(bool)
        Emitted when the dirty state changes.

    Public API
    ----------
    - load_profile(profile: dict, values: dict)
    - is_dirty() -> bool
    - gather_changes() -> tuple[name|None, description|None, set_values|None, remove_keys|None]
    - reset_dirty()

    Usage
    -----
    >>> api = SettingsProfilesAPI()
    >>> w = SettingsProfileEditorWidget(api=api)
    >>> w.load_profile(profile={'id':'..','name':'Default','description':None}, values={'a':1})
    """

    dirtyChanged = Signal(bool) if PYSIDE_AVAILABLE else None  # type: ignore[assignment]

    def __init__(self, api: Optional[SettingsProfilesAPI] = None, parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for SettingsProfileEditorWidget")

        super().__init__(parent)
        self._api = api or SettingsProfilesAPI()

        # Original state (used to compute diffs)
        self._profile_id: Optional[str] = None
        self._orig_name: Optional[str] = None
        self._orig_description: Optional[str] = None
        self._orig_values: Dict[str, Any] = {}

        # Dirty flags (quick-path checks)
        self._meta_dirty: bool = False
        self._kv_dirty: bool = False

        self._build_ui()

    # ------------------------------------------------------------------ UI ----
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Metadata group (simple form without group box for compactness)
        form = QFormLayout()
        layout.addLayout(form)

        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Profile name (1–64 chars; letters, digits, space, _ or -)")
        self._name_validator = ProfileNameValidator(self._api, self)
        self.inp_name.setValidator(self._name_validator)  # type: ignore[arg-type]
        form.addRow("Name:", self.inp_name)

        self.lbl_name_error = QLabel("")
        self.lbl_name_error.setStyleSheet("color: #c00; font-size: 12px;")
        form.addRow("", self.lbl_name_error)

        self.inp_description = QPlainTextEdit()
        self.inp_description.setPlaceholderText("Optional description")
        self.inp_description.setMinimumHeight(60)
        form.addRow("Description:", self.inp_description)

        # Key/Value table and actions
        header = QHBoxLayout()
        lbl_kv = QLabel("Key/Value Items")
        lbl_kv.setStyleSheet("font-weight: bold;")
        header.addWidget(lbl_kv)
        header.addStretch()

        self.btn_add = QPushButton("Add…")
        self.btn_edit = QPushButton("Edit…")
        self.btn_remove = QPushButton("Remove")
        header.addWidget(self.btn_add)
        header.addWidget(self.btn_edit)
        header.addWidget(self.btn_remove)
        layout.addLayout(header)

        self.tbl = QTableView(self)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setWordWrap(False)
        self.tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.model = KeyValueTableModel(self)
        self.tbl.setModel(self.model)
        self.tbl.horizontalHeader().setStretchLastSection(True)  # Value column stretches
        layout.addWidget(self.tbl, 1)

        # Hook signals
        self.inp_name.textChanged.connect(self._on_meta_changed)
        self.inp_description.textChanged.connect(self._on_meta_changed)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_remove.clicked.connect(self._on_remove)
        self.tbl.selectionModel().selectionChanged.connect(self._update_action_states)  # type: ignore[attr-defined]

        self._update_action_states()
        self._update_name_error()

    # ------------------------------------------------------------ State/Diff ----
    def load_profile(self, profile: Dict[str, Any], values: Dict[str, Any]) -> None:
        """
        Load a profile dictionary and its key/value items into the editor.

        Parameters
        ----------
        profile : Dict[str, Any]
            Profile metadata as returned by SettingsProfilesAPI.get_profile or list call.
        values : Dict[str, Any]
            Mapping of key → Python value for the profile.
        """
        self._profile_id = str(profile.get("id", ""))
        name = str(profile.get("name", "") or "")
        desc = profile.get("description")
        desc = None if desc is None else str(desc)
        self._orig_name = name
        self._orig_description = desc
        self._orig_values = dict(values or {})

        # Populate UI
        self.inp_name.blockSignals(True)
        self.inp_description.blockSignals(True)
        self.inp_name.setText(name)
        self.inp_description.setPlainText(desc or "")
        self.inp_name.blockSignals(False)
        self.inp_description.blockSignals(False)

        self.model.set_items_from_dict(values or {})
        self._meta_dirty = False
        self._kv_dirty = False
        self._emit_dirty_if_changed()
        self._update_action_states()
        self._update_name_error()

    def is_dirty(self) -> bool:
        """Return True if there are unsaved changes."""
        return bool(self._meta_dirty or self._kv_dirty)

    def reset_dirty(self) -> None:
        """Reset dirty flags to False (call after successful apply)."""
        self._meta_dirty = False
        self._kv_dirty = False
        self._emit_dirty_if_changed()

    def gather_changes(self) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]], Optional[Sequence[str]]]:
        """
        Compute diffs between current UI state and the original snapshot.

        Returns
        -------
        Tuple[name_or_None, description_or_None, set_values_or_None, remove_keys_or_None]
            - name_or_None: new name if changed (stripped), else None
            - description_or_None: new description (stripped or empty to clear) if changed, else None
            - set_values_or_None: dict of key → value to upsert (changed or added)
            - remove_keys_or_None: list of keys to remove (case-insensitive compare)
        """
        cur_name = (self.inp_name.text() or "").strip()
        cur_desc = (self.inp_description.toPlainText() or "").strip()
        cur_vals = self.model.to_dict()

        name_change = cur_name if cur_name != (self._orig_name or "") else None
        desc_change = cur_desc if (cur_desc or None) != (self._orig_description or None) else None

        # Case-insensitive diff for keys
        orig_map = {k.lower(): (k, v) for k, v in (self._orig_values or {}).items()}
        cur_map = {k.lower(): (k, v) for k, v in (cur_vals or {}).items()}

        # Removed keys = in orig but not in current
        removed_lc = [k for k in orig_map.keys() if k not in cur_map]
        remove_keys = [orig_map[k][0] for k in removed_lc] if removed_lc else None

        # Changed/new values
        set_values: Dict[str, Any] = {}
        for lc, (ckey, cval) in cur_map.items():
            if lc not in orig_map:
                set_values[ckey] = cval
            else:
                _, oval = orig_map[lc]
                if not self._json_equal(oval, cval):
                    set_values[ckey] = cval
        set_values_map = set_values or None

        return name_change, desc_change, set_values_map, remove_keys

    # --------------------------------------------------------------- Events ----
    def _on_meta_changed(self) -> None:
        self._meta_dirty = (
            (self.inp_name.text() or "").strip() != (self._orig_name or "")
            or (self.inp_description.toPlainText() or "").strip() != (self._orig_description or "")
        )
        self._emit_dirty_if_changed()
        self._update_name_error()

    def _update_name_error(self) -> None:
        try:
            t = self.inp_name.text()
            state = self._name_validator.validate(t, len(t))[0]  # type: ignore[index]
            msg = self._name_validator.last_error()  # type: ignore[attr-defined]
            self.lbl_name_error.setText("" if state == self._name_validator.Acceptable else (msg or ""))  # type: ignore[attr-defined]
        except Exception:
            # In case validator is stubbed/missing
            self.lbl_name_error.setText("")

    def _on_add(self) -> None:
        if not self._profile_id:
            return
        dlg = KeyValueEditDialog(self._api, parent=self)
        if dlg.exec() == dlg.Accepted:
            key, value = dlg.result_value()
            # Check local duplicate (case-insensitive); update instead of duplicate
            current = self.model.to_dict()
            for k in list(current.keys()):
                if k.lower() == key.lower():
                    # Update existing
                    self.model.add_item(key, value)
                    self._kv_dirty = True
                    self._emit_dirty_if_changed()
                    self._update_action_states()
                    return
            # Append new
            self.model.add_item(key, value)
            self._kv_dirty = True
            self._emit_dirty_if_changed()
            self._update_action_states()

    def _on_edit(self) -> None:
        idxs = self.tbl.selectionModel().selectedRows()  # type: ignore[attr-defined]
        if len(idxs) != 1:
            return
        r = idxs[0].row()
        kv = self.model.get_row(r)
        if not kv:
            return
        key0, val0 = kv
        dlg = KeyValueEditDialog(self._api, parent=self, initial_key=key0, initial_value=val0)
        if dlg.exec() == dlg.Accepted:
            key, value = dlg.result_value()
            self.model.add_item(key, value)
            self._kv_dirty = True
            self._emit_dirty_if_changed()
            self._update_action_states()

    def _on_remove(self) -> None:
        idxs = self.tbl.selectionModel().selectedRows()  # type: ignore[attr-defined]
        if not idxs:
            return
        # Collect keys
        keys: List[str] = []
        for i in idxs:
            kv = self.model.get_row(i.row())
            if kv:
                keys.append(kv[0])

        if not keys:
            return
        details = "\n".join(keys[:10]) + ("\n…" if len(keys) > 10 else "")
        resp = QMessageBox.question(
            self,
            "Remove Items",
            f"Remove {len(keys)} item(s)?\n\n{details}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        removed = self.model.remove_keys(keys)
        if removed > 0:
            self._kv_dirty = True
            self._emit_dirty_if_changed()
            self._update_action_states()

    def _update_action_states(self) -> None:
        has_sel = False
        try:
            has_sel = bool(self.tbl.selectionModel().selectedRows())  # type: ignore[attr-defined]
        except Exception:
            pass
        self.btn_edit.setEnabled(has_sel and True)
        self.btn_remove.setEnabled(has_sel and True)

    # -------------------------------------------------------------- Helpers ----
    def _emit_dirty_if_changed(self) -> None:
        # Emit only when changed to reduce noise
        if hasattr(self, "_last_dirty_emitted"):
            last = getattr(self, "_last_dirty_emitted", None)
        else:
            last = None
        now = self.is_dirty()
        if last is None or bool(last) != bool(now):
            setattr(self, "_last_dirty_emitted", bool(now))
            try:
                self.dirtyChanged.emit(bool(now))  # type: ignore[attr-defined]
            except Exception:
                pass

    @staticmethod
    def _json_equal(a: Any, b: Any) -> bool:
        """
        Compare two Python structures for JSON-equivalent equality using a stable serialization.
        """
        try:
            aj = json.dumps(a, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            bj = json.dumps(b, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return aj == bj
        except Exception:
            return a == b