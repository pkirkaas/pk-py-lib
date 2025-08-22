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
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QApplication
from src.pk_py_lib.gui.utils.messages import show_selectable_error

from .main_window import MainWindow

from src.pk_py_lib.api.settings_profiles import SettingsProfilesAPI
from src.pk_py_lib.gui.settings_manager.structured_dialog import structured_settings_manager_dialog


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

    Startup sequence (modal Settings Manager enforced):
    1) Instantiate QApplication.
    2) Initialize/open database and run migrations via DatabaseManager.
    3) Create SettingsProfilesAPI and ensure_default_profile() to guarantee an Active profile exists.
    4) Present the Settings Manager dialog modally (always shown on launch).
    5) After dismissal (OK or Cancel), fetch the active profile; if missing, ensure a default and re-fetch.
    6) Create and show MainWindow, passing the active profile.

    Returns
    -------
    int
        Qt event loop exit code; non-zero on fatal startup error.

    Notes
    -----
    - The dialog is shown before the main window; exec() on the dialog runs a nested event loop.
    - Robust error handling: any fatal error during DB/API/dialog startup is shown via QMessageBox, and the app exits.
    """
    app = _ensure_application()

    # Will be attached to the MainWindow if initialized successfully
    db_mgr = None
    config_mgr = None
    cache_mgr = None
    active_profile: Optional[Dict[str, Any]] = None

    try:
        # Import core managers (development layout import path)
        from src.pk_py_lib.core.database import DatabaseManager
        from src.pk_py_lib.core.configuration import ConfigurationManager
        from src.pk_py_lib.core.cache import CacheManager

        # 2) Initialize/open DBs and run migrations
        db_mgr = DatabaseManager()
        db_mgr.initialize()

        # 3) Profiles API bound to this DB; ensure a default/active profile exists
        api = SettingsProfilesAPI(db_mgr)
        ensured = api.ensure_default_profile()
        if not ensured.success:
            show_selectable_error(
                None,
                "Startup Error",
                f"Failed to ensure default settings profile:\n{ensured.message or 'Unknown error'}",
            )
            return 1

        # 4) Present Settings Manager dialog (always on launch, modal)
        try:
            # Get the active profile from the dialog; exit if canceled
            active_profile = structured_settings_manager_dialog(parent=None, modal=True)
            if active_profile is None:
                # User canceled the dialog, exit the application
                return 0
        except Exception as dlg_exc:
            show_selectable_error(
                None,
                "Settings Manager Error",
                f"Failed to open Settings Manager:\n{dlg_exc}",
            )
            return 1

        # 5) Use the active profile returned from the dialog
        # No need for defensive repair since dialog ensures valid active profile

        # Optional managers (best-effort; failures are non-fatal)
        try:
            config_mgr = ConfigurationManager(db_mgr)
            cache_dir = db_mgr.data_dir / "cache"
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

    # 6) Create main window, pass active profile, and attach managers
    window = MainWindow(active_profile=active_profile)
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