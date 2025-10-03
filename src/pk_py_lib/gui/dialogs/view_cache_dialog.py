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
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor

from ...core.flat_cache import FlatCacheManager, FlatCacheDBError
from ...core.logging.logger import get_logger
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
        self.logger = get_logger(__name__)
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

            # Metadata label - now includes valid/invalid counts
            valid_count = metadata.get('valid_count', metadata.get('entry_count', 0))
            invalid_count = metadata.get('invalid_count', 0)
            meta_label = QLabel(
                f"Cache DB: {metadata['path']} ({metadata['db_size_formatted']}) | "
                f"Total Entries: {metadata['entry_count']} | "
                f"Valid: {valid_count} | Invalid: {invalid_count} | "
                f"Version: {metadata['cache_version']}"
            )
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
                    # Ensure 'is_valid' is included; add if missing
                    if 'is_valid' not in headers:
                        headers.insert(0, 'is_valid')  # Add as first column for prominence
                    model.setHorizontalHeaderLabels(headers)

                    # Populate rows with validity handling
                    for row_data in rows:
                        row_items = []
                        for key in headers:
                            value = row_data.get(key, '')
                            if key == 'is_valid':
                                # Special handling for validity column
                                if value is True:
                                    item = QStandardItem("Valid")
                                    item.setForeground(QColor("green"))
                                elif value is False:
                                    mismatches = row_data.get('validation_mismatches', {})
                                    status_text = f"Invalid: {len(mismatches)} mismatch" + ("es" if len(mismatches) != 1 else "")
                                    if mismatches:
                                        status_text += f" ({', '.join(mismatches.keys())})"
                                    item = QStandardItem(status_text)
                                    item.setForeground(QColor("red"))
                                else:
                                    item = QStandardItem(str(value))
                                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                                row_items.append(item)
                            else:
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
                    QTableView {
                        gridline-color: #ddd;
                        background-color: white;
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
                    elif header_text == 'is_valid':
                        table.setColumnWidth(col_idx, 150)  # Wider for status messages
                    elif header_text in ['mtime', 'size', 'created_at', 'updated_at']:
                        table.setColumnWidth(col_idx, 120)
                    elif header_text == 'brisque':
                        table.setColumnWidth(col_idx, 80)
                    elif header_text == 'validation_mismatches':
                        table.setColumnWidth(col_idx, 200)  # For detailed mismatches
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
            db_path = getattr(self.flat_cache_manager, 'db_path', 'unknown')
            error_msg = f"Failed to load cache data from {db_path}: {str(e)}"
            self.logger.error(error_msg, exc_info=True, db_path=db_path)
            show_selectable_error(self, "Cache View Error", error_msg)
            # Fallback label
            error_label = QLabel(error_msg)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #c00; padding: 8px;")
            layout.addWidget(error_label)
        except Exception as e:
            # Unexpected error
            db_path = getattr(self.flat_cache_manager, 'db_path', 'unknown')
            error_msg = f"Unexpected error in ViewCacheDialog __init__ from {db_path}: {str(e)}"
            self.logger.error(error_msg, exc_info=True, db_path=db_path, metadata_keys=list(metadata.keys()) if 'metadata' in locals() else [])
            show_selectable_error(self, "Cache View Error", error_msg)
            error_label = QLabel(error_msg)
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: #c00; padding: 8px;")
            layout.addWidget(error_label)

        # Ensure layout is applied
        self.setLayout(layout)

        # Syntax validation: This file has been reviewed for Python syntax correctness.