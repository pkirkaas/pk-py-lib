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
import inspect
import traceback
import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import asdict

from src.pk_py_lib.core.logging import get_logger

from PySide6.QtWidgets import QApplication
from src.pk_py_lib.gui.utils.messages import show_selectable_error

from .main_window import MainWindow

from src.pk_py_lib.api.settings import UnifiedSettingsAPI
from src.pk_py_lib.gui.settings_manager.structured_dialog import structured_settings_manager_dialog
from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController

from src.pk_py_lib.core.settings.json_unified_manager import JSONSettingsManager
from src.pk_py_lib.core.logging.logger import configure_logging, LogLevel, PKLogger, get_cache_logger
from src.pk_py_lib.core.logging.decorators import log_errors
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
    """
    # --- Global Exception Hook ---
    def log_exceptions(exc_type, exc_value, exc_traceback):
        """Log unhandled exceptions to the terminal and show a message box."""
        # Format the traceback
        traceback_details = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )

        # Print to stderr as a fallback
        print(f"Unhandled exception:\n{traceback_details}", file=sys.stderr)

        # Log the exception
        try:
            from src.pk_py_lib.core.logging import get_logger
            logger = get_logger("img_app.global_errors")
            logger.error(
                "Unhandled exception caught:\n"
                f"Type: {exc_type.__name__}\n"
                f"Value: {exc_value}\n"
                f"Traceback:\n{traceback_details}"
            )
        except Exception:
            # If logging fails, the stderr output will have to suffice
            pass

        # Show the error in a message box
        show_selectable_error(
            None,
            "Unhandled Exception",
            f"An unexpected error occurred:\n\n{exc_value}\n\n"
            "Please check the logs for more details.",
        )

    sys.excepthook = log_exceptions

    # Startup message for terminal launches
    print("\n" * 8)
    print("=============")
    print("Starting imgapp")
    print("=============")

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

    # Early main logging (minimal, will be fully configured after settings)
    # Create FileOutput directly with rotate_existing=False to prevent double renaming
    try:
        from src.pk_py_lib.core.logging.logger import configure_logging, LogLevel, _global_outputs
        from src.pk_py_lib.core.logging.outputs.file import FileOutput

        # Create early file output with rotation disabled to avoid double rename conflict
        early_file_output = FileOutput(
            file_path=early_log_file_path,
            rotate_existing=False  # Disable automatic rotation for early logging
        )

        # Configure logging with console only (file output added manually)
        configure_logging(
            console=True,
            file_path=None,  # No file path since we're adding FileOutput manually
            level=LogLevel.DEBUG,
            rich_console=True
        )

        # Add the early file output to global outputs
        _global_outputs.append(early_file_output)

    except Exception as exc:
        print(f"Warning: Failed to configure early logging: {exc}", file=sys.stderr)

    logger = get_logger("img_app.app")

    if args.location:
        # CLI mode: initialize managers and print actual paths
        try:
            # Use the unified data directory for path reporting
            from src.pk_py_lib.core import get_data_dir
            data_dir = get_data_dir().resolve()

            # Initialize JSON settings manager
            json_settings_mgr = JSONSettingsManager()

            # Initialize JSON settings manager
            json_settings_mgr = JSONSettingsManager()

            # Collect and print actual resolved paths with existence checks
            backups_dir = (data_dir / 'backups').resolve()

            # JSON settings files
            app_settings_json = json_settings_mgr.settings_dir / "app-settings.json"
            search_profiles_json = json_settings_mgr.settings_dir / "search-profiles.json"

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
            print(f"App Settings JSON: {app_settings_json}{status(app_settings_json)}")
            print(f"Search Profiles JSON: {search_profiles_json}{status(search_profiles_json)}")
            print(f"Flat Cache DB: {flat_cache_db}{status(flat_cache_db)}")
            print(f"Backups Dir: {backups_dir}{status(backups_dir)}")
            print(f"Log File: {app_log}{status(app_log)}")
            sys.exit(0)
        except Exception as exc:
            print(f"Error initializing managers for --location: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        # Pass through any remaining args (likely Qt flags) to QApplication
        app = _ensure_application([sys.argv[0]] + qt_argv)

        # Will be attached to the MainWindow if initialized successfully
        flat_cache_mgr = None # Add FlatCacheManager
        controller = None # New variable for the controller
        active_profile: Optional[Dict[str, Any]] = None

        try:
            # Core managers imported at module top; using them directly

            # 2) Initialize JSON settings manager and ensure default profile exists
            json_settings_manager = JSONSettingsManager()
            api = UnifiedSettingsAPI(json_settings_manager)
            # JSON settings manager automatically creates default profiles on initialization
            # No need for explicit ensure_default_profile call

            # 2.1) Initialize the Settings Manager Controller
            from src.pk_py_lib.gui.settings_manager.controller import SettingsManagerController
            controller = SettingsManagerController(api)

            # 3) Get the active profile for the main window
            active_resp = api.get_active()
            if active_resp.success and active_resp.data:
                active_profile = asdict(active_resp.data)
            else:
                # Fallback: get first profile if active not set
                list_resp = api.list_profiles()
                if list_resp.success and list_resp.data and len(list_resp.data) > 0:
                    active_profile = asdict(list_resp.data[0])
                else:
                    logger.error(
                        "No settings profiles available",
                        exception=ValueError("No settings profiles available. Please create a profile to continue."),
                        file_path=__file__,
                        line_number=inspect.currentframe().f_lineno,
                        func_name="main",
                        profiles_count=0
                    )
                    show_selectable_error(
                        None,
                        "Startup Error",
                        "No settings profiles available. Please create a profile to continue."
                    )
                    return 1

            # Optional managers (best-effort; failures are non-fatal)
            flat_cache_mgr = None

            try:
                # Use JSON settings for logging configuration instead of SQLite ConfigurationManager
                # api.get_setting returns the value directly (Any), not ApiResponse
                logging_to_user_dir = api.get_setting('logging_to_user_dir', default=False)
                flat_cache_mgr = FlatCacheManager()

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
                    level=LogLevel.DEBUG,  # Enable debug logging for enhanced error context
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
                logger.error(
                    "Optional manager init failed",
                    exception=exc,
                    file_path=__file__,
                    line_number=inspect.currentframe().f_lineno,
                    func_name="main",
                    stack_trace=traceback.format_exc()
                )
                # If config fails, logging remains in project root (fallback)

        except Exception as exc:
            # Any fatal initialization error -> show and exit
            logger.error(
                "Fatal initialization error",
                exception=exc,
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="main",
                config_state="failed",
                profiles_count=len(api.list_profiles().data) if 'api' in locals() else 0,
                stack_trace=traceback.format_exc()
            )
            show_selectable_error(
                None,
                "Startup Error",
                f"Fatal initialization error: {str(exc)}"
            )
            return 1

        # 5) Create main window, pass active profile, and attach managers
        window = MainWindow(active_profile=active_profile, cli_args=args)
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
    except Exception:
        traceback.print_exc(file=sys.stderr)
        raise


if __name__ == "__main__":
    # Allow direct execution for convenience during development
    raise SystemExit(main())
