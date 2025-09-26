"""
img_app/img_app/widgets/base_group_manager.py

Base dialog for managing groups of images (duplicates or similar).

Implements shared UI components:
- QTreeWidget for hierarchical group/image display.
- QTableWidget for detailed preview.
- Selection tracking and synchronization logic.
- Delete functionality.
- Custom GroupTreeDelegate for styling and checkbox handling.

Derived classes must implement group generation logic and mode-specific UI elements.

Syntax validation: ast.parse verified.
"""

from __future__ import annotations

import os
from PIL import Image
from typing import Optional, List, Union, Dict, Any
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod, ABCMeta

from PySide6.QtCore import Qt, QRect, QSize, QEvent, QModelIndex, QSignalBlocker
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QSplitter, QStyledItemDelegate, QStyle, QWidget, QPushButton,
    QScrollArea, QTabWidget, QMessageBox, QMenu, QHeaderView,
    QSizePolicy, QTableWidget, QTableWidgetItem, QAbstractItemView, QCheckBox,
    QTextEdit, QApplication
)
from PySide6.QtGui import QPainter, QPixmap, QFont, QAction, QColor, QBrush, QPalette, QImage, QPen
from PySide6.QtWidgets import QStyleOptionViewItem

from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error
from src.pk_py_lib.core.logging import get_logger
from pk_py_lib.gui.models import Group, ImageData, Stats

# --- Logging Setup ---
BASE_LOGGER = get_logger("img_app.base_manager")

# --- Helper Functions ---

def _qt_item_flag(name: str, default: int = 0):
    """
    Return a Qt.ItemFlag enum value by name in a version-compatible way.
    Tries Qt.ItemFlag.<name>, then Qt.<name>. If not found, returns default (0).

    Notes
    -----
    - This helper shields us from PySide6 enum API differences between versions.
    - Qt6 exposes flags under Qt.ItemFlag; some versions also expose legacy aliases directly on Qt.
    - If neither exists, we return default (0) so callers can OR it safely or skip it.

    Examples
    --------
    - _qt_item_flag('ItemIsTristate', 0)
    - _qt_item_flag('ItemIsAutoTristate', 0)
    """
    # Prefer the Qt6-style enum container
    try:
        return getattr(Qt.ItemFlag, name)
    except Exception:
        pass
    # Fallback to legacy alias directly on Qt
    return getattr(Qt, name, default)

# Optional debug at import time to record available tri-state symbol
try:
    _tri = _qt_item_flag("ItemIsTristate", 0) or _qt_item_flag("ItemIsAutoTristate", 0)
    if _tri:
        BASE_LOGGER.debug(f"Tri-state item flag available: {_tri}")
    else:
        BASE_LOGGER.debug("Tri-state item flag not available; using manual partial-state visuals")
except Exception:
    # Best-effort logging; never fail at import time
    pass


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string.

    Args:
        size_bytes (int): Size in bytes.

    Returns:
        str: Formatted size (e.g., "1.2 MB").

    Example:
        >>> format_file_size(1048576)
        '1.0 MB'
    """
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {size_names[i]}"


def format_timestamp(ts: float) -> str:
    """
    Format Unix timestamp to date string.

    Args:
        ts (float): Timestamp.

    Returns:
        str: "dd-MMM-yy" or "Unknown".

    Example:
        >>> format_timestamp(1726400000.0)
        '15-Sep-25'
    """
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d-%b-%y")
    except (ValueError, OSError):
        return "Unknown"

def compute_group_stats(images: List[ImageData]) -> Stats:
    """
    Compute stats for a group of images.

    Args:
        images (List[ImageData]): List of image data objects.

    Returns:
        Stats: Computed statistics including total size, savings, and score range/average.
    """
    if not images:
        return Stats(total_size=0, savings=0, min_score=0, max_score=0, avg_score=0)
    total_size = sum(img.size for img in images)
    min_size = min(img.size for img in images)
    savings = total_size - min_size
    
    # Check if score attribute exists and is not None (handles similarity vs duplicate mode data)
    if hasattr(images[0], 'score') and images[0].score is not None:
        scores = [img.score for img in images]
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)
    else:
        # Default to 1.0 (100%) for duplicates or if score is missing
        min_score = max_score = avg_score = 1.0
        
    return Stats(total_size=total_size, savings=savings, min_score=min_score, max_score=max_score, avg_score=avg_score)


# --- Delegate ---

class GroupTreeDelegate(QStyledItemDelegate):
    """
    Custom delegate for styling QTreeWidget items in Image Group Manager Dialogs.
 
    - Group headers (top-level): #fafafa background, #333333 text, bold font.
    - Child items: White background with #111111 (dark) text for high contrast.
    - Selection: #4a90e2 background, white text (bold for groups).
    - Directly draws text to ensure visibility across all themes.
    - For column 0, it explicitly draws a custom checkbox and handles its events.
    """
    def __init__(self, parent=None, logger=None):
        """
        Initialize the delegate.
 
        Args:
            parent: Parent object.
            logger: Logger for debug output.
        """
        super().__init__(parent)
        self.logger = logger or BASE_LOGGER

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Override paint to apply custom backgrounds, fonts, and directly draw text for guaranteed visibility.
 
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with rect, state, palette, font.
            index (QModelIndex): Model index for the item.
 
        Strategy:
        - For column 0, perform custom checkbox painting.
        - For other columns, prevent Qt from drawing text, let it draw background/decorations,
          then manually draw our text with explicit colors for visibility.
        """
        if index.column() == 0:
            # --- Custom Checkbox Painting (for column 0) ---
            is_group = index.parent() == QModelIndex()
            selected = bool(option.state & QStyle.State_Selected)
            state = index.data(Qt.CheckStateRole)
    
            # Draw cell background
            bg_color = QColor(74, 144, 226) if selected else (QColor(250, 250, 250) if is_group else QColor(255, 255, 255))
            painter.fillRect(option.rect, bg_color)
    
            # Draw indicator (small square on left)
            ind_rect = self._indicator_rect(option)
    
            painter.save()
            if state == Qt.Checked:
                painter.fillRect(ind_rect, QColor(74, 144, 226))
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                w = ind_rect.width()
                painter.drawLine(ind_rect.left() + w // 3, ind_rect.top() + w // 2, ind_rect.left() + w // 2, ind_rect.bottom() - w // 3)
                painter.drawLine(ind_rect.left() + w // 2, ind_rect.bottom() - w // 3, ind_rect.right() - w // 3, ind_rect.top() + w // 3)
            elif state == Qt.PartiallyChecked:
                painter.fillRect(ind_rect, QColor(240, 208, 0))
                painter.setPen(QPen(QColor(0, 0, 0), 2))
                mid_y = ind_rect.top() + ind_rect.height() // 2
                painter.drawLine(ind_rect.left() + 2, mid_y, ind_rect.right() - 2, mid_y)
            else:
                painter.fillRect(ind_rect, QColor(255, 255, 255))
                painter.setPen(QPen(QColor(170, 170, 170), 1))
                painter.drawRect(ind_rect)
            painter.restore()
            return

        # For columns other than 0, use custom text painting without super().paint()
        self._paint_text_cell(painter, option, index)

    def _indicator_rect(self, option: QStyleOptionViewItem) -> QRect:
        """
        Compute the rectangle for the checkbox indicator within the cell.
        """
        ind_size = 16
        ind_x = option.rect.left() + 4
        ind_y = option.rect.top() + (option.rect.height() - ind_size) // 2
        return QRect(ind_x, ind_y, ind_size, ind_size)

    def _draw_cell_background(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Draw the cell background with appropriate colors for selection, hover, and disabled states.
        
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with rect, state, palette.
            index (QModelIndex): Model index for the item.
            
        Notes:
            - Uses Qt's style APIs for consistent look across themes.
            - Handles group vs child item differentiation.
            - Manages selection, hover, focus, and disabled states.
        """
        # Initialize style option to get proper visual states
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        
        # Let Qt draw the background using style APIs for consistency
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

    def _draw_cell_text(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Draw the cell text with proper alignment, elision, and visual states.
        
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with rect, state, palette.
            index (QModelIndex): Model index for the item.
            
        Notes:
            - Handles text elision for long content.
            - Applies appropriate text colors based on selection state.
            - Uses custom font styling for group headers.
            - Respects column-specific text alignment.
        """
        is_group = index.parent() == QModelIndex()
        selected = bool(option.state & QStyle.State_Selected)
        
        # Determine text color based on selection state
        if selected:
            text_color = option.palette.color(QPalette.HighlightedText)
        else:
            text_color = option.palette.color(QPalette.Text)
        
        # Setup font with bold for group headers
        font = QFont(option.font)
        if is_group:
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        
        # Get text to display
        text = index.data(Qt.DisplayRole)
        if not text:
            return
            
        # Get text alignment for this column
        alignment = self._get_text_alignment(index.column())
        
        # Calculate text rectangle with padding
        text_rect = QRect(option.rect)
        text_rect.adjust(4, 0, -4, 0)  # 4px padding on left and right
        
        # Draw elided text
        elided_text = option.fontMetrics.elidedText(str(text), Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, alignment, elided_text)

    def _draw_focus_indicator(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        """
        Draw focus indicator rectangle if the item has focus.
        
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with focus state.
            
        Notes:
            - Only draws focus indicator when State_HasFocus is set.
            - Uses dotted line style for consistency with Qt defaults.
        """
        if option.state & QStyle.State_HasFocus:
            focus_rect = QRect(option.rect)
            focus_rect.adjust(1, 1, -1, -1)  # Slightly inset from cell borders
            painter.save()
            painter.setPen(QPen(option.palette.color(QPalette.Highlight), 1, Qt.DotLine))
            painter.drawRect(focus_rect)
            painter.restore()

    def _get_text_alignment(self, column: int) -> int:
        """
        Return the appropriate text alignment for the given column.
        
        Args:
            column (int): Column index (0-6).
            
        Returns:
            int: Qt alignment flags for the column.
            
        Notes:
            - Column 0 (Select): Left aligned (checkbox handled separately)
            - Column 1 (Name): Left aligned
            - Column 2 (Directory): Left aligned
            - Column 3 (Size): Right aligned for numeric values
            - Column 4 (Resolution): Left aligned
            - Column 5 (Date): Left aligned
            - Column 6 (Score): Right aligned for numeric values
        """
        if column in (3, 6):  # Size and Score columns - right aligned for numbers
            return Qt.AlignRight | Qt.AlignVCenter
        else:  # All other columns - left aligned
            return Qt.AlignLeft | Qt.AlignVCenter

    def _paint_text_cell(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Main painting method for text columns (non-checkbox columns).
        
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with rect, state, palette.
            index (QModelIndex): Model index for the item.
            
        Notes:
            - Coordinates all painting operations for text cells.
            - Handles background, text, and focus indicator drawing.
            - Eliminates reliance on super().paint() for text rendering.
        """
        # Draw background with proper visual states
        self._draw_cell_background(painter, option, index)
        
        # Draw text content
        self._draw_cell_text(painter, option, index)
        
        # Draw focus indicator if needed
        self._draw_focus_indicator(painter, option)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Provide a size hint, especially for column 0 to ensure checkbox is visible.
        """
        if index.column() == 0:
            fm = option.fontMetrics
            h = max(22, fm.height() + 6)
            w = max(28, 22)
            return QSize(w, h)
        return super().sizeHint(option, index)

    def editorEvent(self, event, model, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        """
        Handle user interaction (mouse/key) to toggle the checkbox state for column 0.
        """
        if index.column() != 0:
            return False

        try:
            from PySide6.QtGui import QMouseEvent, QKeyEvent
        except Exception:
            QMouseEvent = object
            QKeyEvent = object

        et = event.type()
        # Mouse toggle
        if et == QEvent.MouseButtonRelease and hasattr(event, "button") and event.button() == Qt.LeftButton:
            pt = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if option.rect.contains(pt):
                state = index.data(Qt.CheckStateRole)
                new_state = Qt.Checked if state != Qt.Checked else Qt.Unchecked
                if self.logger:
                    path = index.data(Qt.UserRole) or "group"
                    self.logger.debug(f"editorEvent mouse toggle for {path}: {state} -> {new_state}")
                return bool(model.setData(index, new_state, Qt.CheckStateRole))

        # Keyboard toggle
        if et == QEvent.KeyPress and hasattr(event, "key"):
            key = event.key()
            if key in (Qt.Key_Space, Qt.Key_Select):
                state = index.data(Qt.CheckStateRole)
                new_state = Qt.Checked if state != Qt.Checked else Qt.Unchecked
                if self.logger:
                    path = index.data(Qt.UserRole) or "group"
                    self.logger.debug(f"editorEvent key toggle for {path}: {state} -> {new_state}")
                return bool(model.setData(index, new_state, Qt.CheckStateRole))

        return False


# --- Base Dialog Class ---

class QtABCMeta(type(QDialog), ABCMeta):
    """
    Metaclass combining QDialog's metaclass (QObject's metaclass) and ABCMeta
    to resolve the metaclass conflict when inheriting from both QDialog and ABC.
    """
    pass

class BaseImageGroupManagerDialog(QDialog, ABC, metaclass=QtABCMeta):
    """
    Abstract base dialog for managing groups of images (duplicates or similar).

    Handles all common UI setup, selection management, tree population, and deletion logic.
    Requires derived classes to define specific UI controls and group generation logic.

    Args:
        groups (Optional[List[Group]]): Initial groups.
        summary_text (str): Processing summary.
        report_text (str): Report text.
        parent (Optional[QWidget]): Parent widget.
        logger (Optional[logging.Logger]): Specific logger instance for the derived class.
    """

    def __init__(
        self,
        groups: Optional[List[Group]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None,
        logger=None
    ) -> None:
        super().__init__(parent)
        self.logger = logger or BASE_LOGGER
        self._groups: List[Group] = []
        self.groups = groups or []
        self._preview_enabled: bool = self._should_include_preview()
        self.preview_table: Optional[QTableWidget] = None
        
        # Reentrancy guard: when True, suppresses handling of itemChanged to avoid
        # re-entrant sync loops and transient visual reverts during programmatic updates
        self._suppress_tree_item_changed: bool = False
        
        # Global set of normalized paths selected for deletion
        self.selected_images: set[str] = set()

        self.setModal(True)
        self.resize(1200, 800)

        main_layout = QVBoxLayout(self)
        
        # Tabs for summary and report
        self.tabs = QTabWidget()
        self.summary_tab = QTextEdit(readOnly=True)
        self.summary_tab.setPlainText(summary_text)
        self.report_tab = QTextEdit(readOnly=True)
        self.report_tab.setPlainText(report_text)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, self._get_report_tab_title())
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_layout.addWidget(self.tabs)

        # Vertical splitter for controls, tree/preview, status, and buttons
        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(v_splitter)

        # --- Top Controls Pane (Abstracted) ---
        controls_widget = self._setup_controls()
        controls_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v_splitter.addWidget(controls_widget)

        # --- Middle Pane (Tree and Preview) ---
        h_splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        
        # Enhanced palette for visibility
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.Text, QColor(17, 17, 17))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.Highlight, QColor(74, 144, 226))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        self.tree.setPalette(palette)
        viewport = self.tree.viewport()
        viewport.setAutoFillBackground(True)
        viewport.setPalette(palette)
        
        self.tree.setItemDelegate(GroupTreeDelegate(self.tree, self.logger))
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(["Select", "Name", "Directory", "Size", "Resolution", "Date", "Score"])
        header = self.tree.header()
        for i in range(self.tree.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        header.setMinimumSectionSize(60)
        header.resizeSection(0, 60)
        header.setStretchLastSection(False)
        
        # Stylesheet for tree
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #ffffff;
                color: #111111;
                border: 1px solid #d0d0d0;
            }
            QTreeWidget::viewport {
                background-color: #ffffff;
            }
            QTreeWidget::item {
                padding: 2px 4px;
                border-bottom: 1px solid #e0e0e0;
            }
            QTreeWidget::item:selected {
                background-color: #4a90e2;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f5f5f5;
                border: 1px solid #e0e0e0;
                padding: 5px;
                font-weight: bold;
                color: #333333;
            }
        """)
        
        self.tree.setAlternatingRowColors(False)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        h_splitter.addWidget(self.tree)

        secondary_widget = self._build_secondary_panel()
        if secondary_widget is not None:
            h_splitter.addWidget(secondary_widget)
            h_splitter.setSizes([800, 400])
            h_splitter.setStretchFactor(0, 3)
            h_splitter.setStretchFactor(1, 2)
        else:
            h_splitter.setStretchFactor(0, 1)
        h_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v_splitter.addWidget(h_splitter)
 
        if self._preview_enabled:
            self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.itemChanged.connect(self._on_tree_item_changed)

        # --- Status Label ---
        self.status_label = QLabel("0 files selected for deletion")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v_splitter.addWidget(self.status_label)

        # --- Bottom Buttons Pane ---
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)

        # Footer option: explicit opt-in to clear selections after delete
        self.clear_after_delete_cb = QCheckBox("Clear selections after delete")
        self.clear_after_delete_cb.setChecked(False)
        btn_layout.addWidget(self.clear_after_delete_cb)

        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        btn_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v_splitter.addWidget(btn_widget)

        # Final setup
        self._setup_dialog_title()
        self._setup_mode_specific_ui()
        self._populate_tree()
        self._update_status_line()
        self._update_delete_btn()

    # --- Abstract Methods (Must be implemented by derived classes) ---

    @abstractmethod
    def _setup_dialog_title(self) -> None:
        """Set the window title based on the specific manager type."""
        pass

    @abstractmethod
    def _get_report_tab_title(self) -> str:
        """Return the title for the report tab (e.g., 'Duplicate Report', 'Similarity Report')."""
        pass

    @abstractmethod
    def _setup_mode_specific_ui(self) -> None:
        """Perform any mode-specific UI setup (e.g., hiding columns, adding controls)."""
        pass

    @abstractmethod
    def _setup_controls(self) -> QWidget:
        """Setup and return the top controls widget."""
        pass

    @abstractmethod
    def _get_group_score_text(self, group: Group) -> tuple[str, str]:
        """
        Return the text for the group header columns 4 (score range) and 6 (average score).
        
        Returns:
            tuple[str, str]: (score_range_text, avg_score_text)
        """
        pass

    @abstractmethod
    def _get_image_score_text(self, img: ImageData) -> str:
        """
        Return the text for the image child item column 6 (individual score).
        """
        pass
 
    def _should_include_preview(self) -> bool:
        """
        Indicate whether the dialog should include the secondary preview pane.
        
        Returns:
            bool: True when the preview table/sidebar should be constructed.
        """
        return True
 
    def _build_secondary_panel(self) -> Optional[QWidget]:
        """
        Construct the secondary pane that appears to the right of the tree.
 
        Returns:
            Optional[QWidget]: Widget to insert into the splitter, or None to
                operate as a single-pane layout.
        """
        if not self._preview_enabled:
            self.preview_table = None
            return None
        return self._create_preview_panel()
 
    def _create_preview_panel(self) -> QWidget:
        """
        Create the default preview panel (scroll area containing a table).
 
        Returns:
            QWidget: Scroll area wrapping the preview table.
        """
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(["Select", "Preview", "Dimensions", "Size", "Path"])
        self.preview_table.setSortingEnabled(False)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
 
        # Stylesheet for preview table checkboxes visibility
        self.preview_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                color: #111111;
                gridline-color: #e0e0e0;
                border: 1px solid #d0d0d0;
            }
            QTableWidget::item {
                padding: 2px 4px;
            }
            QCheckBox {
                background-color: #f0f0f0;
                color: #000000;
                border: 1px solid #cccccc;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #b8b8b8;
                background-color: #f0f0f0;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #4a90e2;
                background-color: #4a90e2;
            }
        """)
 
        preview_scroll = QScrollArea(widgetResizable=True)
        preview_scroll.setWidget(self.preview_table)
        return preview_scroll
 
    # --- Shared Utility Methods ---

    @property
    def groups(self) -> List[Group]:
        """
        Normalized image groups available to the dialog.

        Returns:
            List[Group]: List of Group dataclasses ready for consumption by the UI.
        """
        return self._groups

    @groups.setter
    def groups(self, raw_groups: Optional[List[Any]]) -> None:
        """
        Normalize and assign incoming group data.

        Args:
            raw_groups (Optional[List[Any]]): Raw group collection supplied by callers.
        """
        self._groups = self._normalize_groups(raw_groups or [])

    def _normalize_groups(self, raw_groups: List[Any]) -> List[Group]:
        """
        Normalize arbitrary group payloads into Group dataclass instances.

        Args:
            raw_groups (List[Any]): Raw group entries (dicts, namespaces, Group instances, etc.).

        Returns:
            List[Group]: Normalized groups with ImageData members.
        """
        if not raw_groups:
            return []
        normalized: List[Group] = []
        discarded = 0
        for index, raw_group in enumerate(raw_groups):
            try:
                normalized.append(self._normalize_single_group(raw_group, index))
            except Exception as exc:
                discarded += 1
                self.logger.error(
                    f"Discarding group at index {index} during normalization: {exc}"
                )
        if discarded:
            self.logger.warning(
                f"Normalized {len(normalized)} group entries ({discarded} discarded)"
            )
        else:
            self.logger.debug(f"Normalized {len(normalized)} group entries")
        return normalized

    def _normalize_single_group(self, raw_group: Any, index: int) -> Group:
        """
        Normalize a single group entry into a Group dataclass.

        Args:
            raw_group (Any): Raw group representation.
            index (int): Sequence index for fallback identifiers.

        Returns:
            Group: Normalized group.
        """
        if isinstance(raw_group, Group):
            return raw_group

        if isinstance(raw_group, dict):
            data: Dict[str, Any] = raw_group
        else:
            try:
                data = vars(raw_group)
            except TypeError:
                data = {}
                for attr in ("id", "images", "files", "stats", "ref_path", "reference_path"):
                    if hasattr(raw_group, attr):
                        data[attr] = getattr(raw_group, attr)

        images_source = data.get("images")
        if images_source is None and "files" in data:
            images_source = data["files"]
        if not images_source:
            raise ValueError("Group is missing an 'images' or 'files' collection")

        images = [self._coerce_image_data(img, index) for img in images_source]
        if not images:
            raise ValueError("Group contains no valid image entries after normalization")

        stats = self._coerce_stats(data.get("stats"), images)
        ref_path = data.get("ref_path") or data.get("reference_path")
        if not ref_path:
            ref_path = images[0].path

        group_id = data.get("id")
        try:
            group_id = int(group_id) if group_id is not None else index + 1
        except Exception:
            group_id = index + 1

        return Group(
            id=group_id,
            images=images,
            stats=stats,
            ref_path=ref_path
        )

    def _coerce_stats(self, raw_stats: Any, images: List[ImageData]) -> Stats:
        """
        Ensure stats are represented as a Stats dataclass.

        Args:
            raw_stats (Any): Raw stats payload.
            images (List[ImageData]): Image items for fallback computations.

        Returns:
            Stats: Normalized statistics.
        """
        if isinstance(raw_stats, Stats):
            return raw_stats

        if isinstance(raw_stats, dict):
            return Stats(
                min_score=float(raw_stats.get("min_score", raw_stats.get("min", 0.0)) or 0.0),
                max_score=float(raw_stats.get("max_score", raw_stats.get("max", 0.0)) or 0.0),
                avg_score=float(raw_stats.get("avg_score", raw_stats.get("average", 0.0)) or 0.0),
                total_size=int(raw_stats.get("total_size", raw_stats.get("size", 0)) or 0),
                savings=int(raw_stats.get("savings", raw_stats.get("potential_savings", 0)) or 0),
            )

        return compute_group_stats(images)

    def _coerce_image_data(self, raw_image: Any, group_index: int) -> ImageData:
        """
        Normalize a raw image payload into an ImageData instance.

        Args:
            raw_image (Any): Raw image entry.
            group_index (int): Parent group index for logging context.

        Returns:
            ImageData: Normalized image metadata.
        """
        if isinstance(raw_image, ImageData):
            return raw_image

        if isinstance(raw_image, dict):
            data: Dict[str, Any] = raw_image
        else:
            try:
                data = vars(raw_image)
            except TypeError:
                data = {}
                for attr in ("path", "file_path", "size", "file_size", "mod_date", "modified", "resolution", "dimensions", "score"):
                    if hasattr(raw_image, attr):
                        data[attr] = getattr(raw_image, attr)

        path = str(data.get("path") or data.get("file_path") or "").strip()
        if not path:
            raise ValueError(f"Group {group_index}: image entry is missing a path")

        size = data.get("size", data.get("file_size"))
        if size is None:
            try:
                size = os.path.getsize(path)
            except Exception:
                size = 0
        try:
            size = int(size)
        except Exception:
            size = 0

        resolution = data.get("resolution") or data.get("dimensions") or ""
        if not resolution:
            try:
                with Image.open(path) as pil_img:
                    resolution = f"{pil_img.width}x{pil_img.height}"
            except Exception:
                resolution = "Unknown"

        mod_value = data.get("mod_date", data.get("modified"))
        mod_date = self._format_mod_date(mod_value, path)

        score = self._normalize_score(data.get("score"))
        if score is None:
            score = self._normalize_score(data.get("similarity"))
        if score is None:
            score = self._normalize_score(data.get("percent"))
        if score is None:
            score = 1.0

        return ImageData(
            path=path,
            size=size,
            resolution=resolution,
            mod_date=mod_date,
            score=score
        )

    def _normalize_score(self, value: Any) -> Optional[float]:
        """
        Normalize varied score representations to a 0.0-1.0 float.

        Args:
            value (Any): Raw score or percentage.

        Returns:
            Optional[float]: Normalized score or None if unavailable.
        """
        if value in (None, ""):
            return None
        try:
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    return None
                if stripped.endswith("%"):
                    stripped = stripped[:-1]
                    return max(0.0, min(1.0, float(stripped) / 100.0))
                numeric = float(stripped)
            else:
                numeric = float(value)
            if numeric > 1.0:
                numeric = numeric / 100.0
            return max(0.0, min(1.0, numeric))
        except Exception:
            return None

    def _format_mod_date(self, value: Any, path: str) -> str:
        """
        Format modification date information into a human-readable string.

        Args:
            value (Any): Raw modification metadata.
            path (str): Image path for fallback metadata.

        Returns:
            str: Formatted modification date.
        """
        if isinstance(value, (int, float)):
            return format_timestamp(float(value))
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                pass
            else:
                try:
                    numeric = float(stripped)
                    return format_timestamp(float(numeric))
                except Exception:
                    return stripped
        if path:
            try:
                return format_timestamp(os.path.getmtime(path))
            except Exception:
                pass
        return "Unknown"

    def _norm_path(self, p: str) -> str:
        """
        Normalize a filesystem path for consistent comparisons across platforms.
        """
        import os
        try:
            return os.path.normcase(os.path.normpath(p))
        except Exception:
            return p
 
    # --- Tree Population and Synchronization ---

    def _populate_tree(self) -> None:
        """
        Populate tree with current groups.
    
        Group top items with stats, child items with details.
        Uses abstract methods for score display.
        """
        self.tree.clear()
        if not self.groups:
            item = QTreeWidgetItem(self.tree)
            item.setText(1, "No groups to display")
            return
    
        # Suppress itemChanged during initial population to avoid reentrant slot and visual flicker
        self._suppress_tree_item_changed = True
        blocker = QSignalBlocker(self.tree)
        try:
            for group in self.groups:
                if not (hasattr(group, 'id') and hasattr(group, 'images') and isinstance(group.images, list)):
                    self.logger.error(f"Invalid group: missing 'id', 'images', or 'images' not list. Skipping group.")
                    continue
                
                top = QTreeWidgetItem(self.tree)
                top.setText(1, f"Group {group.id}: {len(group.images)} images")
                top.setText(2, "")  # Directory empty for group
                top.setText(3, format_file_size(group.stats.total_size))
                
                # Use abstract method for score text
                score_range_text, avg_score_text = self._get_group_score_text(group)
                top.setText(4, score_range_text)
                top.setText(6, avg_score_text)
                
                min_size = min(img.size for img in group.images) if group.images else 0
                savings = group.stats.total_size - min_size
                top.setText(5, format_file_size(savings))
                
                tristate = _qt_item_flag('ItemIsTristate', 0) or _qt_item_flag('ItemIsAutoTristate', 0)
                top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | tristate)
                top.setCheckState(0, Qt.Unchecked)

                for idx, img in enumerate(group.images):
                    child = QTreeWidgetItem(top)
                    child.setFlags(child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    child.setText(1, os.path.basename(img.path))
                    child.setText(2, os.path.dirname(img.path))  # Full directory path
                    child.setText(3, format_file_size(img.size))
                    child.setText(4, img.resolution)
                    child.setText(5, img.mod_date)
                    
                    # Use abstract method for image score text
                    child.setText(6, self._get_image_score_text(img))
                    
                    norm = self._norm_path(img.path)
                    child.setData(0, Qt.UserRole, norm)
                    # Explicitly set CheckStateRole so delegate can paint, even when Unchecked
                    state = Qt.Checked if norm in self.selected_images else Qt.Unchecked
                    child.setCheckState(0, state)
                    
                    if idx < 3:
                        try:
                            self.logger.debug(f"child-check init: {img.path} state={int(state)}")
                        except Exception:
                            self.logger.debug(f"child-check init: {img.path} state={state}")

                self.tree.expandItem(top)
                self._update_group_checkstate(top)
            
            if self.tree.topLevelItemCount() == 0 and self.groups:
                item = QTreeWidgetItem(self.tree)
                item.setText(1, "No valid groups to display")
        
        finally:
            del blocker  # release to re-enable signals
            self._suppress_tree_item_changed = False
            self._sync_tree_from_selections()
            self._update_status_line()


    def _update_group_checkstate(self, parent: QTreeWidgetItem) -> None:
        """
        Update group header checkstate based on children states.
        
        - Unchecked: 0 selected
        - Checked: all selected
        - PartiallyChecked: some but not all selected
        
        This maintains bidirectional sync for group-level selection.
        """
        if not parent or parent.childCount() == 0:
            return
        
        self.tree.blockSignals(True)
        try:
            checked_count = sum(
                1 for i in range(parent.childCount())
                if parent.child(i).checkState(0) == Qt.Checked
            )
            total = parent.childCount()
            
            if checked_count == 0:
                new_state = Qt.Unchecked
            elif checked_count == total:
                new_state = Qt.Checked
            else:
                new_state = Qt.PartiallyChecked
            parent.setCheckState(0, new_state)
        finally:
            self.tree.blockSignals(False)
        self.tree.viewport().update()


    def _sync_tree_from_selections(self) -> None:
        """
        Synchronize all tree checkboxes to reflect self.selected_images state.
        
        Iterates over all groups and children, setting checkstates accordingly.
        Updates group headers to checked/partial/unchecked based on children.
        Ensures tree reflects global selections without user interaction.
        """
        # Suppress re-entrant itemChanged during programmatic sync and block tree signals.
        self._suppress_tree_item_changed = True
        blocker = QSignalBlocker(self.tree)
        try:
            self.tree.blockSignals(True)
            for top_level in range(self.tree.topLevelItemCount()):
                group_item = self.tree.topLevelItem(top_level)
                child_count = group_item.childCount()
                count_selected = 0
                for child_idx in range(child_count):
                    child_item = group_item.child(child_idx)
                    raw = child_item.data(0, Qt.UserRole)
                    path = self._norm_path(str(raw) if raw else "")
                    in_sel = bool(path and path in self.selected_images)
                    if in_sel:
                        count_selected += 1
                    child_item.setCheckState(0, Qt.Checked if in_sel else Qt.Unchecked)
                    self.logger.debug(f"Child {path}: checked={in_sel}")
                if count_selected == child_count:
                    group_state = Qt.Checked
                elif count_selected > 0:
                    group_state = Qt.PartiallyChecked
                else:
                    group_state = Qt.Unchecked
                group_item.setCheckState(0, group_state)
                self.logger.debug(f"Group {top_level}: {count_selected}/{child_count} selected, state: {group_state}")
        finally:
            self.tree.blockSignals(False)
            del blocker  # release to re-enable signals
            self._suppress_tree_item_changed = False
        self.tree.viewport().update()


    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle changes to checkstate in the Select column (column 0) of the tree.
        
        Bidirectional sync logic:
        - For group headers (top-level): Toggle all children in the group (add/remove paths from selected_images).
          Sets all child checkstates to match.
        - For child items: Add/remove individual path from selected_images, then update parent group checkstate.
        """
        # Non-reentrant guard: ignore signals caused by our own programmatic updates
        if getattr(self, "_suppress_tree_item_changed", False):
            self.logger.debug("itemChanged suppressed")
            return
        if column != 0:
            return
        
        state = item.checkState(0)
        self.logger.debug(f"Toggling tree item '{item.text(1)}' state: {state}")
        
        if state == Qt.PartiallyChecked and item.parent() is None:
            # Partial is derived; no action on selected_images
            self.tree.viewport().update()
            return
        
        self.tree.blockSignals(True)
        try:
            if item.parent() is None:  # Group header
                group_idx = self.tree.indexOfTopLevelItem(item)
                if 0 <= group_idx < len(self.groups):
                    # Normalize all paths for group bulk operation
                    raw_paths = [img.path for img in self.groups[group_idx].images]
                    group_paths = [self._norm_path(str(p)) for p in raw_paths]
                    if state == Qt.Checked:
                        self.selected_images.update(group_paths)
                        self.logger.debug(f"group-toggle add: {len(group_paths)} items")
                    elif state == Qt.Unchecked:
                        self.selected_images.difference_update(group_paths)
                        self.logger.debug(f"group-toggle remove: {len(group_paths)} items")
                    
                    # Propagate to all children: set their checkstates to match group
                    self._suppress_tree_item_changed = True
                    blocker = QSignalBlocker(self.tree)
                    try:
                        for i in range(item.childCount()):
                            child_item = item.child(i)
                            child_item.setCheckState(0, state)
                    finally:
                        del blocker
                        self._suppress_tree_item_changed = False
            else:  # Child item
                raw = item.data(0, Qt.UserRole)
                path = self._norm_path(str(raw) if raw else "")
                if path:
                    op = "add" if state == Qt.Checked else "remove"
                    self.logger.debug(f"tree-toggle {op}: {path}")
                    if state == Qt.Checked:
                        self.selected_images.add(path)
                    elif state == Qt.Unchecked:
                        self.selected_images.discard(path)
                    
                    # Update parent group checkstate based on children
                    parent = item.parent()
                    if parent:
                        self._update_group_checkstate(parent)
        finally:
            self.tree.blockSignals(False)
        
        self._sync_tree_from_selections()
        self.tree.viewport().repaint()
        self._update_status_line()
        self._update_delete_btn()
        self.logger.debug(f"Selected images now: {len(self.selected_images)}")
        
        # Update preview checkboxes if preview is populated (current group)
        if self._preview_enabled and self.preview_table and self.preview_table.rowCount() > 0:
            self._update_preview_checkboxes()

    # --- Preview Table Methods ---

    def _clear_table(self) -> None:
        """
        Clear the preview table without resetting global selections.
        """
        if not self._preview_enabled or not self.preview_table:
            return
        self.preview_table.setRowCount(0)
        self._update_delete_btn()
        self._update_status_line()

    def _on_checkbox_toggled(self, checkbox: QCheckBox, checked: bool) -> None:
        """
        Handle checkbox state change in the preview table.
        
        Args:
            checkbox (QCheckBox): The checkbox that was toggled.
            checked (bool): Whether the checkbox is checked.
        """
        if not self._preview_enabled:
            return
        raw = checkbox.property("path")
        path = self._norm_path(str(raw) if raw else "")
        if not path:
            self.logger.warning("Checkbox without path property")
            return
        op = "add" if checked else "remove"
        self.logger.debug(f"preview-toggle {op}: {path}")
        if checked:
            self.selected_images.add(path)
        else:
            self.selected_images.discard(path)
        self._update_delete_btn()
        self._update_status_line()
        self._sync_tree_from_selections()
        self.tree.viewport().repaint()

    def _on_tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        """
        Handle tree item click to populate the preview table with images from group or single image.
        """
        if not self._preview_enabled or not self.preview_table:
            return
        if item is None:
            self._clear_table()
            return
    
        paths = []
    
        if item.childCount() > 0:  # Group header
            index = self.tree.indexOfTopLevelItem(item)
            if 0 <= index < len(self.groups):
                group = self.groups[index]
                paths = [img.path for img in group.images]
        else:  # Leaf item (single image)
            path = item.data(0, Qt.UserRole)
            if path:
                paths = [path]
    
        if not paths:
            self._clear_table()
            return
    
        # Sort paths by basename
        paths.sort(key=os.path.basename)
    
        # Clear existing content
        self._clear_table()
    
        # Populate the table
        for row, path in enumerate(paths):
            self.preview_table.insertRow(row)
    
            # Column 0: Checkbox
            checkbox = QCheckBox()
            checkbox.setProperty("path", path)
            # Use lambda with default argument to capture the current checkbox instance
            checkbox.toggled.connect(lambda checked, cb=checkbox: self._on_checkbox_toggled(cb, checked))
            self.preview_table.setCellWidget(row, 0, checkbox)
            if self._norm_path(path) in self.selected_images:
                checkbox.setChecked(True)
    
            # Column 1: Preview image
            preview_label = QLabel()
            orig_width, orig_height = 0, 0
            size_bytes = 0
            pixmap = None
            try:
                size_bytes = os.path.getsize(path)
                with Image.open(path) as pil_img:
                    orig_width, orig_height = pil_img.size
                    # Convert PIL to QPixmap
                    pil_img_rgb = pil_img.convert('RGB')
                    stride = 3 * orig_width
                    qimage = QImage(pil_img_rgb.tobytes(), orig_width, orig_height, stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qimage).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception as e:
                self.logger.warning(f"Failed to load preview for {path}: {e}")
    
                # Create placeholder pixmap (red X)
                pixmap = QPixmap(100, 100)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                pen = QPen(QColor("red"), 3)
                painter.setPen(pen)
                painter.drawLine(10, 10, 90, 90)
                painter.drawLine(90, 10, 10, 90)
                painter.end()
                orig_width, orig_height = 0, 0
                size_bytes = 0
    
            preview_label.setPixmap(pixmap)
            preview_label.setAlignment(Qt.AlignCenter)
            self.preview_table.setCellWidget(row, 1, preview_label)
    
            # Column 2: Dimensions
            dim_text = f"{orig_width}x{orig_height}" if orig_width and orig_height else "Load Error"
            dim_item = QTableWidgetItem(dim_text)
            dim_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.preview_table.setItem(row, 2, dim_item)
    
            # Column 3: File Size
            size_text = format_file_size(size_bytes)
            size_item = QTableWidgetItem(size_text)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.preview_table.setItem(row, 3, size_item)
    
            # Column 4: Path
            path_item = QTableWidgetItem(path)
            path_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.preview_table.setItem(row, 4, path_item)
    
        # Adjust table appearance
        self.preview_table.resizeColumnsToContents()
        header = self.preview_table.horizontalHeader()
        for i in range(self.preview_table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
    
        self.preview_table.verticalHeader().setDefaultSectionSize(120)
        self.preview_table.resizeRowsToContents()
        self._update_preview_checkboxes()
        self._update_status_line()

    def _update_preview_checkboxes(self) -> None:
        """
        Update all checkboxes in the preview table to match self.selected_images.
        
        Blocks signals during update to prevent recursive toggles.
        Ensures preview reflects current global selections when group switches or selections change.
        """
        if not self._preview_enabled or not self.preview_table:
            return
        for row in range(self.preview_table.rowCount()):
            checkbox = self.preview_table.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox):
                # We rely on the path property set during table population
                raw = checkbox.property("path")
                path = self._norm_path(str(raw) if raw else "")
                if path:
                    checkbox.blockSignals(True)
                    checkbox.setChecked(path in self.selected_images)
                    checkbox.blockSignals(False)


    # --- Deletion and Status Methods ---

    def _update_status_line(self) -> None:
        """
        Update status with group/file counts and selected files.
        """
        total_groups = len(self.groups)
        total_files = sum(len(g.images) for g in self.groups)
        checked = len(self.selected_images)
        self.status_label.setText(f"{total_groups} groups ({total_files} files), {checked} files selected for deletion")

    def _update_delete_btn(self) -> None:
        """
        Enable delete if any selected in table.
        """
        self.delete_btn.setEnabled(bool(self.selected_images))

    def _show_context_menu(self, position) -> None:
        """
        Show context menu for child items: Delete.
        """
        item = self.tree.itemAt(position)
        if item and item.parent():  # Child
            path = item.data(0, Qt.UserRole)
            if path:
                menu = QMenu(self)
                delete_action = QAction("Delete This Image", self)
                # Pass the path explicitly to the delete handler
                delete_action.triggered.connect(lambda: self._on_delete_clicked([path]))
                menu.addAction(delete_action)
                menu.exec(self.tree.viewport().mapToGlobal(position))

    def _on_delete_clicked(self, arg: Optional[Union[List[str], str, bool]] = None) -> None:
        """
        Delete selected images using table checkboxes or provided paths (e.g., context menu).
        Confirms, deletes with os.remove, removes from groups if successful, refreshes UI.
        """
        # Normalize input into a list of paths
        if arg is None or isinstance(arg, bool):
            # Invoked from button click or no explicit paths: use current checkbox selections
            to_delete = sorted(list(self.selected_images))
        else:
            if isinstance(arg, (list, tuple, set)):
                to_delete = sorted([str(p) for p in arg])
            else:
                # Single value (e.g., str); coerce to single-item list
                to_delete = [str(arg)]
    
        if not to_delete:
            QMessageBox.warning(self, "Warning", "No images selected.")
            return
    
        # List paths briefly
        basenames = [os.path.basename(p) for p in to_delete]
        paths_str = ",\n".join(basenames[:10])
        if len(basenames) > 10:
            paths_str += f"\n... and {len(basenames) - 10} more"
    
        msg = f"Delete {len(to_delete)} selected images?\n\nPaths:\n{paths_str}"
        reply = QMessageBox.question(self, "Confirm Delete", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
    
        successful = []
        failed = []
        for path in to_delete:
            try:
                abs_path = str(Path(path).resolve())
                # Using os.remove as per original implementation, assuming send2trash is not mandatory
                os.remove(abs_path) 
                if not os.path.exists(abs_path):
                    successful.append(path)
                    # Remove from all groups immediately
                    for group in self.groups[:]:
                        group.images = [img for img in group.images if self._norm_path(img.path) != path]
    
                    self.logger.info(f"Deleted: {path}")
                else:
                    raise Exception("File still exists after delete attempt")
            except Exception as e:
                failed.append((path, str(e)))
                self.logger.error(f"Delete failed for {path}: {e}")
    
                # Per-file error message
                show_selectable_error(self, f"Delete Failed: {os.path.basename(path)}", str(e))
    
        # Update selection persistence: remove only successfully deleted paths
        if successful:
            self.selected_images.difference_update(successful)

        # Optional explicit clear (opt-in via footer checkbox)
        if hasattr(self, "clear_after_delete_cb") and self.clear_after_delete_cb.isChecked():
            self.selected_images.clear()

        # Filter out groups with fewer than 2 images and update stats
        self.groups = [g for g in self.groups if len(g.images) >= 2]
        for g in self.groups:
            g.stats = compute_group_stats(g.images)

        # Refresh tree and synchronize UI
        self._populate_tree()
        self._sync_tree_from_selections()
        if self._preview_enabled and self.preview_table and self.preview_table.rowCount() > 0:
            self._update_preview_checkboxes()

        if successful:
            show_selectable_info(self, "Delete Complete", f"Successfully deleted {len(successful)} file(s).")

        # Clear preview and repopulate for current selection, without clearing global selections
        self._clear_table()
        current_item = self.tree.currentItem()
        if current_item:
            self._on_tree_item_clicked(current_item)

        self._update_status_line()
        self._update_delete_btn()