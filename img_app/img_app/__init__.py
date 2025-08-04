"""
img_app package root for the KDC Image Organizer development application.

This package provides a thin PySide6 application shell that consumes reusable
components from pk_py_lib. It is intentionally structured for easy extraction
to its own repository in the future.

Modules:
- app: QApplication bootstrap and main() entry point for PDM script.
- main_window: QMainWindow implementation with title and basic menus.
- widgets: Subpackage containing modular UI widgets used by the main window.
"""
__all__ = ["app", "main_window"]