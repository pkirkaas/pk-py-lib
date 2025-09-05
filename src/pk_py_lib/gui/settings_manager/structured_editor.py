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
        QDialogButtonBox,
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
from ..file_selector.widgets import DirectorySelectorWidget, MultiPathSelectorWidget, PathFilterSpec


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
        # Call _update_ui_state to initialize algorithm combo box correctly
        self._update_ui_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Metadata section - compact single line layout
        meta_group = QGroupBox("Profile Metadata")
        meta_group.setMaximumHeight(80)  # More compact fixed height
        meta_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # Prevent vertical expansion
        meta_layout = QHBoxLayout()
        meta_group.setLayout(meta_layout)

        # Name field with label above
        name_container = QVBoxLayout()
        name_label = QLabel("Name:")
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Profile name (1-64 chars)")
        name_container.addWidget(name_label)
        name_container.addWidget(self.inp_name)
        meta_layout.addLayout(name_container)

        # Add spacing between name and description
        meta_layout.addSpacing(20)

        # Description field with label above - now single line
        desc_container = QVBoxLayout()
        desc_label = QLabel("Description:")
        self.inp_description = QLineEdit()  # Changed from QPlainTextEdit to QLineEdit
        self.inp_description.setPlaceholderText("Optional description")
        desc_container.addWidget(desc_label)
        desc_container.addWidget(self.inp_description)
        meta_layout.addLayout(desc_container)

        # Add stretch to push fields to the left and prevent expansion
        meta_layout.addStretch(1)
        
        layout.addWidget(meta_group)

        # Scope section
        scope_group = QGroupBox("Scope")
        scope_layout = QFormLayout()
        scope_group.setLayout(scope_layout)

        # Create a horizontal layout for Scope Kind and Direction on the same line
        self.scope_direction_layout = QHBoxLayout()
        
        # Scope Kind combo box with label
        scope_kind_label = QLabel("Scope Kind:")
        self.cmb_scope_kind = QComboBox()
        self.cmb_scope_kind.addItems(["single_pool", "two_pool"])
        self.cmb_scope_kind.setMaximumWidth(160)  # ~20 characters
        self.scope_direction_layout.addWidget(scope_kind_label)
        self.scope_direction_layout.addWidget(self.cmb_scope_kind)
        
        # Add stretch to separate Scope Kind and Direction
        self.scope_direction_layout.addSpacing(20)
        
        # Direction combo box with label
        self.direction_label = QLabel("Direction:")
        self.cmb_scope_direction = QComboBox()
        self.cmb_scope_direction.addItems(["A_TO_B", "B_TO_A", "A_WITHOUT_IN_B", "B_WITHOUT_IN_A"])
        self.cmb_scope_direction.setMaximumWidth(160)  # ~20 characters
        self.scope_direction_layout.addWidget(self.direction_label)
        self.scope_direction_layout.addWidget(self.cmb_scope_direction)
        
        # Add the horizontal layout to the form layout
        scope_layout.addRow(self.scope_direction_layout)

        layout.addWidget(scope_group)

        # Pools section - set to expand to fill available space
        pools_group = QGroupBox("Pools")
        pools_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        pools_layout = QVBoxLayout()
        pools_group.setLayout(pools_layout)

        # Pool A
        pool_a_group = QGroupBox("Pool A (Required)")
        pool_a_layout = QVBoxLayout()
        pool_a_group.setLayout(pool_a_layout)

        # Top row with label and button
        pool_a_top_layout = QHBoxLayout()
        paths_label = QLabel("Paths:")
        self.btn_pool_a_select = QPushButton("Browse...")
        pool_a_top_layout.addWidget(paths_label)
        pool_a_top_layout.addStretch(1)  # Push button to the right
        pool_a_top_layout.addWidget(self.btn_pool_a_select)
        pool_a_layout.addLayout(pool_a_top_layout)

        # Paths text area that expands
        self.inp_pool_a_paths = QPlainTextEdit()
        self.inp_pool_a_paths.setPlaceholderText("Enter paths for Pool A (one per line)\nOr use Browse to add directories/files")
        self.inp_pool_a_paths.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set fixed-width font for paths
        font = self.inp_pool_a_paths.font()
        font.setFamily("Consolas")
        self.inp_pool_a_paths.setFont(font)
        pool_a_layout.addWidget(self.inp_pool_a_paths)

        pools_layout.addWidget(pool_a_group)

        # Pool B
        self.pool_b_group = QGroupBox("Pool B (Optional - for two-pool operations)")
        pool_b_layout = QVBoxLayout()
        self.pool_b_group.setLayout(pool_b_layout)

        # Top row with label and button
        pool_b_top_layout = QHBoxLayout()
        paths_label_b = QLabel("Paths:")
        self.btn_pool_b_select = QPushButton("Browse...")
        pool_b_top_layout.addWidget(paths_label_b)
        pool_b_top_layout.addStretch(1)  # Push button to the right
        pool_b_top_layout.addWidget(self.btn_pool_b_select)
        pool_b_layout.addLayout(pool_b_top_layout)

        # Paths text area that expands
        self.inp_pool_b_paths = QPlainTextEdit()
        self.inp_pool_b_paths.setPlaceholderText("Enter paths for Pool B (one per line)\nOr use Browse to add directories/files")
        self.inp_pool_b_paths.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Set fixed-width font for paths
        font = self.inp_pool_b_paths.font()
        font.setFamily("Consolas")
        self.inp_pool_b_paths.setFont(font)
        pool_b_layout.addWidget(self.inp_pool_b_paths)

        pools_layout.addWidget(self.pool_b_group)
        layout.addWidget(pools_group)

        # Mode and criteria section
        mode_group = QGroupBox("Operation Mode")
        mode_layout = QFormLayout()
        mode_group.setLayout(mode_layout)

        # Create a horizontal layout for Mode and Algorithm on the same line
        mode_algo_layout = QHBoxLayout()
        
        # Mode combo box with label
        mode_label = QLabel("Mode:")
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["duplicates", "similarity"])
        self.cmb_mode.setMaximumWidth(160)  # ~20 characters
        mode_algo_layout.addWidget(mode_label)
        mode_algo_layout.addWidget(self.cmb_mode)
        
        # Add stretch to separate Mode and Algorithm
        mode_algo_layout.addSpacing(20)
        
        # Algorithm combo box with label
        algo_label = QLabel("Algorithm:")
        self.cmb_algorithm = QComboBox()
        # Start with empty combo box, _update_ui_state will populate it correctly
        self.cmb_algorithm.setMaximumWidth(160)  # ~20 characters
        mode_algo_layout.addWidget(algo_label)
        mode_algo_layout.addWidget(self.cmb_algorithm)
        
        # Add the horizontal layout to the form layout
        mode_layout.addRow(mode_algo_layout)

        # Criteria sub-group for degree controls (stays on its own line)
        criteria_group = QGroupBox("Criteria")
        criteria_layout = QFormLayout()
        criteria_group.setLayout(criteria_layout)

        # Create label for "Similarity Degree:"
        self.lbl_degree_label = QLabel("Similarity Degree:")
        # Create a widget to contain the degree layout
        self.degree_widget = QWidget()
        degree_layout = QHBoxLayout(self.degree_widget)  # Set layout on widget
        self.sld_degree = QSlider(Qt.Horizontal)
        self.sld_degree.setRange(0, 100)
        self.sld_degree.setValue(90)
        degree_layout.addWidget(self.sld_degree)
        self.lbl_degree = QLabel("90%")
        self.lbl_degree.setTextInteractionFlags(Qt.TextSelectableByMouse)
        degree_layout.addWidget(self.lbl_degree)
        # Add row to form layout
        criteria_layout.addRow(self.lbl_degree_label, self.degree_widget)

        mode_layout.addRow(criteria_group)
        layout.addWidget(mode_group)

        # Output section
        output_group = QGroupBox("Output")
        output_layout = QFormLayout()
        output_group.setLayout(output_layout)

        self.cmb_output_mode = QComboBox()
        self.cmb_output_mode.addItems(["report_only"])
        self.cmb_output_mode.setMaximumWidth(160)  # ~20 characters
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
        self.inp_pool_a_paths.textChanged.connect(self._on_change)
        self.btn_pool_a_select.clicked.connect(lambda: self._select_path("pool_a"))

        # Pool B
        self.inp_pool_b_paths.textChanged.connect(self._on_change)
        self.btn_pool_b_select.clicked.connect(lambda: self._select_path("pool_b"))

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
        """Open multi-path editor dialog for the specified pool."""
        self._edit_paths(pool)

    def _on_mode_changed(self, mode: str) -> None:
        """Handle mode change with conditional UI updates."""
        self._update_ui_state()  # Update UI first to ensure consistent state
        self._on_change()        # Then update profile and validate to ensure algorithm is set correctly

    def _on_scope_changed(self, scope_kind: str) -> None:
        """Handle scope kind change with conditional UI updates."""
        self._update_ui_state()  # Update UI state
        self._on_change()        # Then update profile and validate since no signal from UI changes

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
            "description": self.inp_description.text().strip(),
            "pools": {
                "A": {
                    "paths": [path.strip() for path in self.inp_pool_a_paths.toPlainText().splitlines() if path.strip()],
                    "recurse": True,
                    "follow_symlinks": True,
                    "include_hidden": True,
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

        # Add Pool B if paths are specified and scope is two_pool
        pool_b_paths = [path.strip() for path in self.inp_pool_b_paths.toPlainText().splitlines() if path.strip()]
        if pool_b_paths and self.cmb_scope_kind.currentText() == "two_pool":
            profile["pools"]["B"] = {
                "paths": pool_b_paths,
                "recurse": True,
                "follow_symlinks": True,
                "include_hidden": True,
            }

        # For similarity mode, add degree_ui
        if profile["mode"] == "similarity":
            profile["criteria"]["degree_ui"] = self.sld_degree.value()

        # For two_pool scope, add direction
        if profile["scope"]["kind"] == "two_pool":
            profile["scope"]["direction"] = self.cmb_scope_direction.currentText()

        self._current_profile = profile

    def _get_complete_profile(self, for_validation: bool = False) -> Dict[str, Any]:
        """
        Get the current profile with all required generated fields added.
        
        Parameters
        ----------
        for_validation : bool
            If True, normalize the profile to fill in defaults for validation
            If False, return the profile with only generated fields added
            
        Returns
        -------
        Dict[str, Any]
            Complete profile ready for validation or saving
        """
        profile = self._current_profile.copy()
        
        # Add generated fields that are required by schema but not user-editable
        if not self._original_profile:  # New profile
            from uuid import uuid4
            from datetime import datetime, timezone
            
            profile.setdefault("id", str(uuid4()))
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            profile.setdefault("created_at", now)
            profile.setdefault("updated_at", now)
        else:  # Existing profile
            profile.setdefault("id", self._original_profile.get("id"))
            profile.setdefault("created_at", self._original_profile.get("created_at"))
            profile.setdefault("updated_at", self._original_profile.get("updated_at"))
        
        profile.setdefault("profile_version", "1.0.0")
        profile.setdefault("schema_version", "1.0")
        
        if for_validation:
            # Use normalization to fill in all other defaults for validation
            try:
                return normalize_settings(profile)
            except Exception as e:
                raise ValueError(f"Normalization error: {e}")
        
        return profile

    def _validate_profile(self) -> None:
        """Validate the current profile and update validation status."""
        if not self._current_profile:
            self.lbl_validation.setText("Profile incomplete")
            return
            
        # Check required user-editable fields before schema validation
        name = self._current_profile.get("name", "").strip()
        if not name:
            self.lbl_validation.setText("Profile incomplete: name is required")
            return
            
        pool_a = self._current_profile.get("pools", {}).get("A", {})
        pool_a_paths = pool_a.get("paths", [])
        if not pool_a_paths:
            self.lbl_validation.setText("Profile incomplete: Pool A must have at least one path")
            return
            
        # For two-pool scope, check Pool B paths
        scope = self._current_profile.get("scope", {})
        if scope.get("kind") == "two_pool":
            pool_b = self._current_profile.get("pools", {}).get("B", {})
            if pool_b is None:
                self.lbl_validation.setText("Profile incomplete: Pool B configuration is required for two-pool scope")
                return
            pool_b_paths = pool_b.get("paths", [])
            if not pool_b_paths:
                self.lbl_validation.setText("Profile incomplete: Pool B must have at least one path for two-pool scope")
                return

        # Get complete profile with generated fields for validation
        try:
            validation_profile = self._get_complete_profile(for_validation=True)
        except Exception as e:
            self.lbl_validation.setText(str(e))
            return
        
        # Validate the complete profile
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

        # Show/hide and enable/disable degree controls based on mode
        is_similarity = mode == "similarity"
        self.lbl_degree_label.setVisible(is_similarity)
        self.degree_widget.setVisible(is_similarity)
        self.sld_degree.setEnabled(is_similarity)
        self.lbl_degree.setEnabled(is_similarity)

        # Update algorithm options based on mode
        if mode == "duplicates":
            desired_algos = ["blake3", "xxh3"]
        elif mode == "similarity":
            desired_algos = ["pHash"]
        else:
            desired_algos = []
        
        # Save current algorithm before potentially changing items
        current_algo_before = self.cmb_algorithm.currentText()
        
        # Get current items in the algorithm combo box
        current_items = [self.cmb_algorithm.itemText(i) for i in range(self.cmb_algorithm.count())]
        
        # Only update the combo box items if they are different from desired
        if set(current_items) != set(desired_algos):
            self.cmb_algorithm.blockSignals(True)
            self.cmb_algorithm.clear()
            if desired_algos:
                self.cmb_algorithm.addItems(desired_algos)
                # After adding items, set current text: preserve if valid, else use first item
                if current_algo_before in desired_algos:
                    self.cmb_algorithm.setCurrentText(current_algo_before)
                else:
                    self.cmb_algorithm.setCurrentText(desired_algos[0])
            self.cmb_algorithm.blockSignals(False)
        
        # Ensure current algorithm is valid for the mode (in case it was set to something invalid)
        current_algo = self.cmb_algorithm.currentText()
        if desired_algos and current_algo not in desired_algos:
            self.cmb_algorithm.blockSignals(True)
            self.cmb_algorithm.setCurrentText(desired_algos[0])
            self.cmb_algorithm.blockSignals(False)
            # Update _current_profile to reflect the change
            if "criteria" not in self._current_profile:
                self._current_profile["criteria"] = {}
            self._current_profile["criteria"]["algorithm"] = desired_algos[0]
        
        # Enable/disable based on mode
        self.cmb_algorithm.setEnabled(bool(desired_algos))

        # Show/hide and enable/disable Pool B and Direction based on scope kind
        is_two_pool = scope_kind == "two_pool"
        
        # Pool B visibility and enablement
        self.pool_b_group.setVisible(is_two_pool)
        self.inp_pool_b_paths.setEnabled(is_two_pool)
        self.btn_pool_b_select.setEnabled(is_two_pool)
        
        # Direction combo box visibility and enablement
        self.cmb_scope_direction.setVisible(is_two_pool)
        self.cmb_scope_direction.setEnabled(is_two_pool)
        
        # Also hide the Direction label when not in two-pool mode
        self.direction_label.setVisible(is_two_pool)

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
        self.inp_description.setText(profile.get("description", "") or "")

        # Pool A
        pools = profile.get("pools", {})
        pool_a = pools.get("A", {})
        paths_a = pool_a.get("paths", [])
        self.inp_pool_a_paths.setPlainText("\n".join(paths_a))

        # Pool B
        pool_b = pools.get("B", {})
        if pool_b:
            paths_b = pool_b.get("paths", [])
            self.inp_pool_b_paths.setPlainText("\n".join(paths_b))

        # Block signals for mode and algorithm comboboxes to prevent recursive updates during load
        self.cmb_mode.blockSignals(True)
        self.cmb_algorithm.blockSignals(True)

        # Mode
        mode = profile.get("mode", "duplicates")
        self.cmb_mode.setCurrentText(mode)

        # Set algorithm combo box items based on mode to ensure correct options before setting algorithm
        if mode == "duplicates":
            desired_algos = ["blake3", "xxh3"]
        elif mode == "similarity":
            desired_algos = ["pHash"]
        else:
            desired_algos = []

        # Get current items in the algorithm combo box
        current_items = [self.cmb_algorithm.itemText(i) for i in range(self.cmb_algorithm.count())]
        
        # Only update the combo box items if they are different from desired
        if set(current_items) != set(desired_algos):
            self.cmb_algorithm.clear()
            if desired_algos:
                self.cmb_algorithm.addItems(desired_algos)

        # Now set criteria from profile
        criteria = profile.get("criteria", {})
        # Get algorithm with mode-based default
        if mode == "duplicates":
            default_algo = "blake3"
        else:
            default_algo = "pHash"
        algorithm = criteria.get("algorithm", default_algo)
        self.cmb_algorithm.setCurrentText(algorithm)
        self.sld_degree.setValue(criteria.get("degree_ui", 90))

        # Unblock signals
        self.cmb_algorithm.blockSignals(False)
        self.cmb_mode.blockSignals(False)

        # Update UI state for enable/disable logic (without changing algorithm items)
        self._update_ui_state()

        # Set scope and output
        scope = profile.get("scope", {})
        self.cmb_scope_kind.setCurrentText(scope.get("kind", "single_pool"))
        self.cmb_scope_direction.setCurrentText(scope.get("direction", "A_TO_B"))

        output = profile.get("output", {})
        self.cmb_output_mode.setCurrentText(output.get("mode", "report_only"))

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
        # Include generated/schema-required fields so downstream API has a complete payload
        return self._get_complete_profile(for_validation=False)
    def get_validation_status(self) -> Tuple[bool, list]:
        """
        Return schema validation status and errors for the current form state.

        This applies early UI gating for required user-provided fields before
        running schema validation on a complete, normalized profile (with
        generated fields included).

        Gating mirrors _validate_profile():
        - name must be non-empty
        - Pool A root_path must be non-empty
        - If scope.kind == 'two_pool', Pool B root_path must be non-empty
        """
        # Early gating
        if not self._current_profile:
            return False, ["Profile incomplete"]
        name = self._current_profile.get("name", "").strip()
        if not name:
            return False, ["Profile incomplete: name is required"]

        pool_a = self._current_profile.get("pools", {}).get("A", {})
        pool_a_paths = (pool_a or {}).get("paths", [])
        if not pool_a_paths:
            return False, ["Profile incomplete: Pool A must have at least one path"]

        scope = self._current_profile.get("scope", {})
        if scope.get("kind") == "two_pool":
            pool_b = self._current_profile.get("pools", {}).get("B", {})
            pool_b_paths = (pool_b or {}).get("paths", [])
            if not pool_b_paths:
                return False, ["Profile incomplete: Pool B must have at least one path for two-pool scope"]

        # Build complete, normalized profile for schema validation
        try:
            validation_profile = self._get_complete_profile(for_validation=True)
        except Exception as e:
            return False, [str(e)]

        return validate_settings_schema(validation_profile)


    def _edit_paths(self, pool: str) -> None:
        """Open multi-path editor dialog for the specified pool."""
        # Get current paths from the text edit
        if pool == "pool_a":
            current_text = self.inp_pool_a_paths.toPlainText()
        else:
            current_text = self.inp_pool_b_paths.toPlainText()
        
        current_paths = [line.strip() for line in current_text.splitlines() if line.strip()]
        
        # Create filter spec that allows both files and directories
        filter_spec = PathFilterSpec(
            allow_dirs=True,
            allow_files=True,
            include_hidden=False,
        )
        
        # Create dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {pool.replace('_', ' ').title()} Paths")
        layout = QVBoxLayout(dlg)
        
        # Create multi-path selector widget
        widget = MultiPathSelectorWidget(
            parent=dlg,
            title="Paths",
            start_dir=None,
            filter_spec=filter_spec,
        )
        widget.set_paths(current_paths)
        layout.addWidget(widget)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        
        if dlg.exec() == QDialog.Accepted:
            new_paths = widget.get_paths()
            new_text = "\n".join(str(p) for p in new_paths)
            if pool == "pool_a":
                self.inp_pool_a_paths.setPlainText(new_text)
            else:
                self.inp_pool_b_paths.setPlainText(new_text)




__all__ = ["StructuredProfileEditorWidget"]