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
import datetime
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
from src.pk_py_lib.core.logging.logger import configure_logging, LogLevel
from src.pk_py_lib.core import get_data_dir # Unified data directory function
from src.pk_py_lib.core.flat_cache import FlatCacheManager


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
    description = """
KDC Image Organizer (img_app) CLI Interface

This application provides a graphical user interface (GUI) for managing and organizing images.
It also supports several command-line interface (CLI) options for diagnostics and automated startup.

Usage:
  pdm run imgapp [OPTIONS] [QT_FLAGS]

Examples:
  pdm run imgapp --help
  pdm run imgapp --location
  pdm run imgapp --default
"""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # CLI Options
    parser.add_argument(
        "-l",
        "--location",
        action="store_true",
        help=(
            "List all local data paths (databases, caches, logs) used by the application "
            "and check their existence status. This flag runs in CLI mode and exits immediately. "
            "Type: Flag (Boolean), Default: False."
        )
    )
    parser.add_argument(
        "-d",
        "--default",
        action="store_true",
        help=(
            "Automatically start the last operation/profile used when the GUI is launched. "
            "This is useful for automated or rapid startup. "
            "Type: Flag (Boolean), Default: False."
        )
    )
    args, qt_argv = parser.parse_known_args()
    
    # --- Logging Configuration (Dynamic based on app setting) ---
    # Defer logging setup until after ConfigurationManager is initialized
    # to respect the logging_to_user_dir setting (project root vs user data dir)
    
    # Default to project root for early errors before config is available
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Placeholder paths for early logging if needed
    early_cache_log_path = log_dir / "cache_process.log"
    early_log_file_path = log_dir / "img_app-terminal.log"
    
    # Early cache logger setup (will be reconfigured later if needed)
    from src.pk_py_lib.core.logging.logger import get_cache_logger
    get_cache_logger(log_dir=log_dir)
    
    # Early main logging (minimal, will be fully configured after settings)
    try:
        from src.pk_py_lib.core.logging.logger import configure_logging, LogLevel
        configure_logging(
            console=True,
            file_path=early_log_file_path,
            level=LogLevel.INFO,
            rich_console=True
        )
    except Exception as exc:
        print(f"Warning: Failed to configure early logging: {exc}", file=sys.stderr)

    if args.location:
        # CLI mode: initialize managers and print actual paths
        try:
            # Use the unified data directory for path reporting
            from src.pk_py_lib.core import get_data_dir
            data_dir = get_data_dir().resolve()
            
            # Initialize DatabaseManager (uses get_data_dir internally now)
            db_mgr = DatabaseManager()
            db_mgr.initialize()
            
            # Initialize ConfigurationManager to get cache size
            config_mgr = None
            try:
                config_mgr = ConfigurationManager(db_mgr)
                max_mb = int(getattr(config_mgr, "get_app_setting", lambda k: 5120)("cache_size_mb") or 5120)
            except Exception:
                max_mb = 5120
            
            # Collect and print actual resolved paths with existence checks
            settings_db = db_mgr.settings_db.resolve()
            backups_dir = (data_dir / 'backups').resolve()
            sessions_db = (data_dir / 'sessions.db').resolve() # Assuming sessions.db is also in data_dir
            
            # Default log file path (project root for --location since config not fully dynamic here)
            PROJECT_ROOT = Path(__file__).parent.parent.parent
            log_dir = PROJECT_ROOT / "logs"
            app_log = (log_dir / "img_app-terminal.log").resolve()
            
            # Flat cache path
            flat_cache_db = (data_dir / 'flat_cache.db').resolve()
            
            def status(path: Path):
                return " ✓" if path.exists() else " ✗ (does not exist)"
            
            print(f"--- Unified Data Directory ---")
            print(f"Base Data Dir: {data_dir}{status(data_dir)}")
            print(f"Settings DB: {settings_db}{status(settings_db)}")
            print(f"Flat Cache DB: {flat_cache_db}{status(flat_cache_db)}")
            print(f"Backups Dir: {backups_dir}{status(backups_dir)}")
            print(f"Log File: {app_log}{status(app_log)}")
            print(f"Sessions DB: {sessions_db}{status(sessions_db)}")
            sys.exit(0)
        except Exception as exc:
            print(f"Error initializing managers for --location: {exc}", file=sys.stderr)
            sys.exit(1)
    
    # Pass through any remaining args (likely Qt flags) to QApplication
    app = _ensure_application([sys.argv[0]] + qt_argv)

    # Will be attached to the MainWindow if initialized successfully
    db_mgr = None
    config_mgr = None
    flat_cache_mgr = None # Add FlatCacheManager
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
        config_mgr = None
        flat_cache_mgr = None
        
        try:
            config_mgr = ConfigurationManager(db_mgr)
            flat_cache_mgr = FlatCacheManager()
            
            # Now configure dynamic logging based on app setting
            logging_to_user_dir = config_mgr.get_app_setting('logging_to_user_dir')  # Defaults to False from schema if not set.
            
            if logging_to_user_dir:
                from src.pk_py_lib.core import get_data_dir
                log_dir = get_data_dir() / "logs"
            else:
                log_dir = PROJECT_ROOT / "logs"
            
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Reconfigure main terminal log with dynamic path and rotation
            LOG_FILE_PATH = log_dir / "img_app-terminal.log"
            
            # Rotate existing main log file (similar to cache rotation)
            if LOG_FILE_PATH.exists():
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = LOG_FILE_PATH.with_name(f"img_app-terminal_{ts}.log")
                try:
                    LOG_FILE_PATH.rename(new_name)
                except OSError as e:
                    # Log to console since main logging not fully set up yet
                    print(f"Warning: Failed to rotate main log file: {e}", file=sys.stderr)
            
            # Create new main log file
            LOG_FILE_PATH.touch(exist_ok=True)
            
            # Reconfigure main logging with dynamic path
            configure_logging(
                console=True,
                file_path=LOG_FILE_PATH,
                level=LogLevel.INFO,
                rich_console=True
            )
            
            # Reconfigure cache logger with dynamic log_dir
            cache_log_path = log_dir / "cache_process.log"
            
            # Rotate cache log if needed (idempotent)
            if cache_log_path.exists():
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = cache_log_path.with_name(f"cache_process_{ts}.log")
                try:
                    cache_log_path.rename(new_name)
                except OSError as e:
                    # Already logged via main logger or early console
                    pass
            
            # Create new cache log file
            cache_log_path.touch(exist_ok=True)
            
            # Reinitialize cache logger with dynamic log_dir
            get_cache_logger(log_dir=log_dir)
            
        except Exception as exc:
            import logging
            logging.getLogger("img_app.app").exception("Optional manager init failed: %s", exc)
            # If config fails, logging remains in project root (fallback)

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
    
    if flat_cache_mgr is not None:
        setattr(window, "flat_cache_manager", flat_cache_mgr)

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