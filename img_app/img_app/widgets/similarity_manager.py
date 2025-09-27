"""img_app/img_app/widgets/similarity_manager.py

Similarity Manager dialog implemented with composition over inheritance. The dialog
provides a dual-pane interface where groups of perceptually similar images are
listed alongside a live preview pane. Selection state is shared via the centralized
SelectionStore pattern and the dialog integrates with the Settings Profiles v1
validator for Option A profiles.

Key characteristics
-------------------
* Native Qt styling (no custom painting) through :class:`FileGroupView` and
  :class:`SimilarityPreviewPane`.
* Supports algorithm selection (pHash / wHash) and user-adjustable thresholds.
* Provides direction-aware filtering for single-pool and two-pool workflows.
* Fetches perceptual hashes from the cache database on demand and clusters them
  using :func:`find_similar_images`.
* Synchronises preview thumbnails and selection state with :class:`SelectionStore`.
* Validates incoming Settings Profiles through :func:`validate_settings_schema`.
* All user-facing text is selectable per project requirements.

Syntax validation was performed with Python's ``ast`` module prior to inclusion.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image.similarity import (
    find_similar_images,
    get_image_metadata,
)
from src.pk_py_lib.core.settings_schema import validate_settings_schema
from src.pk_py_lib.core.utils.thresholds import internal_to_ui_percent
from src.pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats
from src.pk_py_lib.gui.dialogs.base_file_manager_dialog import BaseFileManagerDialog
from src.pk_py_lib.gui.models import FileGroupModel, PoolDirection, SelectionStore
from src.pk_py_lib.gui.utils.messages import show_selectable_error, show_selectable_info
from src.pk_py_lib.gui.widgets import FileGroupView, SimilarityPreviewPane
from src.pk_py_lib.core.logging import get_logger

LOGGER = get_logger("img_app.widgets.similarity_manager")


class SimilarityManagerDialog(BaseFileManagerDialog):
    """Dialog for managing perceptually similar image groups.

    Parameters
    ----------
    groups:
        Iterable of :class:`Group` instances that will be rendered initially.
    pool_map:
        Optional mapping from absolute file paths to pool labels (``"A"`` or ``"B"``)
        enabling direction-aware filters.
    selection_store:
        Shared :class:`SelectionStore` instance. A fresh store is created when omitted.
    db_manager:
        Optional :class:`DatabaseManager` used to compute similarity groups on demand.
    summary_text:
        Optional textual summary displayed within the Summary tab.
    report_text:
        Optional textual report displayed within the Report tab.
    initial_direction:
        Initial :class:`PoolDirection` filter; defaults to :attr:`PoolDirection.ALL`.
    profile_payload:
        Optional Settings Profile payload (Option A schema). When supplied the dialog
        validates the payload and surfaces diagnostics.
    algorithms:
        Optional iterable listing supported perceptual hash algorithms. Defaults to
        ``("phash", "whash")``.
    parent:
        Optional Qt parent widget.

    Notes
    -----
    * Settings Profiles v1 operate in report-only mode. Deletion requests therefore
      show guidance rather than mutating the filesystem.
    * When a database manager is provided the **Compute Groups** button will query the
      cache database for perceptual hashes and recompute clusters with the selected
      algorithm and threshold.
    """

    _DEFAULT_ALGORITHMS: Tuple[str, str] = ("phash", "whash")
    _DEFAULT_THRESHOLDS: Mapping[str, int] = {
        "phash": 10,
        "whash": 12,
    }

    def __init__(
        self,
        *,
        groups: Optional[Iterable[Group]] = None,
        pool_map: Optional[Mapping[str, str]] = None,
        selection_store: Optional[SelectionStore] = None,
        db_manager: Optional[DatabaseManager] = None,
        summary_text: str = "",
        report_text: str = "",
        initial_direction: PoolDirection = PoolDirection.ALL,
        profile_payload: Optional[dict] = None,
        algorithms: Optional[Iterable[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        self._selection_store = selection_store or SelectionStore()
        self._model: FileGroupModel = FileGroupModel()
        self._pool_map: Dict[str, str] = dict(pool_map or {})
        self._group_lookup: Dict[str, Group] = {}
        self._profile_payload: Optional[dict] = None
        self._validator_errors: List[str] = []
        self._db_manager = db_manager
        self._algorithms = tuple(algorithms or self._DEFAULT_ALGORITHMS)

        super().__init__(
            groups=list(groups or []),
            selection_store=self._selection_store,
            parent=parent,
        )

        if summary_text:
            self.set_summary_text(summary_text)
        if report_text:
            self.set_report_text(report_text)

        self._model = FileGroupModel(
            groups=tuple(groups or []),
            pool_map=self._pool_map,
            direction=initial_direction,
        )
        self._update_model(self._model)
        self._apply_direction_to_combo(initial_direction)

        if profile_payload:
            self.apply_settings_profile(profile_payload)

    # ------------------------------------------------------------------#
    # UI construction hooks (override BaseFileManagerDialog)
    # ------------------------------------------------------------------#
    def _build_controls(self) -> QWidget:
        """Build similarity-specific controls including algorithm and threshold."""
        controls_widget = QWidget(self)
        # Ensure the controls row does not expand vertically
        controls_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QHBoxLayout(controls_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        mode_label = QLabel("Mode: Similarity (Perceptual)", controls_widget)
        mode_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(mode_label)

        layout.addSpacing(24)
        direction_label = QLabel("Direction:", controls_widget)
        direction_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(direction_label)

        self._direction_combo = QComboBox(controls_widget)
        for direction, label in DuplicateDirectionLabels.items():
            self._direction_combo.addItem(label, direction)
        self._direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        layout.addWidget(self._direction_combo)

        layout.addSpacing(12)
        algorithm_label = QLabel("Algorithm:", controls_widget)
        algorithm_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(algorithm_label)

        self._algorithm_combo = QComboBox(controls_widget)
        for algorithm in self._algorithms:
            self._algorithm_combo.addItem(algorithm.upper(), algorithm)
        self._algorithm_combo.currentIndexChanged.connect(self._on_algorithm_changed)
        layout.addWidget(self._algorithm_combo)

        layout.addSpacing(12)
        threshold_label = QLabel("Threshold:", controls_widget)
        threshold_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(threshold_label)

        self._threshold_spin = QSpinBox(controls_widget)
        self._threshold_spin.setRange(0, 64)
        default_threshold = self._DEFAULT_THRESHOLDS.get(self._algorithm_combo.currentData(), 10)
        self._threshold_spin.setValue(default_threshold)
        layout.addWidget(self._threshold_spin)

        self._compute_button = QPushButton("Compute Groups", controls_widget)
        self._compute_button.clicked.connect(self._on_compute_clicked)
        layout.addWidget(self._compute_button)

        self._clear_selection_button = QPushButton("Clear Selection", controls_widget)
        self._clear_selection_button.clicked.connect(self.selection_store.clear_selection)
        layout.addWidget(self._clear_selection_button)

        layout.addStretch(1)

        self._apply_direction_to_combo(PoolDirection.ALL)
        return controls_widget

    def _build_content_area(self, parent_layout: QVBoxLayout) -> None:
        """Create the dual-pane layout with group view and preview pane."""
        splitter = QSplitter(Qt.Horizontal, self)

        self._group_view = FileGroupView(
            selection_store=self.selection_store,
            display_mode="similarity",
            parent=self,
        )
        self._group_view.selection_changed.connect(self._on_group_view_selection_changed)
        self._group_view.tree_widget.itemSelectionChanged.connect(self._on_tree_selection_changed)
        splitter.addWidget(self._group_view)

        self._preview_pane = SimilarityPreviewPane(self.selection_store, parent=self)
        splitter.addWidget(self._preview_pane)
        splitter.setSizes([780, 420])

        parent_layout.addWidget(splitter)

    # ------------------------------------------------------------------#
    # Public API
    # ------------------------------------------------------------------#
    @property
    def file_group_model(self) -> FileGroupModel:
        """Return the immutable :class:`FileGroupModel` backing the dialog."""
        return self._model

    def apply_settings_profile(self, profile_payload: dict) -> None:
        """Validate and attach a Settings Profile Option A payload to the dialog."""
        self._profile_payload = profile_payload or {}
        is_valid, errors = validate_settings_schema(self._profile_payload)
        self._validator_errors = errors or []
        LOGGER.info(
            "Settings profile validation for SimilarityManagerDialog",
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
            return

        info_lines = [
            "Settings Profile Validation",
            "---------------------------",
            "Status: VALID",
        ]
        threshold = self._extract_similarity_threshold()
        if threshold is not None:
            info_lines.append(
                f"Normalized threshold: {threshold * 100:.1f}% (UI {internal_to_ui_percent(threshold)})."
            )
        show_selectable_info(self, "Profile Validation Successful", "\n".join(info_lines))

    def refresh_groups(
        self,
        groups: Sequence[Group],
        *,
        pool_map: Optional[Mapping[str, str]] = None,
        direction: Optional[PoolDirection] = None,
    ) -> None:
        """Replace rendered groups and optionally update pool mapping and direction."""
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

    # ------------------------------------------------------------------#
    # Base dialog overrides
    # ------------------------------------------------------------------#
    def _on_delete_clicked(self) -> None:
        """Handle delete requests in report-only mode."""
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
                "The selected files have been marked for review but were not deleted. "
                "Export the report or use future workflow stages to action deletions safely."
            ),
        )
        LOGGER.info(
            "SimilarityManagerDialog delete requested in report-only mode",
            variables={"selected_count": selected_count},
        )

    # ------------------------------------------------------------------#
    # Internal helpers
    # ------------------------------------------------------------------#
    def _on_direction_changed(self) -> None:
        direction = self._direction_combo.currentData()
        if isinstance(direction, PoolDirection):
            LOGGER.debug("Applying pool direction %s", direction)
            new_model = self._model.with_direction(direction)
            self._update_model(new_model)

    def _on_algorithm_changed(self) -> None:
        algorithm = self._algorithm_combo.currentData()
        default = self._DEFAULT_THRESHOLDS.get(str(algorithm), self._threshold_spin.value())
        self._threshold_spin.setValue(default)

    def _on_compute_clicked(self) -> None:
        """Compute similarity groups via database hashes."""
        if self._db_manager is None:
            show_selectable_error(
                self,
                "Database Unavailable",
                "A DatabaseManager instance is required to compute similarity groups.",
            )
            return

        algorithm = str(self._algorithm_combo.currentData() or "phash").lower()
        threshold = int(self._threshold_spin.value())
        LOGGER.info(
            "Computing similarity groups",
            extra={"algorithm": algorithm, "threshold": threshold},
        )
        try:
            groups, pool_map = self._compute_groups_from_database(algorithm, threshold)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Similarity grouping failed")
            show_selectable_error(
                self,
                "Computation Error",
                f"Failed to compute similarity groups:\n\n{exc}",
            )
            return

        if not groups:
            show_selectable_info(
                self,
                "No Similar Groups",
                "No similarity clusters were found with the current algorithm/threshold.",
            )
            return

        direction = self._direction_combo.currentData()
        if not isinstance(direction, PoolDirection):
            direction = PoolDirection.ALL
        self.refresh_groups(groups, pool_map=pool_map, direction=direction)
        self._select_first_group()

    def _compute_groups_from_database(
        self,
        algorithm: str,
        threshold: int,
    ) -> Tuple[List[Group], Dict[str, str]]:
        """Fetch perceptual hashes from the cache DB and compute clusters."""
        hashes: List[Dict[str, str]] = []
        pool_map: Dict[str, str] = {}

        with self._db_manager.get_connection(self._db_manager.cache_db) as conn:  # type: ignore[arg-type]
            rows = conn.execute(
                """
                SELECT im.file_path AS path,
                       ih.hash_value AS hash,
                       im.pool AS pool
                FROM image_hashes ih
                JOIN image_metadata im ON im.id = ih.image_id
                WHERE ih.algorithm = ?
                  AND ih.hash_value IS NOT NULL
                """,
                (algorithm,),
            ).fetchall()

        for row in rows:
            path = str(row["path"])
            hash_value = str(row["hash"])
            hashes.append({"path": path, "hash": hash_value})
            pool_label = str(row["pool"] or "A").upper()
            pool_map[path] = pool_label

        if not hashes:
            return [], pool_map

        sim_groups = find_similar_images(
            hashes=hashes,
            algorithm=algorithm,
            threshold=threshold,
            settings=self._profile_payload,
        )
        dialog_groups = self._convert_similarity_groups(sim_groups)
        return dialog_groups, pool_map

    def _convert_similarity_groups(
        self,
        similarity_groups: Iterable[CoreSimilarityGroup],
    ) -> List[Group]:
        """Convert core similarity groups into dialog-friendly immutable groups."""
        converted: List[Group] = []
        for index, sim_group in enumerate(similarity_groups, start=1):
            file_items: List[FileItem] = []
            for image in sim_group.images:
                metadata = self._safe_image_metadata(image.path, image.size, image.resolution, image.mod_date)
                file_type = Path(image.path).suffix.lstrip(".").upper() or ""
                file_items.append(
                    FileItem(
                        path=image.path,
                        size=metadata["size"],
                        resolution=metadata["resolution"],
                        mod_date=metadata["mod_date"],
                        score=image.score,
                        file_type=file_type,
                        savings=0,
                    )
                )

            if not file_items:
                continue

            stats = GroupStats(
                total_size=sum(item.size for item in file_items),
                savings=0,
                min_score=sim_group.stats.min_score,
                max_score=sim_group.stats.max_score,
                avg_score=sim_group.stats.avg_score,
                file_count=len(file_items),
            )
            converted.append(
                Group(
                    id=index,
                    items=file_items,
                    stats=stats,
                    ref_path=sim_group.ref_path,
                )
            )
        return converted

    def _safe_image_metadata(
        self,
        path: str,
        fallback_size: int,
        fallback_resolution: str,
        fallback_mod_date: str,
    ) -> Dict[str, any]:
        """Fetch metadata for preview purposes with fallbacks."""
        try:
            return get_image_metadata(path)
        except Exception:  # pylint: disable=broad-except
            return {
                "size": fallback_size,
                "resolution": fallback_resolution or "—",
                "mod_date": fallback_mod_date or "Unknown",
            }

    def _update_model(self, model: FileGroupModel) -> None:
        """Persist the model and refresh UI components."""
        self._model = model
        self._group_lookup = {group.ref_path: group for group in self._model.groups}
        self._group_view.update_model(model)
        self.update_groups(list(model.groups))
        self._select_first_group()

    def _select_first_group(self) -> None:
        """Highlight the first group row to populate the preview pane."""
        tree = self._group_view.tree_widget
        if tree.topLevelItemCount() == 0:
            self._preview_pane.clear()
            return
        tree.blockSignals(True)
        tree.clearSelection()
        first_item = tree.topLevelItem(0)
        tree.setCurrentItem(first_item)
        first_item.setSelected(True)
        tree.blockSignals(False)
        self._update_preview_for_item(first_item)

    def _on_tree_selection_changed(self) -> None:
        """Update preview when the group tree selection changes."""
        tree = self._group_view.tree_widget
        current = tree.currentItem()
        if current is None:
            self._preview_pane.clear()
            return
        self._update_preview_for_item(current)

    def _update_preview_for_item(self, item) -> None:
        """Populate the preview pane based on the selected tree item."""
        if item is None:
            self._preview_pane.clear()
            return

        group_item = item if item.parent() is None else item.parent()
        ref_path = group_item.data(0, Qt.UserRole)
        group = self._group_lookup.get(ref_path)
        if not group:
            self._preview_pane.clear()
            return
        self._preview_pane.update_preview(group.items)

    def _on_group_view_selection_changed(self, selection: set) -> None:
        """Log selection changes relayed from the FileGroupView."""
        LOGGER.debug(
            "Selection updated in SimilarityManagerDialog",
            extra={"selection_count": len(selection)},
        )

    def _apply_direction_to_combo(self, direction: PoolDirection) -> None:
        """Synchronize the direction combo box with the provided direction."""
        for index in range(self._direction_combo.count()):
            if self._direction_combo.itemData(index) == direction:
                self._direction_combo.blockSignals(True)
                self._direction_combo.setCurrentIndex(index)
                self._direction_combo.blockSignals(False)
                return

    def _extract_similarity_threshold(self) -> Optional[float]:
        """Best-effort extraction of normalized threshold from the profile payload."""
        try:
            criteria = (self._profile_payload or {}).get("criteria") or {}
            threshold = criteria.get("degree_normalized")
            if threshold is None:
                degree_ui = criteria.get("degree_ui")
                if degree_ui is not None:
                    threshold = float(degree_ui) / 100.0
            return float(threshold) if threshold is not None else None
        except Exception:  # pylint: disable=broad-except
            return None


# Mapping used for direction combo labels (shared between duplicates/similarity)
DuplicateDirectionLabels: Mapping[PoolDirection, str] = {
    PoolDirection.ALL: "All Pools",
    PoolDirection.A_TO_B: "Pool A → Pool B",
    PoolDirection.B_TO_A: "Pool B → Pool A",
    PoolDirection.A_WITHOUT_IN_B: "Pool A without matches in Pool B",
    PoolDirection.B_WITHOUT_IN_A: "Pool B without matches in Pool A",
}

__all__ = ["SimilarityManagerDialog"]