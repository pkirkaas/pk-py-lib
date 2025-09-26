"""
Widgets subpackage for img_app.

Houses modular widgets used by the KDC Image Organizer application. Initial
milestone keeps widgets minimal; as the UI grows, these widgets will be
expanded and/or replaced by reusable components sourced from pk_py_lib.
"""

# Export the new manager dialogs and the base class for convenient import.
from .base_group_manager import BaseImageGroupManagerDialog
from .duplicate_manager import DuplicateManagerDialog
from .similarity_manager import SimilarityManagerDialog

__all__ = [
    "BaseImageGroupManagerDialog",
    "DuplicateManagerDialog",
    "SimilarityManagerDialog"
]