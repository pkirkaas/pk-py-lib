"""
src/pk_py_lib/gui/settings_manager/structured_editor.py

Structured editor widget for Settings Profiles (Option A) with pools, mode selection,
and proper form controls instead of key-value pairs.

Features:
- Pool configuration with path selection
- Mode selection (duplicates/similarity)
- Criteria settings with algorithm and degree
- Scope settings with direction
- Real-time validation and conditional UI enablement
- Integration with path selector dialog

Note: Syntax validation was performed using Python's ast module per project rules.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

# Defensive import for PySide6 to keep library importable in headless environments
try:
    from PySide6.QtCore import Qt, Signal, QSize
    from PySide6.QtGui import QIcon, QDoubleValidator
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QComboBox,
        QCheckBox,
        QSpinBox,
        QSlider,
        QGroupBox,
        QFormLayout,
        QGridLayout,
        QMessageBox,
        QSizePolicy,
        QDialog,
    )
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for GUI widgets")

    QWidget = QVBoxLayout = QHBoxLayout = QLabel = QLineEdit = QPlainTextEdit = QPushButton = QComboBox = QCheckBox = QSpinBox = QSlider = QGroupBox = QFormLayout = QGridLayout = QMessageBox = QSizePolicy = QDialog = Signal = Qt = QIcon = QDoubleValidator = _Missing()  # type: ignore


from ...api.settings_profiles import SettingsProfilesAPI
from ...core.settings_schema import (
    validate_settings_schema,
    normalize_settings,
    is_valid_for_save,
    is_valid_for_run,
    create_default_profile,
)
from ..file_selector.widgets import DirectorySelectorWidget


class StructuredProfileEditorWidget(QWidget):
    """
    Structured editor for SettingsProfileOptionA with form controls instead of key-value pairs.

    Signals
    -------
    dirtyChanged(bool)
        Emitted when the dirty state changes.

    Public API
    ----------
    - load_profile(profile: dict)
    - is_dirty() -> bool
    - gather_changes() -> dict
    - reset_dirty()
    """

    dirtyChanged = Signal(bool) if PYSIDE_AVAILABLE else None  # type: ignore[assignment]

    def __init__(self, api: Optional[SettingsProfilesAPI] = None, parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for StructuredProfileEditorWidget")

        super().__init__(parent)
        self._api = api or SettingsProfilesAPI()

        # Original state for diff computation
        self._original_profile: Dict[str, Any] = {}
        self._current_profile: Dict[str, Any] = {}

        # Dirty state
        self._dirty = False

        self._build_ui()
        self._update_ui_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Metadata section
        meta_group = QGroupBox("Profile Metadata")
        meta_layout = QFormLayout()
        meta_group.setLayout(meta_layout)

        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Profile name (1-64 chars)")
        meta_layout.addRow("Name:", self.inp_name)

        self.inp_description = QPlainTextEdit()
        self.inp_description.setPlaceholderText("Optional description")
        self.inp_description.setMaximumHeight(80)
        meta_layout.addRow("Description:", self.inp_description)

        layout.addWidget(meta_group)

        # Pools section
        pools_group = QGroupBox("Pools")
        pools_layout = QVBoxLayout()
        pools_group.setLayout(pools_layout)

        # Pool A
        pool_a_group = QGroupBox("Pool A (Required)")
        pool_a_layout = QFormLayout()
        pool_a_group.setLayout(pool_a_layout)

        pool_a_path_layout = QHBoxLayout()
        self.inp_pool_a_path = QLineEdit()
        self.inp_pool_a_path.setPlaceholderText("Select directory for Pool A")
        pool_a_path_layout.addWidget(self.inp_pool_a_path)
        self.btn_pool_a_select = QPushButton("Browse...")
        pool_a_path_layout.addWidget(self.btn_pool_a_select)
        pool_a_layout.addRow("Root Path:", pool_a_path_layout)

        self.chk_pool_a_recurse = QCheckBox("Recurse subdirectories")
        self.chk_pool_a_recurse.setChecked(True)
        pool_a_layout.addRow("", self.chk_pool_a_recurse)

        self.chk_pool_a_follow_symlinks = QCheckBox("Follow symbolic links")
        pool_a_layout.addRow("", self.chk_pool_a_follow_symlinks)

        self.chk_pool_a_include_hidden = QCheckBox("Include hidden files")
        pool_a_layout.addRow("", self.chk_pool_a_include_hidden)

        pools_layout.addWidget(pool_a_group)

        # Pool B
        pool_b_group = QGroupBox("Pool B (Optional - for two-pool operations)")
        pool_b_layout = QFormLayout()
        pool_b_group.setLayout(pool_b_layout)

        pool_b_path_layout = QHBoxLayout()
        self.inp_pool_b_path = QLineEdit()
        self.inp_pool_b_path.setPlaceholderText("Select directory for Pool B")
        pool_b_path_layout.addWidget(self.inp_pool_b_path)
        self.btn_pool_b_select = QPushButton("Browse...")
        pool_b_path_layout.addWidget(self.btn_pool_b_select)
        pool_b_layout.addRow("Root Path:", pool_b_path_layout)

        self.chk_pool_b_recurse = QCheckBox("Recurse subdirectories")
        self.chk_pool_b_recurse.setChecked(True)
        pool_b_layout.addRow("", self.chk_pool_b_recurse)

        self.chk_pool_b_follow_symlinks = QCheckBox("Follow symbolic links")
        pool_b_layout.addRow("", self.chk_pool_b_follow_symlinks)

        self.chk_pool_b_include_hidden = QCheckBox("Include hidden files")
        pool_b_layout.addRow("", self.chk_pool_b_include_hidden)

        pools_layout.addWidget(pool_b_group)
        layout.addWidget(pools_group)

        # Mode and criteria section
        mode_group = QGroupBox("Operation Mode")
        mode_layout = QFormLayout()
        mode_group.setLayout(mode_layout)

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["duplicates", "similarity"])
        mode_layout.addRow("Mode:", self.cmb_mode)

        # Criteria sub-group
        criteria_group = QGroupBox("Criteria")
        criteria_layout = QFormLayout()
        criteria_group.setLayout(criteria_layout)

        self.cmb_algorithm = QComboBox()
        self.cmb_algorithm.addItems(["pHash", "blake3"])
        criteria_layout.addRow("Algorithm:", self.cmb_algorithm)

        degree_layout = QHBoxLayout()
        self.sld_degree = QSlider(Qt.Horizontal)
        self.sld_degree.setRange(0, 100)
        self.sld_degree.setValue(90)
        degree_layout.addWidget(self.sld_degree)
        self.lbl_degree = QLabel("90%")
        self.lbl_degree.setTextInteractionFlags(Qt.TextSelectableByMouse)
        degree_layout.addWidget(self.lbl_degree)
        criteria_layout.addRow("Similarity Degree:", degree_layout)

        mode_layout.addRow(criteria_group)
        layout.addWidget(mode_group)

        # Scope section
        scope_group = QGroupBox("Scope")
        scope_layout = QFormLayout()
        scope_group.setLayout(scope_layout)

        self.cmb_scope_kind = QComboBox()
        self.cmb_scope_kind.addItems(["single_pool", "two_pool"])
        scope_layout.addRow("Scope Kind:", self.cmb_scope_kind)

        self.cmb_scope_direction = QComboBox()
        self.cmb_scope_direction.addItems(["A_TO_B", "B_TO_A", "A_WITHOUT_IN_B", "B_WITHOUT_IN_A"])
        scope_layout.addRow("Direction:", self.cmb_scope_direction)

        layout.addWidget(scope_group)

        # Output section
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()
        output_group.setLayout(output_layout)

        self.cmb_output_mode = QComboBox()
        self.cmb_output_mode.addItems(["report_only"])
        output_layout.addRow("Output Mode:", self.cmb_output_mode)

        layout.addWidget(output_group)

        # Validation status
        self.lbl_validation = QLabel("")
        self.lbl_validation.setStyleSheet("color: #c00; font-weight: bold;")
        self.lbl_validation.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_validation)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self) -> None:
        """Connect all UI signals to handlers."""
        # Metadata
        self.inp_name.textChanged.connect(self._on_change)
        self.inp_description.textChanged.connect(self._on_change)

        # Pool A
        self.inp_pool_a_path.textChanged.connect(self._on_change)
        self.btn_pool_a_select.clicked.connect(lambda: self._select_path("pool_a"))
        self.chk_pool_a_recurse.stateChanged.connect(self._on_change)
        self.chk_pool_a_follow_symlinks.stateChanged.connect(self._on_change)
        self.chk_pool_a_include_hidden.stateChanged.connect(self._on_change)

        # Pool B
        self.inp_pool_b_path.textChanged.connect(self._on_change)
        self.btn_pool_b_select.clicked.connect(lambda: self._select_path("pool_b"))
        self.chk_pool_b_recurse.stateChanged.connect(self._on_change)
        self.chk_pool_b_follow_symlinks.stateChanged.connect(self._on_change)
        self.chk_pool_b_include_hidden.stateChanged.connect(self._on_change)

        # Mode and criteria
        self.cmb_mode.currentTextChanged.connect(self._on_mode_changed)
        self.cmb_algorithm.currentTextChanged.connect(self._on_change)
        self.sld_degree.valueChanged.connect(self._on_degree_changed)

        # Scope
        self.cmb_scope_kind.currentTextChanged.connect(self._on_scope_changed)
        self.cmb_scope_direction.currentTextChanged.connect(self._on_change)

        # Output
        self.cmb_output_mode.currentTextChanged.connect(self._on_change)

    def _select_path(self, pool: str) -> None:
        """Open path selector dialog for the specified pool."""
        selector = DirectorySelectorWidget(self)
        if selector.exec() == QDialog.Accepted:
            selected_path = selector.get_selected_path()
            if selected_path:
                if pool == "pool_a":
                    self.inp_pool_a_path.setText(selected_path)
                else:
                    self.inp_pool_b_path.setText(selected_path)

    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode change with conditional UI updates."""
        self._on_change()
        self._update_ui_state()

    def _on_scope_changed(self, scope_kind: str) -> None:
        """Handle scope kind change with conditional UI updates."""
        self._on_change()
        self._update_ui_state()

    def _on_degree_changed(self, value: int) -> None:
        """Handle degree slider change."""
        self.lbl_degree.setText(f"{value}%")
        self._on_change()

    def _on_change(self) -> None:
        """Handle any change in the UI and update dirty state."""
        self._update_current_profile_from_ui()
        self._validate_profile()
        self._set_dirty(self._is_dirty())

    def _update_current_profile_from_ui(self) -> None:
        """Update current_profile dict from UI values."""
        profile = {
            "name": self.inp_name.text().strip(),
            "description": self.inp_description.toPlainText().strip() or None,
            "pools": {
                "A": {
                    "root_path": self.inp_pool_a_path.text().strip(),
                    "recurse": self.chk_pool_a_recurse.isChecked(),
                    "follow_symlinks": self.chk_pool_a_follow_symlinks.isChecked(),
                    "include_hidden": self.chk_pool_a_include_hidden.isChecked(),
                }
            },
            "mode": self.cmb_mode.currentText(),
            "criteria": {
                "algorithm": self.cmb_algorithm.currentText(),
            },
            "scope": {
                "kind": self.cmb_scope_kind.currentText(),
            },
            "output": {
                "mode": self.cmb_output_mode.currentText(),
            }
        }

        # Add Pool B if path is specified and scope is two_pool
        pool_b_path = self.inp_pool_b_path.text().strip()
        if pool_b_path and self.cmb_scope_kind.currentText() == "two_pool":
            profile["pools"]["B"] = {
                "root_path": pool_b_path,
                "recurse": self.chk_pool_b_recurse.isChecked(),
                "follow_symlinks": self.chk_pool_b_follow_symlinks.isChecked(),
                "include_hidden": self.chk_pool_b_include_hidden.isChecked(),
            }

        # For similarity mode, add degree_ui
        if profile["mode"] == "similarity":
            profile["criteria"]["degree_ui"] = self.sld_degree.value()

        # For two_pool scope, add direction
        if profile["scope"]["kind"] == "two_pool":
            profile["scope"]["direction"] = self.cmb_scope_direction.currentText()

        self._current_profile = profile

    def _validate_profile(self) -> None:
        """Validate the current profile and update validation status."""
        if not self._current_profile or "name" not in self._current_profile:
            self.lbl_validation.setText("Profile incomplete")
            return

        # Add required fields for validation
        validation_profile = self._current_profile.copy()
        validation_profile.setdefault("id", "temp-validation-id")
        validation_profile.setdefault("created_at", "2025-01-01T00:00:00Z")
        validation_profile.setdefault("updated_at", "2025-01-01T00:00:00Z")

        is_valid, errors = validate_settings_schema(validation_profile)
        if is_valid:
            self.lbl_validation.setText("✓ Valid configuration")
            self.lbl_validation.setStyleSheet("color: #090; font-weight: bold;")
        else:
            error_msg = errors[0] if errors else "Invalid configuration"
            self.lbl_validation.setText(f"✗ {error_msg}")
            self.lbl_validation.setStyleSheet("color: #c00; font-weight: bold;")

    def _update_ui_state(self) -> None:
        """Update UI state based on current selections."""
        mode = self.cmb_mode.currentText()
        scope_kind = self.cmb_scope_kind.currentText()

        # Enable/disable degree based on mode
        is_similarity = mode == "similarity"
        self.sld_degree.setEnabled(is_similarity)
        self.lbl_degree.setEnabled(is_similarity)

        # Enable/disable algorithm based on mode
        self.cmb_algorithm.setEnabled(True)
        if mode == "duplicates":
            self.cmb_algorithm.setCurrentText("blake3")
            self.cmb_algorithm.setEnabled(False)

        # Enable/disable Pool B based on scope
        is_two_pool = scope_kind == "two_pool"
        self.inp_pool_b_path.setEnabled(is_two_pool)
        self.btn_pool_b_select.setEnabled(is_two_pool)
        self.chk_pool_b_recurse.setEnabled(is_two_pool)
        self.chk_pool_b_follow_symlinks.setEnabled(is_two_pool)
        self.chk_pool_b_include_hidden.setEnabled(is_two_pool)

        # Enable/disable direction based on scope
        self.cmb_scope_direction.setEnabled(is_two_pool)

    def _is_dirty(self) -> bool:
        """Check if current profile differs from original."""
        if not self._original_profile:
            return bool(self._current_profile and self._current_profile.get("name"))

        # Simple comparison - in real implementation, use proper diff
        return json.dumps(self._current_profile, sort_keys=True) != json.dumps(self._original_profile, sort_keys=True)

    def _set_dirty(self, dirty: bool) -> None:
        """Set dirty state and emit signal if changed."""
        if self._dirty != dirty:
            self._dirty = dirty
            if hasattr(self, "dirtyChanged"):
                self.dirtyChanged.emit(dirty)

    # Public API
    def load_profile(self, profile: Dict[str, Any]) -> None:
        """Load a profile into the editor."""
        self._original_profile = profile.copy()
        self._current_profile = profile.copy()

        # Populate UI
        self.inp_name.setText(profile.get("name", ""))
        self.inp_description.setPlainText(profile.get("description", ""))

        # Pool A
        pools = profile.get("pools", {})
        pool_a = pools.get("A", {})
        self.inp_pool_a_path.setText(pool_a.get("root_path", ""))
        self.chk_pool_a_recurse.setChecked(pool_a.get("recurse", True))
        self.chk_pool_a_follow_symlinks.setChecked(pool_a.get("follow_symlinks", False))
        self.chk_pool_a_include_hidden.setChecked(pool_a.get("include_hidden", False))

        # Pool B
        pool_b = pools.get("B", {})
        if pool_b:
            self.inp_pool_b_path.setText(pool_b.get("root_path", ""))
            self.chk_pool_b_recurse.setChecked(pool_b.get("recurse", True))
            self.chk_pool_b_follow_symlinks.setChecked(pool_b.get("follow_symlinks", False))
            self.chk_pool_b_include_hidden.setChecked(pool_b.get("include_hidden", False))

        # Mode and criteria
        self.cmb_mode.setCurrentText(profile.get("mode", "duplicates"))
        criteria = profile.get("criteria", {})
        self.cmb_algorithm.setCurrentText(criteria.get("algorithm", "pHash"))
        self.sld_degree.setValue(criteria.get("degree_ui", 90))

        # Scope
        scope = profile.get("scope", {})
        self.cmb_scope_kind.setCurrentText(scope.get("kind", "single_pool"))
        self.cmb_scope_direction.setCurrentText(scope.get("direction", "A_TO_B"))

        # Output
        output = profile.get("output", {})
        self.cmb_output_mode.setCurrentText(output.get("mode", "report_only"))

        self._update_ui_state()
        self._validate_profile()
        self._set_dirty(False)

    def is_dirty(self) -> bool:
        """Return True if there are unsaved changes."""
        return self._dirty

    def reset_dirty(self) -> None:
        """Reset dirty state."""
        self._original_profile = self._current_profile.copy()
        self._set_dirty(False)

    def gather_changes(self) -> Dict[str, Any]:
        """Return the current profile data for saving."""
        return self._current_profile.copy()

    def get_validation_status(self) -> Tuple[bool, list]:
        """Return validation status and errors."""
        validation_profile = self._current_profile.copy()
        validation_profile.setdefault("id", "temp-validation-id")
        validation_profile.setdefault("created_at", "2025-01-01T00:00:00Z")
        validation_profile.setdefault("updated_at", "2025-01-01T00:00:00Z")
        
        return validate_settings_schema(validation_profile)


__all__ = ["StructuredProfileEditorWidget"]