"""
Data models for file management dialogs with immutable data structures.

This module provides the core data structures for file management dialogs,
including FileItem, Group, GroupStats, and DialogState classes that implement
immutable patterns for thread safety and proper MVC separation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path

from ..core.logging.decorators import log_errors
from ..core.logging.logger import get_logger
import traceback
import sys
import inspect

from .models import SelectionStore

logger = get_logger(__name__)


class DialogView(Enum):
    """Available view modes for dialogs."""
    TREE = "tree"
    PREVIEW = "preview"
    REPORT = "report"


@dataclass(frozen=True)
class FileItem:
    """
    Immutable representation of a file item in dialogs.
    
    Frozen dataclass ensures thread safety and prevents accidental mutation.
    This class represents a single file with metadata used in both duplicate
    and similarity management dialogs.
    
    Args:
        path: Absolute file path
        size: File size in bytes
        resolution: Image resolution as string (e.g., "1920x1080")
        mod_date: Modification date as string
        score: Similarity score (0-100) for similarity mode, None for duplicates
        file_type: File extension/type
        savings: Potential savings in bytes for duplicate mode
        quality_score: Optional image quality score (normalized, higher is better)
        quality_algorithm: Name of the quality algorithm used (e.g., 'brisque')
    
    Example:
        >>> item = FileItem(
        ...     path="/path/to/image.jpg",
        ...     size=1024,
        ...     resolution="1920x1080",
        ...     mod_date="2023-01-01",
        ...     score=95.5,
        ...     file_type="JPEG",
        ...     savings=2048
        ... )
        >>> item.basename
        'image.jpg'
        >>> item.directory
        '/path/to'
    """
    
    path: str
    size: int
    resolution: str
    mod_date: str
    score: Optional[float] = None
    file_type: str = ""
    savings: int = 0
    quality_score: Optional[float] = None
    quality_algorithm: Optional[str] = None
    
    @property
    def basename(self) -> str:
        """Return file basename."""
        try:
            return Path(self.path).name
        except (ValueError, TypeError) as e:
            logger.error(
                f"Error accessing basename for path '{self.path}'",
                exception=e,
                variables={'path': self.path, 'file': __file__, 'line': sys.exc_info()[2].tb_lineno if sys.exc_info()[2] else inspect.currentframe().f_lineno}
            )
            return "Invalid Path"

    @property
    def directory(self) -> str:
        """Return parent directory."""
        try:
            return str(Path(self.path).parent)
        except (ValueError, TypeError) as e:
            logger.error(
                f"Error accessing directory for path '{self.path}'",
                exception=e,
                variables={'path': self.path, 'file': __file__, 'line': sys.exc_info()[2].tb_lineno if sys.exc_info()[2] else inspect.currentframe().f_lineno}
            )
            return "Invalid Path"


@dataclass(frozen=True)
class GroupStats:
    """
    Statistics for a group of files.
    
    Provides aggregated statistics for a group of duplicate or similar files.
    Used for display purposes and group management operations.
    
    Args:
        total_size: Combined size of all files in the group
        savings: Potential savings if duplicates are removed
        min_score: Minimum similarity score in the group
        max_score: Maximum similarity score in the group
        avg_score: Average similarity score in the group
        file_count: Number of files in the group
    """
    total_size: int
    savings: int
    min_score: float
    max_score: float
    avg_score: float
    file_count: int


@dataclass(frozen=True)
class Group:
    """
    Immutable representation of a file group.
    
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