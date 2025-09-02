"""
File Selector Widgets (PySide6)

Implements:
- PathSelectorDialog: modal dialog with filesystem tree and flexible filtering
- MultiPathSelectorWidget: list-based multi-path selector using the dialog, with validation against core filesystem utilities

Syntax validation performed via ast before delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Literal, Optional, Sequence, Set, Tuple, Union, Dict

# PySide6 imports with defensive fallback error raising for environments without GUI
try:
    from PySide6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QDir, QSize, QByteArray, QBuffer, QIODevice, QRect
    from PySide6.QtGui import QStandardItemModel, QStandardItem, QIcon, QPixmap, QPalette, QPainter, QColor, QPen
    from PySide6.QtWidgets import (
        QDialog,
        QFileSystemModel,
        QTreeView,
        QHeaderView,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QDialogButtonBox,
        QWidget,
        QListWidget,
        QListWidgetItem,
        QLineEdit,
        QComboBox,
        QMessageBox,
        QSpacerItem,
        QSizePolicy,
        QCheckBox,
        QFrame,
        QApplication,
        QSplitter,
        QToolButton,
        QStyle,
    )
    from PySide6.QtCore import QEvent, QPoint
    PYSIDE_AVAILABLE = True
except Exception as e:  # pragma: no cover - headless environments
    PYSIDE_AVAILABLE = False
    # Provide lightweight stubs that raise clear errors if used without PySide6
    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required to use GUI widgets")

    Qt = QSortFilterProxyModel = QModelIndex = QDir = (
        QStandardItemModel
    ) = QStandardItem = QDialog = QFileSystemModel = QTreeView = QVBoxLayout = QHBoxLayout = QLabel = QPushButton = QDialogButtonBox = QWidget = QListWidget = QListWidgetItem = QLineEdit = QComboBox = QMessageBox = QSpacerItem = QSizePolicy = QCheckBox = QFrame = QApplication = QSplitter = QToolButton = _Missing()


# Core filesystem utilities used for validation
from src.pk_py_lib.core.filesystem.paths import PathOperations

# GUI error handling
from ..utils.messages import handle_gui_error


# ----------------------------- Filter Model ---------------------------------


NamedCategory = Literal["images", "image", "audio", "video", "documents", "archives", "code", "all", "any"]


def category_extensions(category: NamedCategory) -> Set[str]:
    """
    Resolve named category to a set of file extensions (all lowercase, with leading dot).
    """
    mapping: Dict[str, Set[str]] = {
        "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif"},
        "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif"},
        "audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
        "video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
        "documents": {".txt", ".md", ".rtf", ".pdf", ".doc", ".docx"},
        "archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
        "code": {".py", ".js", ".ts", ".cpp", ".h", ".hpp", ".java", ".cs", ".go", ".rs"},
        "all": set(),
        "any": set(),
    }
    return mapping.get(str(category).lower(), set())


@dataclass
class PathFilterSpec:
    """
    Declarative filter specification for file selection.

    Attributes:
        whitelist_ext: show only files with these extensions (e.g., {".jpg",".png"})
        blacklist_ext: exclude files with these extensions
        include_categories: named categories to include (combined with whitelist)
        exclude_categories: named categories to exclude (combined with blacklist)
        allow_dirs: whether directories are selectable/visible
        allow_files: whether files are selectable/visible
        include_hidden: whether to include hidden files and directories

    Notes:
        - Extensions are normalized to lowercase with a leading dot.
        - If both whitelist and categories are empty, all files are eligible unless blacklisted.
        - Directories are filtered only by allow_dirs/include_hidden; extension rules apply to files.
    """
    whitelist_ext: Set[str] = field(default_factory=set)
    blacklist_ext: Set[str] = field(default_factory=set)
    include_categories: Set[NamedCategory] = field(default_factory=set)
    exclude_categories: Set[NamedCategory] = field(default_factory=set)
    allow_dirs: bool = True
    allow_files: bool = True
    include_hidden: bool = False

    def normalized(self) -> "PathFilterSpec":
        """Return a copy with normalized extension formats and merged categories."""
        def norm_ext_set(exts: Iterable[str]) -> Set[str]:
            out: Set[str] = set()
            for e in exts:
                if not e:
                    continue
                e = e.strip().lower()
                if not e:
                    continue
                if not e.startswith("."):
                    e = "." + e
                out.add(e)
            return out

        wl = set(self.whitelist_ext)
        bl = set(self.blacklist_ext)
        # merge category extension sets
        for c in self.include_categories:
            wl.update(category_extensions(c))
        for c in self.exclude_categories:
            bl.update(category_extensions(c))
        spec = PathFilterSpec(
            whitelist_ext=norm_ext_set(wl),
            blacklist_ext=norm_ext_set(bl),
            include_categories=set(self.include_categories),
            exclude_categories=set(self.exclude_categories),
            allow_dirs=self.allow_dirs,
            allow_files=self.allow_files,
            include_hidden=self.include_hidden,
        )
        return spec

    def allows_file_extension(self, ext: str) -> bool:
        """Return True if a file extension is allowed by the filter."""
        ext = (ext or "").lower()
        if ext and not ext.startswith("."):
            ext = "." + ext
        # blacklist always excludes
        if ext in self.blacklist_ext:
            return False
        # if whitelist is empty, all (except blacklisted) are allowed
        if not self.whitelist_ext:
            return True
        return ext in self.whitelist_ext


class FileSystemFilterProxy(QSortFilterProxyModel):
    """
    Proxy filter over a QFileSystemModel applying PathFilterSpec rules.

    The source model must be a QFileSystemModel. This proxy will:
    - Filter hidden files/dirs if include_hidden is False
    - Filter out files based on whitelist/blacklist/category-derived extensions
    - Optionally hide files or directories entirely (allow_files / allow_dirs)
    """

    def __init__(self, filter_spec: PathFilterSpec, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._spec = filter_spec.normalized()
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def set_filter_spec(self, spec: PathFilterSpec) -> None:
        """Update filter spec and refresh filtering."""
        self._spec = spec.normalized()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # type: ignore[override]
        source_model = self.sourceModel()
        if not isinstance(source_model, QFileSystemModel):
            return True

        idx = source_model.index(source_row, 0, source_parent)
        if not idx or not idx.isValid():
            return False

        is_dir = source_model.isDir(idx)
        name = source_model.fileName(idx)
        # Hidden check
        if not self._spec.include_hidden and name.startswith("."):
            return False

        # Directory rules
        if is_dir:
            # if directories not allowed to be visible/selectable, still accept
            # directory rows to allow navigation down to files unless we want to fully hide directories
            # Design choice: hide directories from view when allow_dirs is False to keep UI simple
            return self._spec.allow_dirs

        # File rules
        if not self._spec.allow_files:
            return False

        ext = Path(name).suffix.lower()
        return self._spec.allows_file_extension(ext)


# ----------------------------- Custom Branch Delegate ------------------------

class BranchIndicatorDelegate(QStyledItemDelegate):
    """
    Custom delegate to draw explicit +/- branch indicators for QTreeView,
    guaranteeing visibility regardless of platform theme.

    It draws a small boxed + or - within the branch indentation area for
    items that have children (directories) and toggles expansion on click.
    """

    def __init__(self, tree: QTreeView, box_size: int = 12, margin: int = 3, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.tree = tree
        self.box_size = box_size
        self.margin = margin
        # Pre-create plus/minus pixmaps
        self.pm_plus = self._make_indicator(True)
        self.pm_minus = self._make_indicator(False)

    def _make_indicator(self, is_plus: bool) -> QPixmap:
        pm = QPixmap(self.box_size, self.box_size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor("#444"))
        pen.setWidth(1)
        p.setPen(pen)
        # Draw box
        p.drawRect(0, 0, self.box_size - 1, self.box_size - 1)
        # Draw - or +
        mid = self.box_size // 2
        p.drawLine(3, mid, self.box_size - 3, mid)
        if is_plus:
            p.drawLine(mid, 3, mid, self.box_size - 3)
        p.end()
        return pm

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """
        Draw explicit +/- indicator to the LEFT of the default icon/text so it doesn't overlap.
        Strategy:
          1) Compute a small indicator rect at the far left within the item's rect (respecting indentation).
          2) Paint +/- there if the item can expand.
          3) Shift the painter for the default content to the right so icon/text don't overlap our indicator.
        """
        model = index.model()
        # Map to source to query QFileSystemModel for isDir when using proxy
        src_index = index
        if hasattr(model, "sourceModel"):
            try:
                src_index = model.mapToSource(index)
                model = model.sourceModel()
            except Exception:
                pass

        is_dir = False
        has_children = False
        try:
            if isinstance(model, QFileSystemModel):
                is_dir = model.isDir(src_index)
                # Assume directories/drives can expand
                has_children = is_dir or True if model.fileInfo(src_index).isDir() else False
        except Exception:
            pass

        # Compute geometry
        rect: QRect = option.rect
        indicator_x = rect.x() + self.margin
        indicator_y = rect.y() + (rect.height() - self.box_size) // 2
        indicator_rect = QRect(indicator_x, indicator_y, self.box_size, self.box_size)

        # Determine if expanded
        expanded = self.tree.isExpanded(index)

        # If it has children (folder/drive), paint +/-; otherwise, leave space empty but still shift default content
        if has_children:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            pm = self.pm_minus if expanded else self.pm_plus
            painter.drawPixmap(indicator_rect, pm)
            painter.restore()

        # Shift default painting to the right by indicator width + margin so icons don't overlap +/- glyph
        shifted = QStyleOptionViewItem(option)
        shift_px = self.box_size + self.margin + 2
        shifted.rect = QRect(option.rect.x() + shift_px, option.rect.y(), option.rect.width() - shift_px, option.rect.height())
        super().paint(painter, shifted, index)

    def editorEvent(self, event, model, option, index):
        """
        Toggle expand/collapse when clicking inside the indicator box.
        """
        # Map index through proxy if necessary
        view_index = index
        if hasattr(self.tree.model(), "mapFromSource") and model is getattr(self.tree.model(), "sourceModel", None):
            try:
                view_index = self.tree.model().mapFromSource(index)
            except Exception:
                view_index = index

        etype = event.type()
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
            # Build the same indicator rect as in paint()
            rect: QRect = option.rect
            indicator_x = rect.x() + self.margin
            indicator_y = rect.y() + (rect.height() - self.box_size) // 2
            indicator_rect = QRect(indicator_x, indicator_y, self.box_size, self.box_size)
            # PySide6 may expose pos via .position() (Qt6) or .pos() (Qt5 style); support both
            try:
                pos = event.position().toPoint()  # type: ignore[attr-defined]
            except Exception:
                pos = event.pos()  # type: ignore[attr-defined]
            if indicator_rect.contains(pos):
                if etype == QEvent.MouseButtonRelease:
                    # Toggle expansion; consume event
                    self.tree.setExpanded(view_index, not self.tree.isExpanded(view_index))
                    return True
                # Consume press/dblclick inside indicator
                return True

        # Defer to default behavior
        return super().editorEvent(event, model, option, index)

# ----------------------------- PathSelectorDialog ----------------------------


class PathSelectorDialog(QDialog):
    """
    Modal dialog presenting a tree view of the filesystem for selecting a single path.

    Features:
    - QFileSystemModel tree view rooted at a configurable directory (default: filesystem root)
    - Flexible filtering by whitelist/blacklist and named categories
    - Toggle show hidden, files-only, dirs-only
    - Returns a Path on accept, or None on cancel

    Usage example:
        dlg = PathSelectorDialog(
            parent=self,
            title="Select an image",
            start_dir=Path.home(),
            filter_spec=PathFilterSpec(
                include_categories={"images"},
                blacklist_ext={"tmp", "sys"},
                allow_dirs=True,
                allow_files=True,
            ),
        )
        if dlg.exec() == QDialog.Accepted:
            selected = dlg.selected_path()

    Parameters:
        parent: Parent widget
        title: Dialog window title
        start_dir: Initial directory to expand/select
        filter_spec: Initial filter specification
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Select Path",
        start_dir: Optional[Path] = None,
        filter_spec: Optional[PathFilterSpec] = None,
    ):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for PathSelectorDialog")

        super().__init__(parent)
        self.setWindowTitle(title)
        self._start_dir = Path(start_dir).resolve() if start_dir else None
        self._filter_spec = (filter_spec or PathFilterSpec()).normalized()
        self._selected_path: Optional[Path] = None

        self._build_ui()
        self._apply_filter_to_model()

        # Expand the start directory if provided
        if self._start_dir and self._start_dir.exists():
            self._expand_to_path(self._start_dir)

        # Ensure initial dialog width matches containing application window width
        try:
            # Find top-level main window (QApplication.activeWindow or parent chain)
            main_win = QApplication.activeWindow()
            if main_win is None:
                # Traverse parent chain
                w = self.parent()
                while w is not None and not hasattr(w, "width"):
                    w = getattr(w, "parent", lambda: None)()
                main_win = w if isinstance(w, QWidget) else None
            if main_win and isinstance(main_win, QWidget):
                mw = main_win.width()
                mh = main_win.height()
                if mw and mw > 0:
                    # Use exact width of main window and a comfortable height
                    self.resize(mw, max(500, int(mh * 0.8)) if mh and mh > 0 else 700)
                    # Additionally, set a size policy to expand horizontally
                    self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            else:
                # As a robust fallback, maximize then restore height to avoid full-screen
                self.showMaximized()
        except Exception:
            pass

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Controls row
        controls = QHBoxLayout()
        layout.addLayout(controls)

        controls.addWidget(QLabel("Whitelist (ext, comma separated):"))
        self.inp_whitelist = QLineEdit(",".join(sorted({e.lstrip(".") for e in self._filter_spec.whitelist_ext})))
        controls.addWidget(self.inp_whitelist, 1)

        controls.addWidget(QLabel("Blacklist:"))
        self.inp_blacklist = QLineEdit(",".join(sorted({e.lstrip(".") for e in self._filter_spec.blacklist_ext})))
        controls.addWidget(self.inp_blacklist, 1)

        self.cmb_category = QComboBox()
        self.cmb_category.addItem("None")
        for cat in ["images", "audio", "video", "documents", "archives", "code"]:
            self.cmb_category.addItem(cat)
        controls.addWidget(QLabel("Category:"))
        controls.addWidget(self.cmb_category)

        self.chk_hidden = QCheckBox("Show hidden")
        self.chk_hidden.setChecked(self._filter_spec.include_hidden)
        controls.addWidget(self.chk_hidden)

        self.chk_allow_files = QCheckBox("Files")
        self.chk_allow_files.setChecked(self._filter_spec.allow_files)
        controls.addWidget(self.chk_allow_files)

        self.chk_allow_dirs = QCheckBox("Directories")
        self.chk_allow_dirs.setChecked(self._filter_spec.allow_dirs)
        controls.addWidget(self.chk_allow_dirs)

        btn_apply = QPushButton("Apply Filter")
        btn_apply.clicked.connect(self._on_apply_filter)
        controls.addWidget(btn_apply)

        # Splitter with tree view
        self.splitter = QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter, 1)

        # Tree view
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setRootPath(QDir.rootPath())

        self.proxy = FileSystemFilterProxy(self._filter_spec, self)
        self.proxy.setSourceModel(self.fs_model)

        self.tree = QTreeView(self)
        self.tree.setModel(self.proxy)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionBehavior(QTreeView.SelectItems)
        self.tree.setSelectionMode(QTreeView.SingleSelection)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        # Install custom branch indicator delegate on the name (column 0) to draw +/- explicitly
        self._branch_delegate = BranchIndicatorDelegate(self.tree, box_size=12, margin=6, parent=self.tree)
        self.tree.setItemDelegateForColumn(0, self._branch_delegate)

        # Ensure table uses 100% width of its container and columns fill space
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tree.setWordWrap(False)
        self.tree.setUniformRowHeights(True)  # improves paint correctness
        self.tree.setAllColumnsShowFocus(True)

        # Configure header/columns to fill available width with visual separators
        header: QHeaderView = self.tree.header()
        try:
            header.setStretchLastSection(False)
            header.setSectionsMovable(False)
            header.setHighlightSections(False)
            header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            header.setMinimumSectionSize(60)
            # Name column expands; other columns auto-size but keep a sane minimum
            header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name
            for col in (1, 2, 3):  # Size, Type, Date Modified
                header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        except Exception:
            pass

        # Visible separators and selection colors; keep text visible on selection
        # Also enforce vertical separators using header style and grid-like item borders
        self.tree.setStyleSheet("""
            QTreeView {
                border: 1px solid #dcdcdc;
                outline: none;
            }
            QTreeView::item {
                border-bottom: 1px solid #e6e6e6;
            }
            QTreeView::item:selected {
                background: #2d6cdf;
                color: #ffffff;
            }
            QTreeView::item:hover:!selected {
                background: #f2f6ff;
            }
            QHeaderView::section {
                border-right: 1px solid #e0e0e0;
                border-bottom: 1px solid #e0e0e0;
                background: #fafafa;
                padding: 4px 6px;
                color: #222;
            }
            /* Force default platform indicators to be visible and prominent */
            QTreeView::branch:has-children:closed,
            QTreeView::branch:closed:has-children {
                border-image: none;
                image: none;
            }
            QTreeView::branch:open:has-children,
            QTreeView::branch:open:has-children:!has-siblings {
                border-image: none;
                image: none;
            }
        """)

        # Ensure indicator size is large enough and explicitly set standard icons for folders
        try:
            style = self.style()
            icon_closed = style.standardIcon(QStyle.SP_DirClosedIcon)
            icon_open = style.standardIcon(QStyle.SP_DirOpenIcon)
            # QFileSystemModel uses internal icons; ensure indicator size is visible
            self.tree.setIconSize(QSize(16, 16))
            # Additionally, set indentation so indicators stand out
            self.tree.setItemsExpandable(True)
            self.tree.setExpandsOnDoubleClick(True)
            self.tree.setAnimated(True)
            self.tree.setIndentation(20)
        except Exception:
            pass

        # Root index for view
        if self._start_dir:
            src_idx = self.fs_model.index(str(self._start_dir))
            root_idx = self.proxy.mapFromSource(src_idx)
            if root_idx.isValid():
                self.tree.setRootIndex(root_idx)
        self.splitter.addWidget(self.tree)

        # Make dialog width initially match the parent window width (best effort)
        try:
            parent_widget = self.parent()
            if isinstance(parent_widget, QWidget):
                pw = parent_widget.width()
                ph = parent_widget.height()
                if pw and pw > 0:
                    # Use same width, reasonable height
                    self.resize(pw, max(500, int(ph * 0.8)) if ph and ph > 0 else 700)
            else:
                # Fallback: maximize horizontally
                self.showMaximized()
        except Exception:
            pass

        # Selected path preview
        preview = QWidget(self)
        pv_layout = QHBoxLayout(preview)
        pv_layout.addWidget(QLabel("Selected:"))
        self.lbl_selected = QLineEdit("")
        self.lbl_selected.setReadOnly(True)
        pv_layout.addWidget(self.lbl_selected, 1)
        self.splitter.addWidget(preview)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Track selection to preview
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _expand_to_path(self, path: Path) -> None:
        try:
            src_idx = self.fs_model.index(str(path))
            if not src_idx.isValid():
                return
            prox_idx = self.proxy.mapFromSource(src_idx)
            if prox_idx.isValid():
                self.tree.expand(prox_idx)
                self.tree.scrollTo(prox_idx)
                self.tree.setCurrentIndex(prox_idx)
        except Exception:
            # Non-fatal
            pass

    def _gather_filter_from_controls(self) -> PathFilterSpec:
        wl = {s.strip() for s in self.inp_whitelist.text().split(",") if s.strip()}
        bl = {s.strip() for s in self.inp_blacklist.text().split(",") if s.strip()}
        cat_text = self.cmb_category.currentText().strip().lower()
        include_cats: Set[NamedCategory] = set()
        if cat_text and cat_text != "none":
            include_cats = {cat_text}  # type: ignore[assignment]
        return PathFilterSpec(
            whitelist_ext=wl,
            blacklist_ext=bl,
            include_categories=include_cats,
            exclude_categories=set(),
            allow_dirs=self.chk_allow_dirs.isChecked(),
            allow_files=self.chk_allow_files.isChecked(),
            include_hidden=self.chk_hidden.isChecked(),
        ).normalized()

    def _on_apply_filter(self) -> None:
        self._filter_spec = self._gather_filter_from_controls()
        self._apply_filter_to_model()

    def _apply_filter_to_model(self) -> None:
        # QFileSystemModel uses name filters differently; we rely on proxy filter
        self.proxy.set_filter_spec(self._filter_spec)

    def _on_selection_changed(self) -> None:
        idx = self.tree.currentIndex()
        if not idx.isValid():
            self._selected_path = None
            self.lbl_selected.setText("")
            return
        src_idx = self.proxy.mapToSource(idx)
        p = Path(self.fs_model.filePath(src_idx))
        self._selected_path = p
        self.lbl_selected.setText(str(p))

    def _on_double_clicked(self, idx: QModelIndex) -> None:
        # On double-click: if file, accept; if dir, toggle expand
        if not idx.isValid():
            return
        src_idx = self.proxy.mapToSource(idx)
        p = Path(self.fs_model.filePath(src_idx))
        is_dir = self.fs_model.isDir(src_idx)
        if is_dir:
            if self.tree.isExpanded(idx):
                self.tree.collapse(idx)
            else:
                self.tree.expand(idx)
        else:
            self._selected_path = p
            self.accept()

    def _accept(self) -> None:
        # Validate selection against filter rules and exist
        if not self._selected_path:
            handle_gui_error(
                parent=self,
                error="Please select a path.",
                title="No selection",
                component_name="PathSelectorDialog"
            )
            return
        p = self._selected_path
        if not p.exists():
            handle_gui_error(
                parent=self,
                error=f"Path does not exist:\n{p}",
                title="Invalid path",
                component_name="PathSelectorDialog"
            )
            return
        if p.is_dir() and not self._filter_spec.allow_dirs:
            handle_gui_error(
                parent=self,
                error="Directory selection is not allowed",
                title="Not allowed",
                component_name="PathSelectorDialog"
            )
            return
        if p.is_file():
            if not self._filter_spec.allow_files:
                handle_gui_error(
                    parent=self,
                    error="File selection is not allowed",
                    title="Not allowed",
                    component_name="PathSelectorDialog"
                )
                return
            if not self._filter_spec.allows_file_extension(p.suffix):
                handle_gui_error(
                    parent=self,
                    error=f"File extension not allowed: {p.suffix}",
                    title="Filtered out",
                    component_name="PathSelectorDialog"
                )
                return
        self.accept()

    def selected_path(self) -> Optional[Path]:
        """
        Return the selected path after exec() returns Accepted, else None.
        """
        return self._selected_path


# -------------------------- MultiPathSelectorWidget --------------------------


class MultiPathSelectorWidget(QWidget):
    """
    Composite widget to manage a list of unique filesystem paths.

    Features:
    - "Add" button launches PathSelectorDialog with provided filter rules
    - List view shows all selected paths with per-item remove buttons (context or toolbar)
    - Validation before adding:
        * path exists
        * path is not already in the list
        * path is not contained within any subdirectories of existing list (using PathOperations.remove_contained_paths logic)
      If a parent of an existing entry is added, it will replace the contained children for minimal set.
    - Error messages shown via QMessageBox for user guidance

    Signals are not strictly required by the current spec; consumers can poll get_paths().
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Paths",
        start_dir: Optional[Path] = None,
        filter_spec: Optional[PathFilterSpec] = None,
    ):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for MultiPathSelectorWidget")

        super().__init__(parent)
        self._title = title
        self._start_dir = Path(start_dir).resolve() if start_dir else None
        self._filter_spec = (filter_spec or PathFilterSpec()).normalized()

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header_lbl = QLabel(self._title)
        header_lbl.setStyleSheet("font-weight: bold;")
        header.addWidget(header_lbl)
        header.addStretch()

        self.btn_add = QPushButton("Add…")
        self.btn_add.clicked.connect(self._on_add_clicked)
        header.addWidget(self.btn_add)

        self.btn_remove_selected = QPushButton("Remove Selected")
        self.btn_remove_selected.clicked.connect(self._on_remove_selected)
        header.addWidget(self.btn_remove_selected)

        layout.addLayout(header)

        # Paths list
        self.list_paths = QListWidget(self)
        self.list_paths.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_paths, 1)

        # Footer: quick info
        footer = QHBoxLayout()
        self.lbl_count = QLabel("0 items")
        footer.addWidget(self.lbl_count)
        footer.addStretch()
        layout.addLayout(footer)

        self._refresh_counts()

    def _refresh_counts(self) -> None:
        self.lbl_count.setText(f"{self.list_paths.count()} items")

    def _on_add_clicked(self) -> None:
        # Launch dialog with current filter settings
        dlg = PathSelectorDialog(
            parent=self,
            title="Select Path",
            start_dir=self._start_dir,
            filter_spec=self._filter_spec,
        )
        if dlg.exec() == QDialog.Accepted:
            p = dlg.selected_path()
            if p:
                self._try_add_path(p)

    def _on_remove_selected(self) -> None:
        for item in list(self.list_paths.selectedItems()):
            row = self.list_paths.row(item)
            self.list_paths.takeItem(row)
        self._refresh_counts()

    def _current_paths(self) -> List[Path]:
        paths: List[Path] = []
        for i in range(self.list_paths.count()):
            txt = self.list_paths.item(i).text().strip()
            if txt:
                paths.append(Path(txt))
        return paths

    def _try_add_path(self, path: Path) -> None:
        """
        Validate and add a new path:
        - Must exist
        - Not already present
        - Not a subpath of any existing entries; if it is a parent of any, replace minimal set
        """
        p = Path(path).resolve()
        if not p.exists():
            handle_gui_error(
                parent=self,
                error=f"The selected path does not exist:\n{p}",
                title="Path Does Not Exist",
                component_name="MultiPathSelectorWidget"
            )
            return

        existing = self._current_paths()
        existing_norm = PathOperations.normalize_paths(existing)

        # Duplicate
        if p in existing_norm:
            handle_gui_error(
                parent=self,
                error=f"The path is already in the list:\n{p}",
                title="Duplicate Path",
                component_name="MultiPathSelectorWidget"
            )
            return

        # Check if the new path is a subpath of any existing path (violates "contained by existing")
        for ex in existing_norm:
            try:
                p.relative_to(ex)
                handle_gui_error(
                    parent=self,
                    error=f"The selected path is contained within an existing path:\n\nSelected: {p}\nExisting: {ex}\n\nPlease choose a different path.",
                    title="Path Is Contained",
                    component_name="MultiPathSelectorWidget"
                )
                return
            except ValueError:
                continue

        # NEW RULE: The new path must not contain any existing paths (i.e., it is a parent of existing)
        contained_existing = []
        for ex in existing_norm:
            try:
                ex.relative_to(p)
                contained_existing.append(ex)
            except ValueError:
                continue
        if contained_existing:
            # Inform and offer to replace contained children by the new parent
            details = "\n".join(str(x) for x in contained_existing)
            resp = QMessageBox.question(
                self,
                "Path Contains Existing Entries",
                f"The selected path contains existing list entries:\n\n{details}\n\n"
                f"Do you want to replace those entries with the selected parent path?\n\nSelected: {p}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if resp == QMessageBox.No:
                return

        # Combine and reduce set with remove_contained_paths (maintain minimal set)
        new_set = existing_norm + [p]
        reduced = PathOperations.remove_contained_paths(new_set)

        # If parent path replaced children, update list accordingly
        reduced_set = set(reduced)
        if set(new_set) != reduced_set:
            self.list_paths.clear()
            for rp in sorted(reduced):
                self.list_paths.addItem(QListWidgetItem(str(rp)))
            self._refresh_counts()
            QMessageBox.information(
                self,
                "Paths Updated",
                "The selected path replaced one or more contained paths to maintain a minimal set."
            )
            return

        # Otherwise, simply append
        self.list_paths.addItem(QListWidgetItem(str(p)))
        self._refresh_counts()

    # Public API

    def get_paths(self) -> List[Path]:
        """
        Return the current list of selected paths as Path objects (normalized).
        """
        return PathOperations.normalize_paths(self._current_paths())

    def set_paths(self, paths: Sequence[Union[str, Path]]) -> None:
        """
        Replace current list with provided paths after normalization and de-containment minimalization.

        Example:
            widget.set_paths([Path('/data/images'), Path('/data/images/cat.jpg')])
            # The resulting list will only include '/data/images'
        """
        norm = PathOperations.normalize_paths([Path(p) for p in paths if p is not None])
        minimal = PathOperations.remove_contained_paths(norm)
        self.list_paths.clear()
        for p in minimal:
            self.list_paths.addItem(QListWidgetItem(str(p)))
        self._refresh_counts()


class DirectorySelectorWidget(PathSelectorDialog):
    """
    A widget (dialog) for selecting a single directory.
    This is a thin wrapper around PathSelectorDialog to provide a consistent interface.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        # Configure for directory selection only
        filter_spec = PathFilterSpec(
            allow_dirs=True,
            allow_files=False,
            include_hidden=False,
        )
        super().__init__(
            parent=parent,
            title="Select Directory",
            start_dir=None,
            filter_spec=filter_spec,
        )

    def get_selected_path(self) -> Optional[str]:
        """Return the selected path as a string, or None."""
        path = self.selected_path()
        return str(path) if path else None


__all__ = [
    "PathFilterSpec",
    "PathSelectorDialog",
    "MultiPathSelectorWidget",
    "DirectorySelectorWidget",
    "NamedCategory",
    "category_extensions",
]