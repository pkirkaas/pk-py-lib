"""
JSON-based unified settings manager.

This module provides a replacement for the SQLite-based SettingsManager
that uses JSON files for storage instead.

Design Notes:
- Maintains the same interface as the original SettingsManager for compatibility
- Uses JSON files stored in the user settings directory
- Simple error handling: delete and recreate on any issues
- No migration logic - fresh start approach
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..models.settings import AppSettings, SettingsProfile
from .json_app_settings import JSONAppSettingsManager
from .json_profiles import JSONProfilesManager

logger = logging.getLogger("pk_py_lib.core.settings.json_unified_manager")


class JSONSettingsManager:
    """
    JSON-based unified settings manager.

    This class provides the same interface as the original SettingsManager
    but uses JSON files for storage instead of SQLite database.

    Attributes
    ----------
    settings_dir : Path
        Directory where settings files are stored
    app_settings : JSONAppSettingsManager
        Manager for application settings
    profiles : JSONProfilesManager
        Manager for search profiles
    """

    def __init__(self, settings_dir: Optional[Path] = None):
        """
        Initialize the JSON settings manager.

        Parameters
        ----------
        settings_dir : Optional[Path]
            Directory where settings files will be stored.
            If None, uses platform-specific data directory.
        """
        if settings_dir is None:
            # Use platform-specific data directory
            settings_dir = self._get_default_settings_dir()

        self.settings_dir = Path(settings_dir)

        # Initialize sub-managers
        self.app_settings = JSONAppSettingsManager(self.settings_dir)
        self.profiles = JSONProfilesManager(self.settings_dir)

        logger.info(f"JSON settings manager initialized for directory: {self.settings_dir}")

    def _get_default_settings_dir(self) -> Path:
        """Get platform-specific default settings directory."""
        # Use the unified data directory directly (same level as flat_cache.db)
        from ...core.utils import get_data_dir
        return get_data_dir()

    def load_all(self) -> Dict[str, Any]:
        """
        Load all settings and profiles.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing both settings and profiles
        """
        logger.debug("Loading all settings and profiles")

        return {
            "app_settings": self.app_settings.load(),
            "profiles": self.profiles.get_all()
        }

    def save_all(self, app_settings: AppSettings, profiles: List[SettingsProfile]) -> None:
        """
        Save all settings and profiles.

        Parameters
        ----------
        app_settings : AppSettings
            Application settings to save
        profiles : List[SettingsProfile]
            Profiles to save
        """
        logger.debug("Saving all settings and profiles")

        self.app_settings.save(app_settings)
        # Note: Saving individual profiles is handled by the profiles manager
        # This method is mainly for bulk operations

    def reset_to_defaults(self) -> None:
        """
        Reset all settings and profiles to defaults.

        This method removes all existing settings files and creates
        fresh defaults for both app settings and search profiles.
        """
        logger.info("Resetting all settings to defaults")

        # Reset app settings
        self.app_settings._settings = None
        self.app_settings.load()

        # Reset profiles
        self.profiles._profiles = []
        self.profiles._create_default_profiles()

        logger.info("Successfully reset all settings to defaults")

    def get_settings_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current settings for debugging.

        Returns
        -------
        Dict[str, Any]
            Summary of settings configuration
        """
        return {
            "settings_dir": str(self.settings_dir),
            "app_settings_file": str(self.settings_dir / "app-settings.json"),
            "profiles_file": str(self.settings_dir / "search-profiles.json"),
            "app_settings_count": 1,  # Always one app settings instance
            "profiles_count": len(self.profiles.get_all())
        }

    def validate_integrity(self) -> Dict[str, Any]:
        """
        Validate the integrity of settings files.

        Returns
        -------
        Dict[str, Any]
            Validation results with any issues found
        """
        issues = []

        try:
            # Test loading app settings
            app_settings = self.app_settings.load()
        except Exception as e:
            issues.append(f"App settings error: {e}")

        try:
            # Test loading profiles
            profiles = self.profiles.get_all()
        except Exception as e:
            issues.append(f"Profiles error: {e}")

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }


__all__ = ["JSONSettingsManager"]
