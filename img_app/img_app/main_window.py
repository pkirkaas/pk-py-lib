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

import sys

from PySide6.QtGui import QAction, QIcon, QPalette, QColor
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QMainWindow, QLabel, QWidget, QVBoxLayout, QMenuBar, QStatusBar,
    QComboBox, QPushButton, QHBoxLayout, QFrame, QProgressBar, QApplication,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QStackedWidget,
    QMessageBox, QToolBar, QMenu, QSizePolicy, QTextEdit
)
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error, gui_error_handler, gui_error_context
from src.pk_py_lib.core.database import CACHE_SCHEMA
from src.pk_py_lib.core.filesystem.paths import PathOperations
from src.pk_py_lib.core.filesystem.traversal import DirectoryTraversal, IMAGE_EXTENSIONS
from src.pk_py_lib.core.filesystem.identity import get_inode_device, compute_sha256
from datetime import datetime
import traceback
from src.pk_py_lib.core.logging.logger import get_logger

from .widgets.duplicate_manager import ImageSimilarityManagerDialog

import logging
from collections import defaultdict
logger = logging.getLogger(__name__)

# Module-level logger for scan workflow; ERROR+ routes to STDERR via console output
LOGGER = get_logger("img_app.scan")

# Import Settings Manager components
try:
    from src.pk_py_lib.gui.settings_manager.structured_editor import StructuredProfileEditorWidget
    from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
except ImportError:
    # Fallback imports if not available
    StructuredProfileEditorWidget = None
    SettingsManagerController = None


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
    validates/refreshes cache entries (image_metadata, image_hashes), and reports progress.

    This worker performs all I/O and SQLite work off the GUI thread to keep the UI responsive.
    It uses a single connection created via DatabaseManager.get_connection(...) within the worker
    thread context (each connection is bound to the creating thread per sqlite3).

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
    - Hash algorithm is currently fixed/parametrized to 'sha256' per MVP; future versions
      may read this from the profile under criteria/settings.
    - Include/Exclude pattern semantics are simplified for MVP: we honor path roots and
      file type filters; glob patterns are not fully evaluated relative to roots yet.
    """

    progress = Signal(int, int, str, str)
    error = Signal(str)
    finished = Signal(str, dict)

    def __init__(self, db_manager, profile_json: dict, algorithm: str = "sha256", mode: str = 'duplicates', compute_hashes: bool = False, profile_name: Optional[str] = None, profile_id: Optional[str] = None, parent=None):
        """
        Initialize worker.
     
        Parameters
        ----------
        db_manager : DatabaseManager
            Database manager providing cache_db path and connection helper.
        profile_json : dict
            Structured Settings Profile (Option A) JSON object.
        algorithm : str
            Hash algorithm token to ensure in image_hashes (default 'sha256').
        mode : str
            Scan mode ('duplicates' or 'similarity').
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
        self.profile = profile_json or {}
        self.algorithm = (algorithm or "sha256").lower().strip()
        self.mode = mode
        self.compute_hashes = compute_hashes
        self.exact_grouping = (mode == 'duplicates')
        # Capture the profile name used for this run (best effort)
        try:
            self.profile_name = str(profile_name or (self.profile.get("name") if isinstance(self.profile, dict) else "") or "")
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
            print(f"[ScanWorker] Mode: {self.mode} — gathered {len(roots)} valid directory roots (post-validation, normalization, and dedup)")
            for r in roots[:3]:  # Show first few for verification
                print(f"[ScanWorker]   root: {r}")
            if len(roots) > 3:
                print(f"[ScanWorker]   ... and {len(roots)-3} more roots")
        except Exception:
            pass

        return roots

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
            
            # Determine patterns
            image_exts = [f"*{ext}" for ext in IMAGE_EXTENSIONS]
            patterns = image_exts if self.mode == 'similarity' else None
            
            # Call extended scan_directory
            # Changed to absolute import from the pk_py_lib library to resolve ModuleNotFoundError.
            # The traversal module is implemented in src/pk_py_lib/core/filesystem/traversal.py,
            # not locally in img_app/img_app/.
            from pk_py_lib.core.filesystem.traversal import scan_directory
            # Compute hashes for both similarity (perceptual) and duplicates (exact SHA256) modes to enable grouping
            effective_compute_hashes = self.compute_hashes or self.exact_grouping
            scan_result = scan_directory(
                roots=roots,
                patterns=patterns,
                compute_hashes=effective_compute_hashes,
                exact_grouping=self.exact_grouping,
                algorithms=self.profile.get('similarity', {}).get('enabled_algorithms', ['phash']) if effective_compute_hashes else None,
                db_manager=self.db_manager,
                cache_manager=None,  # Not used here
                settings=self.profile,
                follow_symlinks=False,  # Default; can add from profile if needed
                include_hidden=False,
            )
            
            files = scan_result['files']
            # Add 'files' to summary for post-scan duplicate grouping
            stats['files'] = scan_result['files']
            if self.exact_grouping:
                stats['groups_data'] = scan_result.get('groups', {})
            
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
            # groups_data is computed post-scan in main_window._on_scan_finished via _compute_duplicate_groups_from_files
            if self.exact_grouping:
                stats['groups_data'] = []
                # Note: scan_result.get('groups', {}) already set earlier; this ensures empty list if no pre-computed groups
                logger.debug(f"Exact groups included in summary: {len(stats['groups_data'])} groups")
            
            # Collect errors from scan_result
            stats["error_details"] = scan_result.get('error_details', [])
            stats["errors"] = len(stats["error_details"])
            
            # Simulate progress (since scan_directory is sync; future: extend with callback)
            for idx in range(1, total + 1):
                if self._stop:
                    break
                current_path = files[idx-1]['path'] if idx <= total else ''
                self.progress.emit(idx, total, current_path, "Processed")
            
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
        print(f"[ScanWorker] Emitting finished signal with profile_name={self.profile_name}, stats={stats}", file=sys.stderr)
        stats['mode'] = self.mode
        stats['compute_hashes'] = self.compute_hashes
        self.finished.emit(self.profile_name, stats)
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

    # Signal emitted when the active profile changes
    profile_changed = Signal(dict)

    def __init__(self, parent: QWidget | None = None, active_profile: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize MainWindow.

        Parameters
        ----------
        parent : QWidget | None
            Optional parent widget.
        active_profile : Optional[Dict[str, Any]]
            Active settings profile to associate with this window; stored on self.active_profile
            for future use by UI components. Passing None keeps behavior identical to prior versions.
        """
        super().__init__(parent)
        # Store the active profile for future use in widgets/controllers
        self.active_profile: Optional[Dict[str, Any]] = active_profile
        self.profiles: List[Dict[str, Any]] = []
        self.controller = None  # Will be set when database manager is available
        self.structured_editor = None
        # Track whether we've connected structured_editor.dirtyChanged to avoid spurious disconnect warnings
        self._editor_dirty_connected: bool = False
         
        self._setup_window()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_profile_toolbar()
        self._setup_progress_section()
        self._setup_central_widget()

        # App-wide palette override for readable, dark non-selected text in item views (QTreeWidget, QTableView, etc.)
        # This avoids dark-theme palettes forcing light/low-contrast text on light row backgrounds.
        self._apply_app_palette_hack()
        
        # Initialize start time for progress simulation
        import time
        self.start_time = time.time()
        self.logger = get_logger(__name__)

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

    def _setup_progress_section(self) -> None:
        """
        Create the progress reporting section with progress bar and status labels.
        """
        # Create a progress section widget (initially hidden)
        self.progress_section = QWidget(self)
        self.progress_section.setVisible(False)
        progress_layout = QVBoxLayout(self.progress_section)
        progress_layout.setContentsMargins(10, 5, 10, 5)
        progress_layout.setSpacing(5)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        # Status labels in a horizontal layout
        status_layout = QHBoxLayout()
        
        self.progress_status_label = QLabel("Ready", self)
        status_layout.addWidget(self.progress_status_label)
        
        self.file_count_label = QLabel("Files processed: 0", self)
        status_layout.addWidget(self.file_count_label)
        
        self.eta_label = QLabel("Estimated time: --", self)
        status_layout.addWidget(self.eta_label)
        
        status_layout.addStretch(1)
        progress_layout.addLayout(status_layout)

        # Add the progress section below the toolbar
        # We'll use a dock widget or place it in the central area temporarily
        # For now, we'll add it to the central widget's layout later

    def _setup_window(self) -> None:
        """Configure basic window properties."""
        self.setWindowTitle("KDC Image Organizer")
        self.resize(1024, 720)

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
        clear_cache_action.setStatusTip("Delete cache.db and recreate it empty")
        clear_cache_action.triggered.connect(self._on_clear_cache)
        cache_menu.addAction(clear_cache_action)
        
        clean_cache_action = QAction("Clean Cache", self)
        clean_cache_action.setStatusTip("Validate entries against the filesystem and remove invalid entries")
        clean_cache_action.triggered.connect(self._on_clean_cache)
        cache_menu.addAction(clean_cache_action)
        
        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._make_noop_action("Reset Layout"))
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About...", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
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

    def _setup_central_widget(self) -> None:
        """
        Create the central widget with progress section and main content.

        The central widget now includes:
        1. Progress section (initially hidden)
        2. Stacked widget for main content (file selector/placeholder and structured editor)
        """
        # Create a container widget for the central area
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Add progress section to the container
        container_layout.addWidget(self.progress_section)

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

    def _load_profiles(self) -> None:
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
                        name = profile.get('name', 'Unnamed')
                        if profile.get('is_active'):
                            name += " ★"
                        self.profile_combo.addItem(name, profile.get('id'))
                    
                    # Select the active profile if available
                    active_profile = None
                    for profile in self.profiles:
                        if profile.get('is_active'):
                            active_profile = profile
                            break
                    
                    if active_profile:
                        self.active_profile = active_profile
                        index = self.profile_combo.findData(active_profile.get('id'))
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
            if profile.get('id') == profile_id:
                selected_profile = profile
                break
                
        if selected_profile:
            self.active_profile = selected_profile
            self.profile_changed.emit(selected_profile)
            self.status_label.setText(f"Active profile: {selected_profile.get('name', 'Unnamed')}")
            
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

    def _on_create_profile(self) -> None:
        """
        Handle create new profile button click.
        """
        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            from src.pk_py_lib.core.settings_schema import create_default_profile
            
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
                    self._load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to create profile: {create_resp.message}")
            else:
                self.status_label.setText("Create profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error creating profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_create_profile")

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
                    self._load_profiles()  # Reload profiles to include the new one
                else:
                    self.status_label.setText(f"Failed to copy profile: {copy_resp.message}")
            else:
                self.status_label.setText("Copy profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error copying profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_copy_profile")

    @gui_error_handler(component_name="MainWindow", operation="start_scan")
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

        # 2) Show progress section and prepare scan
        self.progress_section.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_status_label.setText("Starting operation...")
        self.file_count_label.setText("Files processed: 0")
        self.eta_label.setText("Estimated time: --")
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

        mode = payload.get('mode', 'duplicates')
        self._current_scan_mode = mode
        compute_hashes = mode == 'similarity'

        self._scan_worker = ScanWorker(
            db_manager=db_mgr,
            profile_json=payload,
            algorithm="sha256",
            mode=mode,
            compute_hashes=compute_hashes,
            profile_name=prof_name,
            profile_id=(self.active_profile.get('id') if self.active_profile else None),
            parent=self
        )
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.start()

    def _on_scan_progress(self, processed: int, total: int, current_path: str, message: str) -> None:
        """
        Update progress UI from ScanWorker signals.

        Parameters
        ----------
        processed : int
            Number of files processed so far.
        total : int
            Total files discovered for processing.
        current_path : str
            The path of the file currently being processed.
        message : str
            Short status message from the worker.
        """
        import time
        percent = int((processed / total) * 100) if total > 0 else 0
        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100
        self.progress_bar.setValue(percent)
        self.file_count_label.setText(f"Files processed: {processed}/{total}")
        # ETA
        try:
            elapsed = time.time() - getattr(self, "start_time", time.time())
            if processed > 0 and total > 0:
                remaining = max(total - processed, 0)
                per_item = elapsed / max(processed, 1)
                eta = per_item * remaining
                self.eta_label.setText(f"Estimated time: {eta:.1f}s remaining")
        except Exception:
            pass
        # Status
        self.progress_status_label.setText(f"{message}: {current_path}")

    def _on_scan_error(self, message: str) -> None:
        """
        Record a non-fatal error reported by the worker and reflect in status.
        """
        try:
            self._scan_errors.append(message)
        except Exception:
            self._scan_errors = [message]
        self.status_label.setText(f"Error: {message}")

    def _on_scan_finished(self, profile_name: str, summary: dict) -> None:
        """
        Finalize UI and present summary, textual reports, and the Duplicate Manager dialog.
 
        This function restores a clean structure with a single try/except for the
        report-building section, fixes previous indentation errors, and preserves
        the enhanced debug logging added during diagnosis.
        """
        # Basic completion UI
        try:
            print(f"[DEBUG _on_scan_finished] START: profile_name={profile_name}", file=sys.stderr)
            print(f"[DEBUG _on_scan_finished] Summary keys: {list(summary.keys()) if summary else 'None'}", file=sys.stderr)
            print(f"[DEBUG _on_scan_finished] Summary: {summary}", file=sys.stderr)
            LOGGER.info("Scan finished handler started", variables={
                "profile_name": profile_name,
                "summary_keys": list(summary.keys()) if summary else [],
                "found_count": int((summary or {}).get("found", 0) or 0),
            })
        except Exception:
            pass

        self.progress_bar.setValue(100)
        self.progress_status_label.setText("Operation completed")
        self.start_btn.setEnabled(True)

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
            algo = str(summary.get("algorithm") or "sha256")
        except Exception:
            algo = "sha256"
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
            pools_obj = payload_for_mode.get('pools', {}) if isinstance(payload_for_mode, dict) else {}
            paths_a = [str(p) for p in (pools_obj.get("A") or {}).get("paths", [])]
            paths_b = [str(p) for p in (pools_obj.get("B") or {}).get("paths", [])]
        except Exception:
            pools_obj = {}
            paths_a = []
            paths_b = []

        print(f"[DEBUG _on_scan_finished] FINAL MODE: single_pool={is_single_pool}, two_pool={two_pool}, direction={direction}", file=sys.stderr)
        print(f"[DEBUG _on_scan_finished] Pools: A={len(paths_a)} paths, B={len(paths_b)} paths", file=sys.stderr)
        LOGGER.info("Final mode detection", variables={
            "is_single_pool": is_single_pool,
            "two_pool": two_pool,
            "direction": direction,
            "profile_name": profile_name,
            "found_files": found
        })

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
                with db_mgr.get_connection(db_mgr.cache_db) as conn:
                    # Restrict to current run
                    conn.execute("CREATE TEMP TABLE IF NOT EXISTS temp_run_files (file_path TEXT PRIMARY KEY)")
                    conn.execute("DELETE FROM temp_run_files")
                    if run_paths:
                        conn.executemany(
                            "INSERT OR IGNORE INTO temp_run_files(file_path) VALUES (?)",
                            [(p,) for p in run_paths]
                        )

                    if two_pool:
                        if direction == "duplicates":
                            rows = conn.execute("""
                                SELECT ia.file_path AS a_path, ib.file_path AS b_path
                                FROM image_hashes ih
                                JOIN image_metadata ia ON ia.id = ih.image_id AND ia.pool = 'A'
                                JOIN temp_run_files tra ON tra.file_path = ia.file_path
                                JOIN image_hashes ihb ON ihb.algorithm = ih.algorithm AND ihb.hash_value = ih.hash_value
                                JOIN image_metadata ib ON ib.id = ihb.image_id AND ib.pool = 'B'
                                JOIN temp_run_files trb ON trb.file_path = ib.file_path
                                WHERE ih.algorithm = ? AND ih.hash_value IS NOT NULL
                                ORDER BY ia.file_path, ib.file_path
                            """, (algo,)).fetchall()
                            groups_map: dict[str, list[str]] = defaultdict(list)
                            for r in rows:
                                a = str(r["a_path"]); b = str(r["b_path"])
                                groups_map[a].append(b)
                            report_lines.append("Two-Pool Report — duplicates (A vs B)")
                            for a_path, b_list in groups_map.items():
                                if not b_list:
                                    continue
                                groups += 1
                                total_dups += len(b_list)
                                report_lines.append(f"\nA: {a_path}\nB duplicates:")
                                for b in b_list:
                                    report_lines.append(f"  - {b}")
                        else:
                            rows = conn.execute("""
                                SELECT ib.file_path AS b_path
                                FROM image_hashes hb
                                JOIN image_metadata ib ON ib.id = hb.image_id AND ib.pool = 'B'
                                JOIN temp_run_files trb ON trb.file_path = ib.file_path
                                WHERE hb.algorithm = ? AND hb.hash_value IS NOT NULL
                                  AND NOT EXISTS (
                                      SELECT 1
                                      FROM image_hashes ha
                                      JOIN image_metadata ia ON ia.id = ha.image_id AND ia.pool = 'A'
                                      JOIN temp_run_files tra ON tra.file_path = ia.file_path
                                      WHERE ha.algorithm = hb.algorithm
                                        AND ha.hash_value = hb.hash_value
                                  )
                                ORDER BY ib.file_path
                            """, (algo,)).fetchall()
                            report_lines.append("Two-Pool Report — non_duplicates (B not in A)")
                            for r in rows:
                                b = str(r["b_path"])
                                non_matches += 1
                                report_lines.append(f"  - {b}")
                    else:
                        # Single-pool duplicate clustering
                        rows = conn.execute("""
                            SELECT ih.hash_value AS hv, im.file_path AS p
                            FROM image_hashes ih
                            JOIN image_metadata im ON im.id = ih.image_id AND im.is_valid = 1
                            JOIN temp_run_files tr ON tr.file_path = im.file_path
                            WHERE ih.algorithm = ? AND ih.hash_value IS NOT NULL
                            ORDER BY hv, p
                        """, (algo,)).fetchall()

                        current_hash: str | None = None
                        current_files: list[str] = []
                        report_lines.append("Duplicate Report — Single Pool")

                        def _flush():
                            nonlocal groups, total_dups, report_lines, current_hash, current_files
                            if current_hash is not None and len(current_files) >= 2:
                                groups += 1
                                total_dups += len(current_files)
                                report_lines.append(f"\nHash: {current_hash}")
                                for fp in current_files:
                                    report_lines.append(f"  - {fp}")

                        for r in rows:
                            hv = str(r["hv"]); p = str(r["p"])
                            if hv != current_hash:
                                _flush()
                                current_hash = hv
                                current_files = [p]
                            else:
                                current_files.append(p)
                        _flush()

                        # Prepare data for DuplicateManagerDialog
                        hv_to_paths: dict[str, list[str]] = defaultdict(list)
                        for r in rows:
                            h = str(r["hv"]); p = str(r["p"])
                            hv_to_paths[h].append(p)

                        dup_hashes = [h for h, lst in hv_to_paths.items() if len(lst) >= 2]
                        groups_data_fallback = [
                            {
                                "hash": h,
                                "count": len(hv_to_paths[h]),
                                "files": [{"path": p, "size": 0, "modified": 0, "pool": ""} for p in hv_to_paths[h]],
                            }
                            for h in dup_hashes
                        ]

                        if dup_hashes:
                            placeholders = ",".join("?" for _ in dup_hashes)
                            sql = f"""
                                SELECT ih.hash_value AS hash,
                                       im.file_path,
                                       im.file_size,
                                       im.file_modified,
                                       im.pool
                                FROM image_hashes ih
                                JOIN image_metadata im ON im.id = ih.image_id
                                JOIN temp_run_files tr ON tr.file_path = im.file_path
                                WHERE ih.algorithm = ? AND ih.hash_value IN ({placeholders})
                                ORDER BY ih.hash_value, im.file_path
                            """
                            params = [algo, *dup_hashes]
                            rows2 = conn.execute(sql, params).fetchall()

                            by_hash: dict[str, dict] = {}
                            for rr in rows2:
                                h = str(rr["hash"])
                                g = by_hash.get(h)
                                if g is None:
                                    g = {"hash": h, "count": 0, "files": []}
                                    by_hash[h] = g
                                fp = str(rr["file_path"])
                                try:
                                    sz = int(rr["file_size"]) if rr["file_size"] is not None else 0
                                except Exception:
                                    sz = 0
                                try:
                                    mod = int(rr["file_modified"]) if rr["file_modified"] is not None else 0
                                except Exception:
                                    mod = 0
                                pl = str(rr["pool"] or "")
                                g["files"].append({"path": fp, "size": sz, "modified": mod, "pool": pl})

                            groups_data_prepared = []
                            for h, g in by_hash.items():
                                g["count"] = len(g["files"])
                                if g["count"] >= 2:
                                    groups_data_prepared.append(g)
        except Exception as e:
            try:
                tb = traceback.format_exc()
                print(f"Exception in _on_scan_finished report generation: {e}\n{tb}", file=sys.stderr)
                LOGGER.error("report.generation.failed", exception=e)
            except Exception:
                pass

        # Final debug on groups
        print(f"[DEBUG _on_scan_finished] groups={groups}, total_dups={total_dups}, non_matches={non_matches}", file=sys.stderr)
        print(f"[DEBUG _on_scan_finished] prepared_groups={len(groups_data_prepared)}, fallback_groups={len(groups_data_fallback)}", file=sys.stderr)
        LOGGER.info("Final groups data state", variables={
            "groups_data_prepared_count": len(groups_data_prepared),
            "groups_data_fallback_count": len(groups_data_fallback),
            "total_groups": groups,
            "total_duplicate_files": total_dups,
            "non_matches": non_matches,
            "is_single_pool": is_single_pool,
            "two_pool": two_pool
        })

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

        # Display logic
        if two_pool:
            if direction == "non_duplicates":
                self._show_resizable_text_dialog("Non-duplicates Report", report_text)
                try:
                    self.statusBar().showMessage(f"Non-duplicates (B not in A): {non_matches}", 10000)
                except Exception:
                    pass
            else:
                self._show_resizable_text_dialog("Duplicate Report", report_text)
                try:
                    self.statusBar().showMessage(f"Two-pool duplicates groups: {groups}", 10000)
                except Exception:
                    pass
            return

        # Determine mode from profile
        mode_val = (payload_for_mode.get("mode") if isinstance(payload_for_mode, dict) else "?") or "?"

        # Single-pool: open appropriate dialog based on mode (even if empty)
        is_similarity = ('similarity' in payload_for_mode and payload_for_mode['similarity'].get('enabled_algorithms')) or summary.get('compute_hashes', False) or 'hashes' in summary
        logger.debug(f"Profile similarity: {payload_for_mode.get('similarity', {})} , scan compute_hashes: {summary.get('compute_hashes')}, is_similarity: {is_similarity}")
        if not is_similarity:
            logger.warning("Mode detection failed; defaulting to duplicates mode.")
        try:
            # Use unified dialog with mode
            mode = 'similarity' if is_similarity else 'duplicates'
            if is_similarity:
                # Compute perceptual hash groups for similarity mode
                threshold = payload_for_mode.get('similarity', {}).get('phash_threshold', 10)
                similarity_groups = self._compute_similarity_groups(payload_for_mode, run_paths, db_mgr)
                groups_data = similarity_groups
                logger.info(f"Groups data prepared: {len(groups_data)} groups")
                settings_sim = payload_for_mode.get('similarity', {}) if isinstance(payload_for_mode, dict) else {}
                settings = settings_sim
            else:
                # Diagnostics: summarize shape of file entries before grouping
                try:
                    files_preview = summary.get('files') or []
                    if isinstance(files_preview, list):
                        c_hash = sum(1 for f in files_preview if isinstance(f, dict) and f.get('hash'))
                        c_exact = sum(1 for f in files_preview if isinstance(f, dict) and f.get('exact_hash'))
                        c_sha256_in_hashes = sum(
                            1 for f in files_preview
                            if isinstance(f, dict) and isinstance(f.get('hashes'), dict) and f['hashes'].get('sha256')
                        )
                        c_phash = sum(
                            1 for f in files_preview
                            if isinstance(f, dict) and isinstance(f.get('hashes'), dict) and f['hashes'].get('phash')
                        )
                        c_whash = sum(
                            1 for f in files_preview
                            if isinstance(f, dict) and isinstance(f.get('hashes'), dict) and f['hashes'].get('whash')
                        )
                        LOGGER.info(
                            "scan.summary.files.shape",
                            variables={
                                "n": len(files_preview),
                                "hash_top": c_hash,
                                "exact_hash": c_exact,
                                "hashes.sha256": c_sha256_in_hashes,
                                "hashes.phash": c_phash,
                                "hashes.whash": c_whash,
                            }
                        )
                except Exception:
                    pass
    
                # Use groups_data from scan if available, else fallback
                groups_data = summary.get('groups_data', [])
                if len(groups_data) == 0:
                    groups_data = self._compute_duplicate_groups_from_files(summary['files'])
                groups_data = groups_data or (groups_data_prepared or self._get_duplicate_groups_single_pool() or groups_data_fallback)
                logger.info(f"Groups data prepared: {len(groups_data)} groups")
                settings = {}
            text += f"\nDuplicates: {len(groups_data)} groups"
            dlg = ImageSimilarityManagerDialog(
                mode=mode,
                groups=groups_data or [],
                summary_text=text,
                report_text=report_text,
                db_manager=db_mgr,
                settings=settings,
                paths=run_paths if mode == 'similarity' else None,
                parent=self
            )
            logger.info(f"Created dialog for mode '{self._current_scan_mode or 'duplicates'}': {type(dlg).__name__} with {len(groups_data)} groups")
       
            ret = dlg.exec()
            print(f"[DEBUG _on_scan_finished] Dialog exec() returned: {ret}", file=sys.stderr)
            LOGGER.info("Dialog executed", variables={
                "return_code": ret,
                "dialog_type": "SimilarityManagerDialog" if is_similarity else "DuplicateManagerDialog",
                "groups_passed": len(groups_data)
            })
        except Exception as e:
            try:
                print(f"[DEBUG _on_scan_finished] Exception creating dialog: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if mode_val == "similarity":
                    LOGGER.error("similarity.dialog.failed", exception=e, variables={"groups_count": len(groups_data or [])})
                else:
                    LOGGER.error("dups.dialog.failed", exception=e, variables={"groups_count": len(groups_data or [])})
 
                # Show basic QDialog with summary on error
                try:
                    basic_dlg = QDialog(self)
                    basic_dlg.setWindowTitle("Scan Summary - Error")
                    layout = QVBoxLayout(basic_dlg)
                    text_edit = QTextEdit()
                    text_edit.setPlainText(text)
                    text_edit.setReadOnly(True)
                    layout.addWidget(text_edit)
                    btns = QDialogButtonBox(QDialogButtonBox.Ok)
                    btns.accepted.connect(basic_dlg.accept)
                    layout.addWidget(btns)
                    basic_dlg.resize(600, 400)
                    basic_dlg.exec()
                except Exception:
                    pass  # Fail silently if basic dialog creation fails
            except Exception:
                pass
 
        try:
            self.statusBar().showMessage(f"Duplicate groups: {groups}; duplicate files: {total_dups}", 10000)
        except Exception:
            pass

    def _get_duplicate_groups_single_pool(self) -> list[dict]:
        """
        Return duplicate groups within the current run scope for single_pool mode.

        Data Source and Alignment
        -------------------------
        - Uses image_hashes joined with image_metadata, filtered by:
          • pool = 'A' (single_pool semantics)
          • algorithm = 'sha256' (matches the ScanWorker and the textual report)
        - Re-creates and populates a connection-local temp_run_files table using
          self._last_run_paths to scope results strictly to the most recent run.
        - This logic is intentionally aligned with the textual “Duplicate Report”
          that also reads from image_hashes to ensure consistency between the
          report counts and the DuplicateManagerDialog groups.

        Returns
        -------
        list[dict]
            A list of group dictionaries shaped as:
              [
                { "hash": str, "count": int, "files": [ { "path": str, "size": int, "modified": int, "pool": str }, ... ] },
                ...
              ]

        Filtering and Scope
        -------------------
        - Restricts results strictly to the files processed in the most recent scan run
          by (re)populating a temporary table temp_run_files using the last recorded
          run paths captured from the worker summary (_on_scan_finished()).
        - Limits to the 'A' pool for single_pool semantics.
        - Only groups with at least two files are returned.

        Notes
        -----
        - Uses DatabaseManager.get_connection() to interact with the cache database.
        - Timestamps are returned as integer epoch seconds (best-effort conversion).
        - This helper performs no UI and raises no exceptions outward; on any error
          it returns an empty list to keep the GUI resilient.
        """
        # Best-effort guard: require a database manager and a remembered run scope
        db_mgr = getattr(self, "database_manager", None)
        if db_mgr is None:
            return []
        run_paths = list(getattr(self, "_last_run_paths", []) or [])
        if not run_paths:
            # No remembered scope; nothing to compute
            return []

        # For single_pool milestone we constrain to Pool 'A'
        pool_label = "A"
        # Algorithm aligned with textual duplicates report and ScanWorker (image_hashes.algorithm)
        algorithm = "sha256"
        
        # Local helper to coerce timestamps to integer epoch seconds
        def _to_int_timestamp(val) -> int:
            try:
                return int(val)
            except Exception:
                try:
                    # Attempt common ISO formats
                    from datetime import datetime
                    s = str(val or "").strip()
                    if not s:
                        return 0
                    if s.endswith("Z"):
                        s = s[:-1]
                    s2 = s.replace(" ", "T")
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

        try:
            groups: list[dict] = []
            # Use a new connection; populate a TEMP table with this run's file set
            with db_mgr.get_connection(db_mgr.cache_db) as conn:
                # Populate/refresh the run-scope temp table for this connection
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS temp_run_files (file_path TEXT PRIMARY KEY)")
                conn.execute("DELETE FROM temp_run_files")
                conn.executemany(
                    "INSERT OR IGNORE INTO temp_run_files(file_path) VALUES (?)",
                    [(p,) for p in run_paths]
                )

                # Step 1 (aligned with textual report):
                # Discover duplicate hash values using image_hashes joined with image_metadata,
                # filtered by the current run scope (temp_run_files), Pool 'A', and algorithm.
                dup_rows = conn.execute(
                    """
                    SELECT ih.hash_value AS hash
                    FROM image_hashes ih
                    JOIN image_metadata im ON im.id = ih.image_id
                    JOIN temp_run_files t ON t.file_path = im.file_path
                    WHERE ih.algorithm = ? AND ih.hash_value IS NOT NULL
                    GROUP BY ih.hash_value
                    HAVING COUNT(*) >= 2
                    """,
                    (algorithm,)
                ).fetchall()
                hashes = [str(r["hash"]) for r in dup_rows if r["hash"] is not None]

                if not hashes:
                    return []

                # Step 2 (aligned with textual report):
                # Fetch member files for the discovered hashes from image_hashes+image_metadata,
                # limited to the current run scope and Pool 'A', and ordered stably by (hash, path).
                placeholders = ",".join("?" for _ in hashes)
                sql = f"""
                    SELECT ih.hash_value AS hash,
                           im.file_path,
                           im.file_size,
                           im.file_modified,
                           im.pool
                    FROM image_hashes ih
                    JOIN image_metadata im ON im.id = ih.image_id
                    JOIN temp_run_files t ON t.file_path = im.file_path
                    WHERE ih.algorithm = ? AND ih.hash_value IN ({placeholders})
                    ORDER BY ih.hash_value, im.file_path
                """
                params = [algorithm, *hashes]
                rows = conn.execute(sql, params).fetchall()

                # Group in Python into the requested shape
                grouped: dict[str, dict] = {}
                for r in rows:
                    h = str(r["hash"])
                    g = grouped.get(h)
                    if g is None:
                        g = {"hash": h, "count": 0, "files": []}
                        grouped[h] = g
                    file_path = str(r["file_path"])
                    try:
                        size = int(r["file_size"]) if r["file_size"] is not None else 0
                    except Exception:
                        size = 0
                    modified = _to_int_timestamp(r["file_modified"])
                    pool = str(r["pool"] or "")
                    g["files"].append({"path": file_path, "size": size, "modified": modified, "pool": pool})

                # Finalize counts and filter to groups with at least two members
                for h, g in grouped.items():
                    g["count"] = len(g["files"])
                    if g["count"] >= 2:
                        groups.append(g)

            return groups
        except Exception:
            # Defensive: never crash caller; empty means "no groups"
            return []

    def _compute_duplicate_groups_from_files(self, files: list[dict]) -> list[dict]:
        """
        Compute groups of exact duplicate files based on their SHA256 hashes.
    
        Input flexibility
        - Accepts any of the following per-file keys for the identity hash:
          • 'hash' (legacy callers)
          • 'exact_hash' (preferred; produced by scan_directory)
          • 'hashes' dict containing key 'sha256' (future compatibility)
    
        Behavior
        - Groups by the resolved identity hash value.
        - Skips entries missing a valid path or identity hash.
        - Reduces log noise: aggregates skip counts; per-item issues are logged at DEBUG.
    
        Parameters
        ----------
        files : list[dict]
            File dicts from scan_directory; each should include at least:
            - 'path': absolute file path (str)
            - identity hash under 'exact_hash' or 'hash' or 'hashes.sha256'
    
        Returns
        -------
        list[dict]
            [
              { "hash": str, "files": [ { "path": str }, ... ], "count": int },
              ...
            ]
        """
        groups = defaultdict(list)
        skipped = 0
        has_valid_hashes = False
    
        for file_dict in files:
            try:
                path = file_dict.get('path')
                hashes_dict = file_dict.get('hashes') if isinstance(file_dict.get('hashes'), dict) else {}
                # Resolve identity hash in order of preference
                hash_val = (
                    file_dict.get('hash') or
                    file_dict.get('exact_hash') or
                    (hashes_dict.get('sha256') if hashes_dict else None)
                )
                if not path or not hash_val:
                    skipped += 1
                    # Per-item debug to avoid noisy warnings
                    self.logger.debug(
                        f"Skipping (missing path or identity hash). "
                        f"path={path or 'missing'} keys={list(file_dict.keys())}"
                    )
                    continue
                has_valid_hashes = True
                groups[hash_val].append({'path': path})
            except Exception as e:
                skipped += 1
                self.logger.debug(f"Error processing file dict: {e}")
                continue
    
        total = len(files)
        if skipped > 0:
            self.logger.warning(f"Skipped {skipped} out of {total} files due to missing data or errors")
    
        if not has_valid_hashes:
            self.logger.warning(
                "No valid identity hashes found in files; returning empty groups. "
                "Expected 'exact_hash' from scan_directory."
            )
    
        duplicate_groups: list[dict] = []
        for hash_val, file_list in groups.items():
            if len(file_list) > 1:
                duplicate_groups.append({
                    'hash': hash_val,
                    'files': file_list,
                    'count': len(file_list)
                })
    
        self.logger.info(
            f"Computed {len(duplicate_groups)} duplicate groups from {total} files (skipped {skipped})"
        )
        return duplicate_groups

    def _simulate_operation(self) -> None:
        """
        Simulate an operation with progress updates.
        """
        import time
        total_files = 100  # Simulate 100 files
        
        for i in range(total_files + 1):
            time.sleep(0.05)  # Simulate work
            progress = int((i / total_files) * 100)
            self.progress_bar.setValue(progress)
            self.file_count_label.setText(f"Files processed: {i}/{total_files}")
            
            # Simple ETA calculation
            if i > 0:
                elapsed = time.time() - self.start_time
                remaining = (elapsed / i) * (total_files - i)
                self.eta_label.setText(f"Estimated time: {remaining:.1f}s remaining")
            
            # Process events to update UI
            QApplication.processEvents()
            
        self.progress_status_label.setText("Operation completed")
        # Show results dialog
        self._show_results_dialog()

    def _show_results_dialog(self) -> None:
        """
        Show the results dialog after operation completion.
        """
        # For now, show a message - will implement full results dialog later
        from src.pk_py_lib.gui.utils.messages import show_selectable_info
        show_selectable_info(
            self,
            "Operation Complete",
            "The operation has completed successfully.\n\n"
            f"Profile: {self.active_profile.get('name', 'Unnamed')}\n"
            "Files processed: 100\n"
            "Duplicates found: 5\n"
            "Time taken: 5.0 seconds"
        )
    def _show_resizable_text_dialog(self, title: str, text: str) -> None:
        """
        Show a resizable dialog containing large, selectable report text.

        Parameters
        ----------
        title : str
            Dialog window title.
        text : str
            Complete report text to present. Text is selectable/copyable.

        Notes
        -----
        - Uses a QTextEdit to allow selection and scrolling of large reports.
        - Dialog is explicitly made resizable with a size grip and generous default size.
        - A "Copy to Clipboard" action is provided for quick export.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        layout = QVBoxLayout(dlg)

        # Large, scrollable, selectable text surface
        edit = QTextEdit(dlg)
        edit.setReadOnly(True)
        try:
            edit.setLineWrapMode(QTextEdit.NoWrap)  # keep wide reports readable
        except Exception:
            pass
        edit.setPlainText(text)
        layout.addWidget(edit)

        # Buttons: Copy to Clipboard + Close
        btns = QDialogButtonBox(QDialogButtonBox.Close, parent=dlg)
        copy_btn = QPushButton("Copy to Clipboard", dlg)
        btns.addButton(copy_btn, QDialogButtonBox.ActionRole)

        def _copy() -> None:
            try:
                QApplication.clipboard().setText(text)
            except Exception:
                pass

        copy_btn.clicked.connect(_copy)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        # Make dialog comfortably large and resizable
        try:
            dlg.setSizeGripEnabled(True)
        except Exception:
            pass
        dlg.resize(1000, 700)
        dlg.exec()

    def _format_error_report(self, error_details: List[Dict[str, Any]]) -> str:
        """
        Build a human-readable, fully-detailed error report for scan/comparison errors.

        Parameters
        ----------
        error_details : list[dict]
            A list of dictionaries where each entry describes one error with the following keys:
              - 'timestamp' (str): ISO-8601 timestamp (seconds precision) of when the error was captured.
              - 'operation' (str): The logical operation (e.g., 'scan').
              - 'path' (str): The file or resource path associated with the error.
              - 'exception_type' (str): The exception class name.
              - 'message' (str): The exception message text.
              - 'traceback' (str): The full Python traceback string as plain text.
              - 'context' (dict): Optional arbitrary contextual details (e.g., 'profile_id', 'algorithm', 'sql', 'params', 'placeholder_count', 'param_count'); all keys are displayed generically.

        Returns
        -------
        str
            A multi-line string containing a concise header and one detailed block per error.

        Notes
        -----
        - The returned string is intended for display in a selectable QTextEdit using _show_resizable_text_dialog().
        - Only built-in Python types are assumed; values are defensively coerced to str() where appropriate.
        - Keys missing from an entry are treated as empty strings; context keys with None/empty values are omitted.

        Examples
        --------
        >>> sample = [{
        ...     "timestamp": "2025-09-08T21:00:00",
        ...     "operation": "scan",
        ...     "path": "/tmp/image.jpg",
        ...     "exception_type": "FileNotFoundError",
        ...     "message": "No such file or directory",
        ...     "traceback": "Traceback (most recent call last): ...",
        ...     "context": {"profile_id": "abc123", "algorithm": "sha256"}
        ... }]
        >>> # self is an instance of MainWindow
        >>> isinstance(self._format_error_report(sample), str)
        True
        """
        # Compose header with clear indication that text is selectable/copyable
        lines: List[str] = []
        total = len(error_details or [])
        lines.append("Scan Error Details")
        lines.append(f"Total Errors: {total}")
        lines.append("Note: Text is fully selectable. Copy/paste as needed.")
        lines.append("-" * 80)

        # Emit one fully-detailed section per error
        for i, ed in enumerate(error_details or [], start=1):
            # Defensive extraction with str() coercions to guarantee built-in, serializable types
            ed = ed or {}
            ts = str(ed.get("timestamp") or "")
            op = str(ed.get("operation") or "")
            path = str(ed.get("path") or "")
            ex_type = str(ed.get("exception_type") or "")
            msg = str(ed.get("message") or "")
            tb = str(ed.get("traceback") or "")
            ctx = ed.get("context") or {}
            ctx_items: List[Tuple[str, Any]] = []
            if isinstance(ctx, dict):
                # Render all context items generically, sorted by key for stability
                for k in sorted(ctx.keys(), key=lambda s: str(s)):
                    v = ctx.get(k)
                    if v is None or v == "":
                        continue
                    try:
                        v_str = str(v)
                    except Exception:
                        v_str = repr(v)
                    ctx_items.append((str(k), v_str))

            lines.append(f"Error #{i}")
            if op:
                lines.append(f"Operation: {op}")
            lines.append(f"Path: {path}")
            lines.append(f"Type: {ex_type}")
            lines.append(f"Message: {msg}")
            lines.append(f"Timestamp: {ts}")
            if ctx_items:
                lines.append("Context:")
                for k, v in ctx_items:
                    lines.append(f"  {k}: {v}")
            lines.append("Traceback:")
            # Ensure clean separation with trailing newline removal for consistency
            lines.append(tb.rstrip("\n"))
            lines.append("-" * 80)

        return "\n".join(lines)

    def load_profiles(self) -> None:
        """
        Public method to load profiles after database manager is available.
        This should be called after the database manager is set on the window.
        """
        # Initialize the controller with the database manager
        if hasattr(self, 'database_manager') and self.database_manager is not None:
            try:
                from src.pk_py_lib.api.settings_profiles import SettingsProfilesAPI
                from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
                api = SettingsProfilesAPI(self.database_manager)
                self.controller = SettingsManagerController(api)
            except ImportError:
                self.status_label.setText("Settings Manager controller not available")
                return
        self._load_profiles()

    def _load_profile_into_editor(self, profile_id: str) -> None:
        """
        Load the selected profile into the structured editor.

        Parameters
        ----------
        profile_id : str
            The ID of the profile to load into the editor.
        """
        if self.controller is None:
            return

        # Create structured editor if it doesn't exist
        if self.structured_editor is None:
            try:
                from src.pk_py_lib.gui.settings_manager.structured_editor import StructuredProfileEditorWidget
                self.structured_editor = StructuredProfileEditorWidget(api=self.controller.api, parent=self)
                # Reset connection tracking when editor instance changes
                self._editor_dirty_connected = False
                # Replace the placeholder with the actual editor
                if self.stacked_widget.count() > 1:
                    self.stacked_widget.removeWidget(self.structured_editor_placeholder)
                    self.stacked_widget.addWidget(self.structured_editor)
                else:
                    self.stacked_widget.addWidget(self.structured_editor)
            except ImportError:
                self.status_label.setText("Structured editor not available")
                return

        # Load the profile data
        resp = self.controller.get_profile(profile_id)
        if resp.success and resp.data:
            # Extract Option A payload when profile is JSON-format; otherwise pass as-is
            payload = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data
            self.structured_editor.load_profile(payload)
            # Connect dirtyChanged signal to update save/cancel buttons (connect-once pattern)
            if hasattr(self.structured_editor, 'dirtyChanged') and self.structured_editor.dirtyChanged is not None:
                # Avoid calling disconnect() on an unconnected slot (PySide logs a RuntimeWarning)
                if not getattr(self, "_editor_dirty_connected", False):
                    self.structured_editor.dirtyChanged.connect(self._on_editor_dirty_changed)
                    self._editor_dirty_connected = True
            # Switch to the editor view
            self.stacked_widget.setCurrentIndex(1)
            # Initially disable save/cancel buttons
            self._update_save_cancel_buttons(False)
        else:
            self.status_label.setText(f"Failed to load profile: {resp.message}")

    def _on_rename_profile(self) -> None:
        """
        Handle rename profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to rename")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            current_name = self.active_profile.get('name', 'Unnamed')
            
            # Create a name prompt dialog
            dlg = _NamePromptDialog("Rename Profile", "New name:", current_name, self)
            
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
                
                # Rename the profile
                rename_resp = self.controller.rename_profile(self.active_profile['id'], new_name)
                
                if rename_resp.success:
                    self.status_label.setText(f"Profile renamed to '{new_name}'")
                    self._load_profiles()  # Reload profiles to reflect the change
                else:
                    self.status_label.setText(f"Failed to rename profile: {rename_resp.message}")
            else:
                self.status_label.setText("Rename profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error renaming profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_rename_profile")

    def _on_delete_profile(self) -> None:
        """
        Handle delete profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No active profile selected to delete")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            profile_name = self.active_profile.get('name', 'Unnamed')
            
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete the profile '{profile_name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                delete_resp = self.controller.delete_profile(self.active_profile['id'])
                
                if delete_resp.success:
                    self.status_label.setText(f"Profile '{profile_name}' deleted")
                    self._load_profiles()  # Reload profiles
                else:
                    self.status_label.setText(f"Failed to delete profile: {delete_resp.message}")
            else:
                self.status_label.setText("Delete profile canceled")
        except Exception as exc:
            self.status_label.setText(f"Error deleting profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_delete_profile")

    def _on_set_active_profile(self) -> None:
        """
        Handle set active profile button click.
        """
        if not self.active_profile:
            self.status_label.setText("No profile selected to set as active")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            set_active_resp = self.controller.set_active(self.active_profile['id'])
            
            if set_active_resp.success:
                self.status_label.setText(f"Profile '{self.active_profile.get('name', 'Unnamed')}' set as active")
                self._load_profiles()  # Reload to update active indicator
            else:
                self.status_label.setText(f"Failed to set active profile: {set_active_resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error setting active profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_set_active_profile")

    def _on_save_profile(self) -> None:
        """
        Handle save profile button click - save changes to the current profile.
        """
        if not self.active_profile or not self.structured_editor:
            self.status_label.setText("No profile selected or editor not available")
            return

        try:
            if self.controller is None:
                self.status_label.setText("Controller not available")
                return

            # Validate the profile before saving
            is_valid, errors = self.structured_editor.get_validation_status()
            if not is_valid:
                error_msg = errors[0] if errors else "Profile validation failed"
                self.status_label.setText(f"Cannot save: {error_msg}")
                return

            # Gather changes from the editor
            profile_data = self.structured_editor.gather_changes()
            
            # Update the profile using the controller
            update_resp = self.controller.update_structured_profile(
                profile_id=self.active_profile['id'],
                profile_json=profile_data
            )
            
            if update_resp.success:
                self.status_label.setText(f"Profile '{profile_data.get('name', 'Unnamed')}' saved successfully")
                # Reset dirty state
                self.structured_editor.reset_dirty()
                self._update_save_cancel_buttons(False)
                # Reload profiles to reflect any name changes
                self._load_profiles()
                # Reload the current profile into the editor to ensure UI reflects saved state
                if self.active_profile:
                    self._load_profile_into_editor(self.active_profile['id'])
            else:
                self.status_label.setText(f"Failed to save profile: {update_resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error saving profile: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_save_profile")

    def _on_cancel_changes(self) -> None:
        """
        Handle cancel changes button click - discard unsaved changes.
        """
        if not self.active_profile or not self.structured_editor:
            self.status_label.setText("No profile selected or editor not available")
            return

        try:
            # Reload the original profile data to discard changes
            resp = self.controller.get_profile(self.active_profile['id'])
            if resp.success and resp.data:
                # For JSON-format profiles, reload editor with the embedded json_data payload
                payload = resp.data.get('json_data') if isinstance(resp.data, dict) and resp.data.get('format') == 'json' and 'json_data' in resp.data else resp.data
                self.structured_editor.load_profile(payload)
                self.status_label.setText("Changes discarded")
                self._update_save_cancel_buttons(False)
            else:
                self.status_label.setText(f"Failed to reload profile: {resp.message}")
        except Exception as exc:
            self.status_label.setText(f"Error discarding changes: {exc}")
            import logging
            logging.getLogger("img_app.main_window").exception("Error in _on_cancel_changes")

    def _on_editor_dirty_changed(self, dirty: bool) -> None:
        """
        Handle dirty state changes from the structured editor.
        
        Parameters
        ----------
        dirty : bool
            True if there are unsaved changes, False otherwise.
        """
        self._update_save_cancel_buttons(dirty)

    def _update_save_cancel_buttons(self, enabled: bool) -> None:
        """
        Update the enabled state of save and cancel buttons.
        
        Parameters
        ----------
        enabled : bool
            True to enable buttons, False to disable.
        """
        self.save_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)

    def _get_app_version(self) -> str:
        """
        Return the application version string.

        Tries in order:
        1) img_app.img_app.__app_version__ (app-specific version, if defined)
        2) src.pk_py_lib.__version__ (library version as fallback)
        3) "0.0.0-dev" placeholder if neither is available
        """
        try:
            from img_app.img_app import __app_version__ as v  # type: ignore
            if v:
                return str(v)
        except Exception:
            pass
        try:
            from src.pk_py_lib import __version__ as v  # type: ignore
            if v:
                return str(v)
        except Exception:
            pass
        return "0.0.0-dev"

    def _show_about(self) -> None:
        """
        Show the About dialog using selectable text message utilities.
        
        The dialog displays:
        - Application name (window title if available)
        - Version information
        - Brief description
        
        The text in the dialog is selectable/copyable per project requirements.
        """
        # Determine application name (prefer the current window title)
        app_name = self.windowTitle() or "Image Organizer App"
        version = self._get_app_version()
        description = (
            "Development image organizer built on pk-py-lib.\n"
            "Manage, classify, and deduplicate large image collections."
        )
        about_text = f"{app_name}\nVersion: {version}\n\n{description}"
        
        # Use the selectable info dialog from pk_py_lib; fallback to QMessageBox if unavailable
        try:
            from src.pk_py_lib.gui.utils.messages import show_selectable_info
            show_selectable_info(self, "About", about_text)
        except Exception:
            try:
                QMessageBox.information(self, "About", about_text)
            except Exception:
                # If even this fails, ignore to avoid crashing on About
                pass

    @gui_error_handler(component_name="MainWindow", operation="clear_cache")
    def _on_clear_cache(self) -> None:
        """
        Clear the application's cache database (cache.db).

        Deletes the cache.db file if it exists, then recreates an empty schema
        using the canonical CACHE_SCHEMA via the DatabaseManager connection.

        Uses selectable message dialogs to report success or failure.
        """
        db_mgr = getattr(self, "database_manager", None)
        if db_mgr is None:
            show_selectable_error(self, "Cache Error", "DatabaseManager is not available on the main window.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Clear Cache",
            "This will delete the cache database (cache.db) and recreate it empty.\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        cache_path = db_mgr.cache_db
        # Delete cache.db if present
        try:
            cache_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            # Fallback for Python versions lacking missing_ok
            if cache_path.exists():
                cache_path.unlink()

        # Recreate empty schema
        with db_mgr.get_connection(cache_path) as conn:
            conn.executescript(CACHE_SCHEMA)

        # Notify user
        show_selectable_info(self, "Cache Cleared", f"Cache database cleared and reinitialized.\n\nPath:\n{cache_path}")
        try:
            self.statusBar().showMessage("Cache database cleared and reinitialized", 5000)
        except Exception:
            pass

    @gui_error_handler(component_name="MainWindow", operation="clean_cache")
    def _on_clean_cache(self) -> None:
        """
        Clean the cache database by validating image entries against the filesystem.

        For each row in image_metadata:
        - If file does not exist: delete the row (cascades remove thumbnails and hashes)
        - If file exists but (size or mtime) differ: delete the row
        After deletions, runs VACUUM to compact the database file and reports counts.
        """
        db_mgr = getattr(self, "database_manager", None)
        if db_mgr is None:
            show_selectable_error(self, "Cache Error", "DatabaseManager is not available on the main window.")
            return

        cache_path = db_mgr.cache_db

        # Ensure cache DB exists; create empty if missing
        if not cache_path.exists():
            with db_mgr.get_connection(cache_path) as conn:
                conn.executescript(CACHE_SCHEMA)
            show_selectable_info(self, "Clean Cache", "Cache database did not exist. A new empty cache was created.")
            return

        from datetime import datetime

        def _to_epoch_seconds(val) -> int | None:
            """Best-effort string/number → epoch seconds converter."""
            if val is None:
                return None
            try:
                if isinstance(val, (int, float)):
                    return int(val)
                s = str(val).strip()
                if not s:
                    return None
                if s.isdigit():
                    return int(s)
                # Try ISO formats
                s2 = s[:-1] if s.endswith("Z") else s
                s2 = s2.replace(" ", "T")
                try:
                    dt = datetime.fromisoformat(s2)
                    return int(dt.timestamp())
                except Exception:
                    pass
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        return int(dt.timestamp())
                    except Exception:
                        continue
            except Exception:
                return None
            return None

        removed_missing = 0
        removed_changed = 0
        checked = 0
        to_delete: list[int] = []

        # Read all entries and build deletion list
        with db_mgr.get_connection(cache_path) as conn:
            cur = conn.execute("SELECT id, file_path, file_size, file_modified FROM image_metadata")
            rows = cur.fetchall()
            checked = len(rows)

            for row in rows:
                image_id = int(row["id"])
                p = Path(str(row["file_path"]))
                try:
                    if not p.exists():
                        to_delete.append(image_id)
                        removed_missing += 1
                        continue

                    st = p.stat()
                    try:
                        size_db = int(row["file_size"]) if row["file_size"] is not None else None
                    except Exception:
                        size_db = None
                    mtime_db = _to_epoch_seconds(row["file_modified"])

                    size_changed = (size_db is None) or (int(st.st_size) != size_db)
                    mtime_changed = True
                    if mtime_db is not None:
                        mtime_changed = abs(int(st.st_mtime) - int(mtime_db)) > 1

                    if size_changed or mtime_changed:
                        to_delete.append(image_id)
                        removed_changed += 1
                except Exception:
                    # Conservative: treat as invalid
                    to_delete.append(image_id)
                    removed_changed += 1

            # Delete in chunks; cascades remove thumbnails and hashes
            CHUNK = 500
            for i in range(0, len(to_delete), CHUNK):
                chunk = to_delete[i:i + CHUNK]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(f"DELETE FROM image_metadata WHERE id IN ({placeholders})", chunk)
            # Commit handled by context manager

        # VACUUM to compact file size
        try:
            with db_mgr.get_connection(cache_path) as conn:
                conn.execute("VACUUM")
        except Exception:
            # Non-fatal
            pass

        removed_total = removed_missing + removed_changed
        show_selectable_info(
            self,
            "Clean Cache",
            f"Checked entries: {checked}\n"
            f"Removed entries: {removed_total}\n"
            f"- Missing files: {removed_missing}\n"
            f"- Changed files: {removed_changed}"
        )
        try:
            self.statusBar().showMessage(f"Cache cleaned: removed {removed_total} entries", 5000)
        except Exception:
            pass

    def _make_noop_action(self, text: str) -> QAction:
        """
        Create a no-op QAction placeholder.

        Parameters
        ----------
        text : str
            Display text for the action.

        Returns
        -------
        QAction
            Action connected to a lambda that performs no behavior.
        """
        action = QAction(text, self)
        action.triggered.connect(lambda: None)
        return action

    def _compute_similarity_groups(self, profile_payload: dict, run_paths: list[str], db_mgr) -> list[list[str]]:
        """
        Compute perceptual hash similarity groups for the scanned paths.

        Fetches image paths from the current run, computes pHashes using compute_phash_batch,
        filters valid hashes, and groups similar images using find_similar_phash with threshold
        from profile_payload['similarity']['phash_threshold'] or default 10.

        Args:
            profile_payload (dict): The profile JSON data containing 'similarity' settings.
            run_paths (list[str]): List of absolute paths from the scan run.
            db_mgr: DatabaseManager instance for cache access (if needed for validation).

        Returns:
            list[list[str]]: List of similarity groups, each a list of similar image paths.
                             Empty list if no groups found or computation fails.

        Raises:
            None: Returns empty list on any error for GUI resilience.
        """
        try:
            from src.pk_py_lib.core.image.similarity import compute_phash_batch, find_similar_phash
            from src.pk_py_lib.core.cache import CacheManager

            # Use cache if available via db_mgr (assuming db_mgr has cache_db path)
            cache_mgr = CacheManager(Path(db_mgr.cache_db).parent) if db_mgr else None

            settings = profile_payload.get('similarity', {}) if isinstance(profile_payload, dict) else {}
            hash_size = settings.get('phash_hash_size', 8)
            threshold = settings.get('phash_threshold', 10)

            # Compute pHashes for run paths
            phash_results = compute_phash_batch(
                paths=run_paths,
                hash_size=hash_size,
                settings={'criteria': {'phash': {'hash_size': hash_size}}},
                cache_manager=cache_mgr
            )

            # Filter to valid hashes
            valid_hashes = [
                {'path': path, 'hash': phash}
                for path, phash in phash_results.items()
                if phash is not None
            ]

            if not valid_hashes:
                return []

            # Group similar images
            groups = find_similar_phash(
                hashes=valid_hashes,
                threshold=threshold,
                settings={'similarity': {'phash_threshold': threshold}}
            )

            LOGGER.info(f"Computed {len(groups)} similarity groups (threshold={threshold}, valid_images={len(valid_hashes)})")
            return groups

        except Exception as e:
            LOGGER.error("Similarity groups computation failed", exception=e)
            return []

    def _format_similarity_groups(self, groups: list[list[str]], db_mgr) -> list[dict]:
        """
        Format similarity path groups into the standard groups_data structure for dialogs.

        For each group of paths, queries the DB for file metadata (size, modified) and formats
        as {"hash": "perceptual_group_X", "count": int, "files": [{"path": str, "size": int, "modified": int, "pool": str}, ...]}.
        Uses pool='A' for single-pool similarity. Groups with <2 paths are filtered out.

        Args:
            groups (list[list[str]]): List of path groups from find_similar_phash.
            db_mgr: DatabaseManager for querying image_metadata.

        Returns:
            list[dict]: Formatted groups_data list, empty if no valid groups or DB error.
        """
        if not groups or not db_mgr:
            return []

        try:
            with db_mgr.get_connection(db_mgr.cache_db) as conn:
                # Create temp table for current run paths (reuse logic from _get_duplicate_groups_single_pool)
                conn.execute("CREATE TEMP TABLE IF NOT EXISTS temp_run_files (file_path TEXT PRIMARY KEY)")
                conn.execute("DELETE FROM temp_run_files")
                all_paths = [path for group in groups for path in group]
                conn.executemany("INSERT OR IGNORE INTO temp_run_files(file_path) VALUES (?)", [(p,) for p in all_paths])

                formatted_groups = []
                for idx, group_paths in enumerate(groups, 1):
                    if len(group_paths) < 2:
                        continue

                    # Query metadata for paths in this group
                    placeholders = ",".join("?" for _ in group_paths)
                    sql = f"""
                        SELECT file_path, file_size, file_modified, pool
                        FROM image_metadata
                        WHERE file_path IN ({placeholders})
                        ORDER BY file_path
                    """
                    rows = conn.execute(sql, group_paths).fetchall()

                    files = []
                    for row in rows:
                        path = str(row["file_path"])
                        size = int(row["file_size"] or 0)
                        modified = int(row["file_modified"] or 0)
                        pool = str(row["pool"] or "A")
                        files.append({"path": path, "size": size, "modified": modified, "pool": pool})

                    if len(files) >= 2:
                        group_dict = {
                            "hash": f"perceptual_group_{idx}",
                            "count": len(files),
                            "files": files
                        }
                        formatted_groups.append(group_dict)

            LOGGER.debug(f"Formatted {len(formatted_groups)} similarity groups from {len(groups)} raw groups")
            return formatted_groups

        except Exception as e:
            LOGGER.error("Formatting similarity groups failed", exception=e)
            return []