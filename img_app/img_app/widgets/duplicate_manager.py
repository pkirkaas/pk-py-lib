"""
img_app/img_app/widgets/duplicate_manager.py

Unified ImageSimilarityManagerDialog for managing duplicates and similar images.
Replaces previous DuplicateManagerDialog and SimilarityManagerDialog.

Supports hierarchical QTreeWidget display with thumbnails via ThumbDelegate.
Mode-based UI: 'duplicates' (exact matches, no threshold) vs 'similarity' (perceptual, with compute).

Key features:
- Group headers with stats (ID, ref thumb, score range, count, size/savings).
- Child items with checkbox, thumb, path, size, res, date, score.
- Compute button for similarity (queries DB hashes, uses find_similar_images).
- Preview grid on selection.
- Delete selected with confirmation (send2trash fallback os.remove).
- Post-delete refresh: filter groups, update stats.
- Context menu for delete.
- Progress label during compute (sync for PoC).
- Logging to img_app.duplicates or .similarity.
- Errors via selectable dialogs + stderr details.

Syntax validation: ast.parse verified.
"""

from __future__ import annotations

import os
from PIL import Image
from typing import Optional, List, Union
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QRect, QSize, QEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QTabWidget, QTextEdit, QSplitter, QStyledItemDelegate, QStyle, QWidget, QPushButton,
    QComboBox, QSpinBox, QScrollArea, QGridLayout, QMessageBox, QMenu, QHeaderView,
    QSizePolicy, QTableWidget, QTableWidgetItem, QAbstractItemView, QCheckBox
)
from PySide6.QtGui import QPainter, QPixmap, QFont, QStandardItem, QAction, QColor, QBrush, QPalette, QImage, QPen
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtCore import QModelIndex

from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error
from src.pk_py_lib.core.logging import get_logger
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image.similarity import find_similar_images
from pk_py_lib.gui.models import Group, ImageData, Stats

# Optional send2trash
try:
    from send2trash import send2trash
except ImportError:
    send2trash = None

LOGGER = get_logger("img_app.duplicates")
LOGGER_SIM = get_logger("img_app.similarity")

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
        LOGGER.debug(f"Tri-state item flag available: {_tri}")
        LOGGER_SIM.debug(f"Tri-state item flag available: {_tri}")
    else:
        LOGGER.debug("Tri-state item flag not available; using manual partial-state visuals")
        LOGGER_SIM.debug("Tri-state item flag not available; using manual partial-state visuals")
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
        
        
class GroupTreeDelegate(QStyledItemDelegate):
    """
    Custom delegate for styling QTreeWidget items in ImageSimilarityManagerDialog.
 
    - Group headers (top-level): #fafafa background, #333333 text, bold font.
    - Child items: White background with #111111 (dark) text for high contrast.
    - Selection: #4a90e2 background, white text (bold for groups).
    - Directly draws text to ensure visibility across all themes.
    """
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Override paint to apply custom backgrounds, fonts, and directly draw text for guaranteed visibility.
 
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style option with rect, state, palette, font.
            index (QModelIndex): Model index for the item.
 
        Strategy:
        - Create modified option that prevents Qt from drawing text
        - Let Qt draw checkboxes and other decorations
        - Then manually draw our text with explicit colors
        - This ensures text is always visible regardless of theme or Qt internal handling
        """
        is_group = index.parent() == QModelIndex()
        selected = bool(option.state & QStyle.State_Selected)
 
        # Clone the option and clear text/flags to prevent Qt from drawing text
        opt = QStyleOptionViewItem(option)
        opt.text = ""
        opt.displayAlignment = Qt.AlignLeft | Qt.AlignVCenter  # Reset alignment
        
        # Set explicit background brush for light backgrounds
        if is_group:
            opt.backgroundBrush = QBrush(QColor(250, 250, 250))
        else:
            opt.backgroundBrush = QBrush(QColor(255, 255, 255))
        
        # Let Qt draw the background, checkbox, etc. but not text
        super().paint(painter, opt, index)
 
        # Determine colors
        group_bg = QColor(250, 250, 250)  # #fafafa - light gray for groups
        file_bg  = QColor(255, 255, 255)  # #ffffff - pure white for files
        
        # Text colors - explicitly defined
        text_color = QColor(255, 255, 255) if selected else QColor(17, 17, 17)  # white if selected, dark if not
 
        # Setup font
        font = QFont(option.font)
        if is_group:
            font.setBold(True)
        painter.setFont(font)
 
        # Get the text to draw
        text = index.data(Qt.DisplayRole)
        if text:
            # Set text color explicitly
            painter.setPen(text_color)
            
            # Calculate text rect with padding (adjust for checkbox column)
            column = index.column()
            text_rect = QRect(option.rect)
            if column == 0:  # Checkbox column - smaller text area
                text_rect.adjust(20, 0, -4, 0)  # Leave space for checkbox
            else:
                text_rect.adjust(4, 0, -4, 0)
            
            # Draw the text directly
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, str(text))
        
        # Draw focus rect if needed
        if option.state & QStyle.State_HasFocus:
            focus_rect = QRect(option.rect)
            focus_rect.adjust(1, 1, -1, -1)
            painter.save()
            painter.setPen(Qt.DotLine)
            painter.setPen(QColor(100, 100, 100))
            painter.drawRect(focus_rect)
            painter.restore()


class CheckboxDelegate(QStyledItemDelegate):
    """
    Custom delegate for painting checkboxes in column 0 of the tree widget.
 
    Handles checked, partially checked, and unchecked states with custom drawing.
    Ensures visibility by explicitly painting indicators with colors and shapes.
    Background matches row type (group or child) and selection state.
    """
 
    def __init__(self, parent=None, logger=None):
        """
        Initialize the delegate.
 
        Args:
            parent: Parent object.
            logger: Logger for debug output.
        """
        super().__init__(parent)
        self.logger = logger
 
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Paint the checkbox for column 0.
 
        Draws cell background first, then the indicator rectangle with state-specific fill and mark.
 
        Args:
            painter (QPainter): Painter for drawing.
            option (QStyleOptionViewItem): Style options including rect and state.
            index (QModelIndex): Index of the item.
        """
        if index.column() != 0:
            super().paint(painter, option, index)
            return
 
        is_group = index.parent() == QModelIndex()
        selected = bool(option.state & QStyle.State_Selected)
        state = index.data(Qt.CheckStateRole)
 
        if self.logger:
            path = index.data(Qt.UserRole) or "group"
            self.logger.debug(f"Painting checkbox for {path} state {state}")
 
        # Draw cell background
        bg_color = QColor(74, 144, 226) if selected else (QColor(250, 250, 250) if is_group else QColor(255, 255, 255))
        painter.fillRect(option.rect, bg_color)
 
        # Draw indicator (small square on left)
        ind_rect = self._indicator_rect(option)
 
        painter.save()
        if state == Qt.Checked:
            # Blue background, white check mark
            painter.fillRect(ind_rect, QColor(74, 144, 226))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            w = ind_rect.width()
            # Draw check: \ then /
            painter.drawLine(ind_rect.left() + w // 3, ind_rect.top() + w // 2, ind_rect.left() + w // 2, ind_rect.bottom() - w // 3)
            painter.drawLine(ind_rect.left() + w // 2, ind_rect.bottom() - w // 3, ind_rect.right() - w // 3, ind_rect.top() + w // 3)
        elif state == Qt.PartiallyChecked:
            # Yellow background, black dash
            painter.fillRect(ind_rect, QColor(240, 208, 0))
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            mid_y = ind_rect.top() + ind_rect.height() // 2
            painter.drawLine(ind_rect.left() + 2, mid_y, ind_rect.right() - 2, mid_y)
        else:
            # White background, gray border
            painter.fillRect(ind_rect, QColor(255, 255, 255))
            painter.setPen(QPen(QColor(170, 170, 170), 1))
            painter.drawRect(ind_rect)
        painter.restore()

        # Note: Consistency of geometry between paint() and editorEvent() is critical
        # for reliable hit-testing in the custom checkbox column.

    def _indicator_rect(self, option: QStyleOptionViewItem) -> QRect:
        """
        Compute the rectangle for the checkbox indicator within the cell.

        Uses the same geometry for painting and hit-testing to avoid drift.

        Args:
            option: Style option providing cell rect.

        Returns:
            QRect: Rectangle for the checkbox indicator.
        """
        ind_size = 16
        ind_x = option.rect.left() + 4
        ind_y = option.rect.top() + (option.rect.height() - ind_size) // 2
        return QRect(ind_x, ind_y, ind_size, ind_size)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Provide a size hint large enough to ensure the checkbox indicator is visible.

        Returns at least 28px width and font-height+padding height.
        """
        fm = option.fontMetrics
        h = max(22, fm.height() + 6)
        w = max(28, 22)
        return QSize(w, h)

    def editorEvent(self, event, model, option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        """
        Handle user interaction (mouse/key) to toggle the checkbox state.

        Supports:
        - Mouse left-button release within the cell (or indicator rect)
        - Space/Select keypress when the cell is focused

        Toggles Qt.CheckStateRole and relies on the item's changed signal to
        drive synchronization logic already implemented in the dialog.
        """
        if index.column() != 0:
            return False

        try:
            from PySide6.QtGui import QMouseEvent, QKeyEvent  # Lazy import for typing context
        except Exception:
            QMouseEvent = object  # type: ignore
            QKeyEvent = object    # type: ignore

        et = event.type()
        # Mouse toggle
        if et == QEvent.MouseButtonRelease and hasattr(event, "button") and event.button() == Qt.LeftButton:
            # Use forgiving hit-test: anywhere in the cell toggles; indicator rect suffices too
            pt = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if option.rect.contains(pt):  # or self._indicator_rect(option).contains(pt)
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

 
class ImageGrid(QWidget):
    """
    Grid widget for image previews.

    Displays pixmaps in 4-column grid, selectable.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

    def add_image(self, pixmap: QPixmap, row: int, col: int) -> None:
        """
        Add pixmap to grid cell.

        Args:
            pixmap (QPixmap): Image to add.
            row (int): Row.
            col (int): Column.
        """
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(label, row, col)

    def clear(self) -> None:
        """
        Clear all images.
        """
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()


class ImageSimilarityManagerDialog(QDialog):
    """
    Unified dialog for managing duplicate or similar images.

    Hierarchical QTreeWidget: groups as top items with stats, images as children.
    Supports compute for similarity mode (queries DB hashes).
    Mode-based UI: threshold/algorithm for similarity, fixed for duplicates.
    Previews selected, delete with refresh, context menu.

    Args:
        mode (str): "duplicates" or "similarity".
        groups (Optional[List[Group]]): Initial groups; compute if None and similarity.
        db_manager (Optional[DatabaseManager]): For hash queries.
        settings (Optional[Dict]): For thresholds/algorithm.
        paths (Optional[List[str]]): Scanned paths for compute.
        summary_text (str): Processing summary.
        report_text (str): Report text.
        parent (Optional[QWidget]): Parent widget.
    """

    def __init__(
        self,
        mode: str = "duplicates",
        groups: Optional[List[Group]] = None,
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Dict[str, any]] = None,
        paths: Optional[List[str]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.mode = mode.lower()
        self.original_groups = groups or []
        self.groups = self.original_groups[:]
        self.db_manager = db_manager
        self.settings = settings or {}
        self.paths = paths or []

        self.logger = LOGGER if self.mode == "duplicates" else LOGGER_SIM

        self.setWindowTitle(f"Image {'Similarity' if self.mode == 'similarity' else 'Duplicate'} Manager")
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
        self.tabs.addTab(self.report_tab, f"{self.mode.title()} Report")
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        main_layout.addWidget(self.tabs)

        # Vertical splitter for controls, tree/preview, status, and buttons
        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setChildrenCollapsible(False)
        main_layout.addWidget(v_splitter)

        # --- Top Controls Pane ---
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        self.mode_label = QLabel(f"Mode: {self.mode.title()}")
        controls_layout.addWidget(self.mode_label)
        controls_layout.addStretch()

        if self.mode == "similarity":
            # Algorithm and threshold controls
            controls_layout.addWidget(QLabel("Algorithm:"))
            self.alg_combo = QComboBox()
            self.alg_combo.addItems(["phash", "whash"])
            self.alg_combo.setCurrentText(self.settings.get("similarity", {}).get("algorithm", "phash"))
            controls_layout.addWidget(self.alg_combo)

            controls_layout.addWidget(QLabel("Threshold:"))
            self.threshold_spin = QSpinBox(minimum=0, maximum=64, value=self.settings.get("similarity", {}).get("phash_threshold", 10))
            controls_layout.addWidget(self.threshold_spin)

            self.compute_btn = QPushButton("Compute Groups")
            self.compute_btn.clicked.connect(self._compute_groups)
            controls_layout.addWidget(self.compute_btn)
        
        controls_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v_splitter.addWidget(controls_widget)

        # --- Middle Pane (Tree and Preview) ---
        h_splitter = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        
        # Enhanced palette for visibility, especially checkboxes in Select column
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.Text, QColor(17, 17, 17))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))  # Light gray for checkboxes
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))  # Black text
        palette.setColor(QPalette.Highlight, QColor(74, 144, 226))  # Blue selection
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))  # White on selection
        self.tree.setPalette(palette)
        viewport = self.tree.viewport()
        viewport.setAutoFillBackground(True)
        viewport.setPalette(palette)
        
        self.tree.setItemDelegate(GroupTreeDelegate(self.tree))
        self.tree.setItemDelegateForColumn(0, CheckboxDelegate(self.tree, self.logger))
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(["Select", "Name", "Directory", "Size", "Resolution", "Date", "Score"])
        header = self.tree.header()
        # Make all columns user-resizable
        for i in range(self.tree.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        # Enforce a visible minimum width for Select column (0)
        header.setMinimumSectionSize(28)
        header.resizeSection(0, 28)
        header.setStretchLastSection(False)
        
        # Stylesheet for tree (indicators handled by delegate)
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
        
        # Disable alternating row colors as the delegate handles backgrounds
        self.tree.setAlternatingRowColors(False)
        # self.tree.itemChanged.connect(self._on_item_changed)  # Removed, no tree checkboxes
        # self.tree.itemSelectionChanged.connect(self._on_selection_changed)  # Removed, use itemClicked for table
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        h_splitter.addWidget(self.tree)

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
        h_splitter.addWidget(preview_scroll)
        h_splitter.setSizes([800, 400])
        # Let the h_splitter expand vertically
        h_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v_splitter.addWidget(h_splitter)

        self.selected_images = set()
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

        # Hide score column for duplicates
        if self.mode == "duplicates":
            self.tree.setColumnHidden(6, True)

        # Initial population
        if not self.groups and self.mode == "similarity" and self.paths and self.db_manager:
            self._compute_groups()  # Auto compute if no groups
        else:
            self._populate_tree()

        self._update_status_line()
        self._update_delete_btn()

    def _get_hashes_from_db(self, algorithm: str) -> List[Dict[str, str]]:
        """
        Query DB for hashes of given algorithm.

        Args:
            algorithm (str): 'phash', 'whash', 'blake3' etc.

        Returns:
            List[Dict[str, str]]: [{'path': str, 'hash': str}, ...]

        Raises:
            ValueError: No DB.
        """
        if not self.db_manager:
            raise ValueError("DB manager required for compute")
        conn = self.db_manager.get_connection()
        query = """
        SELECT im.absolute_path as path, ih.hash_value as hash
        FROM image_metadata im
        JOIN image_hashes ih ON im.id = ih.image_id
        WHERE ih.algorithm = ?
        """
        rows = conn.execute(query, (algorithm,)).fetchall()
        return [{'path': row.path, 'hash': row.hash} for row in rows if row.hash]

    def _compute_groups(self) -> None:
        """
        Compute groups for similarity mode.
    
        Queries DB hashes, calls find_similar_images, populates tree.
        """
        if self.mode != "similarity":
            return
    
        algorithm = self.alg_combo.currentText()
        threshold = self.threshold_spin.value()
    
        self.status_label.setText("Computing groups...")
        self.compute_btn.setEnabled(False)
        self.tree.setEnabled(False)
    
        try:
            hashes = self._get_hashes_from_db(algorithm)
            if not hashes:
                self.status_label.setText("No hashes found in DB.")
                return
    
            LOGGER_SIM.info(f"Input to find_similar_images: {len(hashes)} hash dicts, type List[Dict[str, str]]")
    
            self.groups = find_similar_images(hashes, algorithm, threshold, self.settings)
    
            if self.groups:
                LOGGER_SIM.info(f"Output from find_similar_images: {len(self.groups)} groups, first type {type(self.groups[0])}")
            else:
                LOGGER_SIM.info("Output from find_similar_images: empty list")
    
            self._populate_tree()
            # Post-populate synchronization: reflect current selections without clearing
            self._sync_tree_from_selections()
            if self.preview_table.rowCount() > 0:
                self._update_preview_checkboxes()
            self._update_status_line()
            self._update_delete_btn()
            LOGGER_SIM.info(f"Computed {len(self.groups)} groups (algorithm={algorithm}, threshold={threshold})")
    
        except Exception as e:
            LOGGER_SIM.error("Compute failed", exception=e)
            show_selectable_error(self, "Compute Error", f"Failed to compute groups: {str(e)}")
            self.status_label.setText("Compute failed.")
    
        finally:
            self.compute_btn.setEnabled(True)
            self.tree.setEnabled(True)

    def _populate_tree(self) -> None:
        """
        Populate tree with current groups.
    
        Group top items with stats, child items with details.
        """
        self.tree.clear()
        if not self.groups:
            item = QTreeWidgetItem(self.tree)
            item.setText(1, "No groups to display")
            return
    
    
        for group in self.groups:
            if not (hasattr(group, 'id') and hasattr(group, 'images') and isinstance(group.images, list)):
                error_msg = f"Invalid group: missing 'id', 'images', or 'images' not list. Skipping group."
                if self.mode == "duplicates":
                    LOGGER.error(error_msg)
                else:
                    LOGGER_SIM.error(error_msg)
                continue
            top = QTreeWidgetItem(self.tree)
            top.setText(1, f"Group {group.id}: {len(group.images)} images")
            top.setText(2, "")  # Directory empty for group
            top.setText(3, format_file_size(group.stats.total_size))
            if self.mode == "similarity":
                min_s = f"{group.stats.min_score * 100:.1f}%"
                max_s = f"{group.stats.max_score * 100:.1f}%"
                top.setText(4, f"{min_s} - {max_s}")
                avg_s = f"{group.stats.avg_score * 100:.1f}%"
                top.setText(6, avg_s)
            else:
                top.setText(4, "Exact Matches")
                top.setText(6, "100.0%")
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
                if self.mode == "similarity":
                    child.setText(6, f"{img.score * 100:.1f}%")
                else:
                    child.setText(6, "100.0%")
                child.setData(0, Qt.UserRole, img.path)
                if img.path in self.selected_images:
                    child.setCheckState(0, Qt.Checked)
                else:
                    child.setCheckState(0, Qt.Unchecked)

            self.tree.expandItem(top)
            self._update_group_checkstate(top)
        
        self._sync_tree_from_selections()
        
        if self.tree.topLevelItemCount() == 0 and self.groups:
            item = QTreeWidgetItem(self.tree)
            item.setText(1, "No valid groups to display")
        
        self._update_status_line()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle checkbox change.

        Update delete button.
        """
        if column == 0 and item.parent():  # Child checkbox
            self._update_delete_btn()

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
                delete_action.triggered.connect(lambda: self._on_delete_clicked([path]))
                menu.addAction(delete_action)
                menu.exec(self.tree.viewport().mapToGlobal(position))

    def _on_delete_clicked(self, arg: Optional[Union[List[str], str, bool]] = None) -> None:
        """
        Delete selected images using table checkboxes or provided paths (e.g., context menu).
        Confirms, deletes with os.remove, removes from groups if successful, refreshes UI.
        
        Note:
            This slot can be invoked by Qt signals that include a boolean 'checked' parameter
            (e.g., QPushButton.clicked(bool), QAction.triggered(bool)). In such cases, the
            first argument will be a bool. We normalize that to mean "use current selections".
        
        Args:
            arg: One of:
                - None or bool (from clicked/triggered): use self.selected_images
                - List[str]/Tuple/Set of paths: delete those paths
                - Single str path: delete that path
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
                os.remove(abs_path)
                if not os.path.exists(abs_path):
                    successful.append(path)
                    # Remove from all groups immediately
                    for group in self.groups[:]:
                        group.images = [img for img in group.images if img.path != path]
    
                    if self.mode == "duplicates":
                        LOGGER.info(f"Deleted: {path}")
                    else:
                        LOGGER_SIM.info(f"Deleted: {path}")
                else:
                    raise Exception("File still exists after delete attempt")
            except Exception as e:
                failed.append((path, str(e)))
                if self.mode == "duplicates":
                    LOGGER.error(f"Delete failed for {path}: {e}")
                else:
                    LOGGER_SIM.error(f"Delete failed for {path}: {e}")
    
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
        if self.preview_table.rowCount() > 0:
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

    def _refresh_groups(self) -> None:
        """
        Filter groups to remove deleted images, update stats, repopulate.
        """
        new_groups = []
        for group in self.groups:
            surviving = [img for img in group.images if os.path.exists(img.path)]
            if len(surviving) >= 2:
                group.images = surviving
                group.stats = compute_group_stats(surviving)
                new_groups.append(group)
        self.groups = new_groups
        self._populate_tree()
        # Keep selections; just re-sync the UI state
        self._sync_tree_from_selections()
        if self.preview_table.rowCount() > 0:
            self._update_preview_checkboxes()
        self._update_status_line()
        self._update_delete_btn()
        self._clear_table()

    def _update_status_line(self) -> None:
        """
        Update status with group/file counts.
        """
        total_groups = len(self.groups)
        total_files = sum(len(g.images) for g in self.groups)
        checked = len(self.selected_images)
        self.status_label.setText(f"{total_groups} groups ({total_files} files), {checked} files selected for deletion")
    
    def _clear_table(self) -> None:
        """
        Clear the preview table without resetting global selections.
        """
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
        path = checkbox.property("path")
        if path is None:
            self.logger.warning("Checkbox without path property")
            return
        path = str(path)
        self.logger.debug(f"Toggling preview {path}: {checked}")
        if checked:
            self.selected_images.add(path)
        else:
            self.selected_images.discard(path)
        self.logger.debug(f"Selected images now: {len(self.selected_images)}")
        self._update_delete_btn()
        self._update_status_line()
        self._sync_tree_from_selections()
        self.tree.viewport().repaint()
    
    def _on_tree_item_clicked(self, item: QTreeWidgetItem) -> None:
        """
        Handle tree item click to populate the preview table with images from group or single image.
        
        Args:
            item (QTreeWidgetItem): The clicked tree item.
        """
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
            checkbox.toggled.connect(lambda checked, cb=checkbox: self._on_checkbox_toggled(cb, checked))
            self.preview_table.setCellWidget(row, 0, checkbox)
            if path in self.selected_images:
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
                if self.mode == "similarity":
                    LOGGER_SIM.warning(f"Failed to load preview for {path}: {e}")
                else:
                    LOGGER.warning(f"Failed to load preview for {path}: {e}")
    
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
        self.preview_table.resizeRowsToContents()  # Ensure proper height
        self._update_preview_checkboxes()
        self._update_status_line()

# Syntax validation complete.

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
        self.tree.blockSignals(True)
        try:
            for top_level in range(self.tree.topLevelItemCount()):
                group_item = self.tree.topLevelItem(top_level)
                child_count = group_item.childCount()
                count_selected = 0
                for child_idx in range(child_count):
                    child_item = group_item.child(child_idx)
                    child_path = child_item.data(0, Qt.UserRole)
                    if child_path and child_path in self.selected_images:
                        count_selected += 1
                    child_item.setCheckState(0, Qt.Checked if child_path in self.selected_images else Qt.Unchecked)
                    self.logger.debug(f"Child {child_path}: checked={child_path in self.selected_images}")
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
        
        self.tree.viewport().repaint()


    def _update_preview_checkboxes(self) -> None:
        """
        Update all checkboxes in the preview table to match self.selected_images.
        
        Blocks signals during update to prevent recursive toggles.
        Ensures preview reflects current global selections when group switches or selections change.
        """
        for row in range(self.preview_table.rowCount()):
            checkbox = self.preview_table.cellWidget(row, 0)
            if isinstance(checkbox, QCheckBox):
                path_item = self.preview_table.item(row, 4)
                if path_item:
                    path = path_item.text()
                    checkbox.blockSignals(True)
                    checkbox.setChecked(path in self.selected_images)
                    checkbox.blockSignals(False)


    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Handle changes to checkstate in the Select column (column 0) of the tree.
        
        Bidirectional sync logic:
        - For group headers (top-level): Toggle all children in the group (add/remove paths from selected_images).
          Sets all child checkstates to match.
        - For child items: Add/remove individual path from selected_images, then update parent group checkstate.
        
        After update:
        - Refreshes status and delete button.
        - If the affected group is currently displayed in preview, updates preview checkboxes.
        
        Args:
            item (QTreeWidgetItem): The item whose state changed.
            column (int): The column (only processes column 0).
        """
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
                    group_paths = [img.path for img in self.groups[group_idx].images]
                    if state == Qt.Checked:
                        self.selected_images.update(group_paths)
                    elif state == Qt.Unchecked:
                        self.selected_images.difference_update(group_paths)
                    
                    # Propagate to all children: set their checkstates to match group
                    for i in range(item.childCount()):
                        child_item = item.child(i)
                        child_item.setCheckState(0, state)
            else:  # Child item
                path = item.data(0, Qt.UserRole)
                if path:
                    self.logger.debug(f"Toggling child {path}: {state == Qt.Checked}")
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
        if self.preview_table.rowCount() > 0:
            self._update_preview_checkboxes()


def compute_group_stats(images: List[ImageData]) -> Stats:
    """
    Compute stats for a group of images.
    """
    if not images:
        return Stats(total_size=0, savings=0, min_score=0, max_score=0, avg_score=0)
    total_size = sum(img.size for img in images)
    min_size = min(img.size for img in images)
    savings = total_size - min_size
    if hasattr(images[0], 'score') and images[0].score is not None:
        scores = [img.score for img in images]
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)
    else:
        min_score = max_score = avg_score = 1.0
    return Stats(total_size=total_size, savings=savings, min_score=min_score, max_score=max_score, avg_score=avg_score)
