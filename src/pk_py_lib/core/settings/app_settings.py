"""
DEPRECATED: Legacy SQLite-based application settings manager.

This module is deprecated. Use JSON-based settings instead:
- src/pk_py_lib/core/settings/json_app_settings.py
- src/pk_py_lib/core/settings/json_unified_manager.py

This manager is maintained for backward compatibility but now uses
JSON settings internally to avoid creating SQLite settings.db files.
"""

import logging
import warnings
from pathlib import Path
from typing import Optional

from ..models.settings import AppSettings
from .json_app_settings import JSONAppSettingsManager

logger = logging.getLogger("pk_py_lib.core.settings.app_settings")


class AppSettingsManager:
    """
    DEPRECATED: Legacy SQLite-based application settings manager.

    This class is deprecated. Use JSON-based settings managers instead.
    Now acts as a wrapper around JSONAppSettingsManager to maintain
    backward compatibility while using JSON settings internally.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the deprecated app settings manager.

        Parameters
        ----------
        db_path : Path
            DEPRECATED - parameter is ignored, JSON settings are used instead.
        """
        warnings.warn(
            "AppSettingsManager is deprecated. Use JSONAppSettingsManager instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Note: db_path parameter is deprecated and ignored
        # Use JSON settings manager instead of SQLite to avoid creating settings.db
        self.json_manager = JSONAppSettingsManager()
        self._settings: Optional[AppSettings] = None

    def load(self) -> AppSettings:
        """
        Load application settings from JSON (not SQLite).
        """
        warnings.warn(
            "AppSettingsManager.load() is deprecated. Use JSONAppSettingsManager.load() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug("Loading app settings from JSON (legacy compatibility mode)")
        self._settings = self.json_manager.load()
        return self._settings

    def save(self, settings: AppSettings) -> None:
        """
        Save application settings to JSON (not SQLite).
        """
        warnings.warn(
            "AppSettingsManager.save() is deprecated. Use JSONAppSettingsManager.save() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug("Saving app settings to JSON (legacy compatibility mode)")
        self.json_manager.save(settings)
        self._settings = settings
