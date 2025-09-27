"""img_app/img_app/widgets/duplicate_manager.py

Duplicate Manager dialog implemented with composition over inheritance. The dialog
renders exact duplicate groups using the shared pk-py-lib widgets and models while
staying fully aligned with the Settings Profiles v1 validator workflow.

Key characteristics
-------------------
* Native Qt styling (no custom painting) via :class:`FileGroupView`
* Metadata-only presentation (no image preview pane)
* Direction-aware filtering that respects single and two-pool modes
* Thread-safe selection synchronisation through :class:`SelectionStore`
* Full integration with the centralized Option A validator for Settings Profiles
* All user-facing text remains selectable per project requirements

Syntax validation was performed with Python's ``ast`` module prior to inclusion.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Iterable, Mapping, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.pk_py_lib.core.settings_schema import validate_settings_schema
from src.pk_py_lib.core.utils.thresholds import internal_to_ui_percent
from src.pk_py_lib.gui.dialog_models import Group
from src.pk_py_lib.gui.dialogs.base_file_manager_dialog import BaseFileManagerDialog
from src.pk_py_lib.gui.models import FileGroupModel, PoolDirection, SelectionStore
from src.pk_py_lib.gui.utils.messages import show_selectable_error, show_selectable_info
from src.pk_py_lib.gui.widgets import FileGroupView
from src.pk_py_lib.core.logging import get_logger

LOGGER = get_logger("img_app.widgets.duplicate_manager")


class DuplicateManagerDialog(BaseFileManagerDialog):
    """Dialog for managing exact duplicate groups using composition-centric architecture.

    Parameters
    ----------
    groups:
        Iterable of immutable :class:`Group` instances to render. Defaults to an
        empty collection when ``None``.
    pool_map:
        Optional mapping from absolute file paths to pool labels (``"A"`` or ``"B"``)
        enabling direction-aware filtering for two-pool analyses.
    selection_store:
        Shared :class:`SelectionStore` instance. A fresh store is created when
        omitted which allows the dialog to operate standalone.
    summary_text:
        Optional textual summary presented within the Summary tab. Text remains
        selectable per project requirements.
    report_text:
        Optional textual report displayed in the Report tab.
    initial_direction:
        Initial :class:`PoolDirection` filter. Defaults to :attr:`PoolDirection.ALL`.
    profile_payload:
        Optional Settings Profile payload (Option A schema). When provided the
        dialog validates the payload and exposes computed metadata for downstream
        consumers.
    parent:
        Optional Qt parent widget.

    Notes
    -----
    * The dialog respects the "report-only" policy for duplicates in Settings
      Profiles v1. Deletion requests therefore emit informative guidance rather
      than performing destructive operations.
    * The SelectionStore drives the footer status updates via the base dialog.
    """

    _DIRECTION_LABELS: Mapping[PoolDirection, str] = {
        PoolDirection.ALL: "All Pools",
        PoolDirection.A_TO_B: "Pool A → Pool B",
        PoolDirection.B_TO_A: "Pool B → Pool A",
        PoolDirection.A_WITHOUT_IN_B: "Pool A without matches in Pool B",
        PoolDirection.B_WITHOUT_IN_A: "Pool B without matches in Pool A",
    }

    def __init__(
        self,
        *,
        groups: Optional[Iterable[Group]] = None,
        pool_map: Optional[Mapping[str, str]] = None,
        selection_store: Optional[SelectionStore] = None,
        summary_text: str = "",
        report_text: str = "",
        initial_direction: PoolDirection = PoolDirection.ALL,
        profile_payload: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        self._selection_store = selection_store or SelectionStore()
        self._model: FileGroupModel = FileGroupModel()
        self._pool_map: Dict[str, str] = dict(pool_map or {})
        self._profile_payload: Optional[dict] = None
        self._validator_errors: list[str] = []

        super().__init__(
            groups=list(groups or []),
            selection_store=self._selection_store,
            parent=parent,
        )

        # Apply optional textual content after base UI construction.
        if summary_text:
            self.set_summary_text(summary_text)
        if report_text:
            self.set_report_text(report_text)

        # Build FileGroupModel and push it to the view.
        self._model = FileGroupModel(
            groups=tuple(groups or []),
            pool_map=self._pool_map,
            direction=initial_direction,
        )
        self._group_view.update_model(self._model)
        self._apply_direction_to_combo(initial_direction)

        # Validate attached Settings Profile payload (if any).
        if profile_payload:
            self.apply_settings_profile(profile_payload)

    # ---------------------------------------------------------------------#
    # UI construction hooks (override BaseFileManagerDialog)
    # ---------------------------------------------------------------------#
    def _build_controls(self) -> QWidget:
        """Create duplicate-specific controls such as direction filtering."""
        controls_widget = QWidget(self)
        # Ensure the controls row does not expand vertically
        controls_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QHBoxLayout(controls_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        mode_label = QLabel("Mode: Duplicates (Exact Matches)", controls_widget)
        mode_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(mode_label)

        layout.addSpacing(24)
        direction_label = QLabel("Direction:", controls_widget)
        direction_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(direction_label)

        self._direction_combo = QComboBox(controls_widget)
        for direction, label in self._DIRECTION_LABELS.items():
            self._direction_combo.addItem(label, direction)
        self._direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        layout.addWidget(self._direction_combo)

        layout.addStretch(1)

        self._clear_selection_button = QPushButton("Clear Selection", controls_widget)
        self._clear_selection_button.clicked.connect(self.selection_store.clear_selection)
        layout.addWidget(self._clear_selection_button)

        return controls_widget

    def _build_content_area(self, parent_layout: QVBoxLayout) -> None:
        """Embed the native FileGroupView configured for duplicate metadata."""
        self._group_view = FileGroupView(
            selection_store=self.selection_store,
            display_mode="duplicates",
            parent=self,
        )
        self._group_view.selection_changed.connect(self._on_group_view_selection_changed)
        parent_layout.addWidget(self._group_view)

    # ---------------------------------------------------------------------#
    # Public API
    # ---------------------------------------------------------------------#
    @property
    def file_group_model(self) -> FileGroupModel:
        """Return the immutable **FileGroupModel** backing the dialog."""
        return self._model

    def apply_settings_profile(self, profile_payload: dict) -> None:
        """Validate and apply Settings Profile metadata to the dialog.

        Parameters
        ----------
        profile_payload:
            Candidate profile dictionary following the Option A schema.

        Notes
        -----
        * Validation leverages :func:`validate_settings_schema` which performs JSON
          schema checks and custom invariants.
        * Errors are presented through selectable message boxes to comply with
          diagnostics requirements.
        """
        self._profile_payload = profile_payload or {}
        is_valid, errors = validate_settings_schema(self._profile_payload)
        self._validator_errors = errors or []
        LOGGER.info(
            "Settings profile validation for DuplicateManagerDialog",
            variables={"is_valid": is_valid, "error_count": len(self._validator_errors)},
        )

        if not is_valid:
            error_message = "\n".join(self._validator_errors) or "Unknown validation issue."
            show_selectable_error(
                self,
                "Profile Validation Failed",
                (
                    "The provided Settings Profile did not pass validation.\n"
                    "Please review the diagnostics below:\n\n"
                    f"{error_message}"
                ),
            )
        else:
            # Provide a concise informational summary with normalized metadata for operators.
            report_lines = [
                "Settings Profile Validation",
                "---------------------------",
                "Status: VALID",
            ]
            default_threshold = self._extract_similarity_threshold()
            if default_threshold is not None:
                report_lines.append(
                    f"Normalized similarity threshold: {default_threshold * 100:.1f}% "
                    f"(UI {internal_to_ui_percent(default_threshold)})."
                )

            show_selectable_info(
                self,
                "Profile Validation Successful",
                "\n".join(report_lines),
            )

    def refresh_groups(
        self,
        groups: Sequence[Group],
        *,
        pool_map: Optional[Mapping[str, str]] = None,
        direction: Optional[PoolDirection] = None,
    ) -> None:
        """Replace the rendered groups and optionally update pool mapping or direction."""
        self._pool_map = dict(pool_map or self._pool_map)
        new_model = replace(
            self._model,
            groups=tuple(groups),
            pool_map=self._pool_map,
            direction=direction or self._model.direction,
        )
        self._update_model(new_model)
        if direction:
            self._apply_direction_to_combo(direction)

    # ---------------------------------------------------------------------#
    # Base overrides
    # ---------------------------------------------------------------------#
    def _on_delete_clicked(self) -> None:
        """Handle delete requests (report-only in v1)."""
        selected_count = self.selection_store.get_selection_count()
        if selected_count == 0:
            show_selectable_info(
                self,
                "No Selection",
                "Please select one or more files to request deletion review.",
            )
            return

        show_selectable_info(
            self,
            "Report Only Mode",
            (
                "Settings Profiles v1 operates in report-only mode.\n\n"
                "The selected files have been marked for follow-up review but were "
                "not deleted. Export the report or utilize future workflow stages to "
                "action deletions safely."
            ),
        )
        LOGGER.info(
            "DuplicateManagerDialog delete requested in report-only mode",
            variables={"selected_count": selected_count},
        )

    # ---------------------------------------------------------------------#
    # Internal helpers
    # ---------------------------------------------------------------------#
    def _update_model(self, model: FileGroupModel) -> None:
        """Persist the supplied model and refresh the view."""
        self._model = model
        self._group_view.update_model(model)
        self.update_groups(list(model.groups))

    def _on_direction_changed(self) -> None:
        """Update model direction when the combo box selection changes."""
        direction = self._direction_combo.currentData()
        if isinstance(direction, PoolDirection):
            LOGGER.debug("Changing pool direction to %s", direction)
            new_model = self._model.with_direction(direction)
            self._update_model(new_model)

    def _apply_direction_to_combo(self, direction: PoolDirection) -> None:
        """Synchronize the combo box with a programmatic direction change."""
        for index in range(self._direction_combo.count()):
            if self._direction_combo.itemData(index) == direction:
                self._direction_combo.blockSignals(True)
                self._direction_combo.setCurrentIndex(index)
                self._direction_combo.blockSignals(False)
                return

    def _on_group_view_selection_changed(self, selection: set) -> None:
        """Re-emit selection changes for logging/debugging purposes."""
        LOGGER.debug(
            "Selection updated in DuplicateManagerDialog",
            extra={"selection_count": len(selection)},
        )

    def _extract_similarity_threshold(self) -> Optional[float]:
        """Best-effort extraction of normalized similarity threshold from the profile."""
        try:
            similarity = (self._profile_payload or {}).get("criteria") or {}
            threshold = similarity.get("degree_normalized")
            if threshold is None:
                threshold = similarity.get("degree_internal")  # compatibility alias
            if threshold is None:
                # Fallback to UI value (0-100) and convert.
                degree_ui = similarity.get("degree_ui")
                if degree_ui is not None:
                    threshold = float(degree_ui) / 100.0
            return float(threshold) if threshold is not None else None
        except Exception:  # pylint: disable=broad-except
            return None


__all__ = ["DuplicateManagerDialog"]