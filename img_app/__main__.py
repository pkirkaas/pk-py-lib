"""
Module entry point for running the development app as a module:

  python -m img_app

This defers to img_app.img_app.app.main() to launch the PySide6 application.
"""

from __future__ import annotations

from img_app.img_app.app import main

if __name__ == "__main__":
    raise SystemExit(main())