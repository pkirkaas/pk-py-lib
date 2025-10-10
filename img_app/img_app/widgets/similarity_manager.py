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
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Callable

from PySide6.QtCore import Qt, QUrl
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
from src.pk_py_lib.core.image import get_active_image_quality_evaluator
from src.pk_py_lib.core.image.quality.registry import ImageQualityEvaluatorRegistry
from src.pk_py_lib.core.image.similarity import (
    find_similar_images,
    get_image_metadata,
)
from src.pk_py_lib.core.image.similarity.phases import PhaseContext, execute_all_phases
from src.pk_py_lib.core.settings_profiles import get_active_profile_settings
from src.pk_py_lib.core.settings_schema import validate_settings_schema
from src.pk_py_lib.core.utils.thresholds import internal_to_ui_percent
from src.pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats
from src.pk_py_lib.gui.dialogs.base_file_manager_dialog import BaseFileManagerDialog
from src.pk_py_lib.gui.dialogs.progress_dialog import ProgressDialog
from src.pk_py_lib.gui.models import FileGroupModel, PoolDirection, SelectionStore
from src.pk_py_lib.gui.utils.messages import show_selectable_error, show_selectable_info
from src.pk_py_lib.gui.widgets import FileGroupView, SimilarityPreviewPane
from src.pk_py_lib.core.logging import get_logger
from src.pk_py_lib.core.logging.decorators import log_errors, log_warnings
import sqlite3

import platform
import os
import subprocess
import sys
import traceback
import inspect
from PySide6.QtWidgets import QMenu, QApplication, QMessageBox
from PySide6.QtGui import QDesktopServices
from pathlib import Path
from src.pk_py_lib.core.filesystem.operations import FileOperations


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
    * Deletion requests invoke the base dialog's safe deletion workflow, moving
      selected files to the platform recycle bin so the operation remains reversible.
    * When a database manager is provided the **Compute Groups** button will query the
      cache database for perceptual hashes and recompute clusters with the selected
      algorithm and threshold.
    * The Quality column shows normalized score (0-1 range, e.g., 0.745) if BRISQUE selected; '-' otherwise.
      Scores are computed on-the-fly using the active evaluator from settings profiles.
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
        flat_cache_manager=None,
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
        self._flat_cache_manager = flat_cache_manager
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

        # Retrieve algorithm from profile or active settings for reporting
        if self._profile_payload:
            settings = self._profile_payload
        else:
            try:
                settings = get_active_profile_settings()
            except Exception:
                settings = {}

        algorithm = settings.get('criteria', {}).get('similarity_hash_algorithm', 'phash')
        algorithm_display = algorithm.upper()
        algorithm_info = f"Hash Algorithm Used: {algorithm_display}"

        # Append to or set summary text
        if summary_text:
            updated_summary = f"{summary_text}\n\n{algorithm_info}"
            self.set_summary_text(updated_summary)
        else:
            self.set_summary_text(algorithm_info)

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

        layout.addSpacing(12)
        quality_label = QLabel("Image Quality Evaluator:", controls_widget)
        quality_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(quality_label)

        self._quality_combo = QComboBox(controls_widget)
        self._quality_combo.addItem("None", "none")
        self._quality_combo.addItem("BRISQUE", "brisque")
        # NIQE and PIQE implementations are currently disabled and removed from GUI options.
        self._quality_combo.currentTextChanged.connect(self._on_quality_changed)
        layout.addWidget(self._quality_combo)

        self._compute_button = QPushButton("Compute Groups", controls_widget)
        self._compute_button.clicked.connect(self._on_compute_clicked)
        layout.addWidget(self._compute_button)

        self._clear_selection_button = QPushButton("Clear Selection", controls_widget)
        self._clear_selection_button.clicked.connect(self.selection_store.clear_selection)
        layout.addWidget(self._clear_selection_button)

        layout.addStretch(1)

        # Add cache statistics label
        self._cache_stats_label = QLabel("Cache: Not initialized", controls_widget)
        self._cache_stats_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._cache_stats_label.setStyleSheet("QLabel { color: #666; font-style: italic; }")
        layout.addWidget(self._cache_stats_label)

        self._apply_direction_to_combo(PoolDirection.ALL)

        # Load initial quality evaluator selection

        # Map registered keys to their display names (e.g., 'brisque' -> 'BRISQUE')
        key_to_display = {k: k.upper() for k in ImageQualityEvaluatorRegistry.get_registered_keys()}
        key_to_display["none"] = "None"

        try:
            settings = get_active_profile_settings()
            # Default to 'brisque' if setting is missing or settings is not a dict
            key = settings.get("image_quality_evaluator", "brisque") if isinstance(settings, dict) else "brisque"

            # Map the key from settings to the display text, defaulting to 'None' if key is unknown
            text = key_to_display.get(key, "None")

            self._quality_combo.setCurrentText(text)
        except Exception:
            # Fallback to default display text
            self._quality_combo.setCurrentText("BRISQUE")

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
        self._group_view.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._group_view.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._group_view.tree_widget.customContextMenuRequested.connect(self._show_context_menu)
        splitter.addWidget(self._group_view)

        self._preview_pane = SimilarityPreviewPane(self.selection_store, parent=self)
        splitter.addWidget(self._preview_pane)
        splitter.setSizes([780, 420])
        parent_layout.addWidget(splitter)

    @log_errors()
    def _on_item_double_clicked(self, item, column):
        """
        Private handler for double-click events on tree items.

        Parameters
        ----------
        item : QTreeWidgetItem
            The item that was double-clicked.
        column : int
            The column index of the double-click event.

        Notes
        -----
        This method opens the file associated with the item using the default OS application
        handler via QDesktopServices. Only child items (files) are processed; group headers
        are ignored. Success or failure is logged appropriately. Invalid or missing paths
        are handled gracefully without crashing the dialog. The operation uses the system's
        default handler for the file type, supporting images and other files cross-platform
        (primarily Windows 11, but works on Linux/Mac via Qt).
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        if item.parent() is None:
            # Ignore double-clicks on group headers
            return

        path_str = item.data(0, Qt.UserRole)
        if not path_str:
            LOGGER.warning("Double-clicked item has no associated file path")
            return

        url = QUrl.fromLocalFile(str(path_str))
        success = QDesktopServices.openUrl(url)
        if success:
            LOGGER.info(f"Successfully opened file via default handler: {path_str}")
        else:
            LOGGER.warning(f"Failed to open file with default handler: {path_str}")


    # ------------------------------------------------------------------#
    # Public API
    # ------------------------------------------------------------------#
    @property
    def file_group_model(self) -> FileGroupModel:
        """Return the immutable :class:`FileGroupModel` backing the dialog."""
        return self._model

    @log_errors()
    def apply_settings_profile(self, profile_payload: dict) -> None:
        """Validate and attach a Settings Profile Option A payload to the dialog.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        self._profile_payload = profile_payload or {}
        is_valid, errors = validate_settings_schema(self._profile_payload)
        self._validator_errors = errors or []
        LOGGER.debug(
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

        # Success message box removed per user request. Validation status is logged.
        pass

    @log_errors()
    def refresh_groups(
        self,
        groups: Sequence[Group],
        *,
        pool_map: Optional[Mapping[str, str]] = None,
        direction: Optional[PoolDirection] = None,
    ) -> None:
        """Replace rendered groups and optionally update pool mapping and direction.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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
        """Handle delete requests via the shared safe deletion workflow."""
        selected_count = self.selection_store.get_selection_count()
        if selected_count == 0:
            show_selectable_info(
                self,
                "No Selection",
                "Please select one or more files to delete.",
            )
            return

        LOGGER.info(
            "SimilarityManagerDialog deletion requested",
            variables={"selected_count": selected_count},
        )
        super()._on_delete_clicked()

    @log_errors()
    def _get_export_parameters(self) -> Optional[Dict[str, Any]]:
        """
        Get export parameters specific to similarity dialog.

        Returns:
            Dictionary containing dialog_type, algorithm, threshold, profile_name,
            and search_paths for the export service.
        """
        try:
            # Task 3: Get algorithm from combo box for export with logging
            algorithm = str(self._algorithm_combo.currentData() or "phash").lower()
            LOGGER.info(f"Exporting results with algorithm: {algorithm}")

            # Get threshold from spin box
            threshold = int(self._threshold_spin.value())

            # Get profile name from settings
            profile_name = "default"
            if self._profile_payload:
                profile_name = self._profile_payload.get("name", "default")
            else:
                try:
                    from src.pk_py_lib.core.settings_profiles import get_active_profile_settings
                    settings = get_active_profile_settings()
                    profile_name = settings.get("name", "default") if isinstance(settings, dict) else "default"
                except Exception:
                    profile_name = "default"

            # Get search paths from profile or use empty list
            search_paths = []
            if self._profile_payload and "pools" in self._profile_payload:
                pools = self._profile_payload["pools"]
                for pool_name in ["A", "B"]:
                    if pool_name in pools:
                        search_paths.extend(pools[pool_name].get("paths", []))

            return {
                "dialog_type": "similarity",
                "groups": self.dialog_state.groups,
                "profile_name": profile_name,
                "algorithm": algorithm,
                "threshold": threshold,
                "search_paths": search_paths
            }

        except Exception as e:
            LOGGER.error(f"Failed to get export parameters: {e}", exception=e)
            return None

    # ------------------------------------------------------------------#
    # Internal helpers
    # ------------------------------------------------------------------#
    @log_errors()
    def _on_direction_changed(self) -> None:
        """Update model direction when the combo box selection changes.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        direction = self._direction_combo.currentData()
        if isinstance(direction, PoolDirection):
            LOGGER.debug("Applying pool direction %s", direction)
            new_model = self._model.with_direction(direction)
            self._update_model(new_model)

    @log_errors()
    def _on_algorithm_changed(self, index: int) -> None:
        """Update the threshold spin box when the algorithm selection changes.

        Parameters
        ----------
        index : int
            Index emitted by :class:`QComboBox.currentIndexChanged`, identifying the newly
            selected algorithm entry. The handler falls back to the combo box's current
            selection if the index is out of range or does not resolve to data.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        algorithm_data = None
        if 0 <= index < self._algorithm_combo.count():
            algorithm_data = self._algorithm_combo.itemData(index)
        if algorithm_data is None:
            algorithm_data = self._algorithm_combo.currentData()
        algorithm_key = str(algorithm_data or "phash").lower()
        default = self._DEFAULT_THRESHOLDS.get(algorithm_key, self._threshold_spin.value())
        self._threshold_spin.setValue(default)

    @log_errors()
    def _on_quality_changed(self, text: str) -> None:
        """Handle image quality evaluator selection change.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        from src.pk_py_lib.core.image.quality.provider import set_active_evaluator
        key = str(self._quality_combo.currentData())
        try:
            set_active_evaluator(key)
            LOGGER.debug(f"Set image quality evaluator to '{key}'")
            self._refresh_quality_scores()
        except Exception as e:
            LOGGER.error(f"Failed to set image quality evaluator '{key}': {e}")
            # Revert to previous selection on error
            current_index = self._quality_combo.currentIndex()
            self._quality_combo.blockSignals(True)
            self._quality_combo.setCurrentIndex(current_index)
            self._quality_combo.blockSignals(False)


    @log_errors()
    def _get_pool_for_path(self, path: str, profile: Optional[dict]) -> str:
        """
        Determine the pool (A or B) for a given file path based on profile pool configurations.

        Args:
            path: Absolute file path.
            profile: Settings profile payload with "pools" configuration.

        Returns:
            Pool label ("A" or "B"), defaults to "A" if undetermined.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        if not profile or "pools" not in profile:
            return "A"

        pools = profile["pools"]
        path_obj = Path(path)

        # Check Pool A paths
        if "A" in pools:
            a_paths = pools["A"].get("paths", [])
            for p in a_paths:
                pool_path = Path(p)
                try:
                    if path_obj.is_relative_to(pool_path):
                        return "A"
                except (ValueError, OSError) as e:
                    LOGGER.warning(f"Path relative check failed for {p}: {e}")
                    # Not relative, continue
                    pass

        # Check Pool B paths
        if "B" in pools:
            b_paths = pools["B"].get("paths", [])
            for p in b_paths:
                pool_path = Path(p)
                try:
                    if path_obj.is_relative_to(pool_path):
                        return "B"
                except (ValueError, OSError) as e:
                    LOGGER.warning(f"Path relative check failed for {p}: {e}")
                    # Not relative, continue
                    pass

        # Default to A if no match
        return "A"

    @log_errors()
    def _compute_groups_from_database(
        self,
        algorithm: str,
        threshold: int,
    ) -> Tuple[List[Group], Dict[str, str], int]:
        """Fetch perceptual hashes from the cache DB and compute clusters.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        hashes: List[Dict[str, str]] = []
        pool_map: Dict[str, str] = {}

        # Use FlatCacheManager to get hashes instead of old cache.db
        if not hasattr(self, '_flat_cache_manager'):
            show_selectable_error(
                self,
                "Cache Unavailable",
                "FlatCacheManager instance is required to compute similarity groups.",
            )
            return [], {}, 0

        # Reset counters before processing
        self._flat_cache_manager.reset_counters()

        try:
            # For similarity, compute all perceptual hashes + xxh3
            all_types = ['phash', 'whash', 'xxh3']

            # Get paths from profile payload to pass to get_entries()
            search_paths = []
            if self._profile_payload and "pools" in self._profile_payload:
                pools = self._profile_payload["pools"]
                for pool_name in ["A", "B"]:
                    if pool_name in pools:
                        search_paths.extend(pools[pool_name].get("paths", []))

            # Get entries for the search paths, fallback to empty list if no paths
            entries = self._flat_cache_manager.get_entries(search_paths or [])

            # Task 1: Add comprehensive debug logging for hash retrieval
            LOGGER.info(f"Requesting hashes: algorithm={algorithm}, types={all_types}")
            hashes_dict = self._flat_cache_manager.get_hashes(list(entries.keys()), all_types, search_type='similarity')
            LOGGER.info(f"Received {len(hashes_dict)} hash dictionaries from cache")

            # Log first 3 entries for debugging
            for path, hashes_entry in list(hashes_dict.items())[:3]:
                LOGGER.info(f"  Cache entry: {path}")
                LOGGER.info(f"    Available algorithms: {list(hashes_entry.keys())}")
                for alg, hash_val in hashes_entry.items():
                    LOGGER.info(f"    {alg}: {hash_val[:16] if hash_val else None}...")
        except Exception as e:
            LOGGER.error(f"Failed to get hashes from flat cache: {e}", exception=e)
            return [], {}, 0

        # Task 2: Add hash validation
        for path, path_hashes in hashes_dict.items():
            # Validate that requested algorithm exists in cache
            if algorithm not in path_hashes:
                LOGGER.warning(
                    f"Requested algorithm '{algorithm}' not in cache for {path}. "
                    f"Available: {list(path_hashes.keys())}"
                )
                continue

            hash_value = path_hashes.get(algorithm)

            # DEBUG: Detect if whash accidentally equals phash (should never happen)
            if algorithm == 'whash' and 'phash' in path_hashes and hash_value:
                if hash_value == path_hashes['phash']:
                    LOGGER.error(
                        f"BUG DETECTED: whash value equals phash value for {path}! "
                        f"This indicates hashes are not being computed correctly."
                    )

            if hash_value:
                hashes.append({"path": path, "hash": hash_value})
                LOGGER.debug(f"Added {algorithm} hash for {Path(path).name}")
                # Compute pool based on profile paths
                pool = self._get_pool_for_path(path, self._profile_payload)
                pool_map[path] = pool

        # Print cache summary after processing
        cache_hits, cache_misses, invalid_entries = self._flat_cache_manager.get_counters()
        total_files = len(hashes_dict)
        print(f"Cache Summary:\n - Hits: {cache_hits}\n - Misses: {cache_misses}\n - Invalid Entries: {invalid_entries}\nTotal Files Processed: {total_files}")
        self._flat_cache_manager.reset_counters()

        if not hashes:
            return [], pool_map, total_files

        try:
            # Extract just the paths from the hashes we already fetched
            paths = [h['path'] for h in hashes]

            # Ensure settings include the correct algorithm selection
            settings = self._profile_payload or {}
            if 'criteria' not in settings:
                settings['criteria'] = {}
            settings['criteria']['similarity_hash_algorithm'] = algorithm

            # Task 1: Log final call to find_similar_images with ApiResponse
            LOGGER.info(f"Calling find_similar_images with algorithm={algorithm}, threshold={threshold}, {len(paths)} paths")
            response = find_similar_images(
                paths=paths,  # ✅ Correct: Pass file paths as expected
                algorithm=algorithm,
                threshold=threshold,
                settings=settings,
                flat_cache_manager=self._flat_cache_manager,  # ✅ Ensure cache is used
                search_type='similarity',
                return_response=True  # ✅ Use new ApiResponse format
            )

            # Handle ApiResponse
            if not response.success:
                LOGGER.error(f"Similarity detection failed: {response.error.message if response.error else 'Unknown error'}")
                if response.error:
                    LOGGER.error(f"Error code: {response.error.code}, details: {response.error.details}")
                return [], pool_map, total_files

            # Extract similarity groups from response data
            sim_groups = response.data.get('similarity_groups', [])
            duplicate_groups = response.data.get('duplicate_groups', [])

            # Log warnings if any
            if response.warnings:
                for warning in response.warnings:
                    LOGGER.warning(f"Similarity detection warning: {warning}")

            # Log metadata
            metadata = response.metadata
            LOGGER.info(f"Similarity detection completed: {len(sim_groups)} groups, "
                       f"algorithm={metadata.get('algorithm', algorithm)}, "
                       f"threshold={metadata.get('threshold', threshold)}")

            LOGGER.info(f"Returned {len(sim_groups)} similarity groups")
        except (ValueError, KeyError, TypeError) as e:
            LOGGER.error(f"Similarity calculation error: {e}", exception=e)
            return [], pool_map, total_files
        except Exception as e:
            LOGGER.error(f"Unexpected error in find_similar_images: {e}", exception=e)
            return [], pool_map, total_files

        dialog_groups = self._convert_similarity_groups(sim_groups)
        return dialog_groups, pool_map, total_files

    @log_errors()
    def _compute_groups_from_database_with_progress(
        self,
        algorithm: str,
        threshold: int,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_flag: Optional[List[bool]] = None,
    ) -> Tuple[List[Group], Dict[str, str], int]:
        """Compute similarity groups using PhaseContext with enhanced progress reporting.

        Args:
            algorithm: Hash algorithm to use ('phash' or 'whash')
            threshold: Similarity threshold for clustering
            progress_callback: Optional callback function for progress updates
            cancellation_flag: Optional list for cancellation support

        Returns:
            Tuple of (groups, pool_map, total_files)
        """
        hashes: List[Dict[str, str]] = []
        pool_map: Dict[str, str] = {}

        # Use FlatCacheManager to get hashes instead of old cache.db
        if not hasattr(self, '_flat_cache_manager'):
            show_selectable_error(
                self,
                "Cache Unavailable",
                "FlatCacheManager instance is required to compute similarity groups.",
            )
            return [], {}, 0

        # Reset counters before processing
        self._flat_cache_manager.reset_counters()

        try:
            # For similarity, compute all perceptual hashes + xxh3
            all_types = ['phash', 'whash', 'xxh3']

            # Get paths from profile payload to pass to get_entries()
            search_paths = []
            if self._profile_payload and "pools" in self._profile_payload:
                pools = self._profile_payload["pools"]
                for pool_name in ["A", "B"]:
                    if pool_name in pools:
                        search_paths.extend(pools[pool_name].get("paths", []))

            # Get entries for the search paths, fallback to empty list if no paths
            entries = self._flat_cache_manager.get_entries(search_paths or [])

            # Get all required hashes from cache
            hashes_dict = self._flat_cache_manager.get_hashes(list(entries.keys()), all_types, search_type='similarity')

            # Extract paths for PhaseContext processing
            paths = [path for path in entries.keys() if self._is_path_valid_for_similarity(path, hashes_dict)]

        except Exception as e:
            LOGGER.error(f"Failed to get hashes from flat cache: {e}", exception=e)
            return [], {}, 0

        if not paths:
            LOGGER.info("No valid paths found for similarity computation")
            return [], {}, 0

        try:
            # Create PhaseContext with progress support
            context = PhaseContext(
                image_paths=paths,
                algorithm=algorithm,
                threshold=threshold,
                settings=self._profile_payload or {},
                flat_cache_manager=self._flat_cache_manager,
                search_type='similarity',
                max_workers=4,
                progress_callback=progress_callback,
                cancellation_flag=cancellation_flag,
                total_files=len(paths)
            )

            # Execute all phases with progress reporting
            final_context = execute_all_phases(context)

            # Check if operation was cancelled
            if cancellation_flag and cancellation_flag[0]:
                LOGGER.info("Similarity computation was cancelled")
                return [], {}, len(paths)

            # Convert core similarity groups to dialog groups
            dialog_groups = self._convert_similarity_groups(final_context.final_groups)

            # Build pool mapping for the valid paths
            for path in paths:
                pool = self._get_pool_for_path(path, self._profile_payload)
                pool_map[path] = pool

            total_files = len(paths)

            # Print cache summary after processing
            cache_hits, cache_misses, invalid_entries = self._flat_cache_manager.get_counters()
            print(f"Cache Summary:\n - Hits: {cache_hits}\n - Misses: {cache_misses}\n - Invalid Entries: {invalid_entries}\nTotal Files Processed: {total_files}")
            self._flat_cache_manager.reset_counters()

            LOGGER.info(f"PhaseContext similarity computation completed: {len(dialog_groups)} groups from {len(paths)} paths")
            return dialog_groups, pool_map, total_files

        except Exception as e:
            LOGGER.error(f"PhaseContext similarity computation failed: {e}", exception=e)
            return [], {}, len(paths)

    @log_errors()
    def _is_path_valid_for_similarity(self, path: str, hashes_dict: Dict[str, Dict[str, str]]) -> bool:
        """Check if a path has valid data for similarity computation.

        Args:
            path: File path to validate
            hashes_dict: Dictionary of path -> algorithm -> hash mappings

        Returns:
            True if path has required data, False otherwise
        """
        if path not in hashes_dict:
            return False

        path_hashes = hashes_dict[path]

        # For similarity, we need either phash or whash depending on algorithm
        # Also need xxh3 for exact duplicate detection
        algorithm = self._algorithm_combo.currentData() or "phash"
        algorithm = str(algorithm).lower()

        required_algorithms = ['xxh3']  # Always need for exact duplicate detection

        if algorithm in ['phash', 'whash']:
            required_algorithms.append(algorithm)

        for alg in required_algorithms:
            if alg not in path_hashes or not path_hashes[alg]:
                LOGGER.debug(f"Path {path} missing required {alg} hash")
                return False

        return True

    @log_errors()
    def _convert_similarity_groups(
        self,
        similarity_groups: Iterable[CoreSimilarityGroup],
    ) -> List[Group]:
        """Convert core similarity groups into dialog-friendly immutable groups.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        converted: List[Group] = []

        # Determine the active quality evaluator for FileItem creation (Algorithm column removed, but keep for potential future use)
        try:
            evaluator = get_active_image_quality_evaluator()
            quality_algorithm = evaluator.name if evaluator else None
        except Exception as e:
            LOGGER.warning(f"Failed to get active evaluator: {e}")
            quality_algorithm = None

        for index, sim_group in enumerate(similarity_groups, start=1):
            file_items: List[FileItem] = []
            for image in sim_group.images:
                metadata = self._safe_image_metadata(image.path, image.size, image.resolution, image.mod_date)
                file_type = Path(image.path).suffix.lstrip(".").upper() or ""

                # Note: quality_score is computed later in _refresh_quality_scores with normalized 0-1 values
                file_items.append(
                    FileItem(
                        path=image.path,
                        size=metadata["size"],
                        resolution=metadata["resolution"],
                        mod_date=metadata["mod_date"],
                        score=image.score,
                        file_type=file_type,
                        savings=0,
                        quality_algorithm=quality_algorithm,  # Retained for potential future use, though not displayed
                        exact_set_id=image.exact_set_id,
                    )
                )

            if not file_items:
                continue

            try:
                stats = GroupStats(
                    total_size=sum(item.size for item in file_items),
                    savings=0,
                    min_score=sim_group.stats.min_score,
                    max_score=sim_group.stats.max_score,
                    avg_score=sim_group.stats.avg_score,
                    file_count=len(file_items),
                )
            except (AttributeError, TypeError) as e:
                LOGGER.warning(f"Failed to compute group stats: {e}")
                continue

            converted.append(
                Group(
                    id=index,
                    items=file_items,
                    stats=stats,
                    ref_path=sim_group.ref_path,
                )
            )
        return converted

    @log_errors()
    def _safe_image_metadata(
        self,
        path: str,
        fallback_size: int,
        fallback_resolution: str,
        fallback_mod_date: str,
    ) -> Dict[str, any]:
        """Fetch metadata for preview purposes with fallbacks.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            return get_image_metadata(path)
        except Exception as e:  # pylint: disable=broad-except
            LOGGER.warning(f"Failed to get image metadata for {path}: {e}")
            return {
                "size": fallback_size,
                "resolution": fallback_resolution or "—",
                "mod_date": fallback_mod_date or "Unknown",
            }

    @log_errors()
    def _update_model(self, model: FileGroupModel) -> None:
        """Persist the model and refresh UI components.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        self._model = model
        self._group_lookup = {group.ref_path: group for group in self._model.groups}
        self._group_view.update_model(model)
        self.update_groups(list(model.groups))
        # Commented out to prevent automatic preview display on initialization
        # self._select_first_group()

    @log_errors()
    def _select_first_group(self) -> None:
        """Highlight the first group row to populate the preview pane.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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

    @log_errors()
    def _on_tree_selection_changed(self) -> None:
        """Update preview when the group tree selection changes.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        tree = self._group_view.tree_widget
        current = tree.currentItem()
        if current is None:
            self._preview_pane.clear()
            return
        self._update_preview_for_item(current)

    @log_errors()
    def _update_preview_for_item(self, item) -> None:
        """Populate the preview pane based on the selected tree item.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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

    @log_errors()
    def _on_group_view_selection_changed(self, selection: set) -> None:
        """Log selection changes relayed from the FileGroupView.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        LOGGER.debug(
            "Selection updated in SimilarityManagerDialog",
            extra={"selection_count": len(selection)},
        )

    @log_errors()
    def _apply_direction_to_combo(self, direction: PoolDirection) -> None:
        """Synchronize the direction combo box with the provided direction.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        for index in range(self._direction_combo.count()):
            if self._direction_combo.itemData(index) == direction:
                self._direction_combo.blockSignals(True)
                self._direction_combo.setCurrentIndex(index)
                self._direction_combo.blockSignals(False)
                return

    @log_errors()
    def _extract_similarity_threshold(self) -> Optional[float]:
        """Best-effort extraction of normalized threshold from the profile payload.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            criteria = (self._profile_payload or {}).get("criteria") or {}
            threshold = criteria.get("degree_normalized")
            if threshold is None:
                degree_ui = criteria.get("degree_ui")
                if degree_ui is not None:
                    threshold = float(degree_ui) / 100.0
            return float(threshold) if threshold is not None else None
        except (ValueError, KeyError, TypeError) as e:
            LOGGER.warning(f"Failed to extract similarity threshold: {e}")
            return None


    @log_errors()
    def _refresh_quality_scores(self) -> None:
        """
        Refresh the normalized quality scores (0-1 range) in the table based on the current evaluator.

        Iterates over all visible tree items, recomputes quality scores using the active
        evaluator, updates the underlying FileItem data, and refreshes the table display
        for column 7 (Quality). The Algorithm column has been removed; quality scores are
        now displayed with 3 decimal places (e.g., 0.745) for the normalized 0-1 range.

        Raises:
            No explicit raises; errors are logged and cells set to "-".

        Notes:
            This method updates both the visual representation (QTreeWidgetItem) and the
            underlying data (FileItem stored in UserRole + 1) to ensure consistency
            for components like the preview pane. BRISQUE scores are assumed to be pre-normalized
            to 0-1 by the evaluator.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        if not self._model.groups:
            return

        tree = self._group_view.tree_widget
        try:
            evaluator = get_active_image_quality_evaluator()
        except Exception as e:
            LOGGER.warning(f"Failed to get evaluator: {e}")
            evaluator = None

        for i in range(tree.topLevelItemCount()):
            group_item = tree.topLevelItem(i)
            # Set group quality placeholder (Algorithm column removed)
            group_item.setText(7, "—")
            group_item.setText(8, "—")  # Exact placeholder for group

            for j in range(group_item.childCount()):
                child = group_item.child(j)
                path = child.data(0, Qt.UserRole)
                file_item: Optional[FileItem] = child.data(0, Qt.UserRole + 1)

                if not isinstance(path, str) or file_item is None:
                    continue

                score = None
                score_display = "—"

                if evaluator is None:
                    # If no evaluator, keep score as None (no algorithm display needed)
                    new_file_item = replace(file_item, quality_score=None)
                else:
                    try:
                        score = evaluator.evaluate(path)
                        score_display = f"{score:.3f}"  # 0-1 normalized with 3 decimal places
                        LOGGER.info(f"Normalized quality score {score} for {path} using {evaluator.name}")
                        new_file_item = replace(file_item, quality_score=score)
                    except Exception as e:
                        LOGGER.warning(f"Failed to compute quality for {path} using {evaluator.name}: {e}")
                        # If computation fails, set score to None
                        new_file_item = replace(file_item, quality_score=None)

                # Update the underlying data model item stored in the tree widget
                child.setData(0, Qt.UserRole + 1, new_file_item)

                # Update the visual representation (only Quality column)
                child.setText(7, score_display)

                # Update Exact column (unchanged, but ensure consistency)
                exact_text = str(new_file_item.exact_set_id) if new_file_item.exact_set_id is not None else ""
                child.setText(8, exact_text)


    @log_errors()
    def _open_file(self, path: Path) -> None:
        """
        Open the file using the default OS application handler, reusing the double-click logic.

        Parameters
        ----------
        path : Path
            The absolute file path to open.

        Notes
        -----
        Checks if the file exists before attempting to open; logs a warning if it does not.
        Uses QDesktopServices for cross-platform compatibility, primarily tested on Windows 11.
        Logs success or failure for debugging and user feedback.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        if not os.path.exists(path):
            LOGGER.warning(f"Cannot open file - does not exist: {path}")
            return

        url = QUrl.fromLocalFile(str(path))
        success = QDesktopServices.openUrl(url)
        if success:
            LOGGER.info(f"Successfully opened file via default handler: {path}")
        else:
            LOGGER.warning(f"Failed to open file with default handler: {path}")


    @log_errors()
    def _copy_path_to_clipboard(self, path: Path) -> None:
        """
        Copy the absolute file path to the system clipboard.

        Parameters
        ----------
        path : Path
            The absolute file path to copy as a string.

        Notes
        -----
        Always succeeds as it copies the path string regardless of file existence.
        Logs the action for auditing.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            QApplication.clipboard().setText(str(path))
            LOGGER.info(f"Copied path to clipboard: {path}")
        except Exception as e:
            LOGGER.error(f"Failed to copy path to clipboard: {e}", exception=e)
            show_selectable_error(self, "Clipboard Error", "Failed to copy path to clipboard.")


    @log_errors()
    def _open_containing_folder(self, path: Path) -> None:
        """
        Open the containing folder in Windows Explorer, selecting the specific file.

        Parameters
        ----------
        path : Path
            The absolute file path; the parent directory will be opened with the file selected.

        Notes
        -----
        Windows-specific using 'explorer /select,' command.
        If the file does not exist, logs a warning and falls back to opening the parent folder.
        Handles subprocess errors with logging; captures output to avoid console spam.
        Permissions issues are handled by the OS (e.g., access denied).
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        if not os.path.exists(path):
            LOGGER.warning(f"Cannot select file in explorer - does not exist: {path}")
            self._open_folder(path)
            return

        try:
            subprocess.run(['explorer', '/select,', str(path)], check=True, capture_output=True)
            LOGGER.info(f"Opened containing folder selecting file: {path}")
        except (subprocess.CalledProcessError, OSError, FileNotFoundError) as e:
            LOGGER.warning(f"Failed to open containing folder: {e}")
            self._open_folder(path)
        except Exception as e:
            LOGGER.warning(f"Unexpected error opening containing folder: {e}")
            self._open_folder(path)


    @log_errors()
    def _show_properties(self, path: Path) -> None:
        """
        Open the Windows file properties dialog for the specified file.

        Parameters
        ----------
        path : Path
            The absolute file path for which to show properties.

        Notes
        -----
        Windows-specific using rundll32 shell32.dll,Control_RunDLL.
        If the file does not exist or access is denied, the subprocess will fail, and an error is logged.
        No fallback; lets the OS handle invalid cases.
        Shell=True is used for compatibility with the rundll32 command.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            subprocess.run(['rundll32.exe', 'shell32.dll,Control_RunDLL', f'"{path}"'], shell=True, check=True, capture_output=True)
            LOGGER.info(f"Opened properties dialog for: {path}")
        except (subprocess.CalledProcessError, OSError, FileNotFoundError) as e:
            LOGGER.warning(f"Failed to open properties dialog: {e}")
        except Exception as e:
            LOGGER.warning(f"Unexpected error opening properties: {e}")


    @log_errors()
    def _open_folder(self, path: Path) -> None:
        """
        Open the parent folder using a cross-platform method (fallback for non-Windows).

        Parameters
        ----------
        path : Path
            The file path; opens the parent directory.

        Notes
        -----
        Uses QDesktopServices to open the parent directory, compatible with Windows, macOS, and Linux.
        Does not check file existence as the goal is to open the directory.
        Logs success or failure.
        Serves as fallback for Windows-specific actions when they fail.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        parent_path = path.parent
        url = QUrl.fromLocalFile(str(parent_path))
        success = QDesktopServices.openUrl(url)
        if success:
            LOGGER.info(f"Opened parent folder: {parent_path}")
        else:
            LOGGER.warning(f"Failed to open parent folder: {parent_path}")


    @log_errors()
    def _show_context_menu(self, position) -> None:
        """
        Display a right-click context menu for file items in the tree widget.

        Parameters
        ----------
        position : QPoint
            The global position where the right-click occurred.

        Notes
        -----
        Only activates for child file items (ignores group headers and clicks outside items).
        Menu includes universal actions: 'Open File' (reuses double-click logic) and 'Copy Path'.
        OS-dependent actions:
        - On Windows: 'Open Containing Folder' (selects file in Explorer) and 'Properties' (system dialog).
        - On other platforms: 'Open Folder' (opens parent directory via QDesktopServices).
        Focuses on the right-clicked item for simplicity; does not interfere with multi-selection or SelectionStore.
        Future enhancement: Support multi-select by applying actions to all selected items (see TODO).
        Handles edge cases: Invalid paths logged and skipped; non-existent files warned per action; permissions deferred to OS.
        Menu position mapped to global coordinates for proper display.
        Logs menu display for debugging.
        Integrates seamlessly with existing double-click, selection, and preview behaviors without modification.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        item = self._group_view.tree_widget.itemAt(position)
        if item is None or item.parent() is None:
            return  # Ignore group headers and outside clicks

        path_str = item.data(0, Qt.UserRole)
        if not path_str:
            LOGGER.warning("Right-clicked item has no associated file path")
            return

        path = Path(path_str)

        menu = QMenu(self)

        # Universal actions
        open_action = menu.addAction("Open File")
        open_action.triggered.connect(lambda: self._open_file(path))

        copy_action = menu.addAction("Copy Path")
        copy_action.triggered.connect(lambda: self._copy_path_to_clipboard(path))

        # OS-dependent actions
        system = platform.system()
        if system == 'Windows':
            folder_action = menu.addAction("Open Containing Folder")
            folder_action.triggered.connect(lambda: self._open_containing_folder(path))

            props_action = menu.addAction("Properties")
            props_action.triggered.connect(lambda: self._show_properties(path))
        else:
            # Cross-platform fallback
            folder_action = menu.addAction("Open Folder")
            folder_action.triggered.connect(lambda: self._open_folder(path))

        # File management actions
        copy_action = menu.addAction("Copy To")
        copy_action.triggered.connect(lambda: self._perform_copy(path_str))

        move_action = menu.addAction("Move To")
        move_action.triggered.connect(lambda: self._perform_move(path_str))

        # TODO: Extend to multi-select in future by iterating over self._group_view.tree_widget.selectedItems()
        # and applying actions to each valid file item, respecting SelectionStore.

        global_pos = self._group_view.tree_widget.viewport().mapToGlobal(position)
        action = menu.exec(global_pos)
        LOGGER.debug(f"Context menu displayed for file: {path}")


    @log_errors()
    def _perform_copy(self, path: str) -> None:
        """
        Perform copy operation for the selected file in the similarity manager.

        Parameters
        ----------
        path : str
            The absolute file path of the file to copy.

        Notes
        -----
        Opens a directory selection dialog using FileOperations.select_target_directory
        with operation='copy'. If a directory is selected and valid, attempts to copy
        the file using FileOperations.copy_file_to_dir, which preserves metadata and
        handles directory creation. On success, removes the file entry from the current
        groups model (via _remove_file_from_model) and refreshes the view to reflect
        the change, effectively removing it from the similarity display. Logs the
        operation details including target directory. If the copy fails (e.g., due to
        permissions, disk space, or invalid path), displays a warning QMessageBox
        with user-friendly message and returns without model changes; full error
        details are available in the application logs via the provided LOGGER.

        This action is intended for handling similar images by copying them to a new
        location while updating the UI immediately. The original file remains in
        its location post-copy. Clears the preview pane after successful operation
        to reflect the model change.

        Examples
        --------
        Typically triggered from context menu:

        .. code-block:: python

            copy_action = menu.addAction("Copy To")
            copy_action.triggered.connect(lambda: self._perform_copy(path_str))

        Edge Cases:
        - If target_dir selection is canceled, no operation is performed.
        - Handles non-existent source files gracefully (logged as failure).
        - Cross-platform compatible, but tested primarily on Windows 11.
        - Does not support directories; assumes path is a file from the tree widget.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            target_dir = FileOperations.select_target_directory(parent=self, operation='copy')
            if target_dir:
                success = FileOperations.copy_file_to_dir(path, target_dir, logger=LOGGER)
                if success:
                    self._remove_file_from_model(path)
                    self._preview_pane.clear()
                    LOGGER.info(f"File copied to {target_dir} and removed from similarity view: {path}")
                else:
                    @log_warnings
                    def warn_partial_copy():
                        LOGGER.warning("Partial copy operation; some files may remain", variables={"path": path, "target_dir": target_dir})
                    warn_partial_copy()
                    QMessageBox.warning(
                        self,
                        "Copy Failed",
                        "Failed to copy the file. Please check the application logs for detailed error information."
                    )
        except (OSError, IOError, PermissionError, ValueError) as e:
            LOGGER.error(f"File operation error in copy: {e}", exception=e)
            show_selectable_error(self, "Copy Error", f"Copy operation failed: {str(e)}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in copy: {e}", exception=e)
            show_selectable_error(self, "Copy Error", "An unexpected error occurred during copy.")

    @log_errors()
    def _perform_move(self, path: str) -> None:
        """
        Perform move operation for the selected file in the similarity manager.

        Parameters
        ----------
        path : str
            The absolute file path of the file to move.

        Notes
        -----
        Opens a directory selection dialog using FileOperations.select_target_directory
        with operation='move'. If a directory is selected and valid, attempts to move
        the file using FileOperations.move_file_to_dir, which relocates the file and
        removes the source. Handles cross-device moves by copying then deleting.
        On success, removes the file entry from the current groups model (via
        _remove_file_from_model) and refreshes the view. Since this is a similarity
        manager with perceptual matches, moving one file may affect group scores,
        but for simplicity, the item is simply removed from the display and a note
        is logged; no automatic re-grouping or re-scan is performed. Clears the
        preview pane after successful operation.
        Logs the operation details including target directory. If the move fails
        (e.g., permissions, cross-device issues, or invalid path), displays a
        warning QMessageBox and returns without model changes; full details in logs.

        This action relocates the file permanently, updating the UI to reflect its
        removal from the similarity list.

        Examples
        --------
        Typically triggered from context menu:

        .. code-block:: python

            move_action = menu.addAction("Move To")
            move_action.triggered.connect(lambda: self._perform_move(path_str))

        Edge Cases:
        - If target_dir selection is canceled, no operation is performed.
        - Source file is removed on success; no undo except via system recycle bin if applicable.
        - Handles non-existent source files gracefully (logged as failure).
        - Cross-platform, but optimized for Windows 11 file operations.
        - Assumes path is a file; directories not supported in this context.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            target_dir = FileOperations.select_target_directory(parent=self, operation='move')
            if target_dir:
                success = FileOperations.move_file_to_dir(path, target_dir, logger=LOGGER)
                if success:
                    self._remove_file_from_model(path)
                    self._preview_pane.clear_previews()
                    LOGGER.info(f"File moved to {target_dir} and removed from similarity view: {path}")
                    # Note: Moving one similar image may affect group scores; consider re-scanning if needed
                else:
                    @log_warnings
                    def warn_partial_move():
                        LOGGER.warning("Partial move operation; some files may remain", variables={"path": path, "target_dir": target_dir})
                    warn_partial_move()
                    QMessageBox.warning(
                        self,
                        "Move Failed",
                        "Failed to move the file. Please check the application logs for detailed error information."
                    )
        except (OSError, IOError, PermissionError, ValueError) as e:
            LOGGER.error(f"File operation error in move: {e}", exception=e)
            show_selectable_error(self, "Move Error", f"Move operation failed: {str(e)}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in move: {e}", exception=e)
            show_selectable_error(self, "Move Error", "An unexpected error occurred during move.")

    @log_errors()
    def _remove_file_from_model(self, path: str) -> None:
        """
        Remove a specific file path from the groups model and refresh the dialog view.

        Parameters
        ----------
        path : str
            The absolute file path to remove from the groups.

        Notes
        -----
        Iterates through the current self._model.groups (tuple of Group instances) to
        find the group containing the path in its items (tuple of str paths). Creates
        a new Group instance using dataclasses.replace with the file removed from items.
        If the resulting items tuple is empty, skips adding the group to keep the view
        clean (avoids empty similarity groups). Collects all unmodified groups and the
        updated one(s). If the path was found and removed (path_found=True), constructs
        a new tuple of groups and calls self.refresh_groups to update the model and
        rebuild the view via _update_model and FileGroupView.update_model. Logs the
        removal for auditing. If the path is not found in any group, logs a warning
        but performs no refresh.

        This method ensures immutability by using replace and tuples, aligning with
        the composition-centric architecture. Only refreshes if a change occurred,
        optimizing UI updates. After refresh, the preview pane auto-updates via
        existing connections (_on_tree_selection_changed); clears explicitly if needed.

        Examples
        --------
        Called post-copy or post-move:

        .. code-block:: python

            self._remove_file_from_model("/path/to/similar/file.jpg")

        Usage in Context:
        - Ensures the tree widget (self._group_view.tree_widget) reflects the model
          after file operations, maintaining consistency between UI and data.
        - Handles single-file removal; for multi-select, would need extension.

        Edge Cases:
        - Path not in any group: Warns and skips refresh.
        - Multiple groups with same path: Unlikely in similarity model, but would
          remove from first match only (iterative).
        - Empty model: No-op.
        - Group becomes empty: Skipped, reducing group count.
        - Quality scores: If removing a file with score, the refresh will recompute
          if evaluator active, but for simplicity, just remove and refresh.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        try:
            updated_groups = []
            path_found = False
            for group in self._model.groups:
                if path in group.items:
                    new_items = tuple(item for item in group.items if item != path)
                    path_found = True
                    if new_items:
                        new_group = replace(group, items=new_items)
                        updated_groups.append(new_group)
                else:
                    updated_groups.append(group)

            if path_found:
                self.refresh_groups(tuple(updated_groups))
                LOGGER.debug(f"Removed {path} from similarity model and refreshed view")
            else:
                @log_warnings
                def warn_not_found():
                    LOGGER.warning(f"Path not found in any group when removing: {path}")
                warn_not_found()
        except (ValueError, KeyError, AttributeError) as e:
            LOGGER.error(f"Model update error in remove: {e}", exception=e)
            show_selectable_error(self, "Model Error", f"Failed to update model: {str(e)}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in remove_file_from_model: {e}", exception=e)
            show_selectable_error(self, "Model Error", "An unexpected error occurred updating the model.")

    @log_errors()
    def _update_cache_stats_display(self) -> None:
        """Update cache statistics display in GUI."""
        if hasattr(self, '_flat_cache_manager') and self._flat_cache_manager:
            if hasattr(self._flat_cache_manager, '_enhanced_cache'):
                # Use enhanced cache if available
                stats_response = self._flat_cache_manager._enhanced_cache.get_stats()
                if stats_response.success:
                    stats = stats_response.data
                    cache_info = (
                        f"Cache: {stats['total_entries']} entries, "
                        f"{stats['cache_size_mb']:.1f}MB, "
                        f"Hit rate: {stats['hit_rate']:.1f}%"
                    )
                    self._cache_stats_label.setText(cache_info)
                    LOGGER.info(f"Updated cache stats display: {cache_info}")
                else:
                    self._cache_stats_label.setText("Cache: Stats unavailable")
            else:
                # Fallback to legacy cache counters
                counters = self._flat_cache_manager.get_counters()
                total_requests = counters['hits'] + counters['misses']
                hit_rate = (counters['hits'] / total_requests * 100) if total_requests > 0 else 0.0
                cache_info = (
                    f"Cache: {counters['hits']} hits, {counters['misses']} misses, "
                    f"Hit rate: {hit_rate:.1f}%"
                )
                self._cache_stats_label.setText(cache_info)
                LOGGER.info(f"Updated legacy cache stats display: {cache_info}")
        else:
            self._cache_stats_label.setText("Cache: Not available")

    @log_errors()
    def _on_compute_clicked(self) -> None:
        """Compute similarity groups via database hashes using ApiResponse with ProgressDialog integration.
        GUI Context: SimilarityManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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
            variables={"algorithm": algorithm, "threshold": threshold},
        )

        # Create progress dialog for the similarity computation
        progress_dialog = ProgressDialog(
            parent=self,
            title=f"Computing Similarity Groups - {algorithm.upper()}"
        )

        # Create cancellation flag for PhaseContext
        cancellation_flag = [False]

        # Set up cancellation handling
        def handle_cancellation():
            cancellation_flag[0] = True
            LOGGER.info("Similarity computation cancelled by user")

        progress_dialog.cancellation_requested.connect(handle_cancellation)

        # Create progress callback bridge function
        def progress_callback(current: int, total: int, message: str):
            """Bridge function to convert PhaseContext progress to ProgressDialog format."""
            try:
                # Calculate percentage (0-100)
                if total > 0:
                    percentage = min(100, max(0, int((current / total) * 100)))
                else:
                    percentage = 0

                # Update progress dialog
                progress_dialog.set_progress(percentage, message)

                LOGGER.debug(f"Progress update: {percentage}% - {message}")
            except Exception as e:
                LOGGER.error(f"Error updating progress dialog: {e}", exception=e)

        try:
            # Show progress dialog as modal
            progress_dialog.show()

            # Compute groups with progress reporting using PhaseContext
            groups, pool_map, total_files = self._compute_groups_from_database_with_progress(
                algorithm,
                threshold,
                progress_callback,
                cancellation_flag
            )

            # Update cache statistics after computation
            self._update_cache_stats_display()

        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.exception("Similarity grouping failed")
            show_selectable_error(
                self,
                "Computation Error",
                f"Failed to compute similarity groups:\n\n{exc}",
            )
            return
        finally:
            # Always close the progress dialog
            progress_dialog.accept()

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

# Mapping used for direction combo labels (shared between duplicates/similarity)
DuplicateDirectionLabels: Mapping[PoolDirection, str] = {
    PoolDirection.ALL: "All Pools",
    PoolDirection.A_TO_B: "Pool A → Pool B",
    PoolDirection.B_TO_A: "Pool B → Pool A",
    PoolDirection.A_WITHOUT_IN_B: "Pool A without matches in Pool B",
    PoolDirection.B_WITHOUT_IN_A: "Pool B without matches in Pool A",
}

__all__ = ["SimilarityManagerDialog"]
