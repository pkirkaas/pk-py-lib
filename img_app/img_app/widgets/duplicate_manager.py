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

from PySide6.QtCore import Qt, QUrl
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
from src.pk_py_lib.core.logging.decorators import log_errors, log_warnings

from pathlib import Path
import platform
import os
import subprocess
import sys
import traceback
import inspect
from PySide6.QtWidgets import QMenu, QApplication
from PySide6.QtGui import QDesktopServices
from src.pk_py_lib.core.filesystem.operations import FileOperations
 
 
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
    * Deletion requests move selected files to the system recycle bin via the
      :class:`BaseFileManagerDialog` safe deletion workflow, ensuring a reversible
      operation that honours platform conventions.
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
        self._group_view.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._group_view.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self._group_view.tree_widget.customContextMenuRequested.connect(self._show_context_menu)
        parent_layout.addWidget(self._group_view)

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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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


    # ---------------------------------------------------------------------#
    # Public API
    # ---------------------------------------------------------------------#
    @property
    def file_group_model(self) -> FileGroupModel:
        """Return the immutable **FileGroupModel** backing the dialog."""
        return self._model

    @log_errors()
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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        self._profile_payload = profile_payload or {}
        is_valid, errors = validate_settings_schema(self._profile_payload)
        self._validator_errors = errors or []
        LOGGER.debug(
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
            # Validation succeeded; no modal feedback required for duplicate workflow
            LOGGER.debug("DuplicateManagerDialog profile validation succeeded")

    @log_errors()
    def refresh_groups(
        self,
        groups: Sequence[Group],
        *,
        pool_map: Optional[Mapping[str, str]] = None,
        direction: Optional[PoolDirection] = None,
    ) -> None:
        """Replace the rendered groups and optionally update pool mapping or direction.
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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

    # ---------------------------------------------------------------------#
    # Base overrides
    # ---------------------------------------------------------------------#
    def _on_delete_clicked(self) -> None:
        """Handle delete requests by delegating to the base trash workflow."""
        selected_count = self.selection_store.get_selection_count()
        if selected_count == 0:
            show_selectable_info(
                self,
                "No Selection",
                "Please select one or more files to delete.",
            )
            return

        LOGGER.info(
            "DuplicateManagerDialog deletion requested",
            variables={"selected_count": selected_count},
        )
        super()._on_delete_clicked()

    # ---------------------------------------------------------------------#
    # Internal helpers
    # ---------------------------------------------------------------------#
    @log_errors()
    def _update_model(self, model: FileGroupModel) -> None:
        """Persist the supplied model and refresh the view.
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
        self._model = model
        self._group_view.update_model(model)
        self.update_groups(list(model.groups))

    @log_errors()
    def _on_direction_changed(self) -> None:
        """Update model direction when the combo box selection changes.
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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

    @log_errors()
    def _extract_similarity_threshold(self) -> Optional[float]:
        """Best-effort extraction of normalized similarity threshold from the profile.
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
        """
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
        except (ValueError, KeyError, TypeError) as e:
            LOGGER.warning(f"Failed to extract similarity threshold: {e}")
            return None


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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
        Integrates seamlessly with existing double-click and selection behaviors without modification.
        GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
            Perform copy operation for the selected file in the duplicate manager.
            
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
            the change, effectively removing it from the duplicate display. Logs the
            operation details including target directory. If the copy fails (e.g., due to
            permissions, disk space, or invalid path), displays a warning QMessageBox
            with user-friendly message and returns without model changes; full error
            details are available in the application logs via the provided LOGGER.
            
            This action is intended for handling duplicates by copying them to a new
            location while updating the UI immediately. The original file remains in
            its location post-copy.
            
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
            GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
            """
            try:
                target_dir = FileOperations.select_target_directory(parent=self, operation='copy')
                if target_dir:
                    success = FileOperations.copy_file_to_dir(path, target_dir, logger=LOGGER)
                    if success:
                        self._remove_file_from_model(path)
                        LOGGER.info(f"File copied to {target_dir} and removed from duplicate view: {path}")
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
            Perform move operation for the selected file in the duplicate manager.
            
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
            _remove_file_from_model) and refreshes the view. Since this is a duplicate
            manager with exact matches, moving one file may invalidate the group's
            duplicate status, but for simplicity, the item is simply removed from the
            display and a note is logged; no automatic re-grouping or re-scan is performed.
            Logs the operation details including target directory. If the move fails
            (e.g., permissions, cross-device issues, or invalid path), displays a
            warning QMessageBox and returns without model changes; full details in logs.
            
            This action relocates the file permanently, updating the UI to reflect its
            removal from the duplicates list.
            
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
            GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
            """
            try:
                target_dir = FileOperations.select_target_directory(parent=self, operation='move')
                if target_dir:
                    success = FileOperations.move_file_to_dir(path, target_dir, logger=LOGGER)
                    if success:
                        self._remove_file_from_model(path)
                        LOGGER.info(f"File moved to {target_dir} and removed from duplicate view: {path}")
                        # Note: Moving one duplicate may break the group; consider re-scanning if needed
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
            clean (avoids empty duplicate groups). Collects all unmodified groups and the
            updated one(s). If the path was found and removed (path_found=True), constructs
            a new tuple of groups and calls self.refresh_groups to update the model and
            rebuild the view via _update_model and FileGroupView.update_model. Logs the
            removal for auditing. If the path is not found in any group, logs a warning
            but performs no refresh.
            
            This method ensures immutability by using replace and tuples, aligning with
            the composition-centric architecture. Only refreshes if a change occurred,
            optimizing UI updates.
            
            Examples
            --------
            Called post-copy or post-move:
            
            .. code-block:: python
                
                self._remove_file_from_model("/path/to/dupe/file.jpg")
            
            Usage in Context:
            - Ensures the tree widget (self._group_view.tree_widget) reflects the model
              after file operations, maintaining consistency between UI and data.
            - Handles single-file removal; for multi-select, would need extension.
            
            Edge Cases:
            - Path not in any group: Warns and skips refresh.
            - Multiple groups with same path: Unlikely in duplicate model, but would
              remove from first match only (iterative).
            - Empty model: No-op.
            - Group becomes empty: Skipped, reducing group count.
            GUI Context: DuplicateManagerDialog, selected items: {self.selection_store.get_selection_count()}
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
                    LOGGER.debug(f"Removed {path} from duplicate model and refreshed view")
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
  
  
__all__ = ["DuplicateManagerDialog"]