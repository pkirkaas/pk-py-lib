"""
Main application entry point for KDC Image Organizer.

This module contains the main application bootstrap and initialization
logic for the img_app GUI application.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Optional

# PySide6 imports
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer

# Core pk-py-lib imports
from pk_py_lib.core.logging.logger import get_logger
from pk_py_lib.core.api import response
from pk_py_lib.core.api.response import ErrorCodes

# Local application imports
from .main_window import MainWindow


logger = get_logger(__name__)


def main() -> int:
    """
    Main application entry point.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Enable high DPI support
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        # Create application instance
        app = QApplication(sys.argv)
        app.setApplicationName("KDC Image Organizer")
        app.setApplicationVersion("0.1.0-dev")
        app.setOrganizationName("KDC")

        # Set application properties
        # app.setWindowIcon(None)  # Will be set when icon is available

        # Initialize application components
        app_manager = initialize_application()

        # Create and show main window
        window = MainWindow(app_manager)
        window.show()

        logger.info("Application started successfully")

        # Run event loop
        return app.exec()

    except Exception as e:
        logger.exception("Application failed to start")
        show_critical_error("Application Startup Error",
                          f"Failed to start application: {str(e)}")
        return 1


def initialize_application() -> ApplicationManager:
    """
    Initialize application components and managers.

    Returns:
        Initialized ApplicationManager instance
    """
    logger.info("Initializing application components")

    app_manager = ApplicationManager()

    try:
        # Initialize core components
        app_manager.initialize()

        logger.info("Application components initialized successfully")
        return app_manager

    except Exception as e:
        logger.exception("Failed to initialize application components")
        raise


class ApplicationManager:
    """
    Central application manager coordinating all components.

    This class manages the lifecycle and coordination of all application
    components including database, cache, configuration, and processing.
    """

    def __init__(self):
        """Initialize application manager."""
        self.logger = get_logger("img_app.manager")

        # Component managers
        self.database_manager = None
        self.cache_manager = None
        self.settings_manager = None
        self.processing_engine = None

        # Application state
        self.is_initialized = False

    def initialize(self) -> None:
        """
        Initialize all application components.

        This method initializes all core components in the correct order
        and performs startup validation.
        """
        if self.is_initialized:
            return

        try:
            # Step 1: Initialize data locations
            self._initialize_data_locations()

            # Step 2: Initialize database manager
            self._initialize_database_manager()

            # Step 3: Initialize settings manager
            self._initialize_settings_manager()

            # Step 4: Initialize cache manager
            self._initialize_cache_manager()

            # Step 5: Initialize processing engine
            self._initialize_processing_engine()

            # Step 6: Perform startup validation
            self._perform_startup_validation()

            self.is_initialized = True
            self.logger.info("Application manager initialization complete")

        except Exception as e:
            self.logger.exception("Application manager initialization failed")
            raise

    def _initialize_data_locations(self) -> None:
        """Initialize data directory locations."""
        # Implementation will use platformdirs with PK_IMG_APP_HOME override
        self.logger.debug("Data locations initialized")

    def _initialize_database_manager(self) -> None:
        """Initialize database manager with validation and migration."""
        # Implementation will create DatabaseManager with proper validation
        self.logger.debug("Database manager initialized")

    def _initialize_settings_manager(self) -> None:
        """Initialize settings manager with JSON-based storage."""
        # Implementation will create settings manager
        self.logger.debug("Settings manager initialized")

    def _initialize_cache_manager(self) -> None:
        """Initialize cache manager with FlatCacheManager."""
        # Implementation will create FlatCacheManager
        self.logger.debug("Cache manager initialized")

    def _initialize_processing_engine(self) -> None:
        """Initialize processing engine for similarity detection."""
        # Implementation will create processing engine
        self.logger.debug("Processing engine initialized")

    def _perform_startup_validation(self) -> None:
        """Perform comprehensive startup validation."""
        # Implementation will validate databases, settings, etc.
        self.logger.debug("Startup validation completed")

    def shutdown(self) -> None:
        """Shutdown application components gracefully."""
        self.logger.info("Shutting down application")

        # Shutdown components in reverse order
        if self.processing_engine:
            self.processing_engine.shutdown()

        if self.cache_manager:
            self.cache_manager.shutdown()

        if self.database_manager:
            self.database_manager.close_connections()

        self.logger.info("Application shutdown complete")


def show_critical_error(title: str, message: str) -> None:
    """
    Show critical error dialog and exit.

    Args:
        title: Error dialog title
        message: Error message to display
    """
    app = QApplication.instance()
    if app:
        QMessageBox.critical(
            None,
            title,
            f"{message}\n\nThe application will now exit."
        )
    else:
        # No QApplication instance, use console
        print(f"CRITICAL ERROR: {title}")
        print(message)
        print("Application will exit")


def show_error_dialog(title: str, message: str, parent=None) -> None:
    """
    Show error dialog with selectable text.

    Args:
        title: Dialog title
        message: Error message (will be selectable)
        parent: Parent widget
    """
    from pk_py_lib.gui.utils.messages import show_selectable_error

    try:
        show_selectable_error(parent, title, message)
    except Exception:
        # Fallback to basic message box
        QMessageBox.warning(parent, title, message)


def show_info_dialog(title: str, message: str, parent=None) -> None:
    """
    Show info dialog with selectable text.

    Args:
        title: Dialog title
        message: Info message (will be selectable)
        parent: Parent widget
    """
    from pk_py_lib.gui.utils.messages import show_selectable_info

    try:
        show_selectable_info(parent, title, message)
    except Exception:
        # Fallback to basic message box
        QMessageBox.information(parent, title, message)


# Import required modules to avoid circular imports
try:
    from pk_py_lib.gui.utils import messages
except ImportError:
    # Messages module not available yet
    pass
