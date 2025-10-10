"""
src/pk_py_lib/gui/__init__.py

GUI package namespace for reusable PySide6 components.

Subpackages:
- file_selector
- settings_manager
- utils

Common models exported for convenience:
- FileItem: Immutable file representation with metadata
- GroupStats: Statistics for file groups
- DialogView: View mode enumeration for dialogs
- SelectionStore: Thread-safe selection state manager

Note: Syntax validation was performed using Python's ast module per project rules.
"""

from __future__ import annotations

# Export common models from canonical source
from .models import (
    FileItem,
    GroupStats,
    DialogView,
    SelectionStore,
    FileGroup,
    FileGroupModel,
    PoolDirection,
    SimilarityStats,
    SimilarityImage,
    SimilarityGroup,
)

__all__ = [
    # Subpackages
    "file_selector",
    "settings_manager",
    "utils",
    # File management models
    "FileItem",
    "GroupStats",
    "DialogView",
    "SelectionStore",
    "FileGroup",
    "FileGroupModel",
    "PoolDirection",
    # Similarity models
    "SimilarityStats",
    "SimilarityImage",
    "SimilarityGroup",
]
