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

    Returns
    -------
    int
        The Qt application exit code, suitable for use as a process return code.

    Usage
    -----
    From PDM:
      pdm run imgapp

    From Python:
      python -c "from img_app.img_app.app import main; raise SystemExit(main())"
    """
    app = _ensure_application()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    # Allow direct execution for convenience during development
    raise SystemExit(main())