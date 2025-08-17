"""
Application bootstrap for the KDC Image Organizer (img_app).

Provides a stable main() entry point suitable for PDM script invocation:
  pdm run imgapp

This module creates a single QApplication instance (if not already present),
constructs and shows the main window, and starts the Qt event loop.

Note: This app is a thin shell around pk_py_lib components and is designed
for easy extraction to a separate repository.

Syntax validation: This file has been reviewed for Python syntax correctness.
"""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def _ensure_application(argv: Optional[list[str]] = None) -> QApplication:
    """
    Ensure a single QApplication instance exists.

    Parameters
    ----------
    argv : Optional[list[str]]
        Optional list of command-line arguments. If None, sys.argv is used.

    Returns
    -------
    QApplication
        The (existing or newly created) QApplication instance.

    Raises
    ------
    RuntimeError
        If the QApplication cannot be created for any reason.

    Examples
    --------
    >>> app = _ensure_application()
    >>> isinstance(app, QApplication)
    True
    """
    app = QApplication.instance()
    if app is None:
        try:
            app = QApplication(argv or sys.argv)
        except Exception as exc:
            raise RuntimeError(f"Failed to create QApplication: {exc}") from exc
    return app


def main() -> int:
    """
    Entry point for launching the KDC Image Organizer application.

    Creates the QApplication (if one does not already exist), initializes and
    shows the main window, and starts the Qt event loop.

    This startup sequence also initializes the library DatabaseManager,
    ConfigurationManager and CacheManager, wiring them into the MainWindow
    instance for use by UI components. The initialization is defensive: if the
    pk_py_lib components are unavailable the application will still show the
    main window (fallback behavior).
    """
    app = _ensure_application()

    # Initialize library components if possible
    try:
        # Import library components from the in-repo pk_py_lib package.
        # The img_app scaffolding uses the development layout where the package
        # may be importable as `src.pk_py_lib`.
        from src.pk_py_lib.core.database import DatabaseManager
        from src.pk_py_lib.core.configuration import ConfigurationManager
        from src.pk_py_lib.core.cache import CacheManager

        # Initialize database manager (creates DBs and applies migrations)
        db_mgr = DatabaseManager()
        db_mgr.initialize()

        # Initialize configuration manager (reads/creates app_settings/profile rows)
        config_mgr = ConfigurationManager(db_mgr)

        # Initialize cache manager using app_settings.cache_size_mb (MB)
        cache_dir = db_mgr.data_dir / "cache"
        try:
            max_mb = int(config_mgr.get_app_setting("cache_size_mb") or 5120)
        except Exception:
            max_mb = 5120
        cache_mgr = CacheManager(cache_dir, max_size_mb=max_mb)
    except Exception as exc:
        # If anything fails, log and continue with UI-only startup
        import logging
        logging.getLogger("img_app.app").exception("Failed to initialize core components: %s", exc)
        db_mgr = None
        config_mgr = None
        cache_mgr = None

    # Create main window and attach core components for use by UI
    window = MainWindow()
    # Attach managers if available (non-invasive integration)
    if db_mgr is not None:
        setattr(window, "database_manager", db_mgr)
    if config_mgr is not None:
        setattr(window, "configuration_manager", config_mgr)
    if cache_mgr is not None:
        setattr(window, "cache_manager", cache_mgr)

    window.show()
    return app.exec()


if __name__ == "__main__":
    # Allow direct execution for convenience during development
    raise SystemExit(main())