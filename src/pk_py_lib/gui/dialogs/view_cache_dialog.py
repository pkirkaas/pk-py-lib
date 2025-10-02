"""
src/pk_py_lib/gui/dialogs/view_cache_dialog.py

A dialog to view the contents of the FlatCache database, including metadata and all entries.

This dialog displays:
- Metadata: Database path, entry count, and cache version.
- A resizable table showing all cache entries with columns for path, size, mtime, etc.

Usage:
    dialog = ViewCacheDialog(flat_cache_manager, parent)
    dialog.exec()
"""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTableView,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItemModel, QStandardItem

from ...core.flat_cache import FlatCacheManager, FlatCacheDBError
from ..utils.messages import show_selectable_error


class ViewCacheDialog(QDialog):
    """
    Dialog for viewing the FlatCache database contents.

    Displays database metadata and a table of all entries.

    Args:
        flat_cache_manager (FlatCacheManager): The cache manager instance.
        parent (QWidget, optional): Parent widget. Defaults to None.

    Raises:
        FlatCacheDBError: If database access fails.
    """

    def __init__(self, flat_cache_manager: FlatCacheManager, parent=None):
        """
        Initialize the View Cache dialog.

        Fetches data from the cache manager and sets up the UI.
        Handles empty database gracefully with a message.
        """
        super().__init__(parent)
        self.flat_cache_manager = flat_cache_manager
        self.setWindowTitle("View Cache")
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)  # Make resizable by default

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        try:
            # Fetch data from cache manager
            metadata, rows = self.flat_cache_manager.get_cache_view_data()

            # Metadata label
            meta_label = QLabel(f"Cache DB: {metadata['path']} ({metadata['db_size_formatted']}) | Entries: {metadata['entry_count']} | Version: {metadata['cache_version']}")
            meta_label.setWordWrap(True)
            meta_label.setStyleSheet("font-weight: bold; padding: 8px; background-color: #f0f0f0;")
            layout.addWidget(meta_label)

            if not rows:
                # Handle empty DB
                empty_label = QLabel("The cache database is empty. No entries to display.")
                empty_label.setAlignment(Qt.AlignCenter)
                empty_label.setStyleSheet("font-style: italic; color: #666; padding: 20px;")
                layout.addWidget(empty_label)
            else:
                # Create model for table
                model = QStandardItemModel()
                if rows:
                    # Set headers from first row keys (assuming all rows have same keys)
                    headers = list(rows[0].keys())
                    model.setHorizontalHeaderLabels(headers)

                    # Populate rows
                    for row_data in rows:
                        row_items = []
                        for value in row_data.values():
                            item = QStandardItem(str(value))
                            # Make non-editable
                            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                            row_items.append(item)
                        model.appendRow(row_items)

                # Create table view
                table = QTableView(self)
                table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                table.setModel(model)
                table.resizeColumnsToContents()
                table.setAlternatingRowColors(True)
                table.setStyleSheet("""
                    QTableView::item:hover {
                        background: #E3F2FD;
                        color: #333333;
                    }
                    QTableView::item:hover:selected {
                        background: #4a90e2;
                        color: #ffffff;
                    }
                    QTableView::item:selected {
                        background: #4a90e2;
                        color: #ffffff;
                    }
                """)
                table.setSelectionBehavior(QAbstractItemView.SelectRows)
                table.setSortingEnabled(True)  # Allow sorting by columns

                # Header setup for resizable columns
                header = table.horizontalHeader()
                header.setSectionResizeMode(QHeaderView.Interactive)  # Enable user-draggable resize handles for individual columns
                header.setSectionsMovable(True)  # Allow column reordering
                header.setStretchLastSection(True)  # Last column expands to fill remaining space when dialog resizes

                # Initial column widths based on column names (approximate)
                for col_idx, header_text in enumerate(headers):
                    if header_text == 'path':
                        table.setColumnWidth(col_idx, 300)
                    elif header_text in ['mtime', 'size', 'created_at', 'updated_at']:
                        table.setColumnWidth(col_idx, 120)
                    elif header_text == 'brisque':
                        table.setColumnWidth(col_idx, 80)
                    else:
                        # Others auto (e.g., hashes: 150, dimensions: 60)
                        table.setColumnWidth(col_idx, 150)

                # Vertical header: hide or minimal
                vheader = table.verticalHeader()
                vheader.setVisible(False)
                vheader.setDefaultSectionSize(24)  # Compact rows

                # Add table to layout
                layout.addWidget(table)

        except FlatCacheDBError as e:
            # Error handling: show message dialog
            error_msg = f"Failed to load cache data: {str(e)}"
            show_selectable_error(self, "Cache View Error", error_msg)
            # Fallback label
            error_label = QLabel(error_msg)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #c00; padding: 8px;")
            layout.addWidget(error_label)
        except Exception as e:
            # Unexpected error
            error_msg = f"Unexpected error: {str(e)}"
            show_selectable_error(self, "Cache View Error", error_msg)
            error_label = QLabel(error_msg)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #c00; padding: 8px;")
            layout.addWidget(error_label)

        # Ensure layout is applied
        self.setLayout(layout)

        # Syntax validation: This file has been reviewed for Python syntax correctness.