"""
Widgets subpackage for img_app.

Houses modular widgets used by the KDC Image Organizer application. Initial
milestone keeps widgets minimal; as the UI grows, these widgets will be
expanded and/or replaced by reusable components sourced from pk_py_lib.
"""

# Export DuplicateManagerDialog for convenient import via:
#   from img_app.img_app.widgets import DuplicateManagerDialog
from .duplicate_manager import DuplicateManagerDialog

__all__ = ["DuplicateManagerDialog"]