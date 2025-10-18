"""
DEPRECATED: Legacy SQLite-based settings profiles manager.

This module is deprecated. Use JSON-based settings instead:
- src/pk_py_lib/core/settings/json_profiles.py
- src/pk_py_lib/core/settings/json_unified_manager.py

This manager is maintained for backward compatibility but now uses
JSON settings internally to avoid creating SQLite settings.db files.
"""

import logging
import warnings
from pathlib import Path
from typing import Optional, List
from threading import Lock

from ..models.settings import SettingsProfile, DEFAULT_PROFILES
from .json_profiles import JSONProfilesManager

logger = logging.getLogger("pk_py_lib.core.settings.profiles")


class ProfilesManager:
    """
    DEPRECATED: Legacy SQLite-based settings profiles manager.

    This class is deprecated. Use JSON-based settings managers instead.
    Now acts as a wrapper around JSONProfilesManager to maintain
    backward compatibility while using JSON settings internally.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the deprecated profiles manager.

        Parameters
        ----------
        db_path : Path
            DEPRECATED - parameter is ignored, JSON settings are used instead.
        """
        warnings.warn(
            "ProfilesManager is deprecated. Use JSONProfilesManager instead.",
            DeprecationWarning,
            stacklevel=2
        )

        # Note: db_path parameter is deprecated and ignored
        # Use JSON settings manager instead of SQLite to avoid creating settings.db
        self.json_manager = JSONProfilesManager()
        self._lock = Lock()

    def create(self, profile: SettingsProfile) -> SettingsProfile:
        """
        Create a new profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.create() is deprecated. Use JSONProfilesManager.create() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug(f"Creating profile: {profile.name} (legacy compatibility mode)")
            return self.json_manager.create(profile)

    def get_by_id(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get profile by ID (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.get_by_id() is deprecated. Use JSONProfilesManager.get_by_id() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug(f"Getting profile by ID: {profile_id} (legacy compatibility mode)")
        return self.json_manager.get_by_id(profile_id)

    def get_all(self) -> List[SettingsProfile]:
        """
        Get all profiles (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.get_all() is deprecated. Use JSONProfilesManager.get_all() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug("Getting all profiles (legacy compatibility mode)")
        return self.json_manager.get_all()

    def get_default(self) -> SettingsProfile:
        """
        Get the default profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.get_default() is deprecated. Use JSONProfilesManager.get_default() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug("Getting default profile (legacy compatibility mode)")
        return self.json_manager.get_default()

    def get_active(self) -> Optional[SettingsProfile]:
        """
        Get the active settings profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.get_active() is deprecated. Use JSONProfilesManager.get_active() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug("Getting active profile (legacy compatibility mode)")
        return self.json_manager.get_active()

    def update(self, profile: SettingsProfile) -> None:
        """
        Update an existing profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.update() is deprecated. Use JSONProfilesManager.update() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug(f"Updating profile: {profile.name} (legacy compatibility mode)")
            self.json_manager.update(profile)

    def set_active(self, profile_id: int) -> bool:
        """
        Set the specified profile as the active (default) profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.set_active() is deprecated. Use JSONProfilesManager.set_active() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug(f"Setting active profile: {profile_id} (legacy compatibility mode)")
            return self.json_manager.set_active(profile_id)

    def validate_name(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """
        Validate if the given profile name is unique (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.validate_name() is deprecated. Use JSONProfilesManager.validate_name() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        logger.debug(f"Validating profile name: {name} (legacy compatibility mode)")
        return self.json_manager.validate_name(name, exclude_id)

    def delete(self, profile_id: int) -> bool:
        """
        Delete a profile (using JSON settings).
        """
        warnings.warn(
            "ProfilesManager.delete() is deprecated. Use JSONProfilesManager.delete() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        with self._lock:
            logger.debug(f"Deleting profile: {profile_id} (legacy compatibility mode)")
            return self.json_manager.delete(profile_id)
