"""src/pk_py_lib/gui/models.py

Shared data models supporting both the image similarity tooling and the file
management dialogs defined in pk-py-lib. The module provides:

* Immutable containers for perceptual similarity workflows (SimilarityImage,
  SimilarityGroup, SimilarityStats) used by ``core.image.similarity``.
* File-manager centric structures (FileItem, GroupStats, FileGroup,
  FileGroupModel) that keep dialog state immutable and direction-aware.
* A thread-safe SelectionStore implementation built on Qt signals to keep GUI
  widgets in sync without resorting to fragile global sets.

All classes are documented with full PyDoc prose in order to generate reference
documentation automatically.

Syntax validation was performed with Python's ``ast`` module prior to inclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from ..core.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "SimilarityStats",
    "SimilarityImage",
    "SimilarityGroup",
    "DialogView",
    "FileItem",
    "GroupStats",
    "FileGroup",
    "SelectionStore",
    "PoolDirection",
    "FileGroupModel",
]


# --------------------------------------------------------------------------- #
# Similarity-focused data structures (used by core.image.similarity)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SimilarityStats:
    """Aggregate statistics for a perceptual similarity cluster.

    Parameters
    ----------
    min_score:
        Lowest per-image similarity score in the cluster (0.0 - 1.0).
    max_score:
        Highest per-image similarity score in the cluster (0.0 - 1.0).
    avg_score:
        Mean similarity score across all images in the cluster.
    total_size:
        Combined size of all images expressed in bytes.

    Example
    -------
    >>> stats = SimilarityStats(min_score=0.82, max_score=0.97, avg_score=0.90, total_size=1_048_576)
    >>> round(stats.avg_score, 2)
    0.9
    """

    min_score: float = 0.0
    max_score: float = 0.0
    avg_score: float = 0.0
    total_size: int = 0


@dataclass
class SimilarityImage:
    """Metadata captured for a single image in a similarity group.

    Parameters
    ----------
    path:
        Absolute filesystem path to the image.
    size:
        File size in bytes.
    resolution:
        Image dimensions represented as ``"WIDTHxHEIGHT"``.
    mod_date:
        Formatted modification timestamp (for example ``"15-Sep-25"``).
    score:
        Normalised similarity score (0.0 - 1.0) relative to the reference image.
    thumb:
        Optional Qt pixmap used when rendering preview panes; stored separately
        to decouple GUI generation from hashing logic.

    Example
    -------
    >>> img = SimilarityImage(path="/tmp/sample.jpg", size=524_288, resolution="1920x1080",
    ...                       mod_date="15-Sep-25", score=0.94)
    >>> img.basename
    'sample.jpg'
    """

    path: str
    size: int
    resolution: str
    mod_date: str
    score: float = 0.0
    thumb: Optional[QPixmap] = field(default=None, repr=False)

    @property
    def basename(self) -> str:
        """Return the filename component of :attr:`path`."""
        return Path(self.path).name

    @property
    def directory(self) -> str:
        """Return the parent directory containing the image."""
        return str(Path(self.path).parent)


@dataclass(frozen=True)
class SimilarityGroup:
    """Immutable representation of a perceptual similarity cluster.

    Parameters
    ----------
    id:
        Sequential identifier assigned by the caller.
    images:
        Tuple of :class:`SimilarityImage` instances sorted in display order.
    stats:
        Pre-computed statistics for the cluster.
    ref_path:
        Filesystem path used as the reference image when computing scores.

    Example
    -------
    >>> group = SimilarityGroup(
    ...     id=1,
    ...     images=(SimilarityImage("/img/a.jpg", 1, "1x1", "01-Jan-25", 1.0),),
    ...     stats=SimilarityStats(),
    ...     ref_path="/img/a.jpg",
    ... )
    >>> group.ref_path
    '/img/a.jpg'
    """

    id: int
    images: Tuple[SimilarityImage, ...]
    stats: SimilarityStats
    ref_path: str

    @property
    def image_count(self) -> int:
        """Return the number of images bundled in the cluster."""
        return len(self.images)


# --------------------------------------------------------------------------- #
# Dialog-centric data structures
# --------------------------------------------------------------------------- #


class DialogView(Enum):
    """Enumeration describing which dialog view is currently active."""

    TREE = "tree"
    PREVIEW = "preview"
    REPORT = "report"


@dataclass(frozen=True)
class FileItem:
    """Immutable representation of a file entry shown in the management dialogs.

    Parameters
    ----------
    path:
        Absolute filesystem path.
    size:
        File size in bytes.
    resolution:
        Optional resolution string recorded for preview usage.
    mod_date:
        Formatted modification timestamp.
    score:
        Optional similarity score (0.0 - 1.0) for perceptual comparisons.
    file_type:
        Uppercase file type/extension descriptor (``"JPEG"``, ``"PNG"``, ...).
    savings:
        Potential space reclaimed (in bytes) if this file is deleted in favour of
        the reference item.

    The dataclass is frozen to guarantee immutability and safe sharing across
    threads or Qt signal deliveries.
    """

    path: str
    size: int
    resolution: str
    mod_date: str
    score: Optional[float] = None
    file_type: str = ""
    savings: int = 0

    @property
    def basename(self) -> str:
        """Return the basename of the file."""
        return Path(self.path).name

    @property
    def directory(self) -> str:
        """Return the parent directory path."""
        return str(Path(self.path).parent)


@dataclass(frozen=True)
class GroupStats:
    """Aggregate file statistics for a dialog group.

    Parameters
    ----------
    total_size:
        Sum of file sizes for every item in the group.
    savings:
        Aggregate potential savings obtainable from deletions.
    min_score:
        Minimum similarity score within the group (if available).
    max_score:
        Maximum similarity score within the group (if available).
    avg_score:
        Mean similarity score within the group (if available).
    file_count:
        Total number of files contained in the group.

    Example
    -------
    >>> stats = GroupStats(total_size=1024, savings=512, min_score=0.8, max_score=0.95, avg_score=0.9, file_count=3)
    >>> stats.file_count
    3
    """

    total_size: int
    savings: int
    min_score: float
    max_score: float
    avg_score: float
    file_count: int


@dataclass(frozen=True)
class FileGroup:
    """Immutable container describing a group displayed in a dialog tree."""

    id: int
    items: Tuple[FileItem, ...]
    stats: GroupStats
    ref_path: str

    @property
    def item_count(self) -> int:
        """Return the number of files carried by the group."""
        return len(self.items)


# --------------------------------------------------------------------------- #
# SelectionStore – shared selection state with Qt signals
# --------------------------------------------------------------------------- #


class SelectionStore(QObject):
    """Thread-safe selection tracker emitting Qt signals for dialog widgets.

    The store normalises incoming paths (using ``pathlib.Path.resolve`` by
    default) to guarantee OS-independent equality checks. All public mutation
    operations are protected by a re-entrant lock making the class safe for
    use across worker threads and the GUI thread.

    Signals
    -------
    selection_changed:
        Fires whenever the entire selection set changes.
    item_added:
        Emitted for every newly added path.
    item_removed:
        Emitted for every removed path.
    selection_cleared:
        Emitted when the selection becomes empty.
    selection_count_changed:
        Emitted with the updated selection count after each mutation.

    Example
    -------
    >>> store = SelectionStore()
    >>> store.add_selection("/tmp/img.jpg")
    True
    >>> sorted(store.get_selected_paths())
    ['/tmp/img.jpg']
    """

    selection_changed = Signal(set)          # Emits the updated selection set
    item_added = Signal(str)                 # Emits path added to the selection
    item_removed = Signal(str)               # Emits path removed from selection
    selection_cleared = Signal()             # Fires when selection is emptied
    selection_count_changed = Signal(int)    # Emits the selection count

    def __init__(self, normalizer: Optional[Callable[[str], str]] = None) -> None:
        """
        Parameters
        ----------
        normalizer:
            Callable used to normalise paths. Defaults to ``Path(path).resolve()``
            ensuring case and path separator consistency across platforms.
        """
        super().__init__()
        self._normalizer = normalizer or self._default_normalizer
        self._selected_paths: Set[str] = set()
        self._lock = RLock()

    def add_selection(self, path: str) -> bool:
        """Add a path to the selection; returns ``True`` if newly inserted."""
        normalised = self._normalize(path)
        with self._lock:
            if normalised in self._selected_paths:
                return False
            self._selected_paths.add(normalised)

        self.item_added.emit(normalised)
        self.selection_changed.emit(set(self._selected_paths))
        self.selection_count_changed.emit(len(self._selected_paths))
        return True

    def remove_selection(self, path: str) -> bool:
        """Remove a path from the selection; returns ``True`` if removed."""
        normalised = self._normalize(path)
        with self._lock:
            if normalised not in self._selected_paths:
                return False
            self._selected_paths.remove(normalised)
            empty = not self._selected_paths

        self.item_removed.emit(normalised)
        self.selection_changed.emit(set(self._selected_paths))
        self.selection_count_changed.emit(len(self._selected_paths))
        if empty:
            self.selection_cleared.emit()
        return True

    def toggle_selection(self, path: str) -> bool:
        """Toggle the selection state of *path* returning the new state."""
        if self.is_selected(path):
            self.remove_selection(path)
            return False
        self.add_selection(path)
        return True

    def clear_selection(self) -> None:
        """Clear the selection set and emit the relevant signals."""
        with self._lock:
            if not self._selected_paths:
                return
            self._selected_paths.clear()

        self.selection_cleared.emit()
        self.selection_changed.emit(set())
        self.selection_count_changed.emit(0)

    def get_selection_count(self) -> int:
        """Return the number of selected paths."""
        with self._lock:
            return len(self._selected_paths)

    def is_selected(self, path: str) -> bool:
        """Return ``True`` if *path* is currently selected."""
        normalised = self._normalize(path)
        with self._lock:
            return normalised in self._selected_paths

    def get_selected_paths(self) -> Set[str]:
        """Return a copy of the current selection set."""
        with self._lock:
            return set(self._selected_paths)

    def batch_update(self, paths_to_add: Iterable[str], paths_to_remove: Iterable[str]) -> None:
        """Perform a batch mutation adding and removing paths atomically."""
        adds = {self._normalize(path) for path in paths_to_add}
        removes = {self._normalize(path) for path in paths_to_remove}

        with self._lock:
            if not adds and not removes:
                return
            self._selected_paths.update(adds)
            self._selected_paths.difference_update(removes)
            empty = not self._selected_paths
            current = set(self._selected_paths)

        if adds:
            for path in adds:
                if path not in removes:
                    self.item_added.emit(path)
        if removes:
            for path in removes:
                self.item_removed.emit(path)
        if empty:
            self.selection_cleared.emit()

        self.selection_changed.emit(current)
        self.selection_count_changed.emit(len(current))

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _normalize(self, path: str) -> str:
        return self._normalizer(path)

    @staticmethod
    def _default_normalizer(path: str) -> str:
        return str(Path(path).resolve())


# --------------------------------------------------------------------------- #
# File group model with direction-aware filtering
# --------------------------------------------------------------------------- #


class PoolDirection(Enum):
    """Enumeration of supported pool direction filters."""

    ALL = "ALL"
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"
    A_WITHOUT_IN_B = "A_WITHOUT_IN_B"
    B_WITHOUT_IN_A = "B_WITHOUT_IN_A"


@dataclass(frozen=True)
class FileGroupModel:
    """Immutable view-model representing dialog group state.

    Parameters
    ----------
    groups:
        Tuple of :class:`FileGroup` instances describing the canonical group list.
    pool_map:
        Mapping from file path to pool label (typically ``"A"`` or ``"B"``) used
        to evaluate direction filters.
    direction:
        Currently applied pool direction filter.
    source_label:
        Canonical label for the source/reference pool (defaults to ``"A"``).
    target_label:
        Canonical label for the target/comparison pool (defaults to ``"B"``).

    The model exposes helper methods that return derived copies instead of
    mutating internal state, ensuring referential transparency inside Qt-based
    code paths.
    """

    groups: Tuple[FileGroup, ...] = field(default_factory=tuple)
    pool_map: Mapping[str, str] = field(default_factory=dict)
    direction: PoolDirection = PoolDirection.ALL
    source_label: str = "A"
    target_label: str = "B"

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def with_direction(self, direction: PoolDirection) -> "FileGroupModel":
        """Return a new model instance using *direction* for filtering."""
        return replace(self, direction=direction)

    def with_groups(self, groups: Iterable[FileGroup]) -> "FileGroupModel":
        """Return a new model carrying *groups* as the canonical dataset."""
        return replace(self, groups=tuple(groups))

    def with_pool_map(self, pool_map: Mapping[str, str]) -> "FileGroupModel":
        """Return a new model with an updated path → pool mapping."""
        return replace(self, pool_map=dict(pool_map))

    def filtered_groups(self) -> Tuple[FileGroup, ...]:
        """Return groups filtered according to the active direction setting."""
        if self.direction is PoolDirection.ALL:
            return self.groups
        if self.direction is PoolDirection.A_TO_B:
            return self._extract_cross_pool(self.source_label, self.target_label)
        if self.direction is PoolDirection.B_TO_A:
            return self._extract_cross_pool(self.target_label, self.source_label)
        if self.direction is PoolDirection.A_WITHOUT_IN_B:
            return self._extract_without_counterpart(self.source_label, self.target_label)
        if self.direction is PoolDirection.B_WITHOUT_IN_A:
            return self._extract_without_counterpart(self.target_label, self.source_label)
        # Fallback: unknown direction behaves as ALL
        logger.warning("Unhandled pool direction %s; returning canonical groups", self.direction)
        return self.groups

    def iter_groups(self) -> Iterable[FileGroup]:
        """Yield groups complying with the active direction setting."""
        return iter(self.filtered_groups())

    def is_empty(self) -> bool:
        """Return ``True`` if no groups remain after applying the current filter."""
        return not self.filtered_groups()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _extract_cross_pool(self, source: str, target: str) -> Tuple[FileGroup, ...]:
        extracted: List[FileGroup] = []
        next_id = 1
        for group in self.groups:
            partition = self._partition_group(group)
            if source not in partition or target not in partition:
                continue
            target_items = partition[target]
            if not target_items:
                continue
            stats = self._recalculate_stats(target_items)
            extracted.append(
                FileGroup(
                    id=next_id,
                    items=tuple(target_items),
                    stats=stats,
                    ref_path=target_items[0].path,
                )
            )
            next_id += 1
        return tuple(extracted)

    def _extract_without_counterpart(self, primary: str, counterpart: str) -> Tuple[FileGroup, ...]:
        extracted: List[FileGroup] = []
        next_id = 1
        for group in self.groups:
            partition = self._partition_group(group)
            if counterpart in partition:
                continue
            primary_items = partition.get(primary, [])
            if not primary_items:
                continue
            stats = self._recalculate_stats(primary_items)
            extracted.append(
                FileGroup(
                    id=next_id,
                    items=tuple(primary_items),
                    stats=stats,
                    ref_path=primary_items[0].path,
                )
            )
            next_id += 1
        return tuple(extracted)

    def _partition_group(self, group: FileGroup) -> Dict[str, List[FileItem]]:
        partition: Dict[str, List[FileItem]] = {}
        for item in group.items:
            pool = self.pool_map.get(item.path, self.source_label)
            pool_label = pool.upper()
            partition.setdefault(pool_label, []).append(item)
        return partition

    @staticmethod
    def _recalculate_stats(items: Sequence[FileItem]) -> GroupStats:
        if not items:
            return GroupStats(
                total_size=0,
                savings=0,
                min_score=0.0,
                max_score=0.0,
                avg_score=0.0,
                file_count=0,
            )

        total_size = sum(item.size for item in items)
        total_savings = sum(item.savings for item in items)
        scores = [item.score for item in items if item.score is not None]

        if scores:
            min_score = float(min(scores))
            max_score = float(max(scores))
            avg_score = float(sum(scores) / len(scores))
        else:
            min_score = max_score = avg_score = 0.0

        return GroupStats(
            total_size=total_size,
            savings=total_savings,
            min_score=min_score,
            max_score=max_score,
            avg_score=avg_score,
            file_count=len(items),
        )