"""
src/pk_py_lib/gui/utils/messages.py

Selectable/copyable QMessageBox helpers for consistent error/info dialogs.

- show_selectable_message(...)
- show_selectable_error/warning/info

Note: Syntax validation was performed using Python's ast module per project rules.
"""

from __future__ import annotations

from typing import Optional

# Defensive import to keep library importable in headless/test environments
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QWidget, QLabel
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

    class _Missing:
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for selectable message dialogs")

    Qt = QMessageBox = QWidget = QLabel = _Missing()  # type: ignore


def _enable_label_selection(box: "QMessageBox") -> None:
    """Internal: enable text selection on QMessageBox labels."""
    try:
        # Try Qt6 API if available on QMessageBox directly (may not exist on some bindings)
        try:
            box.setTextInteractionFlags(  # type: ignore[attr-defined]
                Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
            )
        except Exception:
            pass

        # Ensure built-in labels are selectable/copyable
        for name in ("qt_msgbox_label", "qt_msgbox_informativelabel"):
            lbl = box.findChild(QLabel, name)
            if lbl is None:
                continue
            try:
                lbl.setTextInteractionFlags(
                    Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
                )
                lbl.setOpenExternalLinks(True)
                # QLabel defaults to AutoText; leave rendering mode unchanged
                # lbl.setTextFormat(Qt.TextFormat.AutoText)
            except Exception:
                # Ignore if the binding lacks attributes on current platform
                pass
    except Exception:
        # Never let this helper crash the app
        pass


def show_selectable_message(
    parent: Optional["QWidget"],
    title: str,
    text: str,
    informative_text: Optional[str] = None,
    icon: "QMessageBox.Icon" = QMessageBox.Critical,
) -> int:
    """
    Show a modal QMessageBox with selectable/copyable text.

    Parameters
    ----------
    parent : Optional[QWidget]
        Parent widget or None for app-modal.
    title : str
        Dialog window title.
    text : str
        Main message text (plain or rich).
    informative_text : Optional[str]
        Optional subordinate text shown below the main text.
    icon : QMessageBox.Icon
        Icon to display (e.g., Critical, Warning, Information).

    Returns
    -------
    int
        exec() result (QDialog.DialogCode), useful if caller branches on buttons.

    Raises
    ------
    RuntimeError
        If PySide6 is not available in the current environment.
    """
    if not PYSIDE_AVAILABLE:  # pragma: no cover
        raise RuntimeError("PySide6 is required for show_selectable_message")

    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if informative_text:
        try:
            box.setInformativeText(informative_text)
        except Exception:
            # Fallback: append informative text to main text if the property is unavailable
            try:
                box.setText(f"{text}\n\n{informative_text}")
            except Exception:
                pass

    _enable_label_selection(box)
    return box.exec()


def show_selectable_error(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for a Critical message box with selectable text.
    """
    return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Critical)


def show_selectable_warning(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for a Warning message box with selectable text.
    """
    return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Warning)


def show_selectable_info(
    parent: Optional["QWidget"], title: str, text: str, informative_text: Optional[str] = None
) -> int:
    """
    Convenience wrapper for an Information message box with selectable text.
    """
    return show_selectable_message(parent, title, text, informative_text, icon=QMessageBox.Information)


__all__ = [
    "show_selectable_message",
    "show_selectable_error",
    "show_selectable_warning",
    "show_selectable_info",
]