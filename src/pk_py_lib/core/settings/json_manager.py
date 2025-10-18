"""
JSON-based settings file manager.

This module provides the core functionality for managing JSON settings files,
including reading, writing, validation, and error handling.

Design Notes:
- Simple error handling: delete and recreate on any issue
- No migration logic - fresh start approach
- Files stored alongside current SQLite DB in user app settings directory
- Comprehensive logging for debugging
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import os

from .json_schemas import (
    APP_SETTINGS_SCHEMA_VERSION,
    SEARCH_PROFILES_SCHEMA_VERSION,
    create_default_app_settings,
    create_default_search_profiles,
    validate_app_settings,
    validate_search_profiles,
    normalize_app_settings,
    normalize_search_profiles,
    check_schema_version
)

logger = logging.getLogger("pk_py_lib.core.settings.json_manager")


class JSONSettingsManager:
    """
    Manager for JSON-based application settings and search profiles.

    This class handles reading, writing, and validating JSON settings files.
    On any error (corruption, version mismatch, missing files), it creates
    fresh defaults and logs the issue.

    Attributes
    ----------
    settings_dir : Path
        Directory where JSON files are stored
    """

    def __init__(self, settings_dir: Path):
        """
        Initialize the JSON settings manager.

        Parameters
        ----------
        settings_dir : Path
            Directory where settings files will be stored
        """
        self.settings_dir = Path(settings_dir)
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.app_settings_file = self.settings_dir / "app-settings.json"
        self.search_profiles_file = self.settings_dir / "search-profiles.json"

        logger.info(f"JSON settings manager initialized for directory: {self.settings_dir}")

    def load_app_settings(self) -> Dict[str, Any]:
        """
        Load application settings from JSON file.

        Returns
        -------
        Dict[str, Any]
            Application settings, either loaded or fresh defaults

        Notes
        -----
        If file doesn't exist, is corrupted, or has wrong schema version,
        creates fresh defaults and reports the issue.
        """
        try:
            # Check if file exists
            if not self.app_settings_file.exists():
                logger.info("App settings file not found, creating defaults")
                return self._create_default_app_settings()

            # Read and parse file
            with open(self.app_settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate schema version
            if not check_schema_version(data, APP_SETTINGS_SCHEMA_VERSION):
                logger.warning(
                    f"App settings schema version mismatch (found: {data.get('version')}, "
                    f"expected: {APP_SETTINGS_SCHEMA_VERSION}), creating fresh defaults"
                )
                return self._create_default_app_settings()

            # Validate against schema
            validate_app_settings(data)

            # Normalize and return
            normalized = normalize_app_settings(data)
            logger.debug("Successfully loaded app settings")
            return normalized

        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.error(f"Error loading app settings: {e}, creating fresh defaults")
            return self._create_default_app_settings()
        except Exception as e:
            logger.error(f"Unexpected error loading app settings: {e}, creating fresh defaults")
            return self._create_default_app_settings()

    def save_app_settings(self, settings: Dict[str, Any]) -> None:
        """
        Save application settings to JSON file.

        Parameters
        ----------
        settings : Dict[str, Any]
            Settings data to save

        Notes
        -----
        Creates a backup before saving and handles errors gracefully.
        """
        try:
            # Ensure directory exists
            self.settings_dir.mkdir(parents=True, exist_ok=True)

            # Create backup if file exists
            if self.app_settings_file.exists():
                backup_file = self.app_settings_file.with_suffix('.json.bak')
                try:
                    backup_file.write_bytes(self.app_settings_file.read_bytes())
                except Exception as e:
                    logger.warning(f"Failed to create backup: {e}")

            # Validate before saving
            validate_app_settings(settings)

            # Write to temporary file first, then move
            temp_file = self.app_settings_file.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)

            # Atomic move
            temp_file.replace(self.app_settings_file)

            logger.debug("Successfully saved app settings")

        except Exception as e:
            logger.error(f"Error saving app settings: {e}")
            # Try to restore from backup if available
            backup_file = self.app_settings_file.with_suffix('.json.bak')
            if backup_file.exists():
                try:
                    backup_file.replace(self.app_settings_file)
                    logger.info("Restored app settings from backup")
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")

            raise

    def load_search_profiles(self) -> Dict[str, Any]:
        """
        Load search profiles from JSON file.

        Returns
        -------
        Dict[str, Any]
            Search profiles, either loaded or fresh defaults

        Notes
        -----
        If file doesn't exist, is corrupted, or has wrong schema version,
        creates fresh defaults and reports the issue.
        """
        try:
            # Check if file exists
            if not self.search_profiles_file.exists():
                logger.info("Search profiles file not found, creating defaults")
                return self._create_default_search_profiles()

            # Read and parse file
            with open(self.search_profiles_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate schema version
            if not check_schema_version(data, SEARCH_PROFILES_SCHEMA_VERSION):
                logger.warning(
                    f"Search profiles schema version mismatch (found: {data.get('version')}, "
                    f"expected: {SEARCH_PROFILES_SCHEMA_VERSION}), creating fresh defaults"
                )
                return self._create_default_search_profiles()

            # Validate against schema
            validate_search_profiles(data)

            # Normalize and return
            normalized = normalize_search_profiles(data)
            logger.debug("Successfully loaded search profiles")
            return normalized

        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.error(f"Error loading search profiles: {e}, creating fresh defaults")
            return self._create_default_search_profiles()
        except Exception as e:
            logger.error(f"Unexpected error loading search profiles: {e}, creating fresh defaults")
            return self._create_default_search_profiles()

    def save_search_profiles(self, profiles: Dict[str, Any]) -> None:
        """
        Save search profiles to JSON file.

        Parameters
        ----------
        profiles : Dict[str, Any]
            Profiles data to save

        Notes
        -----
        Creates a backup before saving and handles errors gracefully.
        """
        try:
            # Ensure directory exists
            self.settings_dir.mkdir(parents=True, exist_ok=True)

            # Create backup if file exists
            if self.search_profiles_file.exists():
                backup_file = self.search_profiles_file.with_suffix('.json.bak')
                try:
                    backup_file.write_bytes(self.search_profiles_file.read_bytes())
                except Exception as e:
                    logger.warning(f"Failed to create backup: {e}")

            # Validate before saving
            validate_search_profiles(profiles)

            # Write to temporary file first, then move
            temp_file = self.search_profiles_file.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(profiles, f, indent=2, ensure_ascii=False)

            # Atomic move
            temp_file.replace(self.search_profiles_file)

            logger.debug("Successfully saved search profiles")

        except Exception as e:
            logger.error(f"Error saving search profiles: {e}")
            # Try to restore from backup if available
            backup_file = self.search_profiles_file.with_suffix('.json.bak')
            if backup_file.exists():
                try:
                    backup_file.replace(self.search_profiles_file)
                    logger.info("Restored search profiles from backup")
                except Exception as restore_error:
                    logger.error(f"Failed to restore from backup: {restore_error}")

            raise

    def _create_default_app_settings(self) -> Dict[str, Any]:
        """Create and save default app settings."""
        defaults = create_default_app_settings()
        try:
            self.save_app_settings(defaults)
            logger.info("Created default app settings")
        except Exception as e:
            logger.error(f"Failed to save default app settings: {e}")
        return defaults

    def _create_default_search_profiles(self) -> Dict[str, Any]:
        """Create and save default search profiles."""
        defaults = create_default_search_profiles()
        try:
            self.save_search_profiles(defaults)
            logger.info("Created default search profiles")
        except Exception as e:
            logger.error(f"Failed to save default search profiles: {e}")
        return defaults

    def reset_to_defaults(self) -> None:
        """
        Reset both settings files to defaults.

        This method forcibly removes existing files and creates fresh defaults.
        Use with caution as it will lose all current settings.
        """
        logger.info("Resetting all settings to defaults")

        # Remove existing files
        for file_path in [self.app_settings_file, self.search_profiles_file]:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.debug(f"Removed existing file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to remove {file_path}: {e}")

        # Create fresh defaults
        self._create_default_app_settings()
        self._create_default_search_profiles()

        logger.info("Successfully reset all settings to defaults")

    def get_file_paths(self) -> Dict[str, Path]:
        """
        Get paths to all settings files.

        Returns
        -------
        Dict[str, Path]
            Dictionary mapping file types to their paths
        """
        return {
            "app_settings": self.app_settings_file,
            "search_profiles": self.search_profiles_file
        }


class SettingsFileManager:
    """
    High-level manager for settings files with error reporting.

    This class provides a simplified interface for managing settings
    and includes comprehensive error reporting for both terminal and GUI.
    """

    def __init__(self, settings_dir: Path):
        """
        Initialize the settings file manager.

        Parameters
        ----------
        settings_dir : Path
            Directory where settings files will be stored
        """
        self.json_manager = JSONSettingsManager(settings_dir)
        self._app_settings: Optional[Dict[str, Any]] = None
        self._search_profiles: Optional[Dict[str, Any]] = None

    def load_all_settings(self) -> Dict[str, Any]:
        """
        Load all settings with error reporting.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing both app settings and search profiles

        Notes
        -----
        Reports any issues in both terminal (logging) and prepares for GUI reporting.
        """
        issues = []

        # Load app settings
        try:
            self._app_settings = self.json_manager.load_app_settings()
        except Exception as e:
            issues.append(f"Failed to load app settings: {e}")
            logger.error(f"App settings error: {e}")

        # Load search profiles
        try:
            self._search_profiles = self.json_manager.load_search_profiles()
        except Exception as e:
            issues.append(f"Failed to load search profiles: {e}")
            logger.error(f"Search profiles error: {e}")

        # Report issues
        if issues:
            issue_report = "Settings Issues Found:\n" + "\n".join(f"- {issue}" for issue in issues)
            logger.warning(issue_report)
            # TODO: Report to GUI when GUI components are updated

        return {
            "app_settings": self._app_settings,
            "search_profiles": self._search_profiles,
            "issues": issues
        }

    def get_app_settings(self) -> Dict[str, Any]:
        """Get cached app settings, loading if necessary."""
        if self._app_settings is None:
            self._app_settings = self.json_manager.load_app_settings()
        return self._app_settings

    def get_search_profiles(self) -> Dict[str, Any]:
        """Get cached search profiles, loading if necessary."""
        if self._search_profiles is None:
            self._search_profiles = self.json_manager.load_search_profiles()
        return self._search_profiles

    def save_app_settings(self, settings: Dict[str, Any]) -> None:
        """Save app settings and update cache."""
        self.json_manager.save_app_settings(settings)
        self._app_settings = settings

    def save_search_profiles(self, profiles: Dict[str, Any]) -> None:
        """Save search profiles and update cache."""
        self.json_manager.save_search_profiles(profiles)
        self._search_profiles = profiles

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.json_manager.reset_to_defaults()
        self._app_settings = None
        self._search_profiles = None


__all__ = [
    "JSONSettingsManager",
    "SettingsFileManager"
]
