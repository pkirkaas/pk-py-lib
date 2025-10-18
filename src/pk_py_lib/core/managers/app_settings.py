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
from threading import Lock

from pk_py_lib.core.models.settings import AppSettings
from pk_py_lib.core.settings.json_app_settings import JSONAppSettingsManager

logger = logging.getLogger("pk_py_lib.core.managers.app_settings")


class AppSettingsManager:
    """
    DEPRECATED: Legacy SQLite-based application settings manager.

    This class is deprecated. Use JSON-based settings managers instead.
    Now acts as a wrapper around JSONAppSettingsManager to maintain
    backward compatibility while using JSON settings internally.

    Examples
    --------
    >>> manager = AppSettingsManager(Path("settings.db"))  # DEPRECATED
    >>> settings = manager.load()  # Uses JSON internally
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
        self._lock = Lock()

    def load(self) -> AppSettings:
        """
        Load application settings from JSON (not SQLite).

        Returns
        -------
        AppSettings
            AppSettings instance with current settings

        Creates default settings if none exist.

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> settings = manager.load()
        >>> settings.cache_enabled
        True
        """
        warnings.warn(
            "AppSettingsManager.load() is deprecated. Use JSONAppSettingsManager.load() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug("Loading app settings from JSON (legacy compatibility mode)")
            self._settings = self.json_manager.load()
            logger.debug(f"Loaded app settings: cache_size={self._settings.cache_size_mb}MB, theme={self._settings.gui_theme}")
            return self._settings

    def save(self, settings: AppSettings) -> None:
        """
        Save application settings to JSON (not SQLite).

        Parameters
        ----------
        settings : AppSettings
            AppSettings instance to save

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> settings = manager.load()
        >>> settings.cache_size_mb = 1024
        >>> manager.save(settings)
        """
        warnings.warn(
            "AppSettingsManager.save() is deprecated. Use JSONAppSettingsManager.save() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug("Saving app settings to JSON (legacy compatibility mode)")
            self.json_manager.save(settings)
            self._settings = settings
            logger.debug(f"Saved app settings: cache_size={settings.cache_size_mb}MB")

    def get_cache_enabled(self) -> bool:
        """
        Get whether caching is enabled.

        Returns
        -------
        bool
            True if caching is enabled

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> manager.get_cache_enabled()
        True
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.cache_enabled

    def set_cache_enabled(self, enabled: bool) -> None:
        """
        Set whether caching is enabled.

        Parameters
        ----------
        enabled : bool
            True to enable caching

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> manager.set_cache_enabled(False)
        >>> manager.get_cache_enabled()
        False
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.cache_enabled = enabled
        self.save(self._settings)

    def get_cache_size_mb(self) -> int:
        """
        Get cache size in megabytes.

        Returns
        -------
        int
            Cache size in MB
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.cache_size_mb

    def set_cache_size_mb(self, size_mb: int) -> None:
        """
        Set cache size in megabytes.

        Parameters
        ----------
        size_mb : int
            Cache size in MB (must be positive)

        Raises
        ------
        ValueError
            If size_mb is not positive
        """
        if size_mb <= 0:
            raise ValueError("Cache size must be positive")

        if self._settings is None:
            self._settings = self.load()
        self._settings.cache_size_mb = size_mb
        self.save(self._settings)

    def get_max_workers(self) -> int:
        """
        Get maximum number of worker threads.

        Returns
        -------
        int
            Maximum worker threads
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.max_workers

    def set_max_workers(self, workers: int) -> None:
        """
        Set maximum number of worker threads.

        Parameters
        ----------
        workers : int
            Maximum worker threads (must be positive)

        Raises
        ------
        ValueError
            If workers is not positive
        """
        if workers <= 0:
            raise ValueError("Max workers must be positive")

        if self._settings is None:
            self._settings = self.load()
        self._settings.max_workers = workers
        self.save(self._settings)

    def get_gui_theme(self) -> str:
        """
        Get GUI theme setting.

        Returns
        -------
        str
            Theme name ('light', 'dark', or 'auto')
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.gui_theme

    def set_gui_theme(self, theme: str) -> None:
        """
        Set GUI theme.

        Parameters
        ----------
        theme : str
            Theme name ('light', 'dark', or 'auto')

        Raises
        ------
        ValueError
            If theme is not valid
        """
        valid_themes = {'light', 'dark', 'auto'}
        if theme not in valid_themes:
            raise ValueError(f"Invalid theme: {theme}. Must be one of {valid_themes}")

        if self._settings is None:
            self._settings = self.load()
        self._settings.gui_theme = theme
        self.save(self._settings)

    def get_log_level(self) -> str:
        """
        Get logging level.

        Returns
        -------
        str
            Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.log_level

    def set_log_level(self, level: str) -> None:
        """
        Set logging level.

        Parameters
        ----------
        level : str
            Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')

        Raises
        ------
        ValueError
            If level is not valid
        """
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if level.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")

        if self._settings is None:
            self._settings = self.load()
        self._settings.log_level = level.upper()
        self.save(self._settings)

    def get_default_profile_id(self) -> Optional[int]:
        """
        Get default profile ID.

        Returns
        -------
        Optional[int]
            Default profile ID, or None if not set
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.default_profile_id

    def set_default_profile_id(self, profile_id: Optional[int]) -> None:
        """
        Set default profile ID.

        Parameters
        ----------
        profile_id : Optional[int]
            Profile ID to set as default, or None to clear
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.default_profile_id = profile_id
        self.save(self._settings)

    def add_recent_directory(self, directory: str, max_recent: int = 10) -> None:
        """
        Add a directory to recent directories list.

        Parameters
        ----------
        directory : str
            Directory path to add
        max_recent : int
            Maximum number of recent directories to keep (default: 10)
        """
        if self._settings is None:
            self._settings = self.load()

        # Remove if already exists
        if directory in self._settings.recent_directories:
            self._settings.recent_directories.remove(directory)

        # Add to front
        self._settings.recent_directories.insert(0, directory)

        # Trim to max
        if len(self._settings.recent_directories) > max_recent:
            self._settings.recent_directories = self._settings.recent_directories[:max_recent]

        self.save(self._settings)

    def get_recent_directories(self) -> list:
        """
        Get list of recent directories.

        Returns
        -------
        list
            List of recent directory paths
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.recent_directories.copy()

    def set_window_geometry(self, geometry: dict) -> None:
        """
        Save window geometry.

        Parameters
        ----------
        geometry : dict
            Dictionary with window geometry (x, y, width, height)
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.window_geometry = geometry
        self.save(self._settings)

    def get_window_geometry(self) -> Optional[dict]:
        """
        Get saved window geometry.

        Returns
        -------
        Optional[dict]
            Window geometry dictionary, or None if not saved
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.window_geometry


__all__ = ['AppSettingsManager']
