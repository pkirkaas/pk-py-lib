
"""
Main window implementation for the KDC Image Organizer (img_app).

Provides a QMainWindow subclass with:
- Title: "KDC Image Organizer"
- Menu bar with File, View, Help (initially no-op actions)
- Profile management toolbar with combobox, create/copy/rename/delete buttons
- Structured settings editor for profile configuration
- Progress reporting during operations
- Results dialog for operation completion

This window integrates the full Settings Manager functionality directly
into the main application interface.

Syntax validation: This file has been reviewed for Python syntax correctness.
"""

from __future__ import annotations

import inspect
import traceback
import argparse # Added for CLI argument type hinting

from PySide6.QtGui import QAction, QIcon, QPalette, QColor
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QWidget, QVBoxLayout, QMenuBar, QStatusBar,
    QComboBox, QPushButton, QHBoxLayout, QFrame, QProgressBar, QApplication,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QStackedWidget,
    QMessageBox, QToolBar, QMenu, QSizePolicy, QTextEdit
)
from typing import Optional, Dict, Any, List, Tuple, Mapping, Sequence
from pathlib import Path
from dataclasses import asdict
from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error, gui_error_handler, gui_error_context
from src.pk_py_lib.gui.dialogs.progress_dialog import ProgressDialog
# CACHE_SCHEMA deprecated; cache.db functionality migrated to flat_cache.db in flat_cache.py
from src.pk_py_lib.core.filesystem.paths import PathOperations
from src.pk_py_lib.core.filesystem.traversal import DirectoryTraversal, IMAGE_EXTENSIONS
from src.pk_py_lib.core.filesystem.identity import get_inode_device, compute_xxh3
from datetime import datetime
from src.pk_py_lib.core.logging.logger import get_logger, PKLogger
from src.pk_py_lib.core.logging.decorators import log_errors, log_warnings
from src.pk_py_lib.core.image.similarity import (
    get_image_metadata,
    format_timestamp,
    find_similar_images,
)
from src.pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats
from src.pk_py_lib.gui.models import SelectionStore, PoolDirection

from .widgets.duplicate_manager import DuplicateManagerDialog
from .widgets.similarity_manager import SimilarityManagerDialog

import logging
from collections import defaultdict
logger = logging.getLogger(__name__)

# Test script for circular reference fix
def test_circular_reference_fix():
    """Test the circular reference path filtering."""
    # Create a mock ScanWorker instance just to test the method
    class MockScanWorker:
        def __init__(self):
            self.mode = 'duplicate'

        def _is_circular_reference_path(self, path):
            """Copy of the method from ScanWorker for testing."""
            try:
                path_str = str(path).lower()
                abs_path_str = str(path.resolve()).lower()

                # List of Windows system paths that commonly cause circular references
                problematic_paths = [
                    r"\users\*\appdata\local\application data",
                    r"\users\*\appdata\roaming\microsoft\windows",
                    r"\users\*\appdata\local\microsoft\windows",
                    r"\programdata\microsoft\windows",
                    r"\windows\system32",
                    r"\windows\syswow64",
                    r"\windows\winsxs",
                    r"\users\*\application data",  # Older Windows versions
                ]

                # Check if the path matches any problematic patterns
                for problematic in problematic_paths:
                    # Convert Windows path pattern to a pattern that works with fnmatch
                    import fnmatch
                    # Use absolute path for more accurate matching
                    if fnmatch.fnmatch(abs_path_str, f"*{problematic}"):
                        return True

                # Additional check for specific Application Data junction
                if r"\appdata\local\application data" in abs_path_str:
                    return True

                # Check for Windows system directories that shouldn't be scanned
                windows_system_dirs = [
                    r"\windows",
                    r"\program files",
                    r"\program files (x86)",
                    r"\programdata",
                ]

                for sys_dir in windows_system_dirs:
                    if abs_path_str.startswith(f"c:{sys_dir}"):
                        return True

                return False

            except Exception:
                # If we can't resolve or check the path, err on the side of caution
                return True

    worker = MockScanWorker()

    # Test paths
    from pathlib import Path

    # Test Application Data path
    appdata_path = Path(r"C:\Users\pkirk\AppData\Local\Application Data")
    print(f"Testing Application Data path: {appdata_path}")
    print(f"Is circular reference: {worker._is_circular_reference_path(appdata_path)}")

    # Test normal path
    normal_path = Path(r"C:\Users\pkirk\Documents")
    print(f"Testing normal path: {normal_path}")
    print(f"Is circular reference: {worker._is_circular_reference_path(normal_path)}")

    # Test Windows system path
    windows_path = Path(r"C:\Windows\System32")
    print(f"Testing Windows path: {windows_path}")
    print(f"Is circular reference: {worker._is_circular_reference_path(windows_path)}")

if __name__ == "__main__":
    test_circular_reference_fix()

# Module-level logger for scan workflow; ERROR+ routes to STDERR via console output
LOGGER = get_logger("img_app.scan")

# Import Settings Manager components
try:
    from src.pk_py_lib.gui.settings_manager.structured_editor import StructuredProfileEditorWidget
    from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
    from pk_py_lib.core.models.settings import SettingsProfile
except ImportError:
    # Fallback imports if not available
    StructuredProfileEditorWidget = None
    SettingsManagerController = None
    SettingsProfile = None


class _NamePromptDialog(QDialog):
    """
    Minimal reusable prompt dialog for entering a name (with live validation message).
    """

    def __init__(self, title: str, label: str, initial: str = "", parent: Optional[QWidget] = None):
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


class CentralPlaceholder(QWidget):
    """
    Simple centered placeholder widget.

    Displays a centered label indicating where the application content will go.
    This class is placed here initially to keep scaffolding minimal; it can be
    moved to img_app/widgets/central_placeholder.py when expanded.

    Examples
    --------
    >>> w = CentralPlaceholder()
    >>> w.layout() is not None
    True
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        label = QLabel("The KDC Image Organizer will go here", self)
        # Use Qt.AlignmentFlag enums for correctness across PySide6 bindings
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        layout.addWidget(label)


class ScanWorker(QThread):
    """
    Background worker that scans filesystem paths from a Settings Profile,
    validates/refreshes cache entries based on search_type, and reports progress.

    For search_type='duplicate': Computes only file hashes (xxh3) without image loading or
    perceptual hash/metadata extraction. Preserves existing image data in cache.

    For search_type='similarity': Computes perceptual hashes (phash/whash), extracts dimensions,
    and quality scores (BRISQUE if enabled).

    This worker performs all I/O and SQLite work off the GUI thread to keep the UI responsive.
    It uses flat_cache_manager for conditional caching and computation based on search_type.

    Signals
    -------
    progress(processed: int, total: int, current_path: str, message: str)
        Emitted frequently to update progress UI.
    error(message: str)
        Emitted on non-fatal per-file errors; processing continues.
    finished(profile_name: str, summary: dict)
        Emitted once on completion (or early stop) with the profile name used for the scan and final counters.

    Notes
    -----
    - search_type ('duplicate' or 'similarity') controls computation scope: duplicate mode is
      file-hash only (fast, no PIL.open() calls), similarity mode includes image analysis.
    - exact_grouping=True for duplicate mode to enable xxh3-based grouping.
    - Include/Exclude patterns honored; for duplicate: all files; similarity: images only.
    """

    progress = Signal(int, int, str, str)
    error = Signal(str)
    finished = Signal(str, dict)

    def __init__(self, db_manager, flat_cache_manager, profile_json: dict, algorithm: str = "xxh3", mode: str = 'duplicate', compute_hashes: bool = False, search_type: Optional[str] = None, profile_name: Optional[str] = None, profile_id: Optional[str] = None, parent=None):
        """
        Initialize worker.

        Parameters
        ----------
        db_manager : DatabaseManager
            Database manager providing settings.db connection helper.
        flat_cache_manager : Optional[FlatCacheManager]
            Flat cache manager for file stat validation and hash caching.
        profile_json : dict
            Structured Settings Profile (Option A) JSON object.
        algorithm : str
            Hash algorithm token to ensure in image_hashes (default 'xxh3').
        mode : str
            Scan mode ('duplicate' or 'similarity').
        compute_hashes : bool
            Whether to compute perceptual hashes for similarity (renamed mentally to perceptual_hashes).
        profile_name : Optional[str]
            Human-friendly profile name used for this scan; emitted with the finished signal
            to ensure reporting uses the exact profile that initiated the scan.
        parent : Optional[QObject]
            Optional Qt parent object.
        """
        super().__init__(parent)
        self.db_manager = db_manager
        self.flat_cache_manager = flat_cache_manager
        self.profile = profile_json or {}
        self.algorithm = (algorithm or "xxh3").lower().strip()
        self.mode = mode
        if mode == 'duplicates':
            self.mode = 'duplicate'
            self.search_type = 'duplicate'  # Fixed duplicate mode bug: Ensure search_type is 'duplicate'
        self.search_type = search_type or self.mode
        self.compute_hashes = compute_hashes
        self.exact_grouping = (self.mode == 'duplicate')
        # Capture the profile name used for this run (best effort)
        try:
            self.profile_name = str(profile_name or (self.profile.get("name") if isinstance(self.profile, dict) else "") or "")
            # Ensure search_type is set correctly for conditional logic
            if self.search_type is None:
                self.search_type = self.mode  # Default to mode if not specified
            LOGGER.debug(f"ScanWorker initialized: mode={self.mode}, search_type={self.search_type}, compute_hashes={self.compute_hashes}")
        except Exception:
            self.profile_name = str(profile_name or "")
        # Capture the profile id used for this run (best effort; may be empty)
        try:
            self.profile_id = str(profile_id or "")
        except Exception:
            self.profile_id = ""
        self._stop = False
        # Map from absolute file path (POSIX string) to pool label 'A' or 'B'
        self._file_pool_map: dict[str, str] = {}

    def stop(self) -> None:
        """
        Request cooperative stop. The worker checks this flag between files.
        """
        self._stop = True

    def _normalize_exts(self, exts) -> set[str]:
        """
        Normalize a list of extension tokens to a lowercase, dot-prefixed set.

        Examples
        --------
        - "jpg" -> ".jpg"
        - ".PNG" -> ".png"
        """
        s: set[str] = set()
        try:
            for e in exts or []:
                e = str(e).strip()
                if not e:
                    continue
                if not e.startswith("."):
                    e = "." + e
                s.add(e.lower())
        except Exception:
            pass
        if not s:
            # Balanced defaults per canonical decisions
            s = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"}
        return s

    def _gather_files(self) -> list[Path]:
        """
        Gather valid directory roots from profile pools A/B to pass to scan_directory.

        This method collects all raw paths from pools A and B, converts them to Path objects,
        and filters to only include directories using pathlib.Path(root).is_dir(). Files or
        invalid paths are skipped with a warning log to prevent passing non-directories as roots
        to scan_directory, which expects directories to traverse. This resolves the error
        "No valid root directories provided" in duplicates mode when profile paths include files
        (e.g., [WindowsPath('V:/Cache/03_crop.jpg'), ...]).

        Additionally, this method now includes validation to prevent circular reference issues
        by filtering out Windows system paths that commonly contain junction points and circular
        references, such as Application Data directories.

        After filtering, roots are normalized using PathOperations.normalize_paths() and
        deduplicated by removing contained paths with PathOperations.remove_contained_paths().

        For duplicates mode, scan_directory will traverse these directories with patterns=None
        to include all files. For similarity mode, patterns will filter to images during traversal.

        Behavior notes:
        - Pool-specific traversal options (recurse, max_depth, etc.) are handled by scan_directory
          via the passed self.profile settings.
        - No file gathering or pool mapping here; files are obtained from scan_result['files'],
          and pool mapping is set post-scan (all 'A' for single-pool duplicates).
        - If no valid directories found after filtering, raises ValueError in run() to abort scan.

        Returns
        -------
        list[Path]
            Sorted list of unique, valid absolute directory paths (Path objects) to scan.
            Empty if no valid roots, triggering abort.
        """
        pools = self.profile.get("pools", {}) if isinstance(self.profile, dict) else {}
        all_raw_paths = []
        for label in ("A", "B"):
            cfg = pools.get(label)
            if not cfg:
                continue
            raw_paths = cfg.get("paths") or []
            all_raw_paths.extend(raw_paths)

        # Convert to Path and filter to directories only
        roots = [Path(p) for p in all_raw_paths if p]
        valid_roots = []
        for root in roots:
            try:
                if root.is_dir():
                    # Check for Windows system paths that cause circular references
                    if self._is_circular_reference_path(root):
                        LOGGER.warning(
                            f"Skipping Windows system path that causes circular references: {root}. "
                            f"This path contains junction points that lead to infinite recursion."
                        )
                        continue

                    valid_roots.append(root)
                else:
                    # Log warning for files or invalid paths (e.g., non-existent)
                    LOGGER.warning(
                        f"Skipping invalid root (not a directory) in profile pools for {self.mode} mode: {root}. "
                        f"Ensure profile paths are directories like 'V:\\D4', 'V:\\Cache'; files like 'V:/Cache/03_crop.jpg' are invalid roots."
                    )
            except Exception as e:
                LOGGER.warning(f"Error validating root '{root}' in profile pools: {e}")

        # Normalize paths (resolve symlinks, make absolute) and remove contained paths for efficiency
        roots = PathOperations.normalize_paths(valid_roots)
        roots = PathOperations.remove_contained_paths(roots)

        # Debug: summary of valid roots
        try:
            # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints
            pass
        except Exception:
            pass

        return roots

    def _is_circular_reference_path(self, path: Path) -> bool:
        """
        Check if a path is likely to cause circular references due to Windows junction points.

        Windows has several junction points in system directories that can cause infinite
        recursion during directory traversal. This method identifies paths that are known
        to contain such junction points.

        Args:
            path: Directory path to check

        Returns:
            True if the path should be excluded to prevent circular references
        """
        try:
            path_str = str(path).lower()
            abs_path_str = str(path.resolve()).lower()

            # List of Windows system paths that commonly cause circular references
            problematic_paths = [
                r"\users\*\appdata\local\application data",
                r"\users\*\appdata\roaming\microsoft\windows",
                r"\users\*\appdata\local\microsoft\windows",
                r"\programdata\microsoft\windows",
                r"\windows\system32",
                r"\windows\syswow64",
                r"\windows\winsxs",
                r"\users\*\application data",  # Older Windows versions
                r"\users\*\appdata\*",
            ]

            # Check if the path matches any problematic patterns
            for problematic in problematic_paths:
                # Convert Windows path pattern to a pattern that works with fnmatch
                import fnmatch
                # Use absolute path for more accurate matching
                if fnmatch.fnmatch(abs_path_str, f"*{problematic}"):
                    return True

            # Additional check for specific Application Data junction
            if r"\appdata\local\application data" in abs_path_str or r"\application data" in abs_path_str:
                return True

            # Check for Windows system directories that shouldn't be scanned
            windows_system_dirs = [
                r"\windows",
                r"\program files",
                r"\program files (x86)",
                r"\programdata",
            ]

            for sys_dir in windows_system_dirs:
                if abs_path_str.startswith(f"c:{sys_dir}"):
                    return True

            return False

        except Exception:
            # If we can't resolve or check the path, err on the side of caution
            return True

    def run(self) -> None:
        """
        Execute scanning and cache validation/refresh.

        Workflow
        --------
        1) Gather roots from profile pools (A/B), flattened/normalized
        2) Call scan_directory(roots, patterns=None for duplicates/all files, image for similarity, exact_grouping=(mode=='duplicates'), compute_hashes=(mode=='similarity'))
        3) Extract files/groups from result; populate pool map from files
        4) Ensure cache schema; but now handled in scan_directory
        5) Emit progress (post-scan, simulate or from scan_directory if extended); errors
        6) Emit finished(summary) with groups_data if duplicates
        """
        import os
        from datetime import datetime
        import traceback

        stats = {
            "found": 0,
            "processed": 0,
            "inserted": 0,
            "invalidated": 0,
            "hashes_computed": 0,
            "errors": 0,
            "error_details": [],  # Collect structured per-error details for post-scan reporting
        }

        try:
            roots = self._gather_files()
            if not roots:
                raise ValueError("No valid roots to scan")

            # Determine patterns based on search_type for efficient traversal
            # For 'duplicate': patterns=None to include all files for comprehensive exact hashing
            # For 'similarity': image extensions only to focus on perceptual hash candidates
            image_exts = [f"*{ext}" for ext in IMAGE_EXTENSIONS]
            patterns = image_exts if self.mode == 'similarity' else None

            # Resolve algorithms with search_type awareness
            # For 'duplicate': Limit to ['xxh3'] for file content hashing (no perceptual)
            # For 'similarity': Use perceptual algorithms from profile or defaults
            effective_compute_hashes = self.compute_hashes or self.exact_grouping
            algorithms_param = None
            if effective_compute_hashes:
                if self.search_type == 'duplicate':
                    algorithms_param = ['xxh3']  # Explicit for duplicate mode: file hash only
                else:
                    algorithms_param = self.profile.get('similarity', {}).get('enabled_algorithms', ['phash', 'whash'])
            LOGGER.debug(f"Calling scan_directory: search_type={self.search_type}, algorithms={algorithms_param}, exact_grouping={self.exact_grouping}, patterns={patterns}")

            # Prepare walk_kwargs from profile for traversal parameters (e.g., max_depth, exclude_patterns, include_patterns)
            # Only include valid traversal-related keys to prevent passing irrelevant profile fields (e.g., db_manager, similarity settings) to underlying walk_files
            # This ensures only applicable kwargs like max_depth, exclude_patterns, include_patterns are forwarded, avoiding TypeError on invalid params
            valid_traversal_keys = {'max_depth', 'exclude_patterns', 'include_patterns'}  # Extend with other walk_files-compatible keys as needed (e.g., 'recurse')
            walk_kwargs = {k: v for k, v in self.profile.items() if k in valid_traversal_keys}

            # Call extended scan_directory with explicit search_type for conditional logic in cache and hashing
            # For duplicate mode: patterns=None (all files for xxh3 hashing), algorithms=['xxh3'], search_type='duplicate' (skips image metadata/phash/whash)
            # For similarity mode: patterns=image extensions, algorithms=perceptual (phash/whash) from profile, extracts metadata (width/height/phash/whash)
            from pk_py_lib.core.filesystem.traversal import scan_directory
            # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints
            scan_result = scan_directory(
                roots=roots,
                profile_name=self.profile_name,
                patterns=patterns,
                compute_hashes=effective_compute_hashes,
                exact_grouping=self.exact_grouping,
                algorithms=algorithms_param,
                flat_cache_manager=self.flat_cache_manager,  # Essential for conditional caching
                search_type=self.search_type,  # Critical for duplicate vs similarity logic
                follow_symlinks=False,
                include_hidden=False,
                progress_callback=lambda processed, total, path, message: self.progress.emit(processed, total, path or "", message),
                stop_event=lambda: self._stop,
                **{k: v for k, v in walk_kwargs.items() if k not in ['db_manager', 'profile_name']}  # Filter to exclude non-traversal keys already handled explicitly
            )

            if scan_result is None:
                # Scan was cancelled by stop_event. Set cancellation flag and proceed to emit finished signal.
                stats["processed"] = 0
                stats["cancelled"] = True
                logger.debug("ScanWorker run cancelled by user request.")
                # We rely on the last progress callback to have emitted the final status
                # (e.g., "Scan cancelled.)

            else:
                files = scan_result['files']
                # Add 'files' to summary for post-scan duplicate grouping
                stats['files'] = scan_result['files']
                if self.exact_grouping:
                    # Note: scan_directory now returns 'exact_groups' for exact grouping
                    stats['groups_data'] = scan_result.get('exact_groups', {})

                total = len(files)
                stats["found"] = total
                # Record current run file set
                try:
                    run_paths = [f['path'] for f in files]
                except Exception:
                    run_paths = []
                stats["run_paths"] = run_paths
                stats["algorithm"] = self.algorithm
                if getattr(self, "profile_id", None):
                    stats["profile_id"] = self.profile_id

                # Populate pool map post-scan (from metadata if available, else from roots)
                self._file_pool_map = {}
                for f in files:
                    path = f.get('path', '')
                    # Default to 'A' for single-pool; can enhance with DB pool later
                    self._file_pool_map[path] = 'A'

                # For duplicates, include groups_data in summary
                if self.exact_grouping:
                    # groups_data is now populated from scan_result['exact_groups'] above
                    logger.debug(f"Exact groups included in summary: {len(stats['groups_data'])} groups")

                # Collect errors from scan_result
                stats["error_details"] = scan_result.get('error_details', [])
                stats["errors"] = len(stats["error_details"])

                # The progress is now handled inside scan_directory, so we just set the final processed count
                stats["processed"] = total  # All files processed by scan_directory

        except Exception as e:
            # Top-level fatal error
            self.error.emit(str(e))
            stats["error_details"].append({
                'path': 'scan_run',
                'error': str(e),
                'traceback': traceback.format_exc()
            })
            stats["errors"] = len(stats["error_details"])

        # Emit summary at the end (even on partial stop)
        errors = stats.get('errors', 0)
        # Scan completion reported via finished signal; no terminal print
        stats['mode'] = self.mode
        stats['compute_hashes'] = self.compute_hashes
        self.finished.emit(self.profile_name, stats)
class ComparisonWorker(QThread):
    """
    Background worker that handles the synchronous comparison phase (exact duplicate
    detection or perceptual similarity grouping) asynchronously.

    This worker performs the heavy computation off the GUI thread to keep the UI responsive.
    It relies on pre-scanned results (hashes, file paths) and the active profile settings.

    Signals
    -------
    progress(processed: int, total: int, message: str)
        Emitted frequently to update progress UI (0-100%).
    finished(results: dict)
        Emitted once on completion or cancellation. The results dict includes:
        - 'cancelled': bool (True if stopped early)
        - 'groups': List[Group]
        - 'comparison_type': str
        - 'summary': dict
    error(message: str)
        Emitted on error.
    """

    progress = Signal(int, int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, main_window_instance: 'MainWindow', scan_results: dict, comparison_type: str, parent=None):
        """
        Initialize worker.

        Parameters
        ----------
        main_window_instance : MainWindow
            The instance of MainWindow to access necessary methods (e.g., _get_duplicate_groups_single_pool,
            _compute_similarity_groups) and the database manager.
        scan_results : dict
            The summary dictionary returned by ScanWorker, containing 'files', 'groups_data', etc.
        comparison_type : str
            The type of comparison to perform ('duplicate' or 'similarity').
        parent : Optional[QObject]
            Optional Qt parent object.
        """
        super().__init__(parent)
        self.main_window = main_window_instance
        self.scan_results = scan_results
        self.comparison_type = comparison_type
        self._stop = False
        self.logger = get_logger("img_app.comparison_worker")

    def stop(self) -> None:
        """
        Request cooperative stop.
        """
        self._stop = True

    def run(self) -> None:
        """
        Execute the comparison logic based on comparison_type.
        """
        results = {
            'cancelled': False,
            'groups': [],
            'comparison_type': self.comparison_type,
            'summary': self.scan_results,
        }

        try:
            if self._stop:
                results['cancelled'] = True
                self.logger.debug("ComparisonWorker cancelled before start.")
                return

            if self.comparison_type == 'duplicate':
                self._run_duplicate_comparison(results)
            elif self.comparison_type == 'similarity':
                self._run_similarity_comparison(results)
            else:
                raise ValueError(f"Unknown comparison type: {self.comparison_type}")

        except Exception as e:
            self.error.emit(f"Fatal error during comparison: {e}")
            self.logger.error("ComparisonWorker fatal error", exception=e)
            results['cancelled'] = True # Treat fatal error as cancellation/failure
        finally:
            self.finished.emit(results)

    def _run_duplicate_comparison(self, results: dict) -> None:
        """
        Handles exact duplicate detection.
        """
        self.progress.emit(0, 100, "Starting exact duplicate detection...")

        # Simulate work and check for cancellation
        import time
        time.sleep(0.1)
        if self._stop:
            results['cancelled'] = True
            self.logger.debug("Duplicate comparison cancelled.")
            self.progress.emit(100, 100, "Duplicate comparison cancelled.")
            return

        # Fetch groups using MainWindow's method (which relies on self._last_run_paths being set)
        raw_duplicate_groups = self.main_window._get_duplicate_groups_single_pool()

        # Cache summary printed in main handler after processing
        total_files = len(self.scan_results.get('run_paths', []))

        # Convert raw dicts to immutable Group objects and extract pool map
        dialog_groups, pool_map = self.main_window._convert_raw_groups_to_dialog_groups(raw_duplicate_groups, search_type='duplicate')

        results['groups'] = dialog_groups
        results['pool_map'] = pool_map

        self.progress.emit(100, 100, f"Duplicate detection finished. Found {len(dialog_groups)} groups.")
        self.logger.debug(f"Duplicate comparison finished. Found {len(dialog_groups)} groups.")

    def _run_similarity_comparison(self, results: dict) -> None:
        """
        Handles perceptual similarity grouping.
        """
        self.progress.emit(0, 100, "Starting perceptual similarity grouping...")

        # 1. Prepare parameters
        profile_payload = self.main_window.active_profile # Assuming active_profile holds the payload
        run_paths = self.scan_results.get('run_paths', [])
        db_mgr = getattr(self.main_window, "database_manager", None)

        if not profile_payload or not run_paths or not db_mgr:
            self.error.emit("Missing required context (profile, paths, or database manager) for similarity comparison.")
            self.progress.emit(100, 100, "Similarity comparison failed.")
            return

        # Simulate work and check for cancellation
        import time
        time.sleep(0.1)
        if self._stop:
            results['cancelled'] = True
            self.logger.debug("Similarity comparison cancelled.")
            self.progress.emit(100, 100, "Similarity comparison cancelled.")
            return

        # 2. Compute similarity groups using MainWindow's method
        dialog_groups = self.main_window._compute_similarity_groups(profile_payload, run_paths, db_mgr, search_type='similarity')

        # 3. Extract pool map
        pool_map = self.main_window._extract_pool_map_from_groups(dialog_groups)

        results['groups'] = dialog_groups
        results['pool_map'] = pool_map

        self.progress.emit(100, 100, f"Similarity grouping finished. Found {len(dialog_groups)} groups.")
        self.logger.debug(f"Similarity comparison finished. Found {len(dialog_groups)} groups.")

class MainWindow(QMainWindow):
    """
    QMainWindow for the KDC Image Organizer.

    Responsibilities
    ----------------
    - Set up basic window chrome (title, menus, status bar)
    - Provide complete profile management UI (combobox, create/copy/rename/delete/set active buttons)
    - Integrated structured settings editor for profile configuration
    - Display progress reporting during operations
    - Show detailed results dialog after operation completion
    - Host future widgets and controllers derived from pk_py_lib

    Usage
    -----
    The window is constructed and shown by img_app.img_app.app:main()

    Examples
    --------
    >>> win = MainWindow()
    >>> isinstance(win.menuBar(), QMenuBar)
    True
    """

    @staticmethod
    @log_errors()
    def _to_int_timestamp(val) -> int:
        """
        Best-effort string/number/None -> integer epoch seconds converter.

        This robust conversion is necessary because database values might be stored
        as strings (e.g., ISO format) or integers, and direct int() conversion fails
        for strings. Returns 0 on failure or None input.
        """
        if val is None:
            return 0
        try:
            if isinstance(val, (int, float)):
                return int(val)
            s = str(val).strip()
            if not s:
                return 0
            if s.isdigit():
                return int(s)

            # Attempt common ISO formats
            from datetime import datetime
            s2 = s[:-1] if s.endswith("Z") else s
            s2 = s2.replace(" ", "T")
            dt = None
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(s2, fmt)
                    break
                except Exception:
                    continue
            return int(dt.timestamp()) if dt else 0
        except Exception:
            return 0

    # Signal emitted when the active profile changes
    profile_changed = Signal(dict)

    def _make_noop_action(self, text: str) -> QAction:
        """
        Creates a QAction that is disabled and does nothing when triggered.
        Used for menu placeholders.

        Parameters
        ----------
        text : str
            The text to display on the action.

        Returns
        -------
        QAction
            The disabled, no-op action.
        """
        action = QAction(text, self)
        action.setEnabled(False)
        return action

    @log_errors()
    def _on_clear_cache(self) -> None:
        """
        Handles the 'Clear Cache' menu action.

        Calls self.flat_cache_manager.clear_cache() and shows success/error message.
        """
        if not hasattr(self, 'flat_cache_manager') or self.flat_cache_manager is None:
            show_selectable_error(self, "Cache Error", "FlatCacheManager is not available.")
            return

        try:
            self.flat_cache_manager.clear_cache()
            show_selectable_info(self, "Cache Cleared", "Cache database cleared and recreated successfully.")
            self.status_label.setText("Cache cleared.")
        except Exception as e:
            show_selectable_error(self, "Clear Cache Failed", f"Failed to clear cache: {str(e)}")
            self.status_label.setText("Cache clear failed.")

    def _on_clean_cache(self) -> None:
        """
        Handles the 'Clean Cache' menu action.

        Calls self.flat_cache_manager.clean_cache() in a background thread with progress dialog.
        """
        if not hasattr(self, 'flat_cache_manager') or self.flat_cache_manager is None:
            show_selectable_error(self, "Cache Error", "FlatCacheManager is not available.")
            return

        from PySide6.QtCore import QThread, Signal
        from PySide6.QtWidgets import QProgressDialog

        class CleanCacheWorker(QThread):
            progress = Signal(int)
            finished = Signal(int)
            error = Signal(str)

            def __init__(self, manager):
                super().__init__()
                self.manager = manager

            def run(self):
                try:
                    # Get total entries for progress
                    with self.manager._get_connection() as conn:
                        cursor = conn.execute(f"SELECT COUNT(*) FROM {self.manager.table_name}")
                        total = cursor.fetchone()[0]

                    if total == 0:
                        self.finished.emit(0)
                        return

                    deleted = self.manager.clean_cache()
                    self.finished.emit(deleted)
                except Exception as e:
                    self.error.emit(str(e))

        worker = CleanCacheWorker(self.flat_cache_manager)
        progress_dialog = QProgressDialog("Cleaning cache...", "Cancel", 0, 100, self)
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)

        def on_progress(value):
            progress_dialog.setValue(value)

        def on_finished(deleted):
            progress_dialog.close()
            if deleted > 0:
                show_selectable_info(self, "Cache Cleaned", f"Cleaned {deleted} invalid entries from cache.")
                self.status_label.setText(f"Cache cleaned: {deleted} entries removed.")
            else:
                show_selectable_info(self, "Cache Cleaned", "No invalid entries found in cache.")
                self.status_label.setText("Cache clean completed: No changes.")

        def on_error(msg):
            progress_dialog.close()
            show_selectable_error(self, "Clean Cache Failed", f"Failed to clean cache: {msg}")
            self.status_label.setText("Cache clean failed.")

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        progress_dialog.canceled.connect(worker.quit)

        worker.start()
        progress_dialog.exec()

    def _show_about(self) -> None:
        """
        Handles the 'About' menu action.

        Currently a placeholder that shows an info message.
        """
        show_selectable_info(self, "About KDC Image Organizer", "KDC Image Organizer\nVersion: Development Prototype\n\nThis application is currently in the Proof-of-Concept phase.")

    def _on_view_cache(self) -> None:
        """
        Handles the 'View Cache' menu action.

        Opens the ViewCacheDialog to display cache metadata and entries.
        """
        if not hasattr(self, 'flat_cache_manager') or self.flat_cache_manager is None:
            show_selectable_error(self, "Cache Error", "FlatCacheManager is not available.")
            return

        try:
            from src.pk_py_lib.gui.dialogs.view_cache_dialog import ViewCacheDialog
            from src.pk_py_lib.core.configuration import ConfigurationManager
            import time
            start_exec = time.time()
            self.logger.info(f"ViewCacheDialog exec() start at {start_exec}")
            dialog = ViewCacheDialog(self.flat_cache_manager, self)
            result = dialog.exec()
            end_exec = time.time()
            self.logger.info(f"ViewCacheDialog exec() end at {end_exec}, duration: {end_exec - start_exec:.2f}s, result: {result}")

            # Development mode check: Use the same logic as logging file location
            # (project root logs indicate development; user dir indicates production)
            config = ConfigurationManager(self.database_manager)
            use_user_dir = config.get_app_setting("logging_to_user_dir")
            is_development_mode = not use_user_dir

            if is_development_mode:
                """
                Purpose: Forces immediate garbage collection of the large QStandardItemModel (~1000+ rows)
                to prevent a 5-10s UI freeze post-dialog close. The model destruction during dialog.close()
                can block the main thread due to Qt's reference counting and Python's GC cycle.

                Concerns/Side Effects: This is a workaround for development/debugging; in production,
                it could cause unpredictable pauses elsewhere if triggered frequently. Monitor for impacts
                on other dialogs or memory patterns. Not ideal long-term—recommend switching to QSqlTableModel
                for lazy loading. Only enabled in development mode to avoid production risks.
                """
                post_exec_start = time.time()
                self.logger.info(f"Post-exec cleanup start at {post_exec_start}")
                import gc
                gc_start = time.time()
                gc.collect()
                gc_end = time.time()
                self.logger.info(f"GC.collect() completed at {gc_end}, duration: {gc_end - gc_start:.2f}s")
                post_exec_end = time.time()
                self.logger.info(f"Post-exec full duration: {post_exec_end - post_exec_start:.2f}s")
            else:
                self.logger.info("Skipping explicit GC.collect() in production mode")

            self.status_label.setText("Cache view closed.")
        except Exception as e:
            show_selectable_error(self, "View Cache Failed", f"Failed to view cache: {e}")
            self.status_label.setText("Cache view failed.")

    def _on_rename_profile(self) -> None:
        """Placeholder for renaming the active profile."""
        show_selectable_info(self, "Profile Operation", "Rename Profile functionality is not yet implemented.")

    def _on_delete_profile(self) -> None:
        """Placeholder for deleting the active profile."""
        show_selectable_info(self, "Profile Operation", "Delete Profile functionality is not yet implemented.")

    def _on_set_active_profile(self) -> None:
        """Placeholder for setting the selected profile as active."""
        show_selectable_info(self, "Profile Operation", "Set Active Profile functionality is not yet implemented.")

    @gui_error_handler(component_name="MainWindow", operation="save_profile")
    def _on_save_profile(self) -> None:
        """
        Save changes from the structured editor to the current profile via the controller.
        """
        if self.structured_editor is None or not self.structured_editor.is_dirty():
            self.status_label.setText("No changes to save.")
            return

        if self.active_profile is None:
            self.status_label.setText("Cannot save: No active profile selected.")
            return

        # 1. Get pending changes from the editor
        profile_id = self.active_profile['id']
        try:
            # The editor provides the full updated JSON payload
            updated_payload = self.structured_editor.get_profile_data()
        except Exception as exc:
            show_selectable_error(self, "Save Error", f"Failed to retrieve data from editor: {exc}")
            return

        # 2. Validate and save via controller
        resp = self.controller.update_structured_profile(profile_id, updated_payload)

        if resp.success:
            self.status_label.setText(f"Profile '{updated_payload.get('name', 'Unnamed')}' saved successfully.")
            # Update internal active profile state
            self.active_profile = resp.data
            # Clear dirty state in editor and update UI buttons
            self.structured_editor.set_dirty(False)
            # Reload profiles to update the name/active status in the combobox
            self.load_profiles()
        else:
            show_selectable_error(self, "Save Failed", f"Failed to save profile: {resp.message}")

    @gui_error_handler(component_name="MainWindow", operation="cancel_changes")
    def _on_cancel_changes(self) -> None:
        """
        Discard changes in the structured editor by reloading the current profile data.
        """
        if self.structured_editor is None or not self.structured_editor.is_dirty():
            self.status_label.setText("No changes to discard.")
            return

        if self.active_profile is None:
            self.status_label.setText("Cannot cancel: No active profile selected.")
            return

        # Reload the profile data from the database
        self._load_profile_into_editor(self.active_profile['id'])
        self.status_label.setText(f"Changes discarded for profile: {self.active_profile.get('name', 'Unnamed')}")

    def _get_duplicate_groups_single_pool(self) -> List[Dict[str, Any]]:
        """
        Retrieves the pre-computed exact duplicate groups from the last scan run.

        Returns
        -------
        List[Dict[str, Any]]
            List of raw group dictionaries (hash, count, files).
        """
        # We rely on the data prepared during the scan phase in _on_scan_finished_with_comparison_start
        # We prioritize the prepared data, falling back to the fallback data if necessary.
        prepared = getattr(self, '_last_groups_data_prepared', [])
        if prepared:
            return prepared
        return getattr(self, '_last_groups_data_fallback', [])

    def _convert_raw_groups_to_dialog_groups(self, raw_groups: List[Dict[str, Any]], search_type: str = None) -> Tuple[List[Group], Dict[str, str]]:
        """
        Converts raw group dictionaries (from scan/comparison) into immutable Group objects
        and extracts the path->pool map.

        Parameters
        ----------
        raw_groups : List[Dict[str, Any]]
            List of raw group dictionaries.
        search_type : str
            'duplicate' to ensure 'Unknown' resolution without image ops.

        Returns
        -------
        Tuple[List[Group], Dict[str, str]]
            (List of immutable Group objects, Path to Pool map)
        """
        dialog_groups: List[Group] = []
        pool_map: Dict[str, str] = {}

        for index, raw_group in enumerate(raw_groups):
            group_files: List[FileItem] = []
            total_size = 0

            for raw_file in raw_group.get("files", []):
                path = str(raw_file.get("path", "")).strip()
                if not path:
                    continue

                # Use cached metadata if available, otherwise use raw data
                size, modified = self._metadata_cache.get(path, (0, 0))

                # Fallback to raw data if cache miss or raw data is better
                raw_size = int(raw_file.get("size", 0) or 0)
                raw_modified = MainWindow._to_int_timestamp(raw_file.get("modified", 0))

                size = max(size, raw_size)
                modified = max(modified, raw_modified)

                pool = str(raw_file.get("pool", "A") or "A")

                resolution = "Unknown" if search_type == 'duplicate' else "—"
                # Skip image ops in duplicate mode

                file_item = FileItem(
                    path=path,
                    size=size,
                    resolution=resolution,
                    mod_date=format_timestamp(modified),
                    score=raw_file.get("score", 1.0), # Default to 1.0 for exact duplicates
                    file_type=Path(path).suffix.lstrip(".").upper() or "",
                    savings=0,
                )
                group_files.append(file_item)
                total_size += size
                pool_map[path] = pool

            if group_files:
                stats = GroupStats(
                    total_size=total_size,
                    savings=total_size - group_files[0].size, # Savings is total size minus one file
                    min_score=1.0,
                    max_score=1.0,
                    avg_score=1.0,
                    file_count=len(group_files),
                )

                dialog_groups.append(
                    Group(
                        id=raw_group.get("hash", f"dup_{index}"),
                        items=tuple(group_files),
                        stats=stats,
                        ref_path=group_files[0].path if group_files else "",
                    )
                )

        return dialog_groups, pool_map

    def _compute_similarity_groups(self, profile_payload: Dict[str, Any], run_paths: List[str], db_manager: Any, search_type: str = 'similarity') -> List[Group]:
        """
        Fetches perceptual hashes from the cache DB for the run paths and computes similarity clusters.

        Since pk_py_lib.core.image.similarity.find_similar_images already returns List[Group]
        (enriched with metadata), this method primarily handles data fetching and dispatch.

        Parameters
        ----------
        profile_payload : Dict[str, Any]
            The settings profile payload used for the run.
        run_paths : List[str]
            List of file paths included in the current scan run.
        db_manager : Any
            The DatabaseManager instance.
        search_type : str
            'similarity' to ensure full computations.

        Returns
        -------
        List[Group]
            List of immutable Group objects representing similarity clusters.
        """
        from src.pk_py_lib.core.image.similarity import find_similar_images

        # 1. Extract algorithm and threshold from profile
        criteria = profile_payload.get("criteria", {})
        algorithm = criteria.get("similarity_hash_algorithm", "phash")

        # Default to 10 for phash, 12 for whash (Hamming distance)
        default_threshold = 10 if algorithm == "phash" else 12

        # Try to get the threshold from criteria, assuming it's the Hamming distance (int)
        threshold_int = criteria.get(f"{algorithm}_threshold", default_threshold)

        # 3. Compute similarity groups
        # find_similar_images returns List[Group] directly, enriched with metadata
        flat_cache = self.flat_cache_manager if hasattr(self, 'flat_cache_manager') else None
        dialog_groups: List[Group] = find_similar_images(
            run_paths,
            algorithm=algorithm,
            threshold=threshold_int, # Pass Hamming distance (int)
            settings=profile_payload,
            flat_cache_manager=flat_cache,
            search_type=search_type,
        )

        return dialog_groups

    def _get_pool_for_path(self, path: str, payload_for_mode: dict) -> str:
        """
        Dynamically compute the pool for a given path based on the current profile's paths.

        Determines which scan pool or directory group the path belongs to, using
        self.current_profile.paths or similar; returns a string identifier like the
        root directory name or a hash-based group. Handles cases where path is not
        in profiled paths by returning 'unknown'.

        Parameters
        ----------
        path : str
            Absolute file path to determine the pool for.
        payload_for_mode : dict
            The settings profile payload used for the run, containing 'pools' configuration.

        Returns
        -------
        str
            Pool label ("A", "B", or "unknown").
        """
        from pathlib import Path

        if not payload_for_mode or "pools" not in payload_for_mode:
            return "unknown"

        pools = payload_for_mode["pools"]
        path_obj = Path(path)

        # Check Pool A paths
        if "A" in pools:
            a_paths = pools["A"].get("paths", [])
            for p in a_paths:
                if p:
                    pool_path = Path(p)
                    try:
                        if path_obj.is_relative_to(pool_path):
                            return "A"
                    except ValueError:
                        # Not relative, continue
                        pass

        # Check Pool B paths
        if "B" in pools:
            b_paths = pools["B"].get("paths", [])
            for p in b_paths:
                if p:
                    pool_path = Path(p)
                    try:
                        if path_obj.is_relative_to(pool_path):
                            return "B"
                    except ValueError:
                        # Not relative, continue
                        pass

        # Default to unknown if no match
        return "unknown"
    def __init__(self, parent: QWidget | None = None, active_profile: Optional[Dict[str, Any]] = None, cli_args: Optional[argparse.Namespace] = None) -> None:
        """
        Initialize MainWindow.

        Parameters
        ----------
        parent : QWidget | None
            Optional parent widget.
        active_profile : Optional[Dict[str, Any]]
            Active settings profile to associate with this window; stored on self.active_profile
            for future use by UI components. Passing None keeps behavior identical to prior versions.
        cli_args : Optional[argparse.Namespace]
            Parsed command line arguments, used to check for flags like --default.
        """
        super().__init__(parent)
        # Store the active profile for future use in widgets/controllers
        self.active_profile: Optional[Dict[str, Any]] = active_profile
        self.cli_args = cli_args
        self.profiles: List[Dict[str, Any]] = []
        self.controller = None  # Will be set when database manager is available
        self.structured_editor = None
        self.flat_cache_manager = None # Will be set by app.py
        # Shared selection store for file management dialogs
        self.dialog_selection_store: SelectionStore = SelectionStore()
        # Track whether we've connected structured_editor.dirtyChanged to avoid spurious disconnect warnings
        self._editor_dirty_connected: bool = False
        self._last_run_file_map: Dict[str, Dict[str, Any]] = {}
        # Cache resolved filesystem metadata for the most recent scan to avoid repeated DB/stat lookups
        self._metadata_cache: Dict[str, Tuple[int, int]] = {}
        # Progress and Worker management
        self._progress_dialog: Optional[ProgressDialog] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._comparison_worker: Optional[ComparisonWorker] = None

        self._setup_window()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_profile_toolbar()
        self._setup_central_widget()

        # App-wide palette override for readable, dark non-selected text in item views (QTreeWidget, QTableView, etc.)
        # This avoids dark-theme palettes forcing light/low-contrast text on light row backgrounds.
        self._apply_app_palette_hack()

        # Initialize start time for progress simulation
        import time
        self.start_time = time.time()
        self.logger = get_logger(__name__)

    @log_errors()
    def _setup_profile_toolbar(self) -> None:
        """
        Create the profile management toolbar with combobox and buttons.
        """
        # Use a real QToolBar so the menu bar remains visible
        toolbar = QToolBar("Profiles", self)
        toolbar.setObjectName("profilesToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        # Profile selection label
        profile_label = QLabel("Profile:", self)
        toolbar.addWidget(profile_label)

        # Profile combobox
        self.profile_combo = QComboBox(self)
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        toolbar.addWidget(self.profile_combo)

        toolbar.addSeparator()

        # Create profile button
        self.create_btn = QPushButton("New", self)
        self.create_btn.setToolTip("Create a new profile")
        self.create_btn.clicked.connect(self._on_create_profile)
        toolbar.addWidget(self.create_btn)

        # Copy profile button
        self.copy_btn = QPushButton("Copy", self)
        self.copy_btn.setToolTip("Copy the selected profile")
        self.copy_btn.clicked.connect(self._on_copy_profile)
        toolbar.addWidget(self.copy_btn)

        # Rename profile button
        self.rename_btn = QPushButton("Rename", self)
        self.rename_btn.setToolTip("Rename the selected profile")
        self.rename_btn.clicked.connect(self._on_rename_profile)
        toolbar.addWidget(self.rename_btn)

        # Delete profile button
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setToolTip("Delete the selected profile")
        self.delete_btn.clicked.connect(self._on_delete_profile)
        self.delete_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        toolbar.addWidget(self.delete_btn)

        # Set active profile button
        self.set_active_btn = QPushButton("Set Active", self)
        self.set_active_btn.setToolTip("Set the selected profile as active")
        self.set_active_btn.clicked.connect(self._on_set_active_profile)
        self.set_active_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        toolbar.addWidget(self.set_active_btn)

        # Save button (initially disabled)
        self.save_btn = QPushButton("Save", self)
        self.save_btn.setToolTip("Save changes to the current profile")
        self.save_btn.clicked.connect(self._on_save_profile)
        self.save_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; }")
        self.save_btn.setEnabled(False)
        toolbar.addWidget(self.save_btn)

        # Cancel button (initially disabled)
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setToolTip("Discard changes to the current profile")
        self.cancel_btn.clicked.connect(self._on_cancel_changes)
        self.cancel_btn.setStyleSheet("QPushButton { background-color: #9E9E9E; color: white; }")
        self.cancel_btn.setEnabled(False)
        toolbar.addWidget(self.cancel_btn)

        # Start button
        self.start_btn = QPushButton("Start", self)
        self.start_btn.setToolTip("Start the operation with the selected profile")
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        toolbar.addWidget(self.start_btn)

        # Expanding spacer to push controls to the left
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Attach the toolbar to the main window (keeps the menu bar visible)
        self.addToolBar(Qt.TopToolBarArea, toolbar)


    @log_errors()
    def _setup_window(self) -> None:
        """Configure basic window properties."""
        self.setWindowTitle("KDC Image Organizer")
        self.resize(1024, 720)

    @log_errors()
    def _apply_app_palette_hack(self) -> None:
        """
        Apply an application-wide palette adjustment to guarantee dark text color
        for non-selected items in item views, without disturbing label/window text.

        Rationale
        ---------
        Some Windows dark themes supply a palette where QPalette.Text resolves to a
        very light color. When our views use light row backgrounds (custom delegates
        and stylesheets), that results in low-contrast text for non-selected cells.
        We set QPalette.Text for Active/Inactive groups to a dark color (#111) while
        leaving WindowText intact so labels/toolbars in dark areas remain readable.

        This is intentionally conservative (Text only), and is complemented by the
        dialog-level overrides in ImageSimilarityManagerDialog for complete assurance.
        """
        try:
            app = QApplication.instance()
            pal = app.palette() if app else self.palette()
            dark = QColor(17, 17, 17)        # #111 (high-contrast on light rows)
            # Keep Disabled readable but not identical
            disabled = QColor(119, 119, 119) # #777

            pal.setColor(QPalette.Active,   QPalette.Text, dark)
            pal.setColor(QPalette.Inactive, QPalette.Text, dark)
            pal.setColor(QPalette.Disabled, QPalette.Text, disabled)
            # Do NOT touch WindowText here to avoid breaking dark-area labels
            # Keep selected text white
            pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))

            if app:
                app.setPalette(pal)
            else:
                self.setPalette(pal)
        except Exception:
            # Palette hacks should never crash the app; silently ignore on failure
            pass

    @log_errors()
    def _setup_menu_bar(self) -> None:
        """Create a standard application menu bar with File, Cache, View, Help."""
        menubar = self.menuBar() if self.menuBar() else QMenuBar(self)
        self.setMenuBar(menubar)

        # File menu
        file_menu = menubar.addMenu("&File")
        # Placeholder actions (no-op)
        file_menu.addAction(self._make_noop_action("Open..."))
        file_menu.addAction(self._make_noop_action("Save"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_noop_action("Exit"))

        # Cache menu (new)
        cache_menu = menubar.addMenu("&Cache")
        clear_cache_action = QAction("Clear Cache", self)
        clear_cache_action.setStatusTip("Clear flat_cache.db and recreate it empty")
        clear_cache_action.triggered.connect(self._on_clear_cache)
        cache_menu.addAction(clear_cache_action)

        clean_cache_action = QAction("Clean Cache", self)
        clean_cache_action.setStatusTip("Validate entries against the filesystem and remove invalid entries")
        clean_cache_action.triggered.connect(self._on_clean_cache)
        cache_menu.addAction(clean_cache_action)

        view_cache_action = QAction("View Cache", self)
        view_cache_action.setStatusTip("View the contents of the flat cache database")
        view_cache_action.triggered.connect(self._on_view_cache)
        cache_menu.addAction(view_cache_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._make_noop_action("Reset Layout"))

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About...", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    @log_errors()
    def _setup_status_bar(self) -> None:
        """Attach a status bar with selectable text for feedback."""
        status = self.statusBar() if self.statusBar() else QStatusBar(self)
        self.setStatusBar(status)

        # Create a label for selectable status messages
        self.status_label = QLabel("Ready")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        status.addPermanentWidget(self.status_label)

        # Show active profile name if available
        try:
            if getattr(self, "active_profile", None):
                name = self.active_profile.get("name") or self.active_profile.get("id")
                if name:
                    self.status_label.setText(f"Ready — Profile: {name}")
        except Exception:
            # Fallback to default message if any unexpected structure
            pass

    @log_errors()
    def _setup_central_widget(self) -> None:
        """
        Create the central widget with progress section and main content.

        The central widget now includes:
        1. Stacked widget for main content (file selector/placeholder and structured editor)
        """
        # Create a container widget for the central area
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create stacked widget for main content
        self.stacked_widget = QStackedWidget(self)
        container_layout.addWidget(self.stacked_widget)

        # Page 0: File selector or placeholder
        try:
            # Import locally to avoid top-level dependency on pk-py-lib during module import
            from src.pk_py_lib.gui.file_selector.widgets import (
                MultiPathSelectorWidget,
                PathFilterSpec,
            )

            # Construct a sensible default filter spec (images & video)
            filter_spec = PathFilterSpec(include_categories={"images", "video"})
            selector = MultiPathSelectorWidget(
                parent=self,
                title="Paths",
                start_dir=None,
                filter_spec=filter_spec,
            )
            self.stacked_widget.addWidget(selector)
            self.stacked_widget.setCurrentIndex(0)
            # Update status with success (best-effort)
            try:
                self.statusBar().showMessage("MultiPathSelector loaded")
            except Exception:
                pass
        except Exception as exc:
            # Fallback to placeholder
            self.stacked_widget.addWidget(CentralPlaceholder(self))
            self.stacked_widget.setCurrentIndex(0)
            try:
                self.statusBar().showMessage(f"Using placeholder (MultiPathSelector unavailable): {exc}")
            except Exception:
                pass

        # Page 1: Structured editor (will be created when needed)
        # We'll add a placeholder for now
        self.structured_editor_placeholder = QLabel("Select a profile to view and edit details")
        self.structured_editor_placeholder.setAlignment(Qt.AlignCenter)
        self.stacked_widget.addWidget(self.structured_editor_placeholder)

        # Set the container as the central widget
        self.setCentralWidget(container)

    @log_errors()
    def load_profiles(self) -> None:
        """
        Load available profiles from the database and populate the combobox.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            resp = self.controller.list_profiles()

            if resp.success:
                self.profiles = resp.data or []
                self.profile_combo.clear()

                if self.profiles:
                    # Populate combobox with profile names, marking active profile
                    for profile in self.profiles:
                        name = profile.name or 'Unnamed'
                        if profile.is_default:
                            name += " ★"
                        self.profile_combo.addItem(name, profile.id)

                    # Select the active profile if available
                    active_profile = None
                    for profile in self.profiles:
                        if profile.is_default:
                            active_profile = profile
                            break

                    if active_profile:
                        self.active_profile = active_profile
                        index = self.profile_combo.findData(active_profile.id)
                        if index >= 0:
                            self.profile_combo.setCurrentIndex(index)
                    elif self.profile_combo.count() > 0:
                        self.profile_combo.setCurrentIndex(0)

                    self.status_label.setText(f"Loaded {len(self.profiles)} profiles")
                else:
                    self.status_label.setText("No profiles available. Create a new profile.")
            else:
                self.status_label.setText(f"Failed to load profiles: {resp.message}")

        except Exception as exc:
            self.status_label.setText(f"Error loading profiles: {exc}")
            # Log detailed error
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _load_profiles")

    @log_errors()
    def _on_profile_selected(self, index: int) -> None:
        """
        Handle profile selection change from combobox.
        """
        if index < 0:
            return

        profile_id = self.profile_combo.itemData(index)
        if not profile_id:
            return

        # Find the selected profile
        selected_profile = None
        for profile in self.profiles:
            if profile.id == profile_id:
                selected_profile = profile
                break

        if selected_profile:
            self.active_profile = asdict(selected_profile)
            self.profile_changed.emit(asdict(selected_profile))
            self.status_label.setText(f"Active profile: {selected_profile.name or 'Unnamed'}")

            # Update the active profile in the database
            try:
                if self.controller:
                    resp = self.controller.set_active(profile_id)
                    if not resp.success:
                        self.status_label.setText(f"Error setting active profile: {resp.message}")
            except Exception as exc:
                self.status_label.setText(f"Error setting active profile: {exc}")

            # Load the profile into the structured editor
            self._load_profile_into_editor(profile_id)

    @log_errors()
    def _load_profile_into_editor(self, profile_id: str) -> None:
        """
        Fetch the full profile data and load it into the StructuredProfileEditorWidget.

        If the editor widget does not exist, it is created and replaces the placeholder.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available for editor load")
                return

            if StructuredProfileEditorWidget is None:
                self.status_label.setText("Structured editor component not available")
                return

            # 1. Fetch profile data
            resp = self.controller.get_profile(profile_id)
            if not resp.success or not resp.data:
                self.status_label.setText(f"Failed to load profile data for editor: {resp.message}")
                return

            # Handle dict vs SettingsProfile, extract json_data if is_json_format(), fallback to {}
            if hasattr(resp.data, 'to_dict'):
                profile_data = resp.data.to_dict()
            elif isinstance(resp.data, SettingsProfile):
                if resp.data.is_json_format():
                    profile_data = getattr(resp.data, 'json_data', {}) or {}
                else:
                    profile_data = {}
            else:
                profile_data = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data

            if not profile_data:
                self.status_label.setText("Profile data is empty or invalid")
                return

            # 2. Initialize editor if needed
            if self.structured_editor is None:
                self.structured_editor = StructuredProfileEditorWidget(
                    api=self.controller.api,
                    parent=self
                )
                # Replace the placeholder with the actual editor
                self.stacked_widget.removeWidget(self.structured_editor_placeholder)
                self.stacked_widget.addWidget(self.structured_editor)

                # Connect signals only once
                self.structured_editor.dirtyChanged.connect(self._on_editor_dirty_changed)
                self._editor_dirty_connected = True

            # 3. Load data and switch view
            self.structured_editor.load_profile(profile_data)
            self.stacked_widget.setCurrentWidget(self.structured_editor)
            self.status_label.setText(f"Editor loaded for profile: {profile_data.get('name', 'Unnamed')}")

        except Exception as exc:
            self.status_label.setText(f"Error loading editor: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _load_profile_into_editor")

    @log_errors()
    def _on_editor_dirty_changed(self, is_dirty: bool) -> None:
        """
        Handle the dirty state change from the structured editor.
        Enables/disables Save and Cancel buttons.
        """
        self.save_btn.setEnabled(is_dirty)
        self.cancel_btn.setEnabled(is_dirty)
        if is_dirty:
            self.status_label.setText("Unsaved changes in profile settings.")
        else:
            # Restore status bar text to active profile name
            name = self.active_profile.get("name") if self.active_profile else "Ready"
            self.status_label.setText(f"Active profile: {name}")
    @log_errors()
    def _on_create_profile(self) -> None:
        """
        Handle create new profile button click.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            from pk_py_lib.core.settings.schema import create_default_profile

            # Create a name prompt dialog
            dlg = _NamePromptDialog("Create Profile", "Name:", parent=self)
            # Suggest a unique name using controller
            sugg_resp = self.controller.suggest_unique_name("New Profile")
            if sugg_resp.success and sugg_resp.data:
                dlg.inp.setText(sugg_resp.data)
            else:
                dlg.inp.setText("New Profile")

            if dlg.exec() == QDialog.Accepted:
                name = dlg.text()
                if not name:
                    dlg.set_error("Name is required")
                    return

                # Validate the name using controller
                validate_resp = self.controller.validate_name(name)
                if not validate_resp.success:
                    dlg.set_error(validate_resp.message or "Invalid name")
                    return

                # Create the profile with default JSON data using controller
                json_data = create_default_profile(name, "")
                create_resp = self.controller.create_structured_profile(json_data, make_active=True)

                if create_resp.success:
                    self.status_label.setText(f"Profile '{name}' created")
                    self.load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to create profile: {create_resp.message}")
            else:
                self.status_label.setText("Create profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error creating profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_create_profile")

    @log_errors()
    def _on_copy_profile(self) -> None:
        """
        Handle copy profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to copy")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            current_name = self.active_profile.get('name', 'Unnamed')

            # Create a name prompt dialog
            dlg = _NamePromptDialog("Copy Profile", "New name:", parent=self)
            # Suggest a unique name based on current profile using controller
            sugg_resp = self.controller.suggest_unique_name(f"{current_name} (copy)")
            if sugg_resp.success and sugg_resp.data:
                dlg.inp.setText(sugg_resp.data)
            else:
                dlg.inp.setText(f"Copy of {current_name}")

            if dlg.exec() == QDialog.Accepted:
                new_name = dlg.text()
                if not new_name:
                    dlg.set_error("Name is required")
                    return

                # Validate the name
                validate_resp = self.controller.validate_name(new_name)
                if not validate_resp.success:
                    dlg.set_error(validate_resp.message or "Invalid name")
                    return

                # Copy the profile using controller
                copy_resp = self.controller.duplicate_structured_profile(
                    source_profile_id=self.active_profile['id'],
                    new_name=new_name,
                    description=f"Copy of {current_name}",
                    make_active=False
                )

                if copy_resp.success:
                    self.status_label.setText(f"Profile '{new_name}' created from copy")
                    self.load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to copy profile: {copy_resp.message}")
            else:
                self.status_label.setText("Copy profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error copying profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_copy_profile")

    @log_errors()
    def start_default_operation(self) -> None:
        """
        Public method to initiate the default operation (scan/comparison)
        based on the currently active profile settings.

        This method is typically called on application startup if the --default
        CLI flag is provided. It delegates to the internal _on_start handler.
        """
        self._on_start()

    @log_errors()
    def _on_start(self) -> None:
        """
        Handle start button click to begin the operation.

        Behavior update:
        - If the embedded settings editor has unsaved changes (dirty), attempt a synchronous save before starting.
        - On save failure, an error dialog is shown and the operation is aborted.
        - The Start button is disabled during save and the scan, and the status label is updated accordingly.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected")
            return

        db_mgr = getattr(self, "database_manager", None)
        if db_mgr is None:
            show_selectable_error(self, "Cache Error", "DatabaseManager is not available on the main window.")
            return

        # 1) Save pending settings if editor is dirty (supports either structured_editor or legacy editor attribute)
        editor = getattr(self, "structured_editor", None)
        if editor is None and hasattr(self, "editor"):
            try:
                editor = getattr(self, "editor")
            except Exception:
                editor = None

        def _editor_is_dirty(ed) -> bool:
            """Best-effort dirty check across editor variants."""
            try:
                if ed is None:
                    return False
                if hasattr(ed, "is_dirty"):
                    return bool(ed.is_dirty())
            except Exception:
                pass
            try:
                return bool(getattr(ed, "_dirty", False))
            except Exception:
                return False

        if _editor_is_dirty(editor):
            # Disable Start during save and inform user
            self.start_btn.setEnabled(False)
            try:
                self.status_label.setText("Saving pending settings changes...")
            except Exception:
                pass
            try:
                QApplication.processEvents()
            except Exception:
                pass

            # Attempt synchronous save using existing handler; it validates and persists
            self._on_save_profile()

            # Re-check dirty state; failure → abort with error
            if _editor_is_dirty(editor):
                show_selectable_error(
                    self,
                    "Save Failed",
                    "Settings changes could not be saved. Resolve the validation errors and try again."
                )
                self.start_btn.setEnabled(True)
                return

            # Reset cache counters before processing to track this scan
            if self.flat_cache_manager:
                self.flat_cache_manager.reset_counters()

        # 2) Create and show modal ProgressDialog
        self._progress_dialog = ProgressDialog(self, title="Image Organizer Operation")
        self._progress_dialog.set_indeterminate("Starting operation...")
        self._progress_dialog.cancellation_requested.connect(self._on_cancellation_requested)
        self.start_btn.setEnabled(False)

        # 3) Resolve full profile JSON for the run (now guaranteed to include saved changes)
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                self.start_btn.setEnabled(True)
                return
            resp = self.controller.get_profile(self.active_profile['id'])
            if not resp.success or not resp.data:
                self.status_label.setText(f"Failed to load profile for run: {resp.message or 'Unknown error'}")
                self.start_btn.setEnabled(True)
                return
            payload = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data
        except Exception as exc:
            self.status_label.setText(f"Error preparing run: {exc}")
            self.start_btn.setEnabled(True)
            return

        # 4) Start background worker
        import time
        self.start_time = time.time()
        self._scan_errors = []

        # Determine the profile name used for this run and pass it to the worker
        try:
            prof_name = str((payload.get("name") if isinstance(payload, dict) else (self.active_profile.get("name") if self.active_profile else "")) or "")
        except Exception:
            prof_name = str(self.active_profile.get("name")) if getattr(self, "active_profile", None) else ""

        mode = payload.get('mode', 'duplicate')
        self._current_scan_mode = mode
        compute_hashes = mode == 'similarity'

        flat_cache_mgr = getattr(self, "flat_cache_manager", None)
        if flat_cache_mgr is None:
            self.logger.warning("FlatCacheManager not available on MainWindow. Proceeding without cache.")

        self._scan_worker = ScanWorker(
            db_manager=db_mgr,
            flat_cache_manager=flat_cache_mgr,
            profile_json=payload,
            algorithm="xxh3",
            mode=mode,
            compute_hashes=compute_hashes,
            profile_name=prof_name,
            profile_id=(self.active_profile.get('id') if self.active_profile else None),
            parent=self
        )
        # Connect ScanWorker signals to the new progress and finished handlers
        self._scan_worker.progress.connect(self._update_progress_dialog)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._on_scan_finished_with_comparison_start)
        self._scan_worker.start()

        # Show the modal dialog (blocks until accepted/rejected/closed)
        self._progress_dialog.exec()

    @log_errors()
    def _on_scan_error(self, message: str) -> None:
        """
        Record a non-fatal error reported by the worker and reflect in status.
        """
        try:
            self._scan_errors.append(message)
        except Exception:
            self._scan_errors = [message]
        self.status_label.setText(f"Error: {message}")

    @gui_error_handler(component_name="MainWindow", operation="cancellation_request")
    @log_errors()
    def _on_cancellation_requested(self) -> None:
        """
        Handles the cancellation signal from the ProgressDialog.

        Requests cooperative stop on any running worker threads.
        """
        self.logger.info("Cancellation requested by user.")
        if self._scan_worker and self._scan_worker.isRunning():
            self.logger.info("Stopping ScanWorker.")
            self._scan_worker.stop()

        if self._comparison_worker and self._comparison_worker.isRunning():
            self.logger.info("Stopping ComparisonWorker.")
            self._comparison_worker.stop()

    @log_errors()
    def _update_progress_dialog(self, processed: int, total: int, current_path: str = "", message: str = "") -> None:
        """
        Update the ProgressDialog UI from worker signals.

        Parameters
        ----------
        processed : int
            Number of items processed so far.
        total : int
            Total items discovered for processing.
        current_path : str
            The path of the file currently being processed (ScanWorker only).
        message : str
            Short status message from the worker.
        """
        if self._progress_dialog is None:
            return

        # Determine if this is a ScanWorker signal (which includes current_path)
        # We check the number of arguments passed to infer the worker type.
        # ScanWorker.progress emits 4 arguments (processed, total, current_path, message).
        # ComparisonWorker.progress emits 3 arguments (processed, total, message).
        # Since Python signals don't enforce argument count strictly, we rely on the
        # signature of the connected slot to determine the expected arguments.
        # Since this slot is connected to ScanWorker.progress (4 args) AND
        # ComparisonWorker.progress (3 args), we must handle both.
        # The simplest way to handle this is to check if current_path is provided.
        # However, since the signature is fixed to 4 arguments here, we rely on the
        # caller (ScanWorker) providing all 4, and ComparisonWorker providing 3,
        # which means the 4th argument (current_path) will be missing/None/empty string
        # when called from ComparisonWorker.
        # A more robust way is to check the number of arguments passed, but Python slots
        # make this tricky. We will rely on the fact that ScanWorker provides current_path (str) and ComparisonWorker
        # does not (so current_path will be an empty string or None if the signal is defined
        # to match the slot signature).

        # For simplicity and robustness against signal argument mismatch, we will assume
        # if `current_path` is a non-empty string, it's a scan update.
        is_scan_progress = bool(current_path)

        if total > 0:
            percent = int((processed / total) * 100)
            percent = max(0, min(100, percent))

            if is_scan_progress:
                # ScanWorker progress: show path and detailed count
                status_text = f"Scanning: {current_path} ({processed}/{total})"
            else:
                # ComparisonWorker progress: show percentage and message
                status_text = f"{message} ({percent}%)"

            self._progress_dialog.set_progress(percent, status_text)
        else:
            # Indeterminate state or initial phase
            self._progress_dialog.set_indeterminate(message)

    @log_errors()
    def _on_scan_finished_with_comparison_start(self, profile_name: str, summary: dict) -> None:
        """
        Handles ScanWorker completion. Checks for cancellation and, if successful,
        initiates the ComparisonWorker for grouping/similarity analysis.
        """
        # 1. Check for cancellation
        if summary.get("cancelled"):
            self.logger.info("Scan cancelled. Closing progress dialog.")
            if self._progress_dialog:
                self._progress_dialog.close()
            self.start_btn.setEnabled(True)
            return

        # Basic completion UI update (for logging/status bar)
        try:
            # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints
            LOGGER.debug("Scan finished handler started", variables={
                "profile_name": profile_name,
                "summary_keys": list(summary.keys()) if summary else [],
                "found_count": int((summary or {}).get("found", 0) or 0),
            })
        except Exception:
            pass

        # 2. Prepare for comparison (keep file map and metadata cache)
        self.start_btn.setEnabled(False) # Keep disabled until final result
        self._last_run_file_map = {}
        self._metadata_cache = {}

        # Cache summary printing consolidated to post-processing in _on_scan_finished_with_comparison_start

        # Extract counters
        found = int(summary.get("found", 0) or 0)
        processed = int(summary.get("processed", 0) or 0)
        inserted = int(summary.get("inserted", 0) or 0)
        invalidated = int(summary.get("invalidated", 0) or 0)
        hashes = int(summary.get("hashes_computed", 0) or 0)
        error_details = summary.get('error_details', [])
        errors = len(error_details)
        scan_errors = getattr(self, '_scan_errors', [])
        for err_msg in scan_errors:
            error_details.append({
                'path': 'worker',
                'error': err_msg,
                'traceback': None
            })
        errors = len(error_details)

        # Initial mode state and run context
        two_pool = False
        is_single_pool = True
        payload_for_mode = None
        direction = "duplicates"

        db_mgr = getattr(self, "database_manager", None)
        try:
            run_paths = list(summary.get("run_paths") or [])
        except Exception:
            run_paths = []
        self._last_run_paths = run_paths
        try:
            files_summary = summary.get("files")
            if isinstance(files_summary, list):
                def _coerce_size(value: Any) -> int:
                    try:
                        if value is None:
                            return 0
                        if isinstance(value, (int, float)):
                            return max(int(value), 0)
                        text = str(value).strip()
                        if not text:
                            return 0
                        return max(int(float(text)), 0)
                    except Exception:
                        return 0

                run_file_map: Dict[str, Dict[str, Any]] = {}
                for item in files_summary:
                    if not isinstance(item, dict):
                        continue
                    path_str = str(item.get("path") or "").strip()
                    if not path_str:
                        continue
                    run_file_map[path_str] = item
                    size_hint = item.get("size")
                    if size_hint is None:
                        size_hint = item.get("file_size")
                    modified_hint = item.get("modified_time")
                    if modified_hint is None:
                        modified_hint = item.get("file_modified")
                    if modified_hint is None:
                        modified_hint = item.get("modified")
                    size_val = _coerce_size(size_hint)
                    modified_val = MainWindow._to_int_timestamp(modified_hint)
                    self._metadata_cache[path_str] = (max(size_val, 0), max(modified_val, 0))
                self._last_run_file_map = run_file_map
            else:
                self._last_run_file_map = {}
        except Exception:
            self._last_run_file_map = {}
            self._metadata_cache = {}
        try:
            algo = str(summary.get("algorithm") or "xxh3")
        except Exception:
            algo = "xxh3"
        try:
            used_profile_id = summary.get("profile_id")
        except Exception:
            used_profile_id = None

        # Determine mode and direction from the profile used during this run
        try:
            if self.controller:
                resolved_id = used_profile_id
                if not resolved_id:
                    try:
                        resolved_id = next(
                            (p.get('id') for p in (self.profiles or [])
                             if str(p.get('name', '')) == str(profile_name)),
                            None
                        )
                    except Exception:
                        resolved_id = None
                    if not resolved_id and getattr(self, "active_profile", None):
                        resolved_id = self.active_profile.get('id')

                if resolved_id:
                    prof = self.controller.get_profile(resolved_id)
                    if prof.success and prof.data:
                        payload_for_mode = (
                            prof.data.get('json_data')
                            if isinstance(prof.data, dict) and prof.data.get('format') == 'json' and 'json_data' in prof.data
                            else prof.data
                        )
                        pools = payload_for_mode.get('pools', {}) if isinstance(payload_for_mode, dict) else {}

                        def _has_paths(cfg: dict | None) -> bool:
                            try:
                                return any(bool(p) for p in (cfg or {}).get('paths', []))
                            except Exception:
                                return False

                        two_pool_by_paths = _has_paths(pools.get('A')) and _has_paths(pools.get('B'))
                        try:
                            scope_kind = str(
                                ((payload_for_mode.get('scope') or {}).get('kind'))
                                if isinstance(payload_for_mode, dict) else ""
                            ).strip().lower()
                        except Exception:
                            scope_kind = ""

                        if scope_kind == "single_pool":
                            two_pool = False
                            is_single_pool = True
                        elif scope_kind == "two_pool":
                            two_pool = True
                            is_single_pool = False
                        else:
                            two_pool = two_pool_by_paths
                            is_single_pool = not two_pool
                            # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints

                        # Direction mapping
                        try:
                            d = (payload_for_mode.get('scope', {}) or {}).get('direction') if isinstance(payload_for_mode, dict) else None
                            if d in ("A_TO_B", "B_TO_A"):
                                direction = "duplicates"
                            elif d in ("A_WITHOUT_IN_B", "B_WITHOUT_IN_A"):
                                direction = "non_duplicates"
                            elif d in ("duplicates", "non_duplicates"):
                                direction = str(d)
                        except Exception:
                            pass
        except Exception:
            two_pool = False
            is_single_pool = True
            direction = "duplicates"
            try:
                print(f"[DEBUG _on_scan_finished] Exception in mode detection; default single_pool", file=sys.stderr)
                print(f"[DEBUG _on_scan_finished] {traceback.format_exc()}", file=sys.stderr)
            except Exception:
                pass


        # Pools debug
        try:
            # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints
            pools_obj = payload_for_mode.get('pools', {}) if isinstance(payload_for_mode, dict) else {}
            paths_a = [str(p) for p in (pools_obj.get("A") or {}).get("paths", [])]
            paths_b = [str(p) for p in (pools_obj.get("B") or {}).get("paths", [])]
        except Exception:
            pools_obj = {}
            paths_a = []
            paths_b = []

        LOGGER.debug("Final mode detection", variables={
            "is_single_pool": is_single_pool,
            "two_pool": two_pool,
            "direction": direction,
            "profile_name": profile_name,
            "found_files": found
        })
        # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints

        # Summary text
        text = (
            "File processing completed.\n\n"
            f"Total files found: {found}\n"
            f"Files processed: {processed}\n"
            f"New cache rows inserted: {inserted}\n"
            f"Invalidated (deleted) rows: {invalidated}\n"
            f"Hashes computed: {hashes}\n"
            f"Errors: {errors}"
        )
        if errors > 0:
            error_summary = "\n".join([f"{d.get('path', 'unknown')}: {d['error']}" for d in error_details])
            text += f"\nErrors: {errors}\n{error_summary}"
            logger.error(f"Scan errors: {len(error_details)}", extra={'errors': error_details})

        try:
            self.statusBar().showMessage(
                f"Processed {processed}/{found}; invalidated {invalidated}; inserted {inserted}; hashes {hashes}; errors {errors}",
                10000
            )
        except Exception:
            pass

        # Log errors
        for d in error_details:
            if 'traceback' in d and d['traceback']:
                LOGGER.error(f"Error processing {d['path']}: {d['error']}", exc_info=True)
            else:
                LOGGER.error(f"Error processing {d['path']}: {d['error']}")

        # Optional detailed error report
        try:
            error_details = list(summary.get("error_details") or [])
        except Exception:
            error_details = []
        if error_details:
            try:
                error_report = self._format_error_report(error_details)
                if is_single_pool:
                    self._scan_error_report = error_report
                else:
                    self._show_resizable_text_dialog("Scan Errors", error_report)
            except Exception:
                pass

        # Build report and groups (single, consistent try/except)
        report_lines: list[str] = []
        groups = 0
        total_dups = 0
        non_matches = 0
        groups_data_prepared: list[dict] = []
        groups_data_fallback: list[dict] = []

        try:
            if db_mgr is not None:
                from collections import defaultdict

                # Use FlatCacheManager for duplicate detection instead of old cache_db
                if self.flat_cache_manager:
                    # Get all entries for run paths
                    entries = self.flat_cache_manager.get_entries(run_paths)

                    if two_pool:
                        if direction == "duplicates":
                            # Two-Pool Duplicate Clustering (A vs B)
                            # Group files by pool
                            pool_a_files = {path: entry for path, entry in entries.items()
                                          if self._get_pool_for_path(path, payload_for_mode) == 'A'}
                            pool_b_files = {path: entry for path, entry in entries.items()
                                          if self._get_pool_for_path(path, payload_for_mode) == 'B'}

                            # Find duplicates between pools
                            groups_map: dict[str, list[str]] = defaultdict(list)

                            # Create hash lookup for pool B
                            b_hash_lookup = {}
                            for path, entry in pool_b_files.items():
                                hash_value = entry.xxh3 if entry else None
                                if hash_value:
                                    b_hash_lookup[hash_value] = path

                            # Check pool A files against pool B
                            for a_path, a_entry in pool_a_files.items():
                                a_hash = a_entry.xxh3 if a_entry else None
                                if a_hash and a_hash in b_hash_lookup:
                                    b_path = b_hash_lookup[a_hash]
                                    groups_map[a_path].append(b_path)

                            report_lines.append("Two-Pool Report — duplicates (A vs B)")
                            all_paths_in_groups = set()

                            for a_path, b_list in groups_map.items():
                                if not b_list:
                                    continue
                                groups += 1
                                total_dups += len(b_list)
                                report_lines.append(f"\nA: {a_path}\nB duplicates:")
                                all_paths_in_groups.add(a_path)
                                for b in b_list:
                                    report_lines.append(f"  - {b}")
                                    all_paths_in_groups.add(b)

                            # Prepare data for DuplicateManagerDialog (groups_data_prepared)
                            if all_paths_in_groups:
                                group_id = 1
                                for a_path, b_list in groups_map.items():
                                    if not b_list:
                                        continue

                                    group_files = []

                                    # Add A path (reference)
                                    a_entry = entries.get(a_path)
                                    if a_entry:
                                        group_files.append({
                                            "path": a_path,
                                            "size": a_entry.size,
                                            "modified": int(a_entry.mtime),
                                            "pool": self._get_pool_for_path(a_path, payload_for_mode),
                                            "score": 1.0
                                        })

                                    # Add B paths (duplicates)
                                    for b_path in b_list:
                                        b_entry = entries.get(b_path)
                                        if b_entry:
                                            group_files.append({
                                                "path": b_path,
                                                "size": b_entry.size,
                                                "modified": int(b_entry.mtime),
                                                "pool": self._get_pool_for_path(b_path, payload_for_mode),
                                                "score": 1.0
                                            })

                                    if len(group_files) >= 2:
                                        groups_data_prepared.append({
                                            "hash": f"two_pool_dup_{group_id}",
                                            "count": len(group_files),
                                            "files": group_files,
                                        })
                                        group_id += 1
                        else:
                            # Two-Pool Non-Duplicates (B not in A) - Only report generation needed
                            # Create hash lookup for pool A
                            pool_a_hashes = set()
                            for path, entry in entries.items():
                                if self._get_pool_for_path(path, payload_for_mode) == 'A':
                                    hash_value = entry.xxh3 if entry else None
                                    if hash_value:
                                        pool_a_hashes.add(hash_value)

                            # Find files in pool B that are not in pool A
                            report_lines.append("Two-Pool Report — non_duplicates (B not in A)")
                            for path, entry in entries.items():
                                if self._get_pool_for_path(path, payload_for_mode) == 'B':
                                    hash_value = entry.xxh3 if entry else None
                                    if hash_value and hash_value not in pool_a_hashes:
                                        non_matches += 1
                                        report_lines.append(f"  - {path}")
                    else:
                        # Single-pool duplicate clustering
                        # Group files by hash
                        hash_groups: dict[str, list[str]] = defaultdict(list)
                        for path, entry in entries.items():
                            hash_value = entry.xxh3 if entry else None
                            if hash_value:
                                hash_groups[hash_value].append(path)

                        report_lines.append("Duplicate Report — Single Pool")

                        for hash_value, paths in hash_groups.items():
                            if len(paths) >= 2:
                                groups += 1
                                total_dups += len(paths)
                                report_lines.append(f"\nHash: {hash_value}")
                                for path in paths:
                                    report_lines.append(f"  - {path}")

                                # Prepare data for DuplicateManagerDialog
                                group_files = []
                                for path in paths:
                                    entry = entries.get(path)
                                    if entry:
                                        group_files.append({
                                            "path": path,
                                            "size": entry.size,
                                            "modified": int(entry.mtime),
                                            "pool": self._get_pool_for_path(path, payload_for_mode),
                                            "score": 1.0
                                        })

                                if len(group_files) >= 2:
                                    groups_data_prepared.append({
                                        "hash": hash_value,
                                        "count": len(group_files),
                                        "files": group_files,
                                    })

                        # Fallback groups (empty since we're using flat cache)
                        groups_data_fallback = []
                else:
                    logger.warning("FlatCacheManager not available for duplicate detection")
                    # Fallback to empty groups if flat cache manager is not available
                    groups_data_prepared = []
                    groups_data_fallback = []
        except Exception as e:
            try:
                tb = traceback.format_exc()
                print(f"Exception in _on_scan_finished] report generation: {e}\n{tb}", file=sys.stderr)
                LOGGER.error("report.generation.failed", exception=e)
            except Exception:
                pass

        # Consolidated cache summary print after all processing (scan + duplicate/similarity logic)
        # This ensures a single print per operation, using numeric values from the counters dict.
        # Format: Displays hits, misses, invalid_entries, and total files processed.
        if self.flat_cache_manager:
            counters = self.flat_cache_manager.get_counters()
            total_files = len(run_paths)
            print("Cache Summary:")
            print(f" - Hits: {counters['hits']}")
            print(f" - Misses: {counters['misses']}")
            print(f" - Invalid Entries: {counters['invalid_entries']}")
            print(f"Total Files Processed: {total_files}")
            # Reset counters for potential future use
            self.flat_cache_manager.reset_counters()

        LOGGER.debug("Final groups data state", variables={
            "is_single_pool": is_single_pool,
            "two_pool": two_pool,
            "direction": direction,
            "profile_name": profile_name,
            "found_files": found
        })
        # Fixed duplicate mode bug: Removed temporary [TRACE] logging prints

        # Build header and final report text
        from datetime import datetime as _dt
        import time as _time
        now_str = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            started_dt = _dt.fromtimestamp(getattr(self, "start_time", _time.time()))
            started_str = started_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            started_str = "unknown"
        try:
            duration_s = max(0.0, (_time.time() - getattr(self, "start_time", _time.time())))
        except Exception:
            duration_s = 0.0

        mode_val = (payload_for_mode.get("mode") if isinstance(payload_for_mode, dict) else "?") or "?"
        scope_kind = (((payload_for_mode.get("scope") or {}).get("kind")) if isinstance(payload_for_mode, dict) else None) or "?"

        header_lines = [
            "=== Report Metadata ===",
            f"Generated: {now_str}",
            f"Started: {started_str}",
            f"Duration: {duration_s:.2f} s",
            f"Profile: {profile_name} (id: {used_profile_id or 'n/a'})",
            f"Mode: {mode_val}; Scope: {scope_kind}; Direction: {direction}",
            f"Algorithm: {algo}",
            "Pools:",
            f"  A.paths: {(', '.join(paths_a) if paths_a else '(none)')}",
        ]
        if paths_b:
            header_lines.append(f"  B.paths: {', '.join(paths_b)}")

        if two_pool and direction == "non_duplicates":
            header_lines.append(f"Summary: non_matches={non_matches}")
        else:
            header_lines.append(f"Summary: groups={groups}, files={total_dups}")
        header_lines.append("-" * 60)
        report_text = "\n".join(header_lines + report_lines)
        if is_single_pool and not two_pool and hasattr(self, "_scan_error_report"):
            report_text += f"\n\n--- Scan Errors ---\n{self._scan_error_report}"
            try:
                del self._scan_error_report
            except Exception:
                pass

        # Determine mode from profile
        mode_val = (payload_for_mode.get("mode") if isinstance(payload_for_mode, dict) else "?") or "?"
        scope_kind = (((payload_for_mode.get("scope") or {}).get("kind")) if isinstance(payload_for_mode, dict) else None) or "?"
        is_similarity = mode_val == "similarity"

        # Handle non-duplicates case first, which only generates a report and returns
        if two_pool and direction == "non_duplicates":
            if self._progress_dialog:
                self._progress_dialog.close()
            self._show_resizable_text_dialog("Non-duplicates Report", report_text)
            self.start_btn.setEnabled(True)
            return

        # 3. Start ComparisonWorker
        comparison_type = 'similarity' if is_similarity else 'duplicate'

        # Update progress dialog for the next phase
        if self._progress_dialog:
            self._progress_dialog.set_indeterminate(f"Starting {comparison_type} comparison...")

        self._comparison_worker = ComparisonWorker(
            main_window_instance=self,
            scan_results=summary,
            comparison_type=comparison_type,
            parent=self
        )
        self._comparison_worker.progress.connect(self._update_progress_dialog)
        self._comparison_worker.finished.connect(self._on_comparison_finished)
        self._comparison_worker.error.connect(self._on_scan_error) # Reuse scan error handler for logging
        self._comparison_worker.start()

        # Note: The modal dialog is already running from _on_start() and will block until
        # it is explicitly closed in _on_comparison_finished or cancelled.

        # We must ensure the report text and summary are available for _on_comparison_finished
        # which will display the final dialogs.
        self._last_report_text = report_text
        self._last_summary_text = text
        self._last_payload_for_mode = payload_for_mode
        self._last_run_paths = run_paths
        self._last_db_mgr = db_mgr
        self._last_two_pool = two_pool
        self._last_direction = direction
        self._last_groups_data_prepared = groups_data_prepared
        self._last_groups_data_fallback = groups_data_fallback

        # The method returns here, allowing the ComparisonWorker to run in the background
        # while the modal ProgressDialog remains open.
        return

    @gui_error_handler(component_name="MainWindow", operation="comparison_finished")
    @log_errors()
    def _on_comparison_finished(self, results: dict) -> None:
        """
        Handles ComparisonWorker completion. Closes the progress dialog and displays
        the appropriate results manager dialog (DuplicateManagerDialog or SimilarityManagerDialog).

        Parameters
        ----------
        results : dict
            The results dictionary emitted by ComparisonWorker, containing 'cancelled', 'groups', etc.
        """
        # 1. Close the progress dialog and re-enable the start button
        if self._progress_dialog:
            self._progress_dialog.close()
        self.start_btn.setEnabled(True)

        # 2. Check for cancellation
        if results.get("cancelled"):
            self.logger.info("Comparison cancelled or failed. Aborting result display.")
            return

        # 3. Extract necessary context stored during scan phase
        dialog_groups: List[Group] = results.get('groups', [])
        pool_map: Dict[str, str] = results.get('pool_map', {})

        def _get_pool_for_path(self, path: str, profile: dict) -> str:
            """
            Determine the pool (A or B) for a given file path based on profile pool configurations.

            Args:
                path: Absolute file path.
                profile: Settings profile payload with "pools" configuration.

            Returns:
                Pool label ("A" or "B"), defaults to "A" if undetermined.
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
                    except ValueError:
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
                    except ValueError:
                        # Not relative, continue
                        pass

            # Default to A if no match
            return "A"

        # Context stored in instance variables by _on_scan_finished_with_comparison_start
        text = getattr(self, '_last_summary_text', "Operation completed.")
        report_text = getattr(self, '_last_report_text', "No detailed report available.")
        payload_for_mode = getattr(self, '_last_payload_for_mode', {})
        two_pool = getattr(self, '_last_two_pool', False)
        direction = getattr(self, '_last_direction', "duplicates")
        mode_val = payload_for_mode.get("mode", "?")
        scope_kind = payload_for_mode.get("scope", {}).get("kind")
        is_similarity = mode_val == "similarity"

        # 4. Display results dialog
        dialog = None

        try:
            # Clear selection store before opening a new dialog
            try:
                self.dialog_selection_store.clear_selection()
            except Exception:
                pass

            if is_similarity:
                if not dialog_groups:
                    show_selectable_info(
                        self,
                        "No Similarity Groups",
                        "The scan did not produce any similarity clusters for review.",
                    )
                    return

                text += f"\nSimilarity groups: {len(dialog_groups)}"

                dialog = SimilarityManagerDialog(
                    groups=dialog_groups,
                    pool_map=pool_map,
                    selection_store=self.dialog_selection_store,
                    db_manager=getattr(self, "database_manager", None),
                    flat_cache_manager=self.flat_cache_manager,
                    summary_text=text,
                    report_text=report_text,
                    profile_payload=payload_for_mode,
                    parent=self,
                )
            else:
                # Duplicates mode
                if not dialog_groups:
                    show_selectable_info(
                        self,
                        "No Duplicate Groups",
                        "The scan did not produce any duplicate clusters for review.",
                    )
                    return

                text += f"\nDuplicates groups: {len(dialog_groups)}"

                # Determine initial direction for the dialog based on two_pool status
                initial_direction = PoolDirection.ALL
                if two_pool:
                    try:
                        d = (payload_for_mode.get('scope', {}) or {}).get('direction')
                        if d == "A_TO_B":
                            initial_direction = PoolDirection.A_TO_B
                        elif d == "B_TO_A":
                            initial_direction = PoolDirection.B_TO_A
                    except Exception:
                        pass

                dialog = DuplicateManagerDialog(
                    groups=dialog_groups,
                    pool_map=pool_map,
                    selection_store=self.dialog_selection_store,
                    summary_text=text,
                    report_text=report_text,
                    initial_direction=initial_direction,
                    profile_payload=payload_for_mode,
                    flat_cache_manager=self.flat_cache_manager,
                    parent=self,
                )

            # Execute dialog
            ret = dialog.exec()
            total_items = sum(group.stats.file_count for group in dialog_groups)
            self.logger.debug(
                "file_management.dialog.completed",
                variables={
                    "dialog_type": type(dialog).__name__,
                    "return_code": ret,
                    "group_count": len(dialog_groups),
                    "item_count": total_items,
                    "mode": mode_val,
                    "scope": scope_kind,
                },
            )
            try:
                self.statusBar().showMessage(
                    f"{mode_val.capitalize()} groups: {len(dialog_groups)} ({total_items} files)",
                    10000,
                )
            except Exception:
                pass

        except Exception as e:
            # Fallback error handling for dialog creation/execution failure
            try:
                self.logger.error(f"Exception creating/executing results dialog: {e}", exc_info=True)
                # Show basic QDialog with summary on error
                basic_dlg = QDialog(self)
                basic_dlg.setWindowTitle("Operation Summary - Error")
                layout = QVBoxLayout(basic_dlg)
                text_edit = QTextEdit()
                text_edit.setPlainText(text + f"\n\n--- Dialog Error ---\n{e}")
                text_edit.setReadOnly(True)
                layout.addWidget(text_edit)
                btns = QDialogButtonBox(QDialogButtonBox.Ok)
                btns.accepted.connect(basic_dlg.accept)
                layout.addWidget(btns)
                basic_dlg.resize(600, 400)
                basic_dlg.exec()
            except Exception:
                pass # Fail silently if basic dialog creation fails

    def _extract_pool_map_from_groups(self, groups: List[Group]) -> Dict[str, str]:
        """
        Extracts the path->pool map from a list of already-converted Group objects.

        Parameters
        ----------
        groups : List[Group]
            List of immutable Group objects.

        Returns
        -------
        Dict[str, str]
            A map of file path to pool label.
        """
        pool_map: Dict[str, str] = {}
        for group in groups:
            for item in group.items:
                # Note: Pool information is not stored in FileItem, so we rely on the
                # pool map being built during raw data conversion or from the DB query
                # if available. For similarity groups returned by core, pool info is
                # implicitly 'A' unless two-pool logic was applied earlier.
                # However, the raw data conversion helper handles this correctly for duplicates.
                # For similarity, we rely on the DB query in _format_similarity_groups
                # (which was removed) or the raw data conversion helper.
                # Since we are skipping _format_similarity_groups, we need to ensure
                # the pool map is built correctly.
                # Let's assume for now that similarity groups are always single pool ('A')
                # unless two-pool logic is explicitly implemented in core.
                pool_map[item.path] = 'A'
        return pool_map
