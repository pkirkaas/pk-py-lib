"""
Unified settings manager for the pk-py-lib project.

This module provides a consolidated manager for all application settings,
including both global app settings and user-defined profiles.
"""

import logging
from pathlib import Path
from typing import Optional

from ..database import DatabaseManager
from .app_settings import AppSettingsManager
from .profiles import ProfilesManager

logger = logging.getLogger("pk_py_lib.core.settings.manager")


class SettingsManager:
    """
    Unified manager for all settings.

    This class provides a single interface to manage both application-wide
    settings and user-defined profiles. It delegates to the specialized
    managers for each type of setting.

    Attributes
    ----------
    app_settings : AppSettingsManager
        Manager for application-wide settings
    profiles : ProfilesManager
        Manager for user-defined profiles

    Examples
    --------
    >>> manager = SettingsManager()
    >>> app_settings = manager.app_settings.load()
    >>> profiles = manager.profiles.get_all()
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the settings manager.

        Parameters
        ----------
        db_path : Optional[Path]
            Path to the database file. If None, uses the default path.
        """
        if db_path is None:
            from ..config import AppConfig
            db_path = AppConfig().db_path

        self.db_path = db_path
        self.app_settings = AppSettingsManager(self.db_path)
        self.profiles = ProfilesManager(self.db_path)

    def initialize(self):
        """
        Initialize the settings database and managers.
        """
        logger.info("Initializing settings manager...")
        # Initialization is handled by the individual managers' constructors
        pass


__all__ = ['SettingsManager']


def get_active_profile_settings() -> dict:
    """
    Get the settings from the active/default profile.
    """
    manager = SettingsManager()
    profile = manager.profiles.get_default()
    if not profile:
        raise RuntimeError("No default settings profile found.")
    return profile.to_dict()