"""
GUI data models for pk-py-lib.

This module contains data models and structures used by GUI components
throughout the library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from PySide6.QtCore import QObject, Signal
import uuid


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
    exact_set_id: Optional[int] = None

    @property
    def basename(self) -> str:
        """Return file basename."""
        return Path(self.path).name

    @property
    def directory(self) -> str:
        """Return parent directory."""
        return str(Path(self.path).parent)


@dataclass(frozen=True)
class GroupStats:
    """Statistics for a group of files."""
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
    """
    id: int
    items: Tuple[FileItem, ...]  # Immutable tuple
    stats: GroupStats
    ref_path: str

    @property
    def item_count(self) -> int:
        """Return number of items in group."""
        return len(self.items)


@dataclass
class DialogState:
    """
    Complete state of a management dialog.

    Mutable container for immutable data structures.
    """
    groups: List[Group]
    selection_store: SelectionStore
    settings_profile: Optional[Dict[str, Any]] = None
    current_view: DialogView = DialogView.TREE
    filter_text: str = ""

    def get_filtered_groups(self) -> List[Group]:
        """Return groups filtered by current filter text."""
        if not self.filter_text:
            return self.groups

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
                filtered_groups.append(Group(
                    id=group.id,
                    items=tuple(filtered_items),
                    stats=group.stats,  # Note: stats may need recalculation
                    ref_path=group.ref_path
                ))

        return filtered_groups


class SelectionStore(QObject):
    """
    Centralized selection state management for file management dialogs.

    Provides robust selection tracking with proper signal/slot communication
    and path normalization for consistent state management.
    """

    # Signals for state change notifications
    selection_changed = Signal(set)  # Emits new selection set
    item_added = Signal(str)        # Individual item added
    item_removed = Signal(str)      # Individual item removed
    selection_cleared = Signal()    # All selections cleared
    selection_count_changed = Signal(int)  # Selection count changed

    def __init__(self, normalizer: Optional[callable] = None):
        """
        Initialize SelectionStore with optional path normalizer.

        Args:
            normalizer: Function to normalize paths for consistent comparison.
                       Defaults to os.path.normcase(os.path.normpath()).
        """
        super().__init__()
        self._selected_paths: Set[str] = set()
        self._normalizer = normalizer or self._default_normalizer

    def _default_normalizer(self, path: str) -> str:
        """Default path normalization using pathlib."""
        return str(Path(path).resolve())

    def add_selection(self, path: str) -> bool:
        """
        Add a path to the selection.

        Args:
            path: File path to add to selection

        Returns:
            bool: True if path was added, False if already selected
        """
        normalized = self._normalizer(path)
        if normalized not in self._selected_paths:
            self._selected_paths.add(normalized)
            self.item_added.emit(normalized)
            self.selection_changed.emit(self._selected_paths.copy())
            self.selection_count_changed.emit(len(self._selected_paths))
            return True
        return False

    def remove_selection(self, path: str) -> bool:
        """
        Remove a path from the selection.

        Args:
            path: File path to remove from selection

        Returns:
            bool: True if path was removed, False if not selected
        """
        normalized = self._normalizer(path)
        if normalized in self._selected_paths:
            self._selected_paths.remove(normalized)
            self.item_removed.emit(normalized)
            self.selection_changed.emit(self._selected_paths.copy())
            self.selection_count_changed.emit(len(self._selected_paths))
            return True
        return False

    def toggle_selection(self, path: str) -> bool:
        """
        Toggle selection state of a path.

        Args:
            path: File path to toggle

        Returns:
            bool: New selection state (True if selected after toggle)
        """
        normalized = self._normalizer(path)
        if normalized in self._selected_paths:
            return not self.remove_selection(path)
        else:
            return self.add_selection(path)

    def clear_selection(self) -> None:
        """Clear all selections with signal emission."""
        if self._selected_paths:
            self._selected_paths.clear()
            self.selection_cleared.emit()
            self.selection_changed.emit(set())
            self.selection_count_changed.emit(0)

    def get_selection_count(self) -> int:
        """Return number of selected items."""
        return len(self._selected_paths)

    def is_selected(self, path: str) -> bool:
        """Check if path is selected."""
        return self._normalizer(path) in self._selected_paths

    def get_selected_paths(self) -> Set[str]:
        """Return copy of selected paths set."""
        return self._selected_paths.copy()

    def batch_update(self, paths_to_add: Set[str], paths_to_remove: Set[str]) -> None:
        """
        Perform batch update of selections.

        Args:
            paths_to_add: Set of paths to add to selection
            paths_to_remove: Set of paths to remove from selection
        """
        # Normalize all paths
        normalized_add = {self._normalizer(p) for p in paths_to_add}
        normalized_remove = {self._normalizer(p) for p in paths_to_remove}

        # Update selection set
        self._selected_paths.update(normalized_add)
        self._selected_paths.difference_update(normalized_remove)

        # Emit signals
        self.selection_changed.emit(self._selected_paths.copy())
        self.selection_count_changed.emit(len(self._selected_paths))
