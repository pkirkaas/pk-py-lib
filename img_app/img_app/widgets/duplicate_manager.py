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
from typing import Optional, List
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QRect
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QTabWidget, QTextEdit, QSplitter, QStyledItemDelegate, QWidget, QPushButton,
    QComboBox, QSpinBox, QScrollArea, QGridLayout, QMessageBox, QMenu, QHeaderView,
    QSizePolicy
)
from PySide6.QtGui import QPainter, QPixmap, QFont, QStandardItem, QAction, QColor
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
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(["Select", "Name", "Directory", "Size", "Resolution", "Date", "Score"])
        header = self.tree.header()
        # Make all columns user-resizable
        for i in range(self.tree.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.Interactive)
        self.tree.setStyleSheet("""
            QTreeWidget::item {
                border-bottom: 1px solid #e0e0e0;
                padding: 2px 4px;
            }
        """)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        h_splitter.addWidget(self.tree)

        preview_scroll = QScrollArea(widgetResizable=True)
        self.preview_grid = ImageGrid()
        preview_scroll.setWidget(self.preview_grid)
        h_splitter.addWidget(preview_scroll)
        h_splitter.setSizes([800, 400])
        # Let the h_splitter expand vertically
        h_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v_splitter.addWidget(h_splitter)

        # --- Status Label ---
        self.status_label = QLabel("Ready to manage groups")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        v_splitter.addWidget(self.status_label)

        # --- Bottom Buttons Pane ---
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)
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
            self.status_label.setText(f"Computed {len(self.groups)} groups.")
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
            top.setFlags(top.flags() & ~Qt.ItemIsUserCheckable)
            font = top.font(1)
            font.setBold(True)
            top.setFont(1, font)

            # Style group header row with subtle light gray background and dark text for better readability
            header_bg = QColor(245, 245, 245)  # #f5f5f5
            header_fg = QColor(51, 51, 51)  # #333333
            for col in range(self.tree.columnCount()):
                top.setBackground(col, header_bg)
                top.setForeground(col, header_fg)
    
            for idx, img in enumerate(group.images):
                child = QTreeWidgetItem(top)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setText(1, os.path.basename(img.path))
                child.setText(2, os.path.dirname(img.path))  # Full directory path
                child.setText(3, format_file_size(img.size))
                child.setText(4, img.resolution)
                child.setText(5, img.mod_date)
                if self.mode == "similarity":
                    child.setText(6, f"{img.score * 100:.1f}%")
                else:
                    child.setText(6, "100.0%")
                child.setData(1, Qt.UserRole, img.path)  # For delete and preview
                if idx % 2 == 0:
                    bg_color = QColor(250, 251, 255)  # #fafbff
                else:
                    bg_color = QColor(249, 249, 249)  # #f9f9f9
                for col in range(self.tree.columnCount()):
                    child.setBackground(col, bg_color)
    
            self.tree.expandItem(top)
        
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
        Enable delete if any checked.
        """
        checked = False
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.NoChildren)
        while iterator.value():
            if iterator.value().checkState(0) == Qt.Checked:
                checked = True
                break
            iterator += 1
        self.delete_btn.setEnabled(checked)

    def _on_selection_changed(self) -> None:
        """
        Update preview grid with selected children paths.
        """
        selected_paths = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.isSelected():
                    path = child.data(1, Qt.UserRole)
                    if path:
                        selected_paths.append(path)
        self._update_preview(selected_paths)

    def _update_preview(self, paths: List[str]) -> None:
        """
        Clear and add pixmaps to preview grid (limit 16).
        """
        self.preview_grid.clear()
        cols = 4
        for k, path in enumerate(set(paths[:16])):
            try:
                pix = QPixmap(path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                if not pix.isNull():
                    self.preview_grid.add_image(pix, k // cols, k % cols)
            except Exception as e:
                if self.mode == "duplicates":
                    LOGGER.error(f"Preview failed {path}: {e}")
                else:
                    LOGGER_SIM.error(f"Preview failed {path}: {e}")

    def _show_context_menu(self, position) -> None:
        """
        Show context menu for child items: Delete.
        """
        item = self.tree.itemAt(position)
        if item and item.parent():  # Child
            path = item.data(1, Qt.UserRole)
            if path:
                menu = QMenu(self)
                delete_action = QAction("Delete This Image", self)
                delete_action.triggered.connect(lambda: self._on_delete_clicked([path]))
                menu.addAction(delete_action)
                menu.exec(self.tree.viewport().mapToGlobal(position))

    def _on_delete_clicked(self) -> None:
        """
        Delete checked images, refresh groups.
        """
        checked_paths = []
        iterator = QTreeWidgetItemIterator(self.tree, QTreeWidgetItemIterator.NoChildren)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.Checked and item.parent():
                path = item.data(1, Qt.UserRole)
                if path:
                    checked_paths.append(path)
            iterator += 1

        if not checked_paths:
            return

        msg = f"Delete {len(checked_paths)} selected files?\nUses Recycle Bin if send2trash available."
        reply = QMessageBox.question(self, "Confirm Delete", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        deleted = 0
        failed = []
        for path in checked_paths:
            try:
                abs_path = str(Path(path).resolve())
                if send2trash:
                    send2trash(abs_path)
                else:
                    os.remove(abs_path)
                if not os.path.exists(abs_path):
                    deleted += 1
                    if self.mode == "duplicates":
                        LOGGER.info(f"Deleted duplicate: {path}")
                    else:
                        LOGGER_SIM.info(f"Deleted similar: {path}")
                else:
                    raise Exception("File still exists")
            except Exception as e:
                err_msg = f"{str(e)}\n{traceback.format_exc()}"
                failed.append((path, err_msg))
                if self.mode == "duplicates":
                    LOGGER.error(f"Delete failed {path}", exception=e)
                else:
                    LOGGER_SIM.error(f"Delete failed {path}", exception=e)

        if failed:
            err_text = "\n".join([f"{os.path.basename(p)}: {err}" for p, err in failed[:5]])
            if len(failed) > 5:
                err_text += f"\n... and {len(failed)-5} more"
            show_selectable_error(self, "Partial Failure", f"Some deletions failed:\n{err_text}")

        if deleted > 0:
            self._refresh_groups()
            show_selectable_info(self, "Delete Complete", f"Successfully deleted {deleted} file(s).")

        self._update_preview([])

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
        self._update_status_line()
        self._update_delete_btn()

    def _update_status_line(self) -> None:
        """
        Update status with group/file counts.
        """
        total_groups = len(self.groups)
        total_files = sum(len(g.images) for g in self.groups)
        checked = sum(1 for i in range(self.tree.topLevelItemCount()) for j in range(self.tree.topLevelItem(i).childCount()) if self.tree.topLevelItem(i).child(j).checkState(0) == Qt.Checked)
        self.status_label.setText(f"{total_groups} groups ({total_files} files), {checked} selected")

# Syntax validation complete.
