"""
Showcase demos for PathSelectorDialog and MultiPathSelectorWidget.

Provides simple interactive widgets to exercise core features, wired for the showcase app to instantiate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QMessageBox
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False


from src.pk_py_lib.gui.file_selector.widgets import (
    PathSelectorDialog,
    MultiPathSelectorWidget,
    PathFilterSpec,
)


class PathSelectorDemo(QWidget):
    """
    Minimal demo container that opens the PathSelectorDialog and shows the chosen path.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 required")

        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.lbl = QLabel("No selection")
        layout.addWidget(self.lbl)

        btn = QPushButton("Select an image or directory…")
        btn.clicked.connect(self._open_dialog)
        layout.addWidget(btn)

        layout.addStretch()

    def _open_dialog(self) -> None:
        dlg = PathSelectorDialog(
            parent=self,
            title="Select an image or directory",
            filter_spec=PathFilterSpec(
                include_categories={"images"},
                blacklist_ext={"tmp", "sys"},
                allow_dirs=True,
                allow_files=True,
            ),
        )
        # Use QDialog.Accepted enum from PySide6, not an attribute on the dialog instance
        from PySide6.QtWidgets import QDialog  # local import to avoid top-level dependency issues
        if dlg.exec() == QDialog.Accepted:
            sel = dlg.selected_path()
            self.lbl.setText(str(sel) if sel else "None selected")


class MultiPathSelectorDemo(QWidget):
    """
    Demo container for the MultiPathSelectorWidget with a button to inspect current paths.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 required")

        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.selector = MultiPathSelectorWidget(
            parent=self,
            title="Monitored Paths",
            filter_spec=PathFilterSpec(
                include_categories={"images", "video"},
                allow_dirs=True,
                allow_files=True,
            ),
        )
        layout.addWidget(self.selector)

        btn_show = QPushButton("Show current paths")
        btn_show.clicked.connect(self._show_paths)
        layout.addWidget(btn_show)

        layout.addStretch()

    def _show_paths(self) -> None:
        paths = self.selector.get_paths()
        msg = "\n".join(str(p) for p in paths) or "(none)"
        QMessageBox.information(self, "Current Paths", msg)