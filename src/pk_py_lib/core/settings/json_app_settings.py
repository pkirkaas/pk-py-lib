"""
JSON-based application settings manager.

This module provides a replacement for the SQLite-based AppSettingsManager
that uses JSON files for storage instead.

Design Notes:
- Maintains the same interface as the original AppSettingsManager for compatibility
- Uses JSON files stored in the user settings directory
- Simple error handling: delete and recreate on any issues
- No migration logic - fresh start approach
"""

import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from threading import Lock

from ..models.settings import AppSettings
from .json_manager import SettingsFileManager

logger = logging.getLogger("pk_py_lib.core.settings.json_app_settings")


class JSONAppSettingsManager:
    """
    JSON-based manager for application-wide settings.

    This class provides the same interface as the original AppSettingsManager
    but uses JSON files for storage instead of SQLite database.

    Attributes
    ----------
    settings_dir : Path
        Directory where settings files are stored
    """

    def __init__(self, settings_dir: Path):
        """
        Initialize the JSON app settings manager.

        Parameters
        ----------
        settings_dir : Path
            Directory where settings files will be stored
        """
        self.settings_dir = Path(settings_dir)
        self.file_manager = SettingsFileManager(self.settings_dir)
        self._settings: AppSettings = None
        self._lock = Lock()

        logger.info(f"JSON app settings manager initialized for directory: {self.settings_dir}")

    def load(self) -> AppSettings:
        """
        Load application settings from JSON file.

        Returns
        -------
        AppSettings
            Application settings instance

        Notes
        -----
        If file doesn't exist or is corrupted, creates fresh defaults.
        """
        with self._lock:
            logger.debug("Loading app settings from JSON file")

            # Load raw settings data
            settings_data = self.file_manager.get_app_settings()

            # Convert to AppSettings object
            try:
                # Remove version field before creating AppSettings object
                settings_data = settings_data.copy()
                settings_data.pop('version', None)

                # Handle JSON datetime strings
                if isinstance(settings_data.get('last_updated'), str):
                    settings_data['last_updated'] = datetime.fromisoformat(settings_data['last_updated'])

                # Handle JSON boolean/number conversions
                settings_data['cache_enabled'] = bool(settings_data.get('cache_enabled', True))
                settings_data['cache_size_mb'] = int(settings_data.get('cache_size_mb', 500))
                settings_data['max_workers'] = int(settings_data.get('max_workers', 4))

                # Handle window geometry
                window_geom = settings_data.get('window_geometry')
                if window_geom and isinstance(window_geom, dict):
                    settings_data['window_geometry'] = {
                        k: int(v) for k, v in window_geom.items()
                    }

                settings = AppSettings(**settings_data)
                self._settings = settings
                logger.debug("Successfully loaded app settings")
                return settings

            except Exception as e:
                logger.error(f"Error converting settings data: {e}, creating fresh defaults")
                return self._create_fresh_settings()

    def save(self, settings: AppSettings) -> None:
        """
        Save application settings to JSON file.

        Parameters
        ----------
        settings : AppSettings
            Settings instance to save
        """
        with self._lock:
            logger.debug("Saving app settings to JSON file")

            try:
                # Convert AppSettings to dictionary
                settings_dict = settings.to_dict()

                # Add version field required by schema
                settings_dict['version'] = 1

                # Update timestamp
                settings_dict['last_updated'] = datetime.now().isoformat()

                # Save via file manager
                self.file_manager.save_app_settings(settings_dict)

                # Update cached instance
                self._settings = settings

                logger.debug("Successfully saved app settings")

            except Exception as e:
                logger.error(f"Error saving app settings: {e}")
                raise

    def _create_fresh_settings(self) -> AppSettings:
        """Create fresh default settings."""
        logger.info("Creating fresh default app settings")

        # Get default settings data
        defaults = self.file_manager.get_app_settings()

        # Convert to AppSettings object
        try:
            # Remove version field before creating AppSettings object
            defaults_copy = defaults.copy()
            defaults_copy.pop('version', None)

            if isinstance(defaults_copy.get('last_updated'), str):
                defaults_copy['last_updated'] = datetime.fromisoformat(defaults_copy['last_updated'])

            defaults_copy['cache_enabled'] = bool(defaults_copy.get('cache_enabled', True))
            defaults_copy['cache_size_mb'] = int(defaults_copy.get('cache_size_mb', 500))
            defaults_copy['max_workers'] = int(defaults_copy.get('max_workers', 4))

            window_geom = defaults_copy.get('window_geometry')
            if window_geom and isinstance(window_geom, dict):
                defaults_copy['window_geometry'] = {
                    k: int(v) for k, v in window_geom.items()
                }

            settings = AppSettings(**defaults_copy)
            self._settings = settings
            return settings

        except Exception as e:
            logger.error(f"Error creating default settings: {e}")
            # Fallback to basic defaults
            return AppSettings()

    def reload(self) -> AppSettings:
        """
        Reload settings from file, discarding any cached changes.

        Returns
        -------
        AppSettings
            Freshly loaded settings
        """
        self._settings = None
        return self.load()

    def get_settings(self) -> AppSettings:
        """
        Get current settings, loading if necessary.

        Returns
        -------
        AppSettings
            Current settings instance
        """
        if self._settings is None:
            return self.load()
        return self._settings

    def update_setting(self, key: str, value: Any) -> None:
        """
        Update a single setting value.

        Parameters
        ----------
        key : str
            Setting name to update
        value : Any
            New value for the setting
        """
        if self._settings is None:
            self.load()

        if hasattr(self._settings, key):
            setattr(self._settings, key, value)
            self.save(self._settings)
            logger.debug(f"Updated setting {key} to {value}")
        else:
            logger.warning(f"Unknown setting key: {key}")


__all__ = ["JSONAppSettingsManager"]
