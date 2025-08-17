"""
src/pk_py_lib/gui/settings_manager/__init__.py

Reusable Settings Manager GUI package (PySide6).

Exports
-------
- Dialog and entrypoint:
  * SettingsManagerDialog — master-detail modal dialog
  * settings_manager_dialog — helper to show the dialog and return active profile on accept
- Editor widget (detail pane) and non-Qt controller/models/validators for reuse

Usage
-----
>>> # Note: Requires PySide6 to be available in the environment.
>>> from src.pk_py_lib.gui.settings_manager import settings_manager_dialog
>>> active = settings_manager_dialog()
>>> if active:
...     print("Active profile:", active["name"])

Note: Syntax validation was performed using Python's ast module per project rules.
"""

from __future__ import annotations

from .dialog import SettingsManagerDialog, settings_manager_dialog
from .editor_widget import SettingsProfileEditorWidget
from .controller import SettingsManagerController
from .models import ProfilesListModel, KeyValueTableModel, ProfileVM
from .validators import (
    ProfileNameValidator,
    SingleKeyValidator,
    validate_profile_name_via_api,
    validate_keys_via_api,
)

__all__ = [
    "SettingsManagerDialog",
    "settings_manager_dialog",
    "SettingsProfileEditorWidget",
    "SettingsManagerController",
    "ProfilesListModel",
    "KeyValueTableModel",
    "ProfileVM",
    "ProfileNameValidator",
    "SingleKeyValidator",
    "validate_profile_name_via_api",
    "validate_keys_via_api",
]