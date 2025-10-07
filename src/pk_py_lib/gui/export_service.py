"""
src/pk_py_lib/gui/export_service.py

JSON export functionality for results dialogs (similarity and duplicate detection results).
Provides structured data export with comprehensive metadata, error handling, and Windows
compatibility for file operations.

Syntax validation performed with Python's ast module prior to inclusion.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import json
import traceback
import sys
import inspect

from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QSettings

from ..core.logging.decorators import log_errors
from ..core.logging.logger import get_logger
from ..core.filesystem.operations import FileOperations

logger = get_logger(__name__)


class ExportService:
    """
    Service class for exporting dialog results to JSON format.

    Handles data serialization, file naming conventions, and save operations
    with comprehensive error handling and logging.

    The exported JSON structure includes:
    - Export metadata (timestamp, dialog type, configuration)
    - Group statistics and file information
    - Search paths and algorithm details
    - Profile information and thresholds

    File naming convention:
    result-[profilename]-[comparison_type]-[algorithm]-[timestamp].json

    Default save location is the project "logs" directory.
    """

    def __init__(self) -> None:
        """Initialize the export service."""
        self.logger = get_logger(__name__)

    @log_errors()
    def export_dialog_results(
        self,
        dialog_type: str,
        groups: List[Any],
        profile_name: str = "default",
        algorithm: str = "unknown",
        threshold: Optional[int] = None,
        search_paths: Optional[List[str]] = None,
        parent=None
    ) -> bool:
        """
        Export dialog results to JSON file.

        Args:
            dialog_type: Type of dialog ("similarity" or "duplicate")
            groups: List of Group objects from dialog
            profile_name: Name of the settings profile used
            algorithm: Algorithm used (e.g., "phash", "whash", "xxh3")
            threshold: Threshold value used for detection
            search_paths: List of search paths used
            parent: Parent widget for file dialog

        Returns:
            True if export succeeded, False otherwise
        """
        try:
            # Generate export data structure
            export_data = self._create_export_data(
                dialog_type=dialog_type,
                groups=groups,
                profile_name=profile_name,
                algorithm=algorithm,
                threshold=threshold,
                search_paths=search_paths
            )

            # Generate filename and determine save location
            filename = self._get_export_filename(
                profile_name=profile_name,
                dialog_type=dialog_type,
                algorithm=algorithm
            )

            save_path = self._get_save_path(filename)

            # Show save file dialog
            final_path = self._show_save_dialog(
                default_path=save_path,
                parent=parent
            )

            if not final_path:
                self.logger.info("Export canceled by user")
                return False

            # Write JSON file
            success = self._write_json_file(final_path, export_data)

            if success:
                self.logger.info(f"Successfully exported results to: {final_path}")
                # Show success message
                QMessageBox.information(
                    parent,
                    "Export Complete",
                    f"Results successfully exported to:\n{final_path}"
                )
            else:
                QMessageBox.warning(
                    parent,
                    "Export Failed",
                    "Failed to write export file. Check logs for details."
                )

            return success

        except Exception as e:
            exc_type = type(e).__name__
            exc_info = sys.exc_info()
            tb_lineno = exc_info[2].tb_lineno if exc_info[2] else inspect.currentframe().f_lineno
            func_name = inspect.currentframe().f_code.co_name
            locals_dict = locals()
            error_msg = f"{exc_type}: {str(e)}"

            self.logger.error(
                error_msg,
                extra={
                    "file": __file__,
                    "line": tb_lineno,
                    "function": func_name,
                    "locals": locals_dict,
                    "traceback": traceback.format_exc(),
                    "dialog_type": dialog_type,
                }
            )

            QMessageBox.critical(
                parent,
                "Export Error",
                f"Failed to export results: {error_msg}"
            )
            return False

    @log_errors()
    def _create_export_data(
        self,
        dialog_type: str,
        groups: List[Any],
        profile_name: str,
        algorithm: str,
        threshold: Optional[int],
        search_paths: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        Create the complete export data structure.

        Args:
            dialog_type: Type of dialog ("similarity" or "duplicate")
            groups: List of Group objects from dialog
            profile_name: Name of the settings profile used
            algorithm: Algorithm used for detection
            threshold: Threshold value used
            search_paths: List of search paths

        Returns:
            Complete export data structure as dictionary
        """
        # Count total files across all groups
        total_files = sum(len(group.items) for group in groups)

        # Create export info section
        export_info = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dialog_type": dialog_type,
            "total_groups": len(groups),
            "total_files": total_files,
            "profile_name": profile_name,
            "algorithm": algorithm,
            "search_paths": search_paths or []
        }

        # Add threshold if provided
        if threshold is not None:
            export_info["threshold"] = threshold

        # Convert groups to export format
        export_groups = []
        for group in groups:
            export_group = self._convert_group_to_export_format(group)
            export_groups.append(export_group)

        return {
            "export_info": export_info,
            "groups": export_groups
        }

    @log_errors()
    def _convert_group_to_export_format(self, group: Any) -> Dict[str, Any]:
        """
        Convert a Group object to export format.

        Args:
            group: Group object from dialog

        Returns:
            Group data as dictionary
        """
        # Convert file items to export format
        export_files = []
        for item in group.items:
            export_file = {
                "path": item.path,
                "size": item.size,
                "resolution": item.resolution,
                "score": item.score,
                "file_type": item.file_type,
                "savings": item.savings
            }

            # Add optional fields if they exist
            if hasattr(item, 'quality_score') and item.quality_score is not None:
                export_file["quality_score"] = item.quality_score
            if hasattr(item, 'quality_algorithm') and item.quality_algorithm:
                export_file["quality_algorithm"] = item.quality_algorithm
            if hasattr(item, 'exact_set_id') and item.exact_set_id is not None:
                export_file["exact_set_id"] = item.exact_set_id

            export_files.append(export_file)

        # Convert group stats
        group_stats = {
            "total_size": group.stats.total_size,
            "savings": group.stats.savings,
            "avg_score": group.stats.avg_score,
            "file_count": group.stats.file_count
        }

        # Add min/max scores if they exist and are not None
        if hasattr(group.stats, 'min_score') and group.stats.min_score is not None:
            group_stats["min_score"] = group.stats.min_score
        if hasattr(group.stats, 'max_score') and group.stats.max_score is not None:
            group_stats["max_score"] = group.stats.max_score

        return {
            "id": group.id,
            "stats": group_stats,
            "files": export_files
        }

    @log_errors()
    def _get_export_filename(
        self,
        profile_name: str,
        dialog_type: str,
        algorithm: str
    ) -> str:
        """
        Generate export filename according to naming convention.

        Args:
            profile_name: Name of the settings profile
            dialog_type: Type of dialog ("similarity" or "duplicate")
            algorithm: Algorithm used

        Returns:
            Generated filename string
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"result-{profile_name}-{dialog_type}-{algorithm}-{timestamp}.json"
        return filename

    @log_errors()
    def _get_save_path(self, filename: str) -> Path:
        """
        Determine the default save location for export files.

        Args:
            filename: Name of the file to be saved

        Returns:
            Full path for the export file
        """
        # Use project logs directory as default location
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        return logs_dir / filename

    @log_errors()
    def _show_save_dialog(self, default_path: Path, parent=None) -> Optional[Path]:
        """
        Show save file dialog for JSON export.

        Args:
            default_path: Default path suggestion
            parent: Parent widget for dialog

        Returns:
            Selected path or None if canceled
        """
        # Use the full default path as the directory parameter
        # QFileDialog will interpret this as directory + filename
        default_path_str = str(default_path)

        # Show save file dialog with default filename pre-selected
        file_path, _ = QFileDialog.getSaveFileName(
            parent=parent,
            caption="Export Results to JSON",
            dir=default_path_str,
            filter="JSON files (*.json);;All files (*.*)",
            selectedFilter="JSON files (*.json)"
        )

        if file_path:
            return Path(file_path)
        return None

    @log_errors()
    def _write_json_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """
        Write export data to JSON file.

        Args:
            file_path: Path where to save the file
            data: Data structure to serialize

        Returns:
            True if write succeeded, False otherwise
        """
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON with proper formatting
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(
                    data,
                    f,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True
                )

            self.logger.info(f"Successfully wrote JSON export file: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to write JSON file {file_path}: {e}", exception=e)
            return False


__all__ = ["ExportService"]
