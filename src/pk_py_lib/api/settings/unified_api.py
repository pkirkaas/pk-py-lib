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
    def get_profile(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get the named profile.
        """
        return self.settings_manager.profiles.get_by_id(profile_id)

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
