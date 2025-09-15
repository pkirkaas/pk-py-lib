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

from PySide6.QtCore import Qt, QTimer, QRect, QSize
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
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
        bottom_layout.addLayout(controls_layout)

        self.tree_preview_splitter = QSplitter(Qt.Horizontal, self)
        
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Select", "Preview", "Path", "Score"])
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 70)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.setItemDelegate(GroupFrameDelegate(self.tree))
        self.tree_preview_splitter.addWidget(self.tree)

        self.preview_area = QScrollArea(self)
        self.preview_area.setWidgetResizable(True)
        self.preview_pane = ImageGrid(self)
        self.preview_area.setWidget(self.preview_pane)
        self.tree_preview_splitter.addWidget(self.preview_area)
        
        bottom_layout.addWidget(self.tree_preview_splitter)

        self.status_label = QLabel("No similar images to manage", self)
        bottom_layout.addWidget(self.status_label)

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
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
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
        self.tree.clear()
        if not self.groups:
            self.header_label.setText("No similar images found")
            return

        for i, group in enumerate(self.groups, 1):
            paths = group.get('paths', [])
            scores = group.get('scores', [])
            if len(paths) < 2: continue

            avg_score = sum(scores) / len(scores) if scores else 0.0
            top = QTreeWidgetItem(self.tree)
            top.setText(2, f"Group #{i}: {len(paths)} images (avg score: {avg_score:.2f})")
            top.setFlags(top.flags() & ~Qt.ItemIsUserCheckable)
            font = top.font(2)
            font.setBold(True)
            top.setFont(2, font)

            for j, path in enumerate(paths):
                child = QTreeWidgetItem(top)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                
                try:
                    pixmap = QPixmap(path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    child.setIcon(1, QIcon(pixmap))
                except Exception as e:
                    LOGGER_SIM.warning(f"Could not load thumbnail for {path}: {e}")

                child.setText(2, path)
                child.setData(2, Qt.UserRole, path)
                score = scores[j] if j < len(scores) else 0.0
                child.setText(3, f"{score:.2f}")

            self.tree.expandItem(top)
        self._update_header_counts()

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        # This signal is for checkbox changes
        if column == 0:
            self._update_delete_enabled()
            self._update_status_line()

    def _on_selection_changed(self) -> None:
        # This signal is for row selection changes
        selected_items = self.tree.selectedItems()
        paths = []
        for item in selected_items:
            # If a group header is selected, show all its children
            if item.childCount() > 0:
                for i in range(item.childCount()):
                    child_path = item.child(i).data(2, Qt.UserRole)
                    if child_path:
                        paths.append(child_path)
            else: # A file item is selected
                path = item.data(2, Qt.UserRole)
                if path:
                    paths.append(path)
        self._update_preview_pane(list(set(paths))) # Use set to remove duplicates

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
        checked_count = 0
        total_files = 0
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            total_files += group.childCount()
            for j in range(group.childCount()):
                if group.child(j).checkState(0) == Qt.Checked:
                    checked_count += 1
        self.status_label.setText(f"{checked_count} of {total_files} files selected for deletion.")

    def _update_header_counts(self) -> None:
        groups = self.tree.topLevelItemCount()
        files = sum(self.tree.topLevelItem(i).childCount() for i in range(groups))
        self.header_label.setText(f"Similarity Groups: {groups} — Files: {files}")

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

        # Re-compute and format groups
        similarity_groups = self._compute_similarity_groups(profile_payload, self.run_paths, self.db_manager)
        self.groups = self._format_similarity_groups(similarity_groups, self.db_manager)
        
        # Repopulate the tree and update UI
        self._populate_tree()
        self._update_status_line()

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

        # Re-compute and format groups
        similarity_groups = self._compute_similarity_groups(profile_payload, self.run_paths, self.db_manager)
        self.groups = self._normalize_groups_input(similarity_groups)
        
        # Repopulate the tree and update UI
        self._populate_tree()
        self._update_status_line()

    def _on_delete_clicked(self) -> None:
        # Placeholder for delete logic
        show_selectable_info(self, "Delete", "Delete functionality is not yet implemented.")

    def _configure_initial_splitter_sizes(self) -> None:
        try:
            self.splitter.setSizes([self.height() // 4, 3 * self.height() // 4])
            self.tree_preview_splitter.setSizes([self.width() // 2, self.width() // 2])
        except Exception as e:
            LOGGER_SIM.error(f"Failed to set splitter sizes: {e}")

    def _is_separator_item(self, item: QTreeWidgetItem) -> bool:
        return item.data(0, Qt.UserRole) == "__separator__"

    def _compute_similarity_groups(self, profile_payload: dict, run_paths: list[str], db_mgr) -> list[list[str]]:
        """
        Compute perceptual hash similarity groups for the scanned paths.
        """
        try:
            from src.pk_py_lib.core.image.similarity import compute_phash_batch, find_similar_phash
            from src.pk_py_lib.core.cache import CacheManager

            cache_mgr = CacheManager(Path(db_mgr.cache_db).parent) if db_mgr else None
            settings = profile_payload.get('similarity', {})
            hash_size = settings.get('phash_hash_size', 8)
            threshold = settings.get(f'{self.alg_combo.currentText()}_threshold', 10)

            phash_results = compute_phash_batch(
                paths=run_paths,
                hash_size=hash_size,
                settings={'criteria': {'phash': {'hash_size': hash_size}}},
                cache_manager=cache_mgr
            )

            valid_hashes = [{'path': path, 'hash': phash} for path, phash in phash_results.items() if phash is not None]
            if not valid_hashes:
                return []

            groups = find_similar_phash(
                hashes=valid_hashes,
                threshold=threshold,
                settings={'similarity': {f'{self.alg_combo.currentText()}_threshold': threshold}}
            )

            LOGGER.info(f"Computed {len(groups)} similarity groups (threshold={threshold}, valid_images={len(valid_hashes)})")
            return groups
        except Exception as e:
            LOGGER.error("Similarity groups computation failed", exception=e)
            return []

    def _configure_initial_splitter_sizes(self) -> None:
        try:
            self.splitter.setSizes([self.height() // 4, 3 * self.height() // 4])
            self.tree_preview_splitter.setSizes([self.width() // 2, self.width() // 2])
        except Exception as e:
            LOGGER_SIM.error(f"Failed to set splitter sizes: {e}")

    def _is_separator_item(self, item: QTreeWidgetItem) -> bool:
        return item.data(0, Qt.UserRole) == "__separator__"

    def _compute_similarity_groups(self, profile_payload: dict, run_paths: list[str], db_mgr) -> list[list[str]]:
        """
        Compute perceptual hash similarity groups for the scanned paths.
        """
        try:
            from src.pk_py_lib.core.image.similarity import compute_phash_batch, find_similar_phash
            from src.pk_py_lib.core.cache import CacheManager

            cache_mgr = CacheManager(Path(db_mgr.cache_db).parent) if db_mgr else None
            settings = profile_payload.get('similarity', {})
            hash_size = settings.get('phash_hash_size', 8)
            threshold = settings.get(f'{self.alg_combo.currentText()}_threshold', 10)

            phash_results = compute_phash_batch(
                paths=run_paths,
                hash_size=hash_size,
                settings={'criteria': {'phash': {'hash_size': hash_size}}},
                cache_manager=cache_mgr
            )

            valid_hashes = [{'path': path, 'hash': phash} for path, phash in phash_results.items() if phash is not None]
            if not valid_hashes:
                return []

            groups = find_similar_phash(
                hashes=valid_hashes,
                threshold=threshold,
                settings={'similarity': {f'{self.alg_combo.currentText()}_threshold': threshold}}
            )

            LOGGER.info(f"Computed {len(groups)} similarity groups (threshold={threshold}, valid_images={len(valid_hashes)})")
            return groups
        except Exception as e:
            LOGGER.error("Similarity groups computation failed", exception=e)
            return []

    def _format_similarity_groups(self, groups: list[list[str]], db_mgr) -> list[dict]:
        """
        Format similarity path groups into the standard groups_data structure for dialogs.
        """
        if not groups or not db_mgr:
            return []

        try:
            with db_mgr.get_connection(db_mgr.cache_db) as conn:
                all_paths = [path for group in groups for path in group]
                
                formatted_groups = []
                for idx, group_paths in enumerate(groups, 1):
                    if len(group_paths) < 2:
                        continue

                    placeholders = ",".join("?" for _ in group_paths)
                    sql = f"""
                        SELECT file_path, file_size, file_modified, pool
                        FROM image_metadata
                        WHERE file_path IN ({placeholders})
                        ORDER BY file_path
                    """
                    rows = conn.execute(sql, group_paths).fetchall()

                    files = []
                    for row in rows:
                        files.append({
                            "path": str(row["file_path"]),
                            "size": int(row["file_size"] or 0),
                            "modified": int(row["file_modified"] or 0),
                            "pool": str(row["pool"] or "A")
                        })

                    if len(files) >= 2:
                        formatted_groups.append({
                            "hash": f"perceptual_group_{idx}",
                            "count": len(files),
                            "files": files
                        })

            LOGGER.debug(f"Formatted {len(formatted_groups)} similarity groups from {len(groups)} raw groups")
            return formatted_groups
        except Exception as e:
            LOGGER.error("Formatting similarity groups failed", exception=e)
            return []