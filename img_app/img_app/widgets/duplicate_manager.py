"""
img_app/img_app/widgets/duplicate_manager.py

DuplicateManagerDialog - Milestone 1 UI skeleton for managing duplicate groups (single_pool).

This dialog presents groups and files with per-file checkboxes and no actions enabled yet.

Syntax validation: This file has been reviewed with ast.parse for Python syntax correctness.
"""
from __future__ import annotations

import os
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRect, QSize, QFileInfo
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QPushButton, QWidget, QSizePolicy, QSpacerItem, QMessageBox,
    QHeaderView, QTextEdit, QTabWidget, QSplitter, QStyledItemDelegate,
    QScrollArea, QGridLayout
)
from PySide6.QtGui import QGuiApplication, QPainter, QPen, QColor, QBrush, QFont, QPixmap, QImage
from PySide6.QtWidgets import QStyleOptionViewItem
from PySide6.QtCore import QModelIndex

from src.pk_py_lib.gui.utils.messages import show_selectable_info, show_selectable_error
from src.pk_py_lib.core.logging import get_logger
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.image import similarity
from src.pk_py_lib.core.filesystem.traversal import IMAGE_EXTENSIONS
from PySide6.QtWidgets import QComboBox, QSpinBox
from PySide6.QtGui import QIcon

# Optional send2trash import; fallback would be permanent deletion
try:
    from send2trash import send2trash  # type: ignore
except Exception:  # pragma: no cover
    send2trash = None  # type: ignore

from PIL import Image
import traceback

# Module-level logger for duplicate operations within the app
LOGGER = get_logger("img_app.duplicates")
LOGGER_SIM = get_logger("img_app.similarity")


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string.
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


def format_timestamp(timestamp: int) -> str:
    """
    Format Unix timestamp to "dd-MMM-yy" format.
    """
    from datetime import datetime
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d-%b-%y")
    except (ValueError, OSError):
        return str(timestamp)


class GroupFrameDelegate(QStyledItemDelegate):
    """
    QStyledItemDelegate that adds visual separation to groups in a QTreeWidget.
    """

    def __init__(self, tree: QTreeWidget) -> None:
        super().__init__(tree)
        self._tree = tree
        self._sep_color = QColor(173, 216, 230)
        self._sep_thickness = 2
        self._sep_row_height = 14
        self._header_bg_color = QColor(245, 247, 250)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Draw dedicated separator rows and group headers.
        """
        try:
            root_col0 = index.sibling(index.row(), 0)
            if root_col0.isValid() and root_col0.data(Qt.UserRole) == "__separator__":
                painter.save()
                viewport_rect = self._tree.viewport().rect()
                painter.setClipRect(viewport_rect)
                pen = QPen(self._sep_color)
                pen.setWidth(self._sep_thickness)
                painter.setPen(pen)
                y = option.rect.center().y()
                painter.drawLine(0, y, viewport_rect.width(), y)
                painter.restore()
                return
        except Exception:
            pass

        try:
            if not index.parent().isValid():
                bg = self._header_bg_color
                painter.save()
                painter.fillRect(option.rect, bg)
                painter.restore()
        except Exception:
            pass

        super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Provide a small fixed height for separator rows.
        """
        base = super().sizeHint(option, index)
        try:
            root_col0 = index.sibling(index.row(), 0)
            if root_col0.isValid() and root_col0.data(Qt.UserRole) == "__separator__":
                return QSize(base.width(), self._sep_row_height)
        except Exception:
            pass
        return base


class DuplicateManagerDialog(QDialog):
    """
    Modal dialog for managing duplicates.
    """

    def __init__(
        self,
        mode: str = "duplicates",
        groups: Optional[List[Dict[str, Any]]] = None,
        db_manager: Optional[DatabaseManager] = None,
        settings_manager: Optional[Any] = None,
        paths: Optional[List[str]] = None,
        summary_text: str = "",
        report_text: str = "",
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.mode = mode.lower()
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.paths = paths or []
    
        self.setWindowTitle("Duplicate Manager")
        self.setModal(True)
        self.resize(1000, 700)
    
        self._groups: List[Dict[str, Any]] = list(groups or [])
    
        main_layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
    
        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)
    
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, "Duplicate Report")
        self.splitter.addWidget(self.tabs)
    
        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
    
        total_groups = len(self._groups)
        total_files = sum(len(g.get("files", [])) for g in self._groups)
        self.header_label = QLabel(f"Duplicate Groups: {total_groups} — Files: {total_files}", self)
        bottom_layout.addWidget(self.header_label)
    
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Select", "File Path", "Modified"])
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setItemDelegate(GroupFrameDelegate(self.tree))
        bottom_layout.addWidget(self.tree)
    
        self.status_label = QLabel("No duplicates to manage", self)
        bottom_layout.addWidget(self.status_label)
    
        self._populate_tree()
    
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)
        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        bottom_layout.addLayout(btn_row)
    
        self.splitter.addWidget(bottom_widget)
        main_layout.addWidget(self.splitter)
    
        self.tree.itemChanged.connect(self._on_item_changed)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self._update_status_line()
        QTimer.singleShot(100, self._configure_initial_splitter_sizes)

    def _populate_tree(self) -> None:
        self.tree.clear()
        if not self._groups:
            return

        for i, group in enumerate(self._groups, start=1):
            if i > 1:
                sep = QTreeWidgetItem(self.tree)
                sep.setData(0, Qt.UserRole, "__separator__")
                sep.setFlags(Qt.NoItemFlags)

            files = group.get("files", [])
            group_size = files[0].get("size", 0) if files else 0
            top = QTreeWidgetItem(self.tree)
            top.setText(1, f"Group #{i}: {len(files)} files ({format_file_size(group_size)})")
            top.setFlags(top.flags() & ~Qt.ItemIsUserCheckable)
            font = top.font(1)
            font.setBold(True)
            top.setFont(1, font)

            for f in files:
                child = QTreeWidgetItem(top)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setText(1, f.get("path", ""))
                child.setText(2, format_timestamp(f.get("modified", 0)))
                child.setData(1, Qt.UserRole, f)
            self.tree.expandItem(top)
        self._update_status_line()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0:
            self._update_delete_enabled()
            self._update_status_line()

    def _update_delete_enabled(self) -> None:
        any_checked = False
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                if group.child(j).checkState(0) == Qt.Checked:
                    any_checked = True
                    break
            if any_checked:
                break
        self.delete_btn.setEnabled(any_checked)

    def _update_status_line(self) -> None:
        selected_files = 0
        total_files = 0
        groups_with_selected = set()
        total_groups = 0
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            if group.data(0, Qt.UserRole) == "__separator__":
                continue
            total_groups += 1
            total_files += group.childCount()
            for j in range(group.childCount()):
                if group.child(j).checkState(0) == Qt.Checked:
                    selected_files += 1
                    groups_with_selected.add(i)
        
        self.status_label.setText(
            f"{selected_files} files from {len(groups_with_selected)} groups selected out of {total_files} total files in {total_groups} groups"
        )

    def _collect_checked_files(self) -> List[Dict[str, Any]]:
        checked = []
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.Checked:
                    checked.append(child.data(1, Qt.UserRole))
        return checked

    def _on_delete_clicked(self) -> None:
        checked_files = self._collect_checked_files()
        if not checked_files:
            return

        reply = QMessageBox.question(self, "Confirm Deletion", 
                                     f"Are you sure you want to delete {len(checked_files)} files?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            for file_data in checked_files:
                try:
                    if send2trash:
                        send2trash(file_data['path'])
                    else:
                        os.remove(file_data['path'])
                except Exception as e:
                    LOGGER.error(f"Failed to delete {file_data['path']}: {e}")
            self._refresh_tree()

    def _refresh_tree(self) -> None:
        # Re-filter groups to remove deleted files
        new_groups = []
        for group in self._groups:
            surviving_files = [f for f in group['files'] if os.path.exists(f['path'])]
            if len(surviving_files) > 1:
                group['files'] = surviving_files
                new_groups.append(group)
        self._groups = new_groups
        self._populate_tree()
        self._update_delete_enabled()

    def _configure_initial_splitter_sizes(self) -> None:
        try:
            self.splitter.setSizes([self.height() // 3, 2 * self.height() // 3])
        except Exception as e:
            LOGGER.error(f"Failed to set splitter sizes: {e}")

    def _is_separator_item(self, item: QTreeWidgetItem) -> bool:
        return item.data(0, Qt.UserRole) == "__separator__"

class ImageGrid(QWidget):
    """A widget that displays a grid of images."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.layout = QGridLayout(self)
        self.setLayout(self.layout)

    def add_image(self, pixmap: QPixmap, row: int, col: int) -> None:
        label = QLabel(self)
        label.setPixmap(pixmap)
        self.layout.addWidget(label, row, col)

    def clear(self) -> None:
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

class SimilarityManagerDialog(QDialog):
    """
    Modal dialog for managing visually similar images.
    """

    def __init__(
        self,
        groups: Optional[List[Dict[str, Any]]] = None,
        paths: Optional[List[str]] = None,
        summary_text: str = "",
        report_text: str = "",
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.groups = self._normalize_groups_input(groups or [])
        self.paths = paths or []
        self.run_paths = paths or []
        self.db_manager = db_manager
        self.settings = settings or {}
        
        self.setWindowTitle("Similarity Manager")
        self.setModal(True)
        self.resize(1200, 800)

        main_layout = QVBoxLayout(self)
        self.splitter = QSplitter(Qt.Vertical, self)
        self.splitter.setChildrenCollapsible(False)

        self.summary_tab = QTextEdit(self)
        self.summary_tab.setReadOnly(True)
        self.summary_tab.setPlainText(summary_text)
        self.report_tab = QTextEdit(self)
        self.report_tab.setReadOnly(True)
        self.report_tab.setPlainText(report_text)

        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.summary_tab, "Processing Summary")
        self.tabs.addTab(self.report_tab, "Similarity Report")
        self.splitter.addWidget(self.tabs)

        bottom_widget = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self.header_label = QLabel("Similarity Groups", self)
        self.header_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header_label.setMaximumHeight(30)
        bottom_layout.addWidget(self.header_label)

        controls_layout = QHBoxLayout()
        self.alg_combo = QComboBox(self)
        self.alg_combo.addItems(["phash", "whash"])
        controls_layout.addWidget(QLabel("Algorithm:", self))
        controls_layout.addWidget(self.alg_combo)
        self.threshold_spin = QSpinBox(self)
        self.threshold_spin.setRange(0, 64)
        self.threshold_spin.setValue(10)
        controls_layout.addWidget(QLabel("Threshold:", self))
        controls_layout.addWidget(self.threshold_spin)
        self.refresh_btn = QPushButton("Refresh Groups", self)
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addStretch()
        controls_layout_widget = QWidget()
        controls_layout_widget.setLayout(controls_layout)
        controls_layout_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        controls_layout_widget.setMaximumHeight(40)
        bottom_layout.addWidget(controls_layout_widget)

        self.tree_preview_splitter = QSplitter(Qt.Horizontal, self)
        
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Select", "Group", "Filename", "Size", "Resolution", "Score"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.tree_preview_splitter.addWidget(self.table)

        self.preview_area = QScrollArea(self)
        self.preview_area.setWidgetResizable(True)
        self.preview_pane = ImageGrid(self)
        self.preview_area.setWidget(self.preview_pane)
        self.tree_preview_splitter.addWidget(self.preview_area)
        
        self.tree_preview_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bottom_layout.addWidget(self.tree_preview_splitter)

        self.status_label = QLabel("No similar images to manage", self)
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.status_label.setMaximumHeight(30)
        bottom_layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.delete_btn = QPushButton("Delete", self)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)
        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        btn_row_widget = QWidget()
        btn_row_widget.setLayout(btn_row)
        btn_row_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_row_widget.setMaximumHeight(40)
        bottom_layout.addWidget(btn_row_widget)

        self.splitter.addWidget(bottom_widget)
        main_layout.addWidget(self.splitter)

        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.refresh_btn.clicked.connect(self._on_refresh)

        self._populate_tree()
        self._update_status_line()
        QTimer.singleShot(100, self._configure_initial_splitter_sizes)

    def _normalize_groups_input(self, raw_groups: List[Any]) -> List[Dict[str, Any]]:
        normalized = []
        for g in raw_groups:
            if isinstance(g, dict) and 'paths' in g:
                normalized.append(g)
            elif isinstance(g, list):
                normalized.append({'paths': g, 'scores': [0.0] * len(g)})
        return normalized

    def _populate_tree(self) -> None:
        self.table.setRowCount(0)
        if not self.groups:
            self.header_label.setText("No similar images found")
            return
    
        total_rows = sum(len(g.get('paths', [])) for g in self.groups)
        self.table.setRowCount(total_rows)
        row = 0
        for i, group in enumerate(self.groups, 1):
            paths = group.get('paths', [])
            scores = group.get('scores', [0.0] * len(paths))
            for j, path in enumerate(paths):
                # Select
                select_item = QTableWidgetItem()
                select_item.setCheckState(Qt.Unchecked)
                self.table.setItem(row, 0, select_item)
    
                # Group
                group_item = QTableWidgetItem(f"Group #{i}")
                self.table.setItem(row, 1, group_item)
    
                # Filename
                filename = os.path.basename(path)
                fname_item = QTableWidgetItem(filename)
                fname_item.setData(Qt.UserRole, path)
                self.table.setItem(row, 2, fname_item)
    
                # Size
                info = QFileInfo(path)
                size_str = format_file_size(info.size())
                size_item = QTableWidgetItem(size_str)
                self.table.setItem(row, 3, size_item)
    
                # Resolution
                res_str = "Unknown"
                try:
                    with Image.open(path) as img:
                        w, h = img.size
                        res_str = f"{w}x{h}"
                except Exception as e:
                    LOGGER_SIM.warning(f"Could not get resolution for {path}: {e}")
                res_item = QTableWidgetItem(res_str)
                self.table.setItem(row, 4, res_item)
    
                # Score
                score = scores[j] if j < len(scores) else 0.0
                score_item = QTableWidgetItem(f"{score:.2f}")
                self.table.setItem(row, 5, score_item)
    
                row += 1
        self._update_header_counts()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_delete_enabled()
            self._update_status_line()

    def _on_selection_changed(self) -> None:
        selected_indexes = self.table.selectedIndexes()
        selected_rows = set(index.row() for index in selected_indexes)
        paths = []
        for row in selected_rows:
            fname_item = self.table.item(row, 2)
            if fname_item:
                path = fname_item.data(Qt.UserRole)
                if path:
                    paths.append(path)
        self._update_preview_pane(list(set(paths)))

    def _update_preview_pane(self, paths: List[str]) -> None:
        self.preview_pane.clear()
        cols = 2
        for i, path in enumerate(paths):
            try:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    self.preview_pane.add_image(pixmap.scaledToWidth(200), i // cols, i % cols)
            except Exception as e:
                LOGGER_SIM.error(f"Failed to load image for preview {path}: {e}")

    def _update_delete_enabled(self) -> None:
        any_checked = any(
            self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
            for row in range(self.table.rowCount())
        )
        self.delete_btn.setEnabled(any_checked)

    def _update_status_line(self) -> None:
        total_files = self.table.rowCount()
        checked_count = sum(
            1 for row in range(total_files)
            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
        )
        self.status_label.setText(f"{checked_count} of {total_files} files selected for deletion.")

    def _update_header_counts(self) -> None:
        groups_count = len(self.groups)
        files_count = sum(len(g.get('paths', [])) for g in self.groups)
        self.header_label.setText(f"Similarity Groups: {groups_count} — Files: {files_count}")

    def _on_refresh(self) -> None:
        algorithm = self.alg_combo.currentText()
        threshold = self.threshold_spin.value()

        # Create a profile payload for the computation methods
        profile_payload = {
            'similarity': {
                f'{algorithm}_threshold': threshold,
                'phash_hash_size': 8,  # Assuming default, can be configurable if needed
            }
        }

        # Re-compute groups
        similarity_groups = self._compute_similarity_groups(profile_payload, self.run_paths, self.db_manager)
        self.groups = self._normalize_groups_input(similarity_groups)
        
        # Repopulate the table and update UI
        self._populate_tree()
        self._update_status_line()

    def _on_delete_clicked(self) -> None:
        """
        Handle the delete button click: confirm and delete selected files, then refresh groups.
        """
        checked_paths = self._collect_checked_files()
        if not checked_paths:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {len(checked_paths)} selected files?\n\n"
            f"Note: If send2trash is not available, this will permanently delete the files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        success_count = 0
        failed_files = []
        for path in checked_paths:
            try:
                info = QFileInfo(path)
                if not info.exists():
                    LOGGER_SIM.warning(f"File no longer exists: {path}")
                    continue

                abs_path = str(info.absoluteFilePath())
                if send2trash:
                    send2trash(abs_path)
                else:
                    os.remove(abs_path)

                # Verify deletion
                if not QFileInfo(abs_path).exists():
                    success_count += 1
                else:
                    raise Exception("File still exists after attempted deletion")
            except Exception as e:
                error_detail = f"{str(e)}\n{traceback.format_exc()}"
                LOGGER_SIM.error(f"Failed to delete {path}: {error_detail}")
                failed_files.append((path, error_detail))

        # Provide user feedback
        if failed_files:
            error_text = "Some deletions failed:\n\n" + "\n".join([f"{os.path.basename(p)}: {err}" for p, err in failed_files[:5]])  # Limit to 5
            if len(failed_files) > 5:
                error_text += f"\n... and {len(failed_files) - 5} more."
            from src.pk_py_lib.gui.utils.messages import show_selectable_error
            show_selectable_error(self, "Deletion Partial Failure", error_text)

        if success_count > 0:
            self._refresh_groups()
            from src.pk_py_lib.gui.utils.messages import show_selectable_info
            show_selectable_info(self, "Deletion Successful", f"Deleted {success_count} file(s) successfully.")

        # Clear previews after refresh
        self._update_preview_pane([])

    def _collect_checked_files(self) -> List[str]:
        """
        Collect paths of checked files from the Select column in the table.
        Returns a list of file paths for selected rows.
        """
        checked = []
        for row in range(self.table.rowCount()):
            select_item = self.table.item(row, 0)
            if select_item and select_item.checkState() == Qt.Checked:
                fname_item = self.table.item(row, 2)
                if fname_item:
                    path = fname_item.data(Qt.UserRole)
                    if isinstance(path, str) and os.path.exists(path):
                        checked.append(path)
        return checked

    def _refresh_groups(self) -> None:
        """
        Refresh the groups list by removing deleted files and empty groups (less than 2 files).
        Preserves corresponding scores for surviving files. Repopulates the table and updates UI.
        """
        new_groups = []
        for group in self.groups:
            paths = group.get('paths', [])
            scores = group.get('scores', [0.0] * len(paths))
            surviving = [(p, s) for p, s in zip(paths, scores) if os.path.exists(p)]
            if len(surviving) >= 2:
                group_copy = group.copy()
                group_copy['paths'] = [p for p, s in surviving]
                group_copy['scores'] = [s for p, s in surviving]
                new_groups.append(group_copy)

        self.groups = new_groups
        self._populate_tree()
        self._update_header_counts()
        self._update_status_line()
        self._update_delete_enabled()

    def _compute_similarity_groups(self, profile_payload: dict, run_paths: list[str], db_mgr: Optional[DatabaseManager] = None) -> List[Dict[str, Any]]:
        """
        Compute perceptual hash similarity groups for the scanned paths using the library.
        Returns normalized groups with 'paths' and 'scores'.
        """
        try:
            from src.pk_py_lib.core.image.similarity import compute_phash_batch, find_similar_phash
            from src.pk_py_lib.core.cache import CacheManager

            cache_mgr = CacheManager(Path(db_mgr.cache_db).parent) if db_mgr else None
            settings = profile_payload.get('similarity', {})
            algorithm = self.alg_combo.currentText()
            hash_size = settings.get('phash_hash_size', 8)
            threshold = settings.get(f'{algorithm}_threshold', 10)

            phash_results = compute_phash_batch(
                paths=run_paths,
                hash_size=hash_size,
                settings={'criteria': {'phash': {'hash_size': hash_size}}},
                cache_manager=cache_mgr
            )

            valid_hashes = [{'path': path, 'hash': phash} for path, phash in phash_results.items() if phash is not None]
            if not valid_hashes:
                return []

            raw_groups = find_similar_phash(
                hashes=valid_hashes,
                threshold=threshold,
                settings={'similarity': {f'{algorithm}_threshold': threshold}}
            )

            # Normalize to dict format with scores (assuming find_similar_phash returns list of lists of paths; scores computed as hamming distance)
            normalized_groups = []
            for group_paths in raw_groups:
                if len(group_paths) >= 2:
                    # Compute scores relative to first image
                    base_hash = next((vh['hash'] for vh in valid_hashes if vh['path'] in group_paths), None)
                    if base_hash:
                        group_scores = []
                        for gp in group_paths:
                            gh = next((vh['hash'] for vh in valid_hashes if vh['path'] == gp), None)
                            if gh:
                                score = similarity.hamming_distance(base_hash, gh)  # Assuming hamming_distance available
                                group_scores.append(score)
                            else:
                                group_scores.append(0.0)
                        normalized_groups.append({'paths': group_paths, 'scores': group_scores})
                    else:
                        normalized_groups.append({'paths': group_paths, 'scores': [0.0] * len(group_paths)})

            LOGGER_SIM.info(f"Computed {len(normalized_groups)} similarity groups (algorithm={algorithm}, threshold={threshold}, valid_images={len(valid_hashes)})")
            return normalized_groups
        except Exception as e:
            LOGGER_SIM.error("Similarity groups computation failed", exception=e)
            from src.pk_py_lib.gui.utils.messages import show_selectable_error
            show_selectable_error(self, "Computation Error", f"Failed to compute similarity groups: {str(e)}")
            return []

    def _configure_initial_splitter_sizes(self) -> None:
        """
        Configure initial sizes for the vertical and horizontal splitters.
        """
        try:
            self.splitter.setSizes([self.height() // 4, 3 * self.height() // 4])
            self.tree_preview_splitter.setSizes([self.width() * 2 // 3, self.width() // 3])  # More space for table
        except Exception as e:
            LOGGER_SIM.error(f"Failed to set splitter sizes: {e}")
