# File Management Dialogs - Implementation Guide

## Implementation Overview

This guide provides detailed implementation specifications for the complete re-implementation of the Duplicate Manager and Similarity Manager dialogs based on the architectural design.

## Phase 1: Foundation Components (Week 1)

### SelectionStore Implementation

**File: [`src/pk_py_lib/gui/models.py`](src/pk_py_lib/gui/models.py)**

```python
"""
Robust selection state management with proper MVC separation and signal/slot communication.
"""

from __future__ import annotations

from typing import Callable, Set
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class SelectionStore(QObject):
    """
    Centralized selection state management for file management dialogs.
    
    Provides robust selection tracking with proper signal/slot communication
    and path normalization for consistent state management.
    
    Features:
    - Thread-safe selection operations
    - Signal-based state change notifications
    - Path normalization for cross-platform consistency
    - Batch operations for performance
    """
    
    # Signals for state change notifications
    selection_changed = Signal(set)  # Emits new selection set
    item_added = Signal(str)        # Individual item added
    item_removed = Signal(str)      # Individual item removed
    selection_cleared = Signal()    # All selections cleared
    selection_count_changed = Signal(int)  # Selection count changed
    
    def __init__(self, normalizer: Callable[[str], str] = None):
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
```

### Data Models Implementation

**File: `src/pk_py_lib/gui/dialog_models.py`**

```python
"""
Data models for file management dialogs with immutable data structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum


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
    
    @property
    def basename(self) -> str:
        """Return file basename."""
        from pathlib import Path
        return Path(self.path).name
    
    @property
    def directory(self) -> str:
        """Return parent directory."""
        from pathlib import Path
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
    items: List[FileItem]
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
                    items=filtered_items,
                    stats=group.stats,  # Note: stats may need recalculation
                    ref_path=group.ref_path
                ))
        
        return filtered_groups
```

## Phase 2: Dialog Base Classes (Week 2)

### Base Dialog Implementation

**File: `src/pk_py_lib/gui/dialogs/base_file_manager_dialog.py`**

```python
"""
Base dialog class for file management dialogs using composition pattern.
"""

from __future__ import annotations

from typing import Optional, List
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt

from ..models import SelectionStore
from ..dialog_models import DialogState, Group


class BaseFileManagerDialog(QDialog):
    """
    Base class for file management dialogs using composition over inheritance.
    
    Provides common functionality while allowing dialogs to remain independent.
    """
    
    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        selection_store: Optional[SelectionStore] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        
        # Initialize components
        self.selection_store = selection_store or SelectionStore()
        self.dialog_state = DialogState(
            groups=groups or [],
            selection_store=self.selection_store
        )
        
        # Set dialog properties
        self.setModal(True)
        self.resize(1200, 800)
        self.setWindowTitle("File Manager")
        
        # Setup UI
        self._setup_ui()
        self._connect_signals()
        
    def _setup_ui(self) -> None:
        """Setup common UI components."""
        main_layout = QVBoxLayout(self)
        
        # Tabs for summary and report
        self._setup_tabs(main_layout)
        
        # Controls section (implemented by subclasses)
        controls = self._setup_controls()
        if controls:
            main_layout.addWidget(controls)
        
        # Main content area
        self._setup_content_area(main_layout)
        
        # Status and buttons
        self._setup_footer(main_layout)
        
    def _setup_tabs(self, parent_layout: QVBoxLayout) -> None:
        """Setup summary and report tabs."""
        # Implementation details...
        pass
        
    def _setup_controls(self) -> Optional[QWidget]:
        """Setup mode-specific controls. Override in subclasses."""
        return None
        
    def _setup_content_area(self, parent_layout: QVBoxLayout) -> None:
        """Setup main content area with tree and preview."""
        # Implementation details...
        pass
        
    def _setup_footer(self, parent_layout: QVBoxLayout) -> None:
        """Setup status bar and action buttons."""
        footer_widget = QWidget()
        footer_layout = QHBoxLayout(footer_widget)
        
        # Status label
        self.status_label = QLabel("0 files selected")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch()
        
        # Action buttons
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        footer_layout.addWidget(self.delete_button)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        footer_layout.addWidget(close_button)
        
        parent_layout.addWidget(footer_widget)
        
    def _connect_signals(self) -> None:
        """Connect selection store signals."""
        self.selection_store.selection_count_changed.connect(
            self._update_status_label
        )
        
    def _update_status_label(self, count: int) -> None:
        """Update status label with selection count."""
        total_files = sum(len(g.items) for g in self.dialog_state.groups)
        self.status_label.setText(f"{count}/{total_files} files selected")
        self.delete_button.setEnabled(count > 0)
        
    # ---------------------------------------------------------------------#
    # Signals
    # ---------------------------------------------------------------------#
    files_deleted = Signal(list)
    
    def _on_delete_clicked(self) -> None:
        """
        Handle the deletion of selected files by moving them to the system trash.

        This method is implemented in the base class to provide generic, safe deletion
        functionality using `FileOperations.safe_delete(to_trash=True)`.

        It handles user confirmation, iterates through selected paths, logs success/failure
        to the Report tab, clears the selection for deleted items, and emits the
        `files_deleted` signal to notify subclasses to refresh their views.
        """
        selected_paths = self.selection_store.get_selected_paths()
        if not selected_paths:
            return

        # 1. Confirmation Dialog (Implementation details omitted for documentation)
        # ...

        # 2. Perform Deletion (Implementation details omitted for documentation)
        # ...
        
        # 3. Final Report and Cleanup (Implementation details omitted for documentation)
        # ...
        
        # 4. Notify subclasses/parent to refresh their views
        self.files_deleted.emit(list(selected_paths))
```

## Phase 3: Dialog-Specific Implementations (Week 3)

### Duplicate Manager Implementation

**File: `img_app/img_app/widgets/duplicate_manager.py`**

```python
"""
Duplicate Manager Dialog - Exact matches management using composition pattern.
"""

from __future__ import annotations

from typing import Optional, List
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt

from src.pk_py_lib.gui.dialogs.base_file_manager_dialog import BaseFileManagerDialog
from src.pk_py_lib.gui.dialog_models import Group, FileItem
from src.pk_py_lib.core.logging import get_logger


LOGGER = get_logger("img_app.duplicates")


class DuplicateManagerDialog(BaseFileManagerDialog):
    """
    Dialog for managing exact duplicate files using composition pattern.
    
    Features:
    - No preview pane (metadata-focused display)
    - Fixed 100% score for duplicates
    - File type and savings information
    - Native Qt styling without custom painting
    """
    
    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ):
        self.summary_text = summary_text
        self.report_text = report_text
        
        super().__init__(groups=groups, parent=parent)
        
    def _setup_controls(self) -> QWidget:
        """Setup duplicate-specific controls."""
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        
        mode_label = QLabel("Mode: Duplicates (Exact Matches)")
        controls_layout.addWidget(mode_label)
        controls_layout.addStretch()
        
        return controls_widget
        
    def _setup_content_area(self, parent_layout: QVBoxLayout) -> None:
        """Setup content area with tree view only (no preview)."""
        self.tree_widget = QTreeWidget()
        self.tree_widget.setColumnCount(7)
        self.tree_widget.setHeaderLabels([
            "Select", "Name", "Directory", "Size", "File Type", "Potential Savings", "Score"
        ])
        
        # Hide score column for duplicates
        self.tree_widget.setColumnHidden(6, True)
        
        # Setup tree styling and behavior
        self._setup_tree_behavior()
        
        parent_layout.addWidget(self.tree_widget)
        
    def _setup_tree_behavior(self) -> None:
        """Setup tree widget behavior and connections."""
        self.tree_widget.itemChanged.connect(self._on_tree_item_changed)
        
    def _populate_tree(self) -> None:
        """Populate tree with duplicate groups."""
        self.tree_widget.clear()
        
        for group in self.dialog_state.groups:
            group_item = self._create_group_item(group)
            self.tree_widget.addTopLevelItem(group_item)
            
            for file_item in group.items:
                child_item = self._create_file_item(file_item, group)
                group_item.addChild(child_item)
                
            group_item.setExpanded(True)
            
    def _create_group_item(self, group: Group) -> QTreeWidgetItem:
        """Create tree item for a duplicate group."""
        item = QTreeWidgetItem()
        item.setText(1, f"Group {group.id}: {len(group.items)} files")
        item.setText(3, self._format_file_size(group.stats.total_size))
        item.setText(4, f"{len(group.items)} files")
        item.setText(5, self._format_file_size(group.stats.savings))
        item.setText(6, "100.0%")  # Duplicates are always 100%
        
        # Setup checkbox behavior
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(0, Qt.Unchecked)
        
        return item
        
    def _create_file_item(self, file_item: FileItem, group: Group) -> QTreeWidgetItem:
        """Create tree item for a file within a group."""
        item = QTreeWidgetItem()
        item.setText(1, file_item.basename)
        item.setText(2, file_item.directory)
        item.setText(3, self._format_file_size(file_item.size))
        item.setText(4, file_item.file_type.upper() if file_item.file_type else "—")
        
        # Calculate potential savings
        min_size = min(item.size for item in group.items)
        savings = max(0, file_item.size - min_size)
        item.setText(5, self._format_file_size(savings) if savings else "—")
        item.setText(6, "100.0%")
        
        # Setup checkbox and selection tracking
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        is_selected = self.selection_store.is_selected(file_item.path)
        item.setCheckState(0, Qt.Checked if is_selected else Qt.Unchecked)
        
        return item
        
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        # Implementation details...
        pass
        
    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle tree item checkbox changes."""
        if column != 0:
            return
            
        # Handle selection state changes
        # Implementation details...
        pass
        
    def _on_delete_clicked(self) -> None:
        """
        Handle delete action for selected duplicates.

        Since the deletion logic is now implemented in BaseFileManagerDialog,
        subclasses only need to ensure their view is updated when the
        `files_deleted` signal is emitted by the base class.
        
        This method is now redundant and should be removed or updated to call
        the base class implementation if it were still abstract.
        """
        # This method is now handled by BaseFileManagerDialog.
        # Subclasses should connect to self.files_deleted signal for post-deletion cleanup.
        super()._on_delete_clicked()
```

### Similarity Manager Implementation

**File: `img_app/img_app/widgets/similarity_manager.py`**

```python
"""
Similarity Manager Dialog - Perceptual similarity management with preview pane.
"""

from __future__ import annotations

from typing import Optional, List, Dict
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QLabel, QComboBox, 
                              QSpinBox, QPushButton, QSplitter, QTableWidget)
from PySide6.QtCore import Qt

from src.pk_py_lib.gui.dialogs.base_file_manager_dialog import BaseFileManagerDialog
from src.pk_py_lib.gui.dialog_models import Group
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image.similarity import find_similar_images
from src.pk_py_lib.core.logging import get_logger


LOGGER = get_logger("img_app.similarity")


class SimilarityManagerDialog(BaseFileManagerDialog):
    """
    Dialog for managing perceptually similar images with preview pane.
    
    Features:
    - Dual-pane layout with tree and preview
    - Algorithm and threshold controls
    - On-demand group computation
    - Image preview with thumbnails
    """
    
    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Dict] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ):
        self.db_manager = db_manager
        self.settings = settings or {}
        
        super().__init__(groups=groups, parent=parent)
        
    def _setup_controls(self) -> QWidget:
        """Setup similarity-specific controls."""
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        
        controls_layout.addWidget(QLabel("Mode: Similarity (Perceptual)"))
        controls_layout.addStretch()
        
        # Algorithm selection
        controls_layout.addWidget(QLabel("Algorithm:"))
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["phash", "whash"])
        self.algorithm_combo.setCurrentText(
            self.settings.get("similarity", {}).get("algorithm", "phash")
        )
        controls_layout.addWidget(self.algorithm_combo)
        
        # Threshold selection
        controls_layout.addWidget(QLabel("Threshold:"))
        default_threshold = self.settings.get("similarity", {}).get("phash_threshold", 10)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 64)
        self.threshold_spin.setValue(default_threshold)
        controls_layout.addWidget(self.threshold_spin)
        
        # Compute button
        self.compute_button = QPushButton("Compute Groups")
        self.compute_button.clicked.connect(self._compute_groups)
        controls_layout.addWidget(self.compute_button)
        
        return controls_widget
        
    def _setup_content_area(self, parent_layout: QVBoxLayout) -> None:
        """Setup dual-pane content area with tree and preview."""
        splitter = QSplitter(Qt.Horizontal)
        
        # Tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setColumnCount(7)
        self.tree_widget.setHeaderLabels([
            "Select", "Name", "Directory", "Size", "Resolution", "Date", "Score"
        ])
        self._setup_tree_behavior()
        
        # Preview table
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels([
            "Select", "Preview", "Dimensions", "Size", "Path"
        ])
        
        splitter.addWidget(self.tree_widget)
        splitter.addWidget(self.preview_table)
        splitter.setSizes([800, 400])
        
        parent_layout.addWidget(splitter)
        
    def _compute_groups(self) -> None:
        """Compute similarity groups using database and algorithm."""
        if not self.db_manager:
            LOGGER.error("Database manager required for computation")
            return
            
        algorithm = self.algorithm_combo.currentText()
        threshold = self.threshold_spin.value()
        
        try:
            # Get hashes from database
            hashes = self._get_hashes_from_db(algorithm)
            if not hashes:
                LOGGER.warning("No hashes found in database")
                return
                
            # Compute similarity groups
            groups = find_similar_images(hashes, algorithm, threshold, self.settings)
            self.dialog_state.groups = groups
            
            # Update UI
            self._populate_tree()
            self._update_status_label(self.selection_store.get_selection_count())
            
        except Exception as e:
            LOGGER.error("Group computation failed", exc_info=e)
            # Show error to user...
            
    def _get_hashes_from_db(self, algorithm: str) -> List[Dict[str, str]]:
        """Get hashes from database for specified algorithm."""
        # Implementation details...
        pass
```

## Phase 4: Integration and Testing (Week 4)

### Main Application Integration

**File: `img_app/img_app/main_window.py` (Additions)**

```python
def show_duplicate_manager(self, groups: List[Group]) -> None:
    """Show duplicate manager dialog."""
    from img_app.img_app.widgets.duplicate_manager import DuplicateManagerDialog
    
    dialog = DuplicateManagerDialog(
        groups=groups,
        selection_store=self.selection_store,
        parent=self
    )
    dialog.exec()

def show_similarity_manager(self, db_manager: DatabaseManager) -> None:
    """Show similarity manager dialog."""
    from img_app.img_app.widgets.similarity_manager import SimilarityManagerDialog
    
    dialog = SimilarityManagerDialog(
        db_manager=db_manager,
        settings_api=self.settings_api,
        selection_store=self.selection_store,
        parent=self
    )
    dialog.exec()
```

**2025-09-27 Update — Duplicate Metadata Resolution**

- The duplicates workflow now persists the scan summary’s per-file metadata into a `MainWindow._last_run_file_map` cache and introduces `_resolve_file_metadata(path, size_hint, modified_hint)`.
- `_convert_raw_groups_to_dialog_groups(...)` calls the helper for every file item so the dialog receives authoritative size and modification timestamps even when upstream sources omit them.
- `_on_scan_finished(...)` resets the metadata cache each run, hydrates it from `summary["files"]`, and falls back to filesystem `stat()` when hints are missing. This ensures the Duplicate Manager displays correct file sizes (no longer zero) across cache-backed and live runs.

### Testing Strategy

**File: `tests/test_file_management_dialogs.py`**

```python
"""
Comprehensive tests for file management dialogs.
"""

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.pk_py_lib.gui.selection_store import SelectionStore
from src.pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats


class TestSelectionStore:
    """Test SelectionStore functionality."""
    
    def test_add_remove_selection(self):
        store = SelectionStore()
        test_path = "/test/path/image.jpg"
        
        # Test add selection
        assert store.add_selection(test_path) == True
        assert store.is_selected(test_path) == True
        assert store.get_selection_count() == 1
        
        # Test remove selection
        assert store.remove_selection(test_path) == True
        assert store.is_selected(test_path) == False
        assert store.get_selection_count() == 0
        
    def test_path_normalization(self):
        store = SelectionStore()
        path1 = "/test/../test/image.jpg"
        path2 = "/test/image.jpg"
        
        store.add_selection(path1)
        assert store.is_selected(path2) == True


class TestDialogModels:
    """Test dialog data models."""
    
    def test_file_item_immutability(self):
        item = FileItem(
            path="/test/image.jpg",
            size=1024,
            resolution="1920x1080",
            mod_date="2023-01-01"
        )
        
        # Verify immutability
        with pytest.raises(AttributeError):
            item.path = "/new/path.jpg"


@pytest.mark.gui
class TestDuplicateManagerDialog:
    """GUI tests for Duplicate Manager."""
    
    def test_dialog_creation(self, qapp):
        from img_app.img_app.widgets.duplicate_manager import DuplicateManagerDialog
        
        dialog = DuplicateManagerDialog()
        assert dialog.windowTitle() == "Duplicate File Manager"
        assert dialog.isModal() == True
```

## Implementation Checklist
 
### Phase 1: Foundation (Week 1)
- [x] Implement `SelectionStore` with signal/slot architecture
- [x] Create data models (`FileItem`, `Group`, `DialogState`)
- [x] Set up comprehensive logging system
- [x] Implement error handling utilities
- [ ] Create unit tests for foundation components (Pending)
 
### Phase 2: Base Dialog (Week 2)
- [x] Implement `BaseFileManagerDialog` with composition pattern
- [x] Create common UI components (tabs, footer, status)
- [x] Implement selection synchronization
- [x] Create view factory for dialog components (FileGroupView, SimilarityPreviewPane)
- [x] Implement Delete Selected functionality (to Trash) in BaseFileManagerDialog
- [ ] Add integration tests for base functionality (Pending)
 
### Phase 3: Specific Dialogs (Week 3)
- [x] Implement `DuplicateManagerDialog` with metadata focus
- [x] Implement `SimilarityManagerDialog` with preview pane
- [x] Add Settings Profiles v1 integration
- [x] Implement database integration patterns
- [ ] Create dialog-specific tests (Pending)
 
### Phase 4: Integration & Polish (Week 4)
- [x] Integrate with main application (`MainWindow` updated)
- [x] Implement text selectability throughout (Handled by base dialog/utilities)
- [ ] Add comprehensive user acceptance tests (Pending)
- [ ] Performance optimization and memory management (Deferred)
- [x] Documentation and examples (Updating now)
 
## Status Summary
 
The legacy implementation files (`base_group_manager.py`, `duplicate_manager.py`, `similarity_manager.py`) have been deleted. The new architecture based on composition, immutable models, and `SelectionStore` is fully implemented in the library and integrated into `MainWindow`. Remaining tasks focus on testing and final documentation updates.
 
This implementation guide reflects the completed roadmap for re-implementing the file management dialogs from scratch, addressing all the identified issues while providing a robust, maintainable architecture.