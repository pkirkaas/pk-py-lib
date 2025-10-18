"""
JSON-based search profiles manager.

This module provides a replacement for the SQLite-based ProfilesManager
that uses JSON files for storage instead.

Design Notes:
- Maintains the same interface as the original ProfilesManager for compatibility
- Uses JSON files stored in the user settings directory
- Simple error handling: delete and recreate on any issues
- No migration logic - fresh start approach
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from threading import Lock

from ..models.settings import SettingsProfile
from .json_manager import SettingsFileManager

logger = logging.getLogger("pk_py_lib.core.settings.json_profiles")


class JSONProfilesManager:
    """
    JSON-based manager for search profile configurations.

    This class provides the same interface as the original ProfilesManager
    but uses JSON files for storage instead of SQLite database.

    Attributes
    ----------
    settings_dir : Path
        Directory where settings files are stored
    """

    def __init__(self, settings_dir: Path):
        """
        Initialize the JSON profiles manager.

        Parameters
        ----------
        settings_dir : Path
            Directory where settings files will be stored
        """
        self.settings_dir = Path(settings_dir)
        self.file_manager = SettingsFileManager(self.settings_dir)
        self._profiles: List[SettingsProfile] = []
        self._lock = Lock()
        self._next_id = 1  # Track next available sequential ID

        logger.info(f"JSON profiles manager initialized for directory: {self.settings_dir}")

    def create(self, profile: SettingsProfile) -> SettingsProfile:
        """
        Create a new profile.

        Parameters
        ----------
        profile : SettingsProfile
            Profile to create

        Returns
        -------
        SettingsProfile
            Created profile with ID assigned

        Raises
        ------
        ValueError
            If profile name already exists
        """
        with self._lock:
            logger.debug(f"Creating profile: {profile.name}")

            # Check for duplicate names
            if self._name_exists(profile.name):
                raise ValueError(f"Profile with name '{profile.name}' already exists")

            # Assign ID if not present
            if profile.id is None:
                profile.id = self._next_id
                self._next_id += 1

            # Set timestamps
            now = datetime.now()
            if profile.created_at is None:
                profile.created_at = now
            profile.updated_at = now

            # Add to profiles list
            self._profiles.append(profile)

            # Save to file
            self._save_profiles()

            logger.debug(f"Successfully created profile: {profile.name} (ID: {profile.id})")
            return profile

    def get_by_id(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get profile by ID.

        Parameters
        ----------
        profile_id : int
            Profile ID to look for

        Returns
        -------
        Optional[SettingsProfile]
            Profile if found, None otherwise
        """
        self._ensure_loaded()

        for profile in self._profiles:
            if profile.id == profile_id:
                return profile
        return None

    def get_all(self) -> List[SettingsProfile]:
        """
        Get all profiles.

        Returns
        -------
        List[SettingsProfile]
            List of all profiles
        """
        self._ensure_loaded()
        return self._profiles.copy()

    def get_default(self) -> SettingsProfile:
        """
        Get the default profile.

        Returns
        -------
        SettingsProfile
            Default profile

        Raises
        ------
        RuntimeError
            If no default profile found
        """
        self._ensure_loaded()

        for profile in self._profiles:
            if profile.is_default:
                return profile

        # If no default is set, make the first profile default
        if self._profiles:
            self._profiles[0].is_default = True
            self._save_profiles()
            return self._profiles[0]

        raise RuntimeError("No profiles available")

    def get_active(self) -> Optional[SettingsProfile]:
        """
        Get the active (default) profile.

        Returns
        -------
        Optional[SettingsProfile]
            Active profile if found, None otherwise
        """
        try:
            return self.get_default()
        except RuntimeError:
            return None

    def update(self, profile: SettingsProfile) -> None:
        """
        Update an existing profile.

        Parameters
        ----------
        profile : SettingsProfile
            Profile to update (must have ID set)

        Raises
        ------
        ValueError
            If profile ID is not set or profile not found
        """
        with self._lock:
            if profile.id is None:
                raise ValueError("Profile ID must be set for update")

            logger.debug(f"Updating profile: {profile.name} (ID: {profile.id})")

            # Find and update profile
            for i, existing_profile in enumerate(self._profiles):
                if existing_profile.id == profile.id:
                    # Check for name conflicts with other profiles
                    if existing_profile.name != profile.name and self._name_exists(profile.name):
                        raise ValueError(f"Profile with name '{profile.name}' already exists")

                    # Update profile
                    profile.updated_at = datetime.now()
                    self._profiles[i] = profile

                    # Save to file
                    self._save_profiles()

                    logger.debug(f"Successfully updated profile: {profile.name}")
                    return

            raise ValueError(f"Profile with ID {profile.id} not found")

    def set_active(self, profile_id: int) -> bool:
        """
        Set the specified profile as the active (default) profile.

        Parameters
        ----------
        profile_id : int
            ID of profile to set as active

        Returns
        -------
        bool
            True if successful, False if profile not found
        """
        with self._lock:
            logger.debug(f"Setting profile {profile_id} as active")

            # Find profile and update default status
            found = False
            for profile in self._profiles:
                if profile.id == profile_id:
                    profile.is_default = True
                    found = True
                else:
                    profile.is_default = False

            if found:
                self._save_profiles()
                logger.debug(f"Successfully set profile {profile_id} as active")
                return True
            else:
                logger.warning(f"Profile {profile_id} not found for activation")
                return False

    def validate_name(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """
        Validate if the given profile name is unique.

        Parameters
        ----------
        name : str
            Profile name to validate
        exclude_id : Optional[int]
            ID of profile to exclude from check (for updates)

        Returns
        -------
        bool
            True if name is unique, False otherwise
        """
        if not name or not isinstance(name, str):
            return False

        self._ensure_loaded()

        for profile in self._profiles:
            if profile.id != exclude_id and profile.name.lower() == name.lower():
                return False
        return True

    def delete(self, profile_id: int) -> bool:
        """
        Delete a profile.

        Parameters
        ----------
        profile_id : int
            ID of profile to delete

        Returns
        -------
        bool
            True if deleted, False if not found
        """
        with self._lock:
            logger.debug(f"Deleting profile {profile_id}")

            # Find and remove profile
            for i, profile in enumerate(self._profiles):
                if profile.id == profile_id:
                    # Don't allow deletion of system profiles
                    if profile.is_system:
                        logger.warning(f"Cannot delete system profile: {profile.name}")
                        return False

                    # Remove profile
                    del self._profiles[i]

                    # Save to file
                    self._save_profiles()

                    logger.debug(f"Successfully deleted profile {profile_id}")
                    return True

            logger.warning(f"Profile {profile_id} not found for deletion")
            return False

    def _name_exists(self, name: str) -> bool:
        """Check if a profile name already exists."""
        return not self.validate_name(name)

    def _ensure_loaded(self) -> None:
        """Ensure profiles are loaded from file."""
        if not self._profiles:
            self._load_profiles()

    def _load_profiles(self) -> None:
        """Load profiles from JSON file."""
        try:
            profiles_data = self.file_manager.get_search_profiles()
            profiles_list = profiles_data.get("profiles", [])

            self._profiles = []
            max_id = 0
            for profile_dict in profiles_list:
                try:
                    # Handle ID conversion from UUID strings to integers
                    original_id = profile_dict.get('id')
                    if isinstance(original_id, str):
                        # If ID is a UUID string, assign a new sequential ID
                        profile_dict['id'] = self._next_id
                        self._next_id += 1
                        logger.info(f"Converted UUID profile ID '{original_id}' to integer {profile_dict['id']}")
                    elif isinstance(original_id, int):
                        # Check if integer ID is within Qt's 64-bit signed integer range
                        if original_id > 2**63 - 1 or original_id < -2**63:
                            # ID is too large for Qt, assign a new sequential ID
                            logger.warning(f"Profile ID {original_id} exceeds Qt 64-bit range, converting to sequential ID {self._next_id}")
                            profile_dict['id'] = self._next_id
                            self._next_id += 1
                        else:
                            # Track maximum integer ID to set next_id
                            if original_id > max_id:
                                max_id = original_id

                    # Convert dictionary to SettingsProfile
                    profile = self._dict_to_profile(profile_dict)
                    self._profiles.append(profile)
                except Exception as e:
                    logger.warning(f"Error loading profile {profile_dict.get('name', 'unknown')}: {e}")

            # Set next_id to max_id + 1, but at least 1
            self._next_id = max(max_id, 0) + 1
            logger.info(f"Loaded {len(self._profiles)} profiles from JSON file, next_id={self._next_id}")

            logger.debug(f"Loaded {len(self._profiles)} profiles from JSON file, next_id={self._next_id}")

        except Exception as e:
            logger.error(f"Error loading profiles: {e}, creating defaults")
            self._create_default_profiles()

    def _save_profiles(self) -> None:
        """Save profiles to JSON file."""
        try:
            # Convert profiles to dictionaries
            profiles_list = []
            for profile in self._profiles:
                try:
                    profile_dict = self._profile_to_dict(profile)
                    profiles_list.append(profile_dict)
                except Exception as e:
                    logger.error(f"Error converting profile {profile.name} to dict: {e}")

            # Add version field required by schema
            profiles_data = {"version": 1, "profiles": profiles_list}
            self.file_manager.save_search_profiles(profiles_data)

            logger.debug(f"Saved {len(profiles_list)} profiles to JSON file")

        except Exception as e:
            logger.error(f"Error saving profiles: {e}")
            raise

    def _create_default_profiles(self) -> None:
        """Create default system profiles."""
        logger.info("Creating default system profiles")

        now = datetime.now()

        # Create default profiles based on the model defaults
        default_profiles_data = [
            {
                "id": 1,  # Use simple IDs for defaults
                "name": "Exact Duplicates",
                "description": "Find exact duplicate files using xxh3 hashing",
                "mode": "duplicates",
                "algorithm": "xxh3",
                "clustering_method": "dbscan",
                "is_default": True,
                "is_system": True,
                "created_at": now,
                "updated_at": now
            },
            {
                "id": 2,
                "name": "Very Similar",
                "description": "Find very similar images with strict matching (95% similarity)",
                "mode": "similarity",
                "algorithm": "phash",
                "hash_size": 8,
                "similarity_threshold": 0.95,
                "clustering_method": "dbscan",
                "is_system": True,
                "created_at": now,
                "updated_at": now
            },
            {
                "id": 3,
                "name": "Similar Images",
                "description": "Find similar images with moderate matching (90% similarity)",
                "mode": "similarity",
                "algorithm": "phash",
                "hash_size": 8,
                "similarity_threshold": 0.90,
                "clustering_method": "dbscan",
                "is_system": True,
                "created_at": now,
                "updated_at": now
            }
        ]

        self._profiles = []
        for profile_data in default_profiles_data:
            try:
                profile = self._dict_to_profile(profile_data)
                self._profiles.append(profile)
            except Exception as e:
                logger.error(f"Error creating default profile {profile_data['name']}: {e}")

        # Save defaults
        self._save_profiles()

        # Set next_id to maximum ID + 1
        max_id = max(profile.id for profile in self._profiles)
        self._next_id = max_id + 1

        logger.info(f"Created {len(self._profiles)} default profiles, next_id={self._next_id}")

    def _dict_to_profile(self, data: Dict[str, Any]) -> SettingsProfile:
        """Convert dictionary to SettingsProfile object."""
        # Convert datetime strings
        for dt_field in ['created_at', 'updated_at']:
            if dt_field in data and isinstance(data[dt_field], str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        # Convert boolean fields
        for bool_field in ['color_mode', 'is_default', 'is_system']:
            if bool_field in data:
                data[bool_field] = bool(data[bool_field])

        return SettingsProfile(**data)

    def _profile_to_dict(self, profile: SettingsProfile) -> Dict[str, Any]:
        """Convert SettingsProfile object to dictionary."""
        data = profile.to_dict()

        # Convert datetime objects to strings
        for dt_field in ['created_at', 'updated_at']:
            if dt_field in data and isinstance(data[dt_field], datetime):
                data[dt_field] = data[dt_field].isoformat()

        return data

    def reload(self) -> None:
        """Reload profiles from file."""
        self._profiles = []
        self._load_profiles()


__all__ = ["JSONProfilesManager"]
