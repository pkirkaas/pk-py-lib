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

# Application identity
# Keeping the app name/version here allows About dialogs and logs to reference a single source.
# Version can be updated independently of the library version in src/pk_py_lib.
__app_name__ = "KDC Image Organizer"
__app_version__ = "0.1.0-dev"

__all__ = ["app", "main_window", "__app_name__", "__app_version__"]