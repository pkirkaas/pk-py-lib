"""
img_app/img_app/widgets/duplicate_manager.py

Dialog for managing exact duplicate images.

Inherits from BaseImageGroupManagerDialog and implements duplicate-specific logic:
- No compute controls (duplicates are pre-calculated).
- Hides the 'Score' column.
- Uses fixed 100% score for display.

Syntax validation: ast.parse verified.
"""

from __future__ import annotations

from typing import Optional, List
from pathlib import Path
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from src.pk_py_lib.core.logging import get_logger
from pk_py_lib.gui.models import Group, ImageData
from img_app.img_app.widgets.base_group_manager import (
    BaseImageGroupManagerDialog,
    format_file_size,
    format_timestamp,
)

# --- Logging Setup ---
LOGGER = get_logger("img_app.duplicates")

class DuplicateManagerDialog(BaseImageGroupManagerDialog):
    """
    Dialog for managing exact duplicate images.
    """

    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ) -> None:
        """
        Initialize the Duplicate Manager Dialog.

        Args:
            groups (Optional[List[Group]]): Initial groups of duplicate images.
            summary_text (str): Processing summary text.
            report_text (str): Report text detailing the duplicate scan.
            parent (Optional[QWidget]): Parent widget.
        """
        # Pass the specific logger to the base class
        super().__init__(
            groups=groups,
            summary_text=summary_text,
            report_text=report_text,
            parent=parent,
            logger=LOGGER
        )
 
    def _should_include_preview(self) -> bool:
        """Disable the preview pane for duplicate management."""
        return False
 
    def _setup_dialog_title(self) -> None:
        """Set the window title for the Duplicate Manager."""
        self.setWindowTitle("Duplicate File Manager")

    def _get_report_tab_title(self) -> str:
        """Return the title for the report tab."""
        return "Duplicate Report"

    def _setup_mode_specific_ui(self) -> None:
        """Hide unused columns and adjust headers for duplicate workflows."""
        header = self.tree.headerItem()
        if header is not None:
            header.setText(4, "File Type")
            header.setText(5, "Potential Savings")
            header.setText(6, "Score")
        self.tree.setColumnHidden(6, True)

    def _setup_controls(self) -> QWidget:
        """
        Setup and return the top controls widget.
        
        For duplicates, this is minimal, just showing the mode label.
        """
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        mode_label = QLabel("Mode: Duplicates (Exact Matches)")
        controls_layout.addWidget(mode_label)
        controls_layout.addStretch()
        
        return controls_widget
 
    def _populate_tree(self) -> None:
        """Populate the tree and tailor columns for duplicate file review."""
        super()._populate_tree()
 
        for group_index in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(group_index)
            if group_item is None or group_index >= len(self.groups):
                continue
 
            group = self.groups[group_index]
            group_item.setText(4, f"{len(group.images)} files")
            group_item.setText(5, format_file_size(group.stats.savings))
 
            if not group.images:
                continue
            min_size = min(img.size for img in group.images)
 
            for child_index in range(group_item.childCount()):
                child_item = group_item.child(child_index)
                if child_item is None:
                    continue
 
                raw_path = child_item.data(0, Qt.UserRole)
                suffix = (Path(str(raw_path)).suffix or "").upper() if raw_path else ""
                if suffix.startswith("."):
                    suffix = suffix[1:]
                child_item.setText(4, suffix or "—")
                child_item.setToolTip(4, f"File type: {suffix or 'Unknown'}")
 
                image = group.images[child_index] if child_index < len(group.images) else None
                savings = max(0, (image.size - min_size)) if image else 0
                child_item.setText(5, format_file_size(savings) if savings else "—")
                if image:
                    child_item.setToolTip(5, f"Last modified: {image.mod_date}")
 
    def _get_group_score_text(self, group: Group) -> tuple[str, str]:
        """
        Return the score text for a duplicate group header.
        
        Args:
            group (Group): The image group data.
            
        Returns:
            tuple[str, str]: (score_range_text, avg_score_text)
        """
        # Duplicates are always 100% match
        return "Exact Matches", "100.0%"

    def _get_image_score_text(self, img: ImageData) -> str:
        """
        Return the score text for a duplicate image child item.
        
        Args:
            img (ImageData): The image data object.
            
        Returns:
            str: The score text.
        """
        # Duplicates are always 100% match
        return "100.0%"
