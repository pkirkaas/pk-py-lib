"""
src/pk_py_lib/api/settings_api.py

Lightweight adapter exposing a SettingsAPI that delegates to
src.pk_py_lib.core.configuration.ConfigurationManager.

This adapter provides a thin, well-typed surface aligned with the
API specification (docs/roo/img-app-api-specifications.md).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, List

from ...core.settings.manager import SettingsManager
from ...core.api.response import ApiResponse, ErrorCode
from ...core.models.settings import AppSettings, SettingsProfile


logger = logging.getLogger("pk_py_lib.api.settings.unified_api")


class UnifiedSettingsAPI:
    """
    Adapter that exposes configuration functions in an API-friendly shape.

    The adapter intentionally keeps the surface small and delegates heavy
    lifting to the underlying SettingsManager.
    """

    def __init__(self, settings_manager: Optional[SettingsManager] = None):
        """
        Initialize UnifiedSettingsAPI.

        Args:
            settings_manager: Optional SettingsManager. If omitted, a default
                              SettingsManager is created.
        """
        if settings_manager is None:
            settings_manager = SettingsManager()
        self.settings_manager = settings_manager

    # App-scoped methods
    def get_app_settings(self) -> AppSettings:
        """Return the strongly-typed AppSettings instance."""
        return self.settings_manager.app_settings.load()

    def update_app_settings(self, updates: Dict[str, Any]) -> AppSettings:
        """
        Apply partial updates to the AppSettings object and persist.
        """
        settings = self.get_app_settings()
        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.settings_manager.app_settings.save(settings)
        return self.get_app_settings()

    # Profile-scoped methods
    def get_profile(self, profile_id: int) -> ApiResponse:
        """
        Retrieve a specific settings profile by its ID.

        This method delegates to the underlying profiles manager to fetch the profile
        from the database using the provided profile_id. If the profile is found,
        it is wrapped in a success ApiResponse. If not found, an error ApiResponse
        is returned with a specific message indicating the profile does not exist.
        All exceptions are caught and wrapped in an error response for consistent
        error handling.

        Parameters
        ----------
        profile_id : int
            The unique integer ID of the profile to retrieve.

        Returns
        -------
        ApiResponse
            On success: success=True, data=SettingsProfile object for the requested profile.
            On failure:
                - If profile not found: success=False, message="Profile not found",
                  code=ErrorCode.SETTINGS_ERROR
                - On other errors: success=False, message=detailed error description,
                  code=ErrorCode.SETTINGS_ERROR

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This ensures the method always returns a valid ApiResponse object.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.get_profile(1)
        >>> if response.success:
        ...     profile = response.data  # SettingsProfile
        ...     print(f"Profile: {profile.name}")
        ... else:
        ...     print(f"Error: {response.message}")
        """
        try:
            # Delegate to core profiles manager to retrieve the profile by ID
            # This method returns SettingsProfile or None if not found
            profile = self.settings_manager.profiles.get_by_id(profile_id)
            if profile is None:
                # Specific handling for not found case
                # This is treated as a valid error state, not an exception
                return ApiResponse.error_response(
                    code=ErrorCode.SETTINGS_ERROR,
                    message=f"Profile with ID {profile_id} not found"
                )
            # Wrap in success response for consistent API contract
            return ApiResponse.success_response(data=profile)
        except Exception as e:
            # Log the full exception for debugging, including stack trace
            logger.error(
                f"Failed to get profile {profile_id}",
                exc_info=True,
                extra={"error": str(e), "profile_id": profile_id, "manager": "profiles"}
            )
            # Return error response with informative message
            # Use SETTINGS_ERROR code as this is a configuration retrieval failure
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to retrieve profile {profile_id}: {str(e)}"
            )

    def set_active(self, profile_id: int) -> ApiResponse:
        """
        Set the specified profile as the active (default) profile.

        This method delegates to the underlying profiles manager to update the database,
        setting is_default=1 for the given profile_id and is_default=0 for all others.
        It ensures only one profile is active at a time. On success, returns a success
        ApiResponse with data=True. On failure (e.g., profile not found, database error),
        returns an error ApiResponse with details. All exceptions are caught and wrapped.

        Parameters
        ----------
        profile_id : int
            The unique integer ID of the profile to set as active.

        Returns
        -------
        ApiResponse
            On success: success=True, data=True (simple boolean confirmation).
            On failure: success=False, message=detailed error description,
                        code=ErrorCode.SETTINGS_ERROR

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This method is robust and always returns a valid ApiResponse.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.set_active(1)
        >>> if response.success:
        ...     print("Profile set as active successfully")
        ... else:
        ...     print(f"Error: {response.message}")
        """
        try:
            # Delegate to core profiles manager to set the profile active
            # This method returns True on success, False if profile not found/updated
            success = self.settings_manager.profiles.set_active(profile_id)
            if success:
                # Wrap success in ApiResponse for consistent API contract
                return ApiResponse.success_response(data=True)
            else:
                # Profile not found or no rows affected
                return ApiResponse.error_response(
                    code=ErrorCode.SETTINGS_ERROR,
                    message=f"Failed to set profile {profile_id} as active: Profile not found or update failed"
                )
        except Exception as e:
            # Log the full exception for debugging, including stack trace
            logger.error(
                f"Failed to set active profile {profile_id}",
                exc_info=True,
                extra={"error": str(e), "profile_id": profile_id, "manager": "profiles"}
            )
            # Return error response with informative message
            # Use SETTINGS_ERROR code as this is a configuration update failure
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to set active profile {profile_id}: {str(e)}"
            )

    def list_profiles(self) -> ApiResponse:
        """
        Retrieve all available settings profiles.

        This method delegates to the underlying profiles manager to fetch all profiles
        from the database and wraps the result in an ApiResponse for consistent error
        handling, data access, and compatibility with callers expecting wrapped responses.

        The returned ApiResponse allows callers to check success status and access data
        via the .data attribute, or handle errors via .message and .code.

        Parameters
        ----------
        None

        Returns
        -------
        ApiResponse
            On success: success=True, data=list of SettingsProfile objects representing
                        all available profiles.
            On failure: success=False, message=detailed error description,
                        code=ErrorCode.SETTINGS_ERROR

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This ensures the method always returns a valid ApiResponse object.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.list_profiles()
        >>> if response.success:
        ...     profiles = response.data  # List[SettingsProfile]
        ...     for profile in profiles:
        ...         print(profile.name)
        ... else:
        ...     print(f"Error: {response.message}")
        """
        try:
            # Delegate to core profiles manager to retrieve all profiles
            # This method is expected to return a list of SettingsProfile objects
            profiles = self.settings_manager.profiles.get_all()
            # Wrap in success response for consistent API contract
            return ApiResponse.success_response(data=profiles)
        except Exception as e:
            # Log the full exception for debugging, including stack trace
            logger.error(
                "Failed to list profiles",
                exc_info=True,
                extra={"error": str(e), "manager": "profiles"}
            )
            # Return error response with informative message
            # Use SETTINGS_ERROR code as this is a configuration retrieval failure
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to retrieve profiles: {str(e)}"
            )

    def get_active(self) -> ApiResponse:
        """
        Retrieve the currently active settings profile.

        This method delegates to the underlying profiles manager to fetch the active
        profile from the database. The active profile is determined by the 'is_active'
        flag in the profiles table.

        If no active profile is set (e.g., during initial setup or if all profiles
        are inactive), an error response is returned with a specific message.
        All other exceptions are caught and wrapped in an error response.

        This ensures consistent error handling and allows callers to reliably access
        the active profile via the .data attribute or handle absence/errors gracefully.

        Parameters
        ----------
        None

        Returns
        -------
        ApiResponse
            On success: success=True, data=SettingsProfile object for the active profile.
            On failure:
                - If no active profile: success=False, message="No active profile set",
                  code=ErrorCode.SETTINGS_ERROR
                - On other errors: success=False, message=detailed error description,
                  code=ErrorCode.SETTINGS_ERROR

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This method is designed to be robust and always return a valid ApiResponse.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.get_active()
        >>> if response.success:
        ...     active_profile = response.data  # SettingsProfile
        ...     print(f"Active: {active_profile.name}")
        ... else:
        ...     if "No active profile set" in response.message:
        ...         print("No active profile; consider setting one.")
        ...     else:
        ...         print(f"Error: {response.message}")
        """
        try:
            # Delegate to core profiles manager to retrieve the active profile
            # Assumes get_active() returns SettingsProfile or None if not found
            active_profile = self.settings_manager.profiles.get_active()
            if active_profile is None:
                # Specific handling for no active profile case
                # This is not treated as an exception but as a valid error state
                return ApiResponse.error_response(
                    code=ErrorCode.SETTINGS_ERROR,
                    message="No active profile set"
                )
            # Wrap in success response for consistent API contract
            return ApiResponse.success_response(data=active_profile)
        except Exception as e:
            # Log the full exception for debugging, including stack trace
            logger.error(
                "Failed to get active profile",
                exc_info=True,
                extra={"error": str(e), "manager": "profiles"}
            )
            # Return error response with informative message
            # Use SETTINGS_ERROR code as this is a configuration retrieval failure
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to retrieve active profile: {str(e)}"
            )

    def validate_profile_name(self, name: str, exclude_id: Optional[int] = None) -> ApiResponse:
        """
        Validate whether the proposed profile name is unique in the database.

        This method delegates to the underlying ProfilesManager to check for existing
        profiles with the same name (case-insensitive). It excludes the profile with
        the specified exclude_id if provided, allowing updates to existing profiles
        without false positives. The validation is lightweight, performing a COUNT
        query on the database.

        On success, returns an ApiResponse with data=True if the name is unique (no
        duplicates found), or data=False if a duplicate exists. All exceptions are
        caught, logged with full details (including stack trace), and returned as an
        error ApiResponse with ErrorCode.SETTINGS_ERROR for consistent handling.

        Parameters
        ----------
        name : str
            The proposed profile name to validate. Must be a non-empty string.
            The check is case-insensitive (e.g., "Test" matches "test").
        exclude_id : Optional[int], optional
            The ID of an existing profile to exclude from the uniqueness check.
            Useful when updating a profile to allow keeping the same name.
            Defaults to None (checks against all profiles).

        Returns
        -------
        ApiResponse
            On success: success=True, data=bool (True if unique, False if duplicate exists).
            On failure: success=False, message=detailed error description,
                        code=ErrorCode.SETTINGS_ERROR (e.g., database error or invalid input).

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This ensures the method always returns a valid ApiResponse object.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.validate_profile_name("My New Profile")
        >>> if response.success:
        ...     is_unique = response.data
        ...     if is_unique:
        ...         print("Name is available")
        ...     else:
        ...         print("Name already exists")
        ... else:
        ...     print(f"Validation error: {response.message}")

        # Updating an existing profile
        >>> response = api.validate_profile_name("Updated Name", exclude_id=5)
        >>> if response.success and response.data:
        ...     # Proceed with update
        ...     pass

        Notes
        -----
        - Name validation rules: Non-empty string; case-insensitive uniqueness.
        - Edge cases: Empty name or invalid exclude_id results in error response.
        - Thread-safe: Delegates to ProfilesManager, which uses locking.
        - For full name rules (length, characters), use additional client-side validation.
        """
        try:
            if not name or not isinstance(name, str):
                return ApiResponse.error_response(
                    code=ErrorCode.SETTINGS_ERROR,
                    message="Profile name must be a non-empty string"
                )

            # Delegate to core profiles manager for validation
            is_valid = self.settings_manager.profiles.validate_name(name, exclude_id)

            # Wrap in success response with boolean data
            return ApiResponse.success_response(data=is_valid)

        except Exception as e:
            # Log the full exception for debugging, including stack trace
            logger.error(
                f"Failed to validate profile name '{name}'",
                exc_info=True,
                extra={
                    "error": str(e),
                    "name": name,
                    "exclude_id": exclude_id,
                    "manager": "profiles"
                }
            )
            # Return error response with informative message
            # Use SETTINGS_ERROR code as this is a configuration validation failure
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to validate profile name '{name}': {str(e)}"
            )

    def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        make_active: bool = False,
        json_data: Optional[Dict[str, Any]] = None
    ) -> ApiResponse:
        """
        Create a new settings profile.

        This method creates a new SettingsProfile with the provided parameters.
        If json_data is provided, it will be used to populate additional profile
        fields for structured profiles. After creation, if make_active is True,
        the new profile will be set as the active profile.

        Parameters
        ----------
        name : str
            The name of the new profile. Must be unique and non-empty.
        description : Optional[str], optional
            Optional description for the profile. Defaults to None.
        make_active : bool, optional
            Whether to set the new profile as active after creation. Defaults to False.
        json_data : Optional[Dict[str, Any]], optional
            Optional structured data for the profile. If provided, it will be used
            to populate profile fields. Defaults to None.

        Returns
        -------
        ApiResponse
            On success: success=True, data=SettingsProfile object for the created profile.
            On failure: success=False, message=detailed error description,
                        code=ErrorCode.SETTINGS_ERROR

        Raises
        ------
        None
            All exceptions are caught internally and wrapped in an error ApiResponse.
            This ensures the method always returns a valid ApiResponse object.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.create_profile("My Profile", description="A test profile")
        >>> if response.success:
        ...     profile = response.data  # SettingsProfile
        ...     print(f"Created: {profile.name}")
        ... else:
        ...     print(f"Error: {response.message}")

        # Create and set as active
        >>> response = api.create_profile("Active Profile", make_active=True)
        >>> if response.success:
        ...     print("Profile created and set as active")
        """
        try:
            # Validate required parameters
            if not name or not isinstance(name, str):
                return ApiResponse.error_response(
                    code=ErrorCode.SETTINGS_ERROR,
                    message="Profile name must be a non-empty string"
                )

            # Create the profile object
            if json_data:
                # For structured profiles, extract values from json_data
                profile = SettingsProfile(
                    name=name,
                    description=description or json_data.get("description", ""),
                    hash_algorithm=json_data.get("criteria", {}).get("similarity_hash_algorithm", "phash"),
                    hash_size=json_data.get("criteria", {}).get("hash_size", 8),
                    similarity_threshold=json_data.get("criteria", {}).get("similarity_threshold", 0.95),
                    min_resolution=json_data.get("criteria", {}).get("min_resolution"),
                    max_resolution=json_data.get("criteria", {}).get("max_resolution"),
                    color_mode=json_data.get("criteria", {}).get("color_mode", False),
                    clustering_method=json_data.get("criteria", {}).get("clustering_method", "dbscan"),
                    quality_threshold=json_data.get("criteria", {}).get("quality_threshold"),
                )
            else:
                # For simple profiles, use provided parameters with defaults
                profile = SettingsProfile(
                    name=name,
                    description=description or "",
                )

            # Create the profile using the settings manager
            created_profile = self.settings_manager.profiles.create(profile)

            # If make_active is True, set this profile as active
            if make_active:
                try:
                    success = self.settings_manager.profiles.set_active(created_profile.id)
                    if not success:
                        logger.warning(f"Failed to set profile {created_profile.id} as active")
                except Exception as active_error:
                    logger.error(
                        f"Error setting profile {created_profile.id} as active: {active_error}",
                        exc_info=True
                    )
                    # Don't fail the entire operation if setting active fails

            # Return success response with the created profile
            return ApiResponse.success_response(data=created_profile)

        except ValueError as e:
            # Handle validation errors (e.g., duplicate name)
            logger.error(
                f"Validation error creating profile '{name}': {e}",
                exc_info=True,
                extra={"name": name, "description": description, "make_active": make_active}
            )
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to create profile: {str(e)}"
            )
        except Exception as e:
            # Handle unexpected errors
            logger.error(
                f"Unexpected error creating profile '{name}': {e}",
                exc_info=True,
                extra={
                    "error": str(e),
                    "name": name,
                    "description": description,
                    "make_active": make_active,
                    "manager": "profiles"
                }
            )
            return ApiResponse.error_response(
                code=ErrorCode.SETTINGS_ERROR,
                message=f"Failed to create profile '{name}': {str(e)}"
            )



# Generic get/set
    def get_setting(self, key: str, default: Any = None, profile_id: Optional[int] = None) -> Any:
        """
        Get a setting value, automatically resolving scope when not provided.
        """
        # For simplicity, this example only supports getting app settings.
        # A more complete implementation would handle profile settings as well.
        try:
            settings = self.get_app_settings()
            return getattr(settings, key, default)
        except Exception:
            logger.exception("Error fetching setting %s", key)
            return default

    def set_setting(self, key: str, value: Any, profile_id: Optional[int] = None) -> bool:
        """
        Set a setting value in the indicated scope.
        """
        # For simplicity, this example only supports setting app settings.
        try:
            self.update_app_settings({key: value})
            return True
        except Exception:
            logger.exception("Failed to set setting %s=%s", key, value)
            return False

    # Export / import helpers
    def export_settings(self, path: Path, profile_id: Optional[int] = None) -> bool:
        """
        Export settings to a JSON file.
        """
        try:
            if profile_id:
                profile = self.get_profile(profile_id)
                if profile:
                    data = profile.to_dict()
                else:
                    return False
            else:
                data = self.get_app_settings().to_dict()

            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            logger.exception("Failed to export settings to %s", path)
            return False

    def import_settings(self, path: Path, profile: bool = False) -> bool:
        """
        Import settings JSON.
        """
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if profile:
                # A more complete implementation would handle profile creation/updates.
                pass
            else:
                self.update_app_settings(payload)
            return True
        except Exception:
            logger.exception("Failed to import settings from %s", path)
            return False

    def ensure_default_profile(self) -> ApiResponse:
        """
        Ensure that a default settings profile exists in the database.

        This method is idempotent: if default profiles already exist, it does nothing.
        It delegates to the underlying ProfilesManager to create system default profiles
        if none are present. The schema is ensured prior to profile creation.

        Parameters
        ----------
        None

        Returns
        -------
        ApiResponse
            A response object indicating success or failure.
            On success: success=True, data=the default profile
            On failure: success=False, message=error details

        Raises
        ------
        RuntimeError
            If schema creation or profile insertion fails critically.

        Examples
        --------
        >>> api = UnifiedSettingsAPI(settings_manager)
        >>> response = api.ensure_default_profile()
        >>> response.success
        True
        """
        try:
            # Delegate to profiles manager for schema and default profile creation
            # This is idempotent as _ensure_default_profiles checks if profiles exist
            self.settings_manager.profiles._ensure_schema()
            self.settings_manager.profiles._ensure_default_profiles()

            # Retrieve the default profile for confirmation
            default_profile = self.settings_manager.profiles.get_default()
            return ApiResponse.success_response(data=default_profile)
        except Exception as e:
            logger.error(
                "Failed to ensure default profile",
                exc_info=True,
                extra={"error": str(e), "db_path": str(self.settings_manager.profiles.db_path)}
            )
            return ApiResponse.error_response(code=ErrorCode.SETTINGS_ERROR, message=f"Failed to ensure default profile: {str(e)}")

__all__ = ["UnifiedSettingsAPI"]
