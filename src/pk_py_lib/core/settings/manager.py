"""
Unified settings manager for the pk-py-lib project.

This module provides a consolidated manager for all application settings,
including both global app settings and user-defined profiles.

DEPRECATED: This module is deprecated in favor of JSON-based settings management.
Use `src.pk_py_lib.core.settings.json_unified_manager.JSONSettingsManager` instead.
"""

import logging
from pathlib import Path
from typing import Optional

from .json_app_settings import JSONAppSettingsManager
from .json_profiles import JSONProfilesManager

logger = logging.getLogger("pk_py_lib.core.settings.manager")


class SettingsManager:
    """
    Unified manager for all settings.

    DEPRECATED: This class is deprecated in favor of JSON-based settings management.
    Use `JSONSettingsManager` from `src.pk_py_lib.core.settings.json_unified_manager` instead.

    This class provides a single interface to manage both application-wide
    settings and user-defined profiles. It delegates to the specialized
    JSON-based managers to avoid SQLite database creation.

    Attributes
    ----------
    app_settings : JSONAppSettingsManager
        Manager for application-wide settings (JSON-based)
    profiles : JSONProfilesManager
        Manager for user-defined profiles (JSON-based)

    Examples
    --------
    >>> manager = SettingsManager()
    >>> app_settings = manager.app_settings.load()
    >>> profiles = manager.profiles.get_all()
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the settings manager with JSON-based managers.

        Parameters
        ----------
        db_path : Optional[Path]
            DEPRECATED: This parameter is ignored for JSON-based settings.
            Maintained for backward compatibility only.
        """
        # Ignore db_path parameter for JSON-based settings
        # Use JSON managers directly to avoid SQLite database creation
        self.app_settings = JSONAppSettingsManager()
        self.profiles = JSONProfilesManager()

    def initialize(self):
        """
        Initialize the settings managers (no-op for JSON-based settings).
        """
        logger.info("Initializing JSON-based settings manager...")
        # JSON managers handle their own initialization
        pass


__all__ = ['SettingsManager']


def get_active_profile_settings() -> dict:
    """
    Get the settings from the active/default profile.

    DEPRECATED: Use JSON-based settings management instead.
    """
    import warnings
    warnings.warn(
        "get_active_profile_settings() is deprecated. Use JSON-based settings management instead.",
        DeprecationWarning,
        stacklevel=2
    )

    manager = SettingsManager()
    profile = manager.profiles.get_default()
    if not profile:
        raise RuntimeError("No default settings profile found.")
    return profile.to_dict()
