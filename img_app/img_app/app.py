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

import argparse
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QApplication
from src.pk_py_lib.gui.utils.messages import show_selectable_error

from .main_window import MainWindow

from src.pk_py_lib.api.settings_profiles import SettingsProfilesAPI
from src.pk_py_lib.gui.settings_manager.structured_dialog import structured_settings_manager_dialog
from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController

from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.configuration import ConfigurationManager
from src.pk_py_lib.core.cache import CacheManager


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
    
    Startup sequence (direct launch with integrated settings management):
    1) Instantiate QApplication.
    2) Initialize/open database and run migrations via DatabaseManager.
    3) Create SettingsProfilesAPI and ensure_default_profile() to guarantee an Active profile exists.
    4) Fetch the active profile for the main window.
    5) Create and show MainWindow, passing the active profile and managers.
    
    Supports CLI mode: `imgapp -l` or `imgapp --location` to list actual local data paths used.
    Qt flags (e.g., `-platform offscreen`) are passed through to QApplication via parse_known_args().
    
    Returns
    -------
    int
        Qt event loop exit code; non-zero on fatal startup error.
    
    Notes
    -----
    - The application now launches directly with settings management integrated into the main window.
    - Robust error handling: any fatal error during DB/API startup is shown via QMessageBox, and the app exits.
    """
    parser = argparse.ArgumentParser(description="KDC Image Organizer")
    parser.add_argument("-l", "--location", action="store_true", help="List all local data paths used by the application")
    parser.add_argument("-d", "--default", action="store_true", help="Automatically run/start the last profile used when the GUI is started")
    args, qt_argv = parser.parse_known_args()
    
    if args.location:
        # CLI mode: initialize managers and print actual paths
        try:
            db_mgr = DatabaseManager()
            db_mgr.initialize()
            
            config_mgr = None
            try:
                config_mgr = ConfigurationManager(db_mgr)
                cache_dir = db_mgr.cache_dir
                max_mb = int(getattr(config_mgr, "get_app_setting", lambda k: 5120)("cache_size_mb") or 5120)
                cache_mgr = CacheManager(cache_dir, max_size_mb=max_mb)
            except Exception:
                cache_mgr = None
            
            # Collect and print actual resolved paths with existence checks
            data_dir = db_mgr.data_dir.resolve()
            settings_db = db_mgr.settings_db.resolve()
            cache_db = db_mgr.cache_db.resolve()
            sessions_db = (db_mgr.data_dir / 'sessions.db').resolve()
            backups_dir = (db_mgr.data_dir / 'backups').resolve()
            logs_dir = (db_mgr.data_dir / 'logs').resolve()
            img_app_log = (logs_dir / 'img_app.log').resolve()
            pk_py_lib_log = (logs_dir / 'pk_py_lib.log').resolve()
            cache_dir = cache_mgr.cache_dir.resolve() if cache_mgr else db_mgr.cache_dir.resolve()
            thumbnails_dir = cache_mgr.thumb_base.resolve() if cache_mgr else (cache_dir / 'thumbnails').resolve()
            
            def status(path: Path):
                return " ✓" if path.exists() else " ✗ (does not exist)"
            
            print(f"{settings_db}{status(settings_db)}")
            print(f"{cache_db}{status(cache_db)}")
            print(f"{backups_dir}{status(backups_dir)}")
            print(f"{img_app_log}{status(img_app_log)}")
            print(f"{pk_py_lib_log}{status(pk_py_lib_log)}")
            print(f"{thumbnails_dir}{status(thumbnails_dir)}")
            print(f"{sessions_db}{status(sessions_db)}")  # Planned, likely ✗
            sys.exit(0)
        except Exception as exc:
            print(f"Error initializing managers for --location: {exc}", file=sys.stderr)
            sys.exit(1)
    
    # Pass through any remaining args (likely Qt flags) to QApplication
    app = _ensure_application([sys.argv[0]] + qt_argv)

    # Will be attached to the MainWindow if initialized successfully
    db_mgr = None
    config_mgr = None
    cache_mgr = None
    controller = None # New variable for the controller
    active_profile: Optional[Dict[str, Any]] = None
    
    try:
        # Core managers imported at module top; using them directly
    
        # 2) Initialize/open DBs and run migrations
        db_mgr = DatabaseManager()
        db_mgr.initialize()
    
        # 3) Profiles API bound to this DB; ensure a default/active profile exists
        api = SettingsProfilesAPI(db_mgr)
        ensured = api.ensure_default_profile()
        
        # 3.1) Initialize the Settings Manager Controller
        from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
        controller = SettingsManagerController(api)
        if not ensured.success:
            show_selectable_error(
                None,
                "Startup Error",
                f"Failed to ensure default settings profile:\n{ensured.message or 'Unknown error'}",
            )
            return 1

        # 4) Get the active profile for the main window
        active_resp = api.get_active()
        if active_resp.success and active_resp.data:
            active_profile = active_resp.data
        else:
            # Fallback: get first profile if active not set
            list_resp = api.list_profiles()
            if list_resp.success and list_resp.data and len(list_resp.data) > 0:
                active_profile = list_resp.data[0]
            else:
                show_selectable_error(
                    None,
                    "Startup Error",
                    "No settings profiles available. Please create a profile to continue.",
                )
                return 1

        # Optional managers (best-effort; failures are non-fatal)
        try:
            config_mgr = ConfigurationManager(db_mgr)
            cache_dir = db_mgr.cache_dir
            try:
                max_mb = int(getattr(config_mgr, "get_app_setting", lambda k: 5120)("cache_size_mb") or 5120)
            except Exception:
                max_mb = 5120
            cache_mgr = CacheManager(cache_dir, max_size_mb=max_mb)
        except Exception as exc:
            import logging
            logging.getLogger("img_app.app").exception("Optional manager init failed: %s", exc)

    except Exception as exc:
        # Any fatal initialization error -> show and exit
        show_selectable_error(
            None,
            "Startup Error",
            f"Initialization failed:\n{exc}",
        )
        return 1

    # 5) Create main window, pass active profile, and attach managers
    window = MainWindow(active_profile=active_profile, cli_args=args)
    if db_mgr is not None:
        setattr(window, "database_manager", db_mgr)
    if config_mgr is not None:
        setattr(window, "configuration_manager", config_mgr)
    if cache_mgr is not None:
        setattr(window, "cache_manager", cache_mgr)

    if controller is not None:
        setattr(window, "controller", controller)

    # Load profiles now that database manager is available
    window.load_profiles()

    window.show()
    
    # Check for CLI option to automatically start the default operation
    if args.default:
        window.start_default_operation()
        
    return app.exec()


if __name__ == "__main__":
    # Allow direct execution for convenience during development
    raise SystemExit(main())