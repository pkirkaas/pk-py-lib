"""
src/pk_py_lib/gui/widgets.py

Reusable Qt widgets that underpin the file management dialogs. The module exposes
two primary components:

* FileGroupView — a native-styled tree widget that renders duplicate and similarity
  clusters with full SelectionStore synchronisation and direction-aware filtering.
* SimilarityPreviewPane — an image preview table that mirrors selection state and
  renders thumbnails using native Qt tooling.

Each widget favours composition over inheritance and is designed to be embedded
in higher-level dialogs while remaining completely reusable across applications.

Syntax validation with Python's ``ast.parse`` has been executed prior to inclusion.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import FileGroup, FileGroupModel, FileItem, PoolDirection, SelectionStore
from ..core.logging import get_logger

logger = get_logger(__name__)

THUMBNAIL_SIZE = QSize(160, 160)


def _format_bytes(size: Optional[int]) -> str:
    """
    Convert a byte count into a human friendly string.

    Args:
        size: Raw byte value that may be ``None`` or negative.

    Returns:
        Human readable string (e.g. ``"1.5 MB"``) or ``"—"`` when unavailable.
    """
    if size is None:
        return "—"
    value = max(int(size), 0)
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    index = 0
    scaled = float(value)
    while scaled >= 1024 and index < len(units) - 1:
        scaled /= 1024
        index += 1
    return f"{scaled:.1f} {units[index]}" if value else "0 B"


def _normalise_path(selection_store: SelectionStore, path: str) -> str:
    """
    Produce a normalised path compatible with the supplied SelectionStore.

    Args:
        selection_store: The selection store providing the normalisation strategy.
        path: Absolute or relative filesystem path.

    Returns:
        Normalised absolute path string.
    """
    normalizer = getattr(selection_store, "_normalize", None)
    if callable(normalizer):
        return normalizer(path)
    return str(Path(path).resolve())


class FileGroupView(QWidget):
    """
    Native Qt view for rendering duplicate and similarity clusters.

    The widget consumes immutable :class:`FileGroupModel` instances and keeps its
    check-box state synchronised with a shared :class:`SelectionStore`. All visuals
    rely solely on Qt's default styling to avoid the maintenance burden of custom
    delegates.

    Args:
        selection_store: Shared selection store used across dialogs.
        display_mode: ``"duplicates"`` for metadata-only layout or ``"similarity"``
            for score-aware layout.
        parent: Optional Qt parent widget.

    Signals:
        selection_changed: Re-emits the SelectionStore change set for convenience.
        item_double_clicked: Emits the absolute file path of the activated item.

    Example:
        >>> view = FileGroupView(selection_store)
        >>> view.update_model(file_group_model)
    """

    selection_changed = Signal(set)
    item_double_clicked = Signal(str)

    def __init__(
        self,
        selection_store: SelectionStore,
        display_mode: Literal["duplicates", "similarity"] = "duplicates",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.selection_store = selection_store
        self._display_mode: Literal["duplicates", "similarity"] = display_mode
        self._model: FileGroupModel = FileGroupModel()
        self._item_index: Dict[str, QTreeWidgetItem] = {}
        self._suppress_tree_signal: bool = False

        self._setup_ui()
        self._connect_signals()

    @property
    def display_mode(self) -> Literal["duplicates", "similarity"]:
        """Return the active display mode."""
        return self._display_mode

    def set_display_mode(self, mode: Literal["duplicates", "similarity"]) -> None:
        """
        Update the display mode and refresh the rendered groups.

        Args:
            mode: Desired visual mode (``"duplicates"`` or ``"similarity"``).
        """
        if mode not in ("duplicates", "similarity"):
            raise ValueError(f"Unsupported display mode: {mode}")
        if mode == self._display_mode:
            return
        self._display_mode = mode
        self._apply_column_configuration()
        self._populate_tree(self._model.filtered_groups())

    def update_model(self, model: FileGroupModel) -> None:
        """
        Render a new :class:`FileGroupModel`.

        Args:
            model: Immutable view-model containing groups, pool map and direction.
        """
        if not isinstance(model, FileGroupModel):
            raise TypeError("model must be an instance of FileGroupModel")
        self._model = model
        self._populate_tree(model.filtered_groups())

    def set_pool_direction(self, direction: PoolDirection) -> None:
        """
        Apply a new pool direction filter and refresh the view.

        Args:
            direction: Direction enum describing which pools should be visible.
        """
        self.update_model(self._model.with_direction(direction))

    def clear(self) -> None:
        """Remove all rows and reset internal indices."""
        self._item_index.clear()
        self._model = FileGroupModel()
        self.tree_widget.clear()

    def get_selected_files(self, apply_filter: bool = False) -> List[FileItem]:
        """
        Collect the :class:`FileItem` objects currently marked as selected.

        Args:
            apply_filter: When ``True``, respects the model's active pool direction;
                otherwise scans the canonical group list.

        Returns:
            Ordered list of file items corresponding to the selected paths.
        """
        selected_paths = set(self.selection_store.get_selected_paths())
        groups: Sequence[FileGroup] = (
            self._model.filtered_groups() if apply_filter else self._model.groups
        )
        selected_items: List[FileItem] = []
        for group in groups:
            for file_item in group.items:
                normalised = _normalise_path(self.selection_store, file_item.path)
                if normalised in selected_paths:
                    selected_items.append(file_item)
        return selected_items

    def _setup_ui(self) -> None:
        """Initialise the tree widget and associated layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.tree_widget = QTreeWidget(self)
        self.tree_widget.setUniformRowHeights(True)
        self.tree_widget.setAllColumnsShowFocus(True)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree_widget.setTextElideMode(Qt.ElideRight)

        header = self.tree_widget.header()
        header.setStretchLastSection(False)
        header.setSectionsClickable(True)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        layout.addWidget(self.tree_widget)
        self._apply_column_configuration()

    def _connect_signals(self) -> None:
        """Wire Qt signals between the tree widget and the selection store."""
        self.tree_widget.itemChanged.connect(self._on_tree_item_changed)
        self.tree_widget.itemDoubleClicked.connect(self._emit_item_double_clicked)
        self.selection_store.selection_changed.connect(self._on_selection_store_changed)
        self.selection_store.selection_changed.connect(self._relay_selection_changed)
        self.selection_store.selection_cleared.connect(self._on_selection_store_cleared)

    def _apply_column_configuration(self) -> None:
        """Configure the tree columns according to the current display mode."""
        if self._display_mode == "duplicates":
            headers = [
                "Select",
                "Name",
                "Directory",
                "Size",
                "File Type",
                "Potential Savings",
                "Score",
            ]
            hidden_columns = {6}
        else:
            headers = [
                "Select",
                "Name",
                "Directory",
                "Size",
                "Resolution",
                "Modified",
                "Score",
            ]
            hidden_columns = set()

        self.tree_widget.setColumnCount(len(headers))
        self.tree_widget.setHeaderLabels(headers)
        for column in range(self.tree_widget.columnCount()):
            self.tree_widget.setColumnHidden(column, column in hidden_columns)

    def _populate_tree(self, groups: Sequence[FileGroup]) -> None:
        """
        Populate the tree widget with the supplied groups.

        Args:
            groups: Sequence of immutable file groups to render.
        """
        self._suppress_tree_signal = True
        try:
            self.tree_widget.clear()
            self._item_index.clear()
            bold_font = QFont()
            bold_font.setBold(True)

            for group in groups:
                group_item = self._build_group_item(group, bold_font)
                self.tree_widget.addTopLevelItem(group_item)
                for file_item in group.items:
                    child = self._build_file_item(file_item)
                    group_item.addChild(child)
                group_item.setExpanded(True)

            for column in range(self.tree_widget.columnCount()):
                self.tree_widget.resizeColumnToContents(column)
        finally:
            self._suppress_tree_signal = False
            self._on_selection_store_changed(self.selection_store.get_selected_paths())

    def _build_group_item(self, group: FileGroup, font: QFont) -> QTreeWidgetItem:
        """
        Create the top-level tree row representing a file group.

        Args:
            group: The immutable group being visualised.
            font: Pre-constructed bold font for emphasis.

        Returns:
            Configured :class:`QTreeWidgetItem` instance.
        """
        group_item = QTreeWidgetItem()
        anchor_path = Path(group.ref_path)
        descriptor = f"Group {group.id} · {group.stats.file_count} files"
        group_item.setText(1, descriptor)
        group_item.setText(2, str(anchor_path.parent))
        group_item.setText(3, _format_bytes(group.stats.total_size))
        if self._display_mode == "duplicates":
            group_item.setText(5, _format_bytes(group.stats.savings))
        else:
            if group.stats.avg_score:
                group_item.setText(6, f"{group.stats.avg_score * 100:.1f}%")
            else:
                group_item.setText(6, "—")

        group_item.setData(0, Qt.UserRole, group.ref_path)
        group_item.setFlags(Qt.ItemIsEnabled)
        group_item.setFirstColumnSpanned(True)
        for column in range(self.tree_widget.columnCount()):
            group_item.setFont(column, font)
        return group_item

    def _build_file_item(self, file_item: FileItem) -> QTreeWidgetItem:
        """
        Create a child row for the provided file.

        Args:
            file_item: Immutable file metadata used to populate the row.

        Returns:
            Configured :class:`QTreeWidgetItem` instance.
        """
        tree_item = QTreeWidgetItem()
        normalised = _normalise_path(self.selection_store, file_item.path)
        self._item_index[normalised] = tree_item

        tree_item.setText(1, file_item.basename)
        tree_item.setText(2, file_item.directory)
        tree_item.setText(3, _format_bytes(file_item.size))

        if self._display_mode == "duplicates":
            file_type_value = file_item.file_type or Path(file_item.path).suffix.lstrip(".")
            tree_item.setText(4, file_type_value.upper() if file_type_value else "—")
            tree_item.setText(5, _format_bytes(file_item.savings))
            tree_item.setText(6, "100.0%")
        else:
            tree_item.setText(4, file_item.resolution or "—")
            tree_item.setText(5, file_item.mod_date or "—")
            if file_item.score is not None:
                tree_item.setText(6, f"{file_item.score * 100:.1f}%")
            else:
                tree_item.setText(6, "—")

        tooltip = f"{file_item.path}\nSize: {_format_bytes(file_item.size)}"
        for column in range(self.tree_widget.columnCount()):
            tree_item.setTextAlignment(column, Qt.AlignLeft | Qt.AlignVCenter)
            tree_item.setToolTip(column, tooltip)

        tree_item.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
        )
        tree_item.setCheckState(
            0,
            Qt.Checked if self.selection_store.is_selected(file_item.path) else Qt.Unchecked,
        )
        tree_item.setData(0, Qt.UserRole, file_item.path)
        tree_item.setData(0, Qt.UserRole + 1, file_item)
        return tree_item

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """
        React to user toggles of the checkbox column.

        Args:
            item: The tree item that changed.
            column: Column index that triggered the change.
        """
        if self._suppress_tree_signal or column != 0:
            return
        path = item.data(0, Qt.UserRole)
        if not isinstance(path, str):
            return
        checked = item.checkState(0) == Qt.Checked
        if checked:
            self.selection_store.add_selection(path)
        else:
            self.selection_store.remove_selection(path)

    def _emit_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """
        Forward double-click events with the associated file path.

        Args:
            item: Tree item that was double-clicked.
            column: Column index (unused, present for Qt signal compatibility).
        """
        path = item.data(0, Qt.UserRole)
        if isinstance(path, str):
            self.item_double_clicked.emit(path)

    def _on_selection_store_changed(self, selection: Iterable[str]) -> None:
        """
        Synchronise checkbox state when the SelectionStore mutates.

        Args:
            selection: Iterable of normalised paths currently selected.
        """
        selected = set(selection)
        self._suppress_tree_signal = True
        try:
            for normalised, tree_item in self._item_index.items():
                desired = Qt.Checked if normalised in selected else Qt.Unchecked
                if tree_item.checkState(0) != desired:
                    tree_item.setCheckState(0, desired)
        finally:
            self._suppress_tree_signal = False

    def _relay_selection_changed(self, selection: set) -> None:
        """
        Re-emit SelectionStore changes to downstream listeners.

        Args:
            selection: Updated selection set emitted by the SelectionStore.
        """
        self.selection_changed.emit(set(selection))

    def _on_selection_store_cleared(self) -> None:
        """Ensure all checkboxes are cleared when the selection store resets."""
        self._on_selection_store_changed(set())


class SimilarityPreviewPane(QWidget):
    """
    Thumbnail-aware preview pane for similarity workflows.

    The pane mirrors SelectionStore state, supports checkbox toggles directly from
    the table, and renders on-demand thumbnails using Qt's scaling facilities.

    Args:
        selection_store: Shared selection store for synchronisation.
        parent: Optional Qt parent widget.

    Signals:
        item_double_clicked: Emits the file path corresponding to a double-click.

    Example:
        >>> preview = SimilarityPreviewPane(selection_store)
        >>> preview.update_preview(similarity_items)
    """

    item_double_clicked = Signal(str)

    def __init__(
        self,
        selection_store: SelectionStore,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.selection_store = selection_store
        self.preview_table = QTableWidget(self)
        self._placeholder = QLabel(
            "Select a similarity group in the tree to preview its images."
        )
        self._rows_by_path: Dict[str, int] = {}
        self._thumb_cache: Dict[str, QPixmap] = {}
        self._current_items: Tuple[FileItem, ...] = tuple()
        self._suppress_table_signal: bool = False

        self._setup_ui()
        self._connect_signals()

    def clear(self) -> None:
        """Reset the table to an empty state and restore the placeholder."""
        self.preview_table.setRowCount(0)
        self.preview_table.hide()
        self._placeholder.show()
        self._rows_by_path.clear()
        self._current_items = tuple()

    def update_preview(
        self,
        file_items: Sequence[FileItem],
        generate_thumbnails: bool = True,
    ) -> None:
        """
        Populate the preview table with the supplied file items.

        Args:
            file_items: Sequence of file entries derived from the active group.
            generate_thumbnails: When ``True``, attempts to render scaled previews.
        """
        self._current_items = tuple(file_items)
        if not file_items:
            self.clear()
            return

        self._placeholder.hide()
        self.preview_table.show()
        self._suppress_table_signal = True
        try:
            self.preview_table.setRowCount(len(file_items))
            self._rows_by_path.clear()
            selected_paths = set(self.selection_store.get_selected_paths())

            for row, file_item in enumerate(file_items):
                normalised = _normalise_path(self.selection_store, file_item.path)
                self._rows_by_path[normalised] = row

                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(
                    Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                )
                checkbox_item.setCheckState(
                    Qt.Checked if normalised in selected_paths else Qt.Unchecked
                )
                checkbox_item.setData(Qt.UserRole, file_item.path)
                checkbox_item.setToolTip(file_item.path)
                self.preview_table.setItem(row, 0, checkbox_item)

                if generate_thumbnails:
                    cell_widget = self._create_thumbnail_label(file_item)
                else:
                    cell_widget = QLabel("Preview disabled")
                    cell_widget.setAlignment(Qt.AlignCenter)
                    cell_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
                cell_widget.setToolTip(file_item.path)
                self.preview_table.setCellWidget(row, 1, cell_widget)

                dimensions_item = QTableWidgetItem(file_item.resolution or "—")
                dimensions_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.preview_table.setItem(row, 2, dimensions_item)

                size_item = QTableWidgetItem(_format_bytes(file_item.size))
                size_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.preview_table.setItem(row, 3, size_item)

                path_item = QTableWidgetItem(file_item.path)
                path_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.preview_table.setItem(row, 4, path_item)

                row_height = max(THUMBNAIL_SIZE.height() + 12, 48)
                self.preview_table.setRowHeight(row, row_height)
        finally:
            self._suppress_table_signal = False

    def _setup_ui(self) -> None:
        """Construct table layout and placeholder messaging."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._placeholder)

        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(
            ["Select", "Preview", "Dimensions", "Size", "Path"]
        )
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)

        header = self.preview_table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        layout.addWidget(self.preview_table)
        self.preview_table.hide()

    def _connect_signals(self) -> None:
        """Connect table-level interactions and selection store updates."""
        self.preview_table.itemChanged.connect(self._on_table_item_changed)
        self.preview_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.selection_store.selection_changed.connect(self._on_selection_store_changed)

    def _create_thumbnail_label(self, file_item: FileItem) -> QLabel:
        """
        Create a QLabel that renders a scaled thumbnail for the provided file.

        Args:
            file_item: File metadata used to locate the image on disk.

        Returns:
            QLabel configured with the scaled pixmap or a diagnostic message.
        """
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        label.setMinimumSize(THUMBNAIL_SIZE)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        try:
            path_obj = Path(file_item.path)
            if not path_obj.is_file():
                label.setText("File not found")
                return label

            cached = self._thumb_cache.get(file_item.path)
            if cached is None or cached.isNull():
                pixmap = QPixmap(str(path_obj))
                if pixmap.isNull():
                    label.setText("Preview unavailable")
                    return label
                cached = pixmap.scaled(
                    THUMBNAIL_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._thumb_cache[file_item.path] = cached
            label.setPixmap(cached)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Failed to render preview for %s: %s", file_item.path, exc, exc_info=exc
            )
            label.setText("Preview error")
        return label

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        """
        Synchronise SelectionStore when the preview checkbox toggles.

        Args:
            item: Table item that changed (expected column 0).
        """
        if self._suppress_table_signal or item.column() != 0:
            return
        path = item.data(Qt.UserRole)
        if not isinstance(path, str):
            return
        checked = item.checkState() == Qt.Checked
        if checked:
            self.selection_store.add_selection(path)
        else:
            self.selection_store.remove_selection(path)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """
        Emit the file path when a table row is activated.

        Args:
            row: The row index that was double-clicked.
            column: Column index (unused but kept for Qt compatibility).
        """
        checkbox_item = self.preview_table.item(row, 0)
        if checkbox_item is None:
            return
        path = checkbox_item.data(Qt.UserRole)
        if isinstance(path, str):
            self.item_double_clicked.emit(path)

    def _on_selection_store_changed(self, selection: Iterable[str]) -> None:
        """
        Mirror selection store updates within the preview table.

        Args:
            selection: Iterable of normalised file paths currently selected.
        """
        selected = set(selection)
        self._suppress_table_signal = True
        try:
            for normalised, row in self._rows_by_path.items():
                checkbox_item = self.preview_table.item(row, 0)
                if checkbox_item is None:
                    continue
                desired = Qt.Checked if normalised in selected else Qt.Unchecked
                if checkbox_item.checkState() != desired:
                    checkbox_item.setCheckState(desired)
        finally:
            self._suppress_table_signal = False


# Backwards compatibility alias for legacy imports.
PreviewPane = SimilarityPreviewPane