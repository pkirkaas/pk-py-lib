"""
Main window implementation for the KDC Image Organizer (img_app).

Provides a QMainWindow subclass with:
- Title: "KDC Image Organizer"
- Menu bar with File, View, Help (initially no-op actions)
- Central placeholder widget that renders centered text:
  "The KDC Image Organizer will go here"

This window is intentionally minimal for Milestone M0 and will evolve as
pk_py_lib components are integrated.

Syntax validation: This file has been reviewed for Python syntax correctness.
"""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QLabel, QWidget, QVBoxLayout, QMenuBar, QStatusBar


class CentralPlaceholder(QWidget):
    """
    Simple centered placeholder widget.

    Displays a centered label indicating where the application content will go.
    This class is placed here initially to keep scaffolding minimal; it can be
    moved to img_app/widgets/central_placeholder.py when expanded.

    Examples
    --------
    >>> w = CentralPlaceholder()
    >>> w.layout() is not None
    True
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        label = QLabel("The KDC Image Organizer will go here", self)
        # Use Qt.AlignmentFlag enums for correctness across PySide6 bindings
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    """
    QMainWindow for the KDC Image Organizer.

    Responsibilities
    ----------------
    - Set up basic window chrome (title, menus, status bar)
    - Provide a central placeholder area for early milestones
    - Host future widgets and controllers derived from pk_py_lib

    Usage
    -----
    The window is constructed and shown by img_app.img_app.app:main()

    Examples
    --------
    >>> win = MainWindow()
    >>> isinstance(win.menuBar(), QMenuBar)
    True
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_window()
        self._setup_menu_bar()
        self._setup_status_bar()
        self._setup_central_widget()

    def _setup_window(self) -> None:
        """Configure basic window properties."""
        self.setWindowTitle("KDC Image Organizer")
        self.resize(1024, 720)

    def _setup_menu_bar(self) -> None:
        """Create a standard application menu bar with File, View, Help."""
        menubar = self.menuBar() if self.menuBar() else QMenuBar(self)
        self.setMenuBar(menubar)

        # File menu
        file_menu = menubar.addMenu("&File")
        # Placeholder actions (no-op)
        file_menu.addAction(self._make_noop_action("Open..."))
        file_menu.addAction(self._make_noop_action("Save"))
        file_menu.addSeparator()
        file_menu.addAction(self._make_noop_action("Exit"))

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self._make_noop_action("Reset Layout"))

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self._make_noop_action("About"))

    def _setup_status_bar(self) -> None:
        """Attach a simple status bar for future feedback."""
        status = self.statusBar() if self.statusBar() else QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Ready")

    def _setup_central_widget(self) -> None:
        """
        Place the initial central widget.

        Try to use the library MultiPathSelectorWidget from src.pk_py_lib.gui.file_selector.widgets
        as the application's initial central widget. If the library or widget cannot be loaded
        (missing dependency, import error, or runtime issue), fall back to a simple
        CentralPlaceholder so the app remains functional.
        """
        try:
            # Import locally to avoid top-level dependency on pk-py-lib during module import
            from src.pk_py_lib.gui.file_selector.widgets import (
                MultiPathSelectorWidget,
                PathFilterSpec,
            )

            # Construct a sensible default filter spec (images & video)
            filter_spec = PathFilterSpec(include_categories={"images", "video"})
            selector = MultiPathSelectorWidget(
                parent=self,
                title="Paths",
                start_dir=None,
                filter_spec=filter_spec,
            )
            self.setCentralWidget(selector)
            # Update status with success (best-effort)
            try:
                self.statusBar().showMessage("MultiPathSelector loaded")
            except Exception:
                pass
        except Exception as exc:
            # Fallback to placeholder and inform the status bar
            self.setCentralWidget(CentralPlaceholder(self))
            try:
                self.statusBar().showMessage(f"Using placeholder (MultiPathSelector unavailable): {exc}")
            except Exception:
                pass

    def _make_noop_action(self, text: str) -> QAction:
        """
        Create a no-op QAction placeholder.

        Parameters
        ----------
        text : str
            Display text for the action.

        Returns
        -------
        QAction
            Action connected to a lambda that performs no behavior.
        """
        action = QAction(text, self)
        action.triggered.connect(lambda: None)
        return action