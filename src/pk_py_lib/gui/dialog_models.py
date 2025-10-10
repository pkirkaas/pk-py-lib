"""
Data models for file management dialogs with immutable data structures.

DEPRECATION NOTICE:
-------------------
The classes FileItem, GroupStats, and DialogView have been moved to pk_py_lib.gui.models
for consistency and to serve as the single source of truth. This module now imports them
from models.py for backward compatibility.

New code should import directly from pk_py_lib.gui.models:
    from pk_py_lib.gui.models import FileItem, GroupStats, DialogView

This module will be maintained for backward compatibility but may be removed in a future version.

Current module contents:
* FileItem, GroupStats, DialogView - DEPRECATED (imported from models.py)
* Group, DialogState - Still defined here (use List-based groups)
* SelectionStore - DEPRECATED (imported from models.py)

For new code, prefer:
* FileGroup from models.py (uses Tuple instead of List for immutability)
* FileGroupModel from models.py (advanced filtering and direction support)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# Import the canonical versions from models.py
from .models import (
    FileItem,
    GroupStats,
    DialogView,
    SelectionStore,
)

from ..core.logging.decorators import log_errors
from ..core.logging.logger import get_logger
import traceback
import sys
import inspect

logger = get_logger(__name__)

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing FileItem, GroupStats, DialogView, and SelectionStore from "
    "pk_py_lib.gui.dialog_models is deprecated. "
    "Import from pk_py_lib.gui.models instead. "
    "This module will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2
)

# Export the imported classes along with locally-defined ones
__all__ = [
    'FileItem',      # Re-exported from models.py
    'GroupStats',    # Re-exported from models.py
    'DialogView',    # Re-exported from models.py
    'SelectionStore', # Re-exported from models.py
    'Group',         # Defined below (List-based)
    'DialogState',   # Defined below
]


@dataclass(frozen=True)
class Group:
    """
    Immutable representation of a file group (List-based variant).

    NOTE: For new code, consider using FileGroup from models.py which uses
    Tuple[FileItem, ...] instead of List[FileItem] for better immutability.

    Groups can represent duplicates or similarity clusters.
    Each group has a reference path (typically the first file) and
    contains a list of FileItem objects with their metadata.

    Args:
        id: Unique group identifier
        items: List of FileItem objects in the group
        stats: GroupStats object with aggregated statistics
        ref_path: Reference path for the group (typically first file)

    Example:
        >>> group = Group(
        ...     id=1,
        ...     items=[file_item1, file_item2],
        ...     stats=group_stats,
        ...     ref_path="/path/to/reference.jpg"
        ... )
        >>> group.item_count
        2
    """

    id: int
    items: List[FileItem]
    stats: GroupStats
    ref_path: str

    @property
    @log_errors()
    def item_count(self) -> int:
        """Return number of items in group."""
        return len(self.items)


@dataclass
class DialogState:
    """
    Complete state of a management dialog.

    Mutable container for immutable data structures. This class holds
    the complete state of a dialog including groups, selection store,
    settings profile, and UI state.

    Args:
        groups: List of Group objects to display
        selection_store: SelectionStore instance for selection management
        settings_profile: Optional settings profile dictionary
        current_view: Current view mode (tree, preview, report)
        filter_text: Current filter text for searching

    Example:
        >>> state = DialogState(
        ...     groups=[group1, group2],
        ...     selection_store=selection_store,
        ...     settings_profile=profile_data,
        ...     current_view=DialogView.TREE,
        ...     filter_text="jpg"
        ... )
        >>> filtered = state.get_filtered_groups()
    """

    groups: List[Group]
    selection_store: SelectionStore
    settings_profile: Optional[Dict[str, Any]] = None
    current_view: DialogView = DialogView.TREE
    filter_text: str = ""

    @log_errors()
    def get_filtered_groups(self) -> List[Group]:
        """Return groups filtered by current filter text."""
        if not self.filter_text:
            return self.groups

        try:
            filter_lower = self.filter_text.lower()
            filtered_groups = []

            for group in self.groups:
                # Filter group items
                filtered_items = [
                    item for item in group.items
                    if filter_lower in item.path.lower() or
                       filter_lower in item.basename.lower()
                ]

                if filtered_items:
                    # Create new group with filtered items
                    # Note: stats may need recalculation in actual implementation
                    filtered_groups.append(Group(
                        id=group.id,
                        items=filtered_items,
                        stats=group.stats,  # Simplified - stats may need recalculation
                        ref_path=group.ref_path
                    ))

            return filtered_groups
        except (ValueError, AttributeError, TypeError) as e:
            logger.error(
                f"Error filtering groups with text '{self.filter_text}'",
                exception=e,
                variables={'filter_text': self.filter_text, 'groups_count': len(self.groups), 'file': __file__, 'line': sys.exc_info()[2].tb_lineno if sys.exc_info()[2] else inspect.currentframe().f_lineno}
            )
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Filtering Error", f"Failed to filter groups: {str(e)}")
            return self.groups  # Return unfiltered to prevent crash
