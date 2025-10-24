"""
Main window for KDC Image Organizer.

This module contains the main application window with integrated
settings management and image processing capabilities.
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QToolBar, QStatusBar,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QSplitter
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon

# Import functions directly to avoid circular import
from PySide6.QtWidgets import QMessageBox, QApplication
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.gui.models import SelectionStore
from pk_py_lib.gui.models import SelectionStore


class MainWindow(QMainWindow):
    """
    Main application window for KDC Image Organizer.

    This window provides the primary interface for image organization
    with integrated settings management and processing capabilities.
    """

    def __init__(self, app_manager: ApplicationManager):
        """
        Initialize main window.

        Args:
            app_manager: Application manager instance
        """
        super().__init__()
        self.app_manager = app_manager
        self.selection_store = SelectionStore()

        # Window properties
        self.setWindowTitle("KDC Image Organizer")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Setup UI components
        self._setup_menu_bar()
        self._setup_profile_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()

        # Connect signals
        self._connect_signals()

        # Initialize state
        self._initialize_state()

    def _setup_menu_bar(self) -> None:
        """Setup the main menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        self.exit_action = QAction("&Exit", self)
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

        # Cache menu
        cache_menu = menubar.addMenu("&Cache")
        self.clear_cache_action = QAction("&Clear Cache", self)
        self.clear_cache_action.triggered.connect(self._on_clear_cache)
        cache_menu.addAction(self.clear_cache_action)

        self.clean_cache_action = QAction("Clea&n Cache", self)
        self.clean_cache_action.triggered.connect(self._on_clean_cache)
        cache_menu.addAction(self.clean_cache_action)

        # View menu
        view_menu = menubar.addMenu("&View")
        self.reset_layout_action = QAction("&Reset Layout", self)
        view_menu.addAction(self.reset_layout_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        self.about_action = QAction("&About", self)
        self.about_action.triggered.connect(self._show_about)
        help_menu.addAction(self.about_action)

    def _setup_profile_toolbar(self) -> None:
        """Setup the profile management toolbar."""
        toolbar = self.addToolBar("Profile")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)

        # Profile selection
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        toolbar.addWidget(QLabel("Profile:"))
        toolbar.addWidget(self.profile_combo)

        toolbar.addSeparator()

        # Profile management buttons
        self.new_profile_btn = QPushButton("New Profile")
        self.new_profile_btn.clicked.connect(self._on_new_profile)
        toolbar.addWidget(self.new_profile_btn)

        self.copy_profile_btn = QPushButton("Copy Profile")
        self.copy_profile_btn.clicked.connect(self._on_copy_profile)
        toolbar.addWidget(self.copy_profile_btn)

        toolbar.addSeparator()

        # Main action button
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setMinimumWidth(100)
        toolbar.addWidget(self.start_btn)

    def _setup_central_widget(self) -> None:
        """Setup the central widget area."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Create main content splitter
        splitter = QSplitter(Qt.Vertical)

        # Top section - placeholder for now
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        placeholder_label = QLabel("The KDC Image Organizer will go here")
        placeholder_label.setAlignment(Qt.AlignCenter)
        placeholder_label.setStyleSheet("""
            QLabel {
                font-size: 24px;
                color: #666;
                padding: 50px;
            }
        """)

        top_layout.addWidget(placeholder_label)
        splitter.addWidget(top_widget)

        # Bottom section - progress and status
        bottom_widget = self._create_progress_section()
        splitter.addWidget(bottom_widget)

        # Set splitter proportions
        splitter.setSizes([600, 200])

        layout.addWidget(splitter)

    def _create_progress_section(self) -> QWidget:
        """Create the progress and status section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Progress section
        progress_group = QWidget()
        progress_layout = QVBoxLayout(progress_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { padding: 5px; }")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

        # Results section (placeholder)
        results_group = QWidget()
        results_layout = QVBoxLayout(results_group)

        results_label = QLabel("Results will appear here")
        results_label.setAlignment(Qt.AlignCenter)
        results_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #888;
                padding: 20px;
                border: 2px dashed #ddd;
            }
        """)
        results_layout.addWidget(results_label)

        layout.addWidget(results_group)

        return widget

    def _setup_status_bar(self) -> None:
        """Setup the status bar."""
        self.status_bar = self.statusBar()

        # Add permanent widgets to status bar
        self.status_bar.showMessage("Ready")

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        # Connect selection store signals
        self.selection_store.selection_count_changed.connect(
            self._on_selection_count_changed
        )

    def _initialize_state(self) -> None:
        """Initialize window state."""
        # Load available profiles
        self._load_profiles()

        # Update UI state
        self._update_ui_state()

    def _load_profiles(self) -> None:
        """Load available profiles into combo box."""
        try:
            # This will be implemented when settings manager is available
            self.profile_combo.clear()
            self.profile_combo.addItem("Default Profile")
            self.profile_combo.setCurrentIndex(0)
        except Exception as e:
            show_error_dialog(
                self,
                "Profile Loading Error",
                f"Failed to load profiles: {str(e)}"
            )

    def _update_ui_state(self) -> None:
        """Update UI state based on current conditions."""
        # Update button states
        has_profile = self.profile_combo.count() > 0
        self.start_btn.setEnabled(has_profile)

    def _on_profile_changed(self, profile_name: str) -> None:
        """Handle profile selection change."""
        if profile_name:
            self.status_bar.showMessage(f"Profile changed to: {profile_name}")

    def _on_new_profile(self) -> None:
        """Handle new profile creation."""
        show_info_dialog(
            "New Profile",
            "Profile creation will be implemented in the next phase",
            self
        )

    def _on_copy_profile(self) -> None:
        """Handle profile copying."""
        show_info_dialog(
            "Copy Profile",
            "Profile copying will be implemented in the next phase",
            self
        )

    def _on_start(self) -> None:
        """Handle start operation."""
        try:
            self._start_operation()
        except Exception as e:
            show_error_dialog(
                "Operation Error",
                f"Failed to start operation: {str(e)}",
                self
            )

    def _start_operation(self) -> None:
        """Start the image processing operation."""
        current_profile = self.profile_combo.currentText()
        if not current_profile:
            show_error_dialog(
                "No Profile",
                "Please select a profile before starting",
                self
            )
            return

        self.status_bar.showMessage("Starting operation...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)

        # Simulate operation progress
        self._simulate_progress()

    def _simulate_progress(self) -> None:
        """Simulate operation progress for demonstration."""
        progress = 0
        def update_progress():
            nonlocal progress
            progress += 10
            self.progress_bar.setValue(progress)
            self.status_label.setText(f"Processing... {progress}%")

            if progress >= 100:
                self._on_operation_complete()
            else:
                QTimer.singleShot(200, update_progress)

        update_progress()

    def _on_operation_complete(self) -> None:
        """Handle operation completion."""
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Operation completed")
        self.start_btn.setEnabled(True)

        show_info_dialog(
            "Operation Complete",
            "Image processing operation completed successfully!",
            self
        )

    def _on_selection_count_changed(self, count: int) -> None:
        """Handle selection count changes."""
        self.status_bar.showMessage(f"{count} items selected")

    def _on_clear_cache(self) -> None:
        """Handle clear cache action."""
        try:
            # This will be implemented with actual cache manager
            show_info_dialog(
                "Cache Cleared",
                "Cache has been cleared successfully",
                self
            )
        except Exception as e:
            show_error_dialog(
                "Cache Error",
                f"Failed to clear cache: {str(e)}",
                self
            )

    def _on_clean_cache(self) -> None:
        """Handle clean cache action."""
        try:
            # This will be implemented with actual cache manager
            show_info_dialog(
                "Cache Cleaned",
                "Cache has been cleaned successfully",
                self
            )
        except Exception as e:
            show_error_dialog(
                "Cache Error",
                f"Failed to clean cache: {str(e)}",
                self
            )

    def _show_about(self) -> None:
        """Show about dialog."""
        version = getattr(self, '_get_app_version', lambda: "0.1.0-dev")()

        about_text = f"""
KDC Image Organizer v{version}

A comprehensive desktop application for managing and organizing
large collections of digital photographs.

Built with Python {sys.version.split()[0]} and PySide6.

Features:
• Duplicate detection using perceptual hashing
• Image similarity analysis
• Batch file operations
• Comprehensive caching system
• Cross-platform support
        """.strip()

        show_info_dialog("About KDC Image Organizer", about_text, self)

    def _get_app_version(self) -> str:
        """Get application version."""
        try:
            return __app_version__
        except NameError:
            return "0.1.0-dev"


def show_info_dialog(title: str, message: str, parent=None) -> None:
    """Show info dialog with selectable text."""
    from pk_py_lib.gui.utils.messages import show_selectable_info
    try:
        show_selectable_info(parent, title, message)
    except Exception:
        QMessageBox.information(parent, title, message)


def show_error_dialog(parent, title: str, message: str) -> None:
    """Show error dialog with selectable text."""
    from pk_py_lib.gui.utils.messages import show_selectable_error
    try:
        show_selectable_error(parent, title, message)
    except Exception:
        QMessageBox.warning(parent, title, message)


class ApplicationManager:
    """Application manager for img_app."""

    def __init__(self):
        """Initialize application manager."""
        self.logger = get_logger("img_app.manager")

    def initialize(self) -> None:
        """Initialize application."""
        self.logger.info("Application manager initialized")
