"""
Unified settings API for pk-py-lib.

This module provides a clean, consistent API for managing application
settings and profiles with proper error handling and validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from ....core.logging.logger import get_logger
from ....core.api.response import ApiResponse, ErrorCodes, create_success_response, create_error_response
from ...core.database import DatabaseManager
from ...core.settings.manager import UnifiedSettingsManager


logger = get_logger(__name__)


class UnifiedSettingsAPI:
    """
    Unified API for application settings and profile management.

    This API provides a single interface for managing both application-wide
    settings and user profiles with consistent error handling and validation.
    """

    def __init__(self, database_manager: Optional[DatabaseManager] = None):
        """
        Initialize the unified settings API.

        Args:
            database_manager: Optional database manager instance
        """
        self.database_manager = database_manager or DatabaseManager()
        self.settings_manager = UnifiedSettingsManager(self.database_manager)
        self.logger = get_logger(__name__)

    def ensure_default_profile(self) -> ApiResponse[str]:
        """
        Ensure a default profile exists.

        Returns:
            ApiResponse with the name of the default profile
        """
        try:
            profile_name = self.settings_manager.ensure_default_profile()
            return create_success_response(profile_name)
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def list_profiles(self) -> ApiResponse[List[Dict[str, Any]]]:
        """
        List all available settings profiles.

        Returns:
            ApiResponse with list of profile dictionaries
        """
        try:
            profiles = self.settings_manager.list_profiles()
            profile_dicts = [profile.to_dict() for profile in profiles]
            return create_success_response(profile_dicts)
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def get_profile(self, profile_id: str) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get a specific profile by ID.

        Args:
            profile_id: Profile ID to retrieve

        Returns:
            ApiResponse with profile dictionary or None if not found
        """
        try:
            profile = self.settings_manager.get_profile(profile_id)
            if profile:
                return create_success_response(profile.to_dict())
            else:
                return create_error_response(
                    f"Profile not found: {profile_id}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def get_active_profile(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get the currently active profile.

        Returns:
            ApiResponse with active profile dictionary or None if none active
        """
        try:
            profile = self.settings_manager.get_active_profile()
            if profile:
                return create_success_response(profile.to_dict())
            else:
                return create_error_response(
                    "No active profile set",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Create a new settings profile.

        Args:
            name: Profile name
            description: Optional description
            json_data: Optional JSON configuration data

        Returns:
            ApiResponse with created profile dictionary
        """
        try:
            profile = self.settings_manager.create_profile(name, description, json_data)
            if profile:
                return create_success_response(profile.to_dict())
            else:
                return create_error_response(
                    f"Failed to create profile: {name}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def update_profile(
        self,
        profile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Update an existing profile.

        Args:
            profile_id: Profile ID to update
            name: Optional new name
            description: Optional new description
            json_data: Optional new JSON data

        Returns:
            ApiResponse with updated profile dictionary
        """
        try:
            success = self.settings_manager.update_profile(
                profile_id, name, description, json_data
            )
            if success:
                profile = self.settings_manager.get_profile(profile_id)
                if profile:
                    return create_success_response(profile.to_dict())
                else:
                    return create_error_response(
                        f"Profile not found after update: {profile_id}",
                        ErrorCodes.INVALID_CONFIG
                    )
            else:
                return create_error_response(
                    f"Failed to update profile: {profile_id}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def delete_profile(self, profile_id: str) -> ApiResponse[bool]:
        """
        Delete a profile.

        Args:
            profile_id: Profile ID to delete

        Returns:
            ApiResponse with success status
        """
        try:
            success = self.settings_manager.delete_profile(profile_id)
            if success:
                return create_success_response(True)
            else:
                return create_error_response(
                    f"Failed to delete profile: {profile_id}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def set_active_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Set a profile as active.

        Args:
            profile_id: Profile ID to activate

        Returns:
            ApiResponse with activated profile dictionary
        """
        try:
            success = self.settings_manager.set_active_profile(profile_id)
            if success:
                profile = self.settings_manager.get_profile(profile_id)
                if profile:
                    return create_success_response(profile.to_dict())
                else:
                    return create_error_response(
                        f"Profile not found after activation: {profile_id}",
                        ErrorCodes.INVALID_CONFIG
                    )
            else:
                return create_error_response(
                    f"Failed to activate profile: {profile_id}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def validate_profile_name(self, name: str) -> ApiResponse[bool]:
        """
        Validate a profile name.

        Args:
            name: Profile name to validate

        Returns:
            ApiResponse with validation result
        """
        try:
            is_valid = self.settings_manager.validate_profile_name(name)
            return create_success_response(is_valid)
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def export_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Export a profile to dictionary format.

        Args:
            profile_id: Profile ID to export

        Returns:
            ApiResponse with profile data
        """
        try:
            profile = self.settings_manager.get_profile(profile_id)
            if profile:
                return create_success_response(profile.to_dict())
            else:
                return create_error_response(
                    f"Profile not found: {profile_id}",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def import_profile(
        self,
        profile_data: Dict[str, Any],
        strategy: str = "fail_on_conflict"
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Import a profile from dictionary format.

        Args:
            profile_data: Profile data to import
            strategy: Conflict resolution strategy

        Returns:
            ApiResponse with imported profile dictionary
        """
        try:
            # This will be implemented with conflict resolution
            profile = self.settings_manager.import_profile(profile_data, strategy)
            if profile:
                return create_success_response(profile.to_dict())
            else:
                return create_error_response(
                    "Failed to import profile",
                    ErrorCodes.INVALID_CONFIG
                )
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def get_app_settings(self) -> ApiResponse[Dict[str, Any]]:
        """
        Get current application settings.

        Returns:
            ApiResponse with app settings dictionary
        """
        try:
            settings = self.settings_manager.get_app_settings()
            return create_success_response(settings.to_dict())
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)

    def update_app_settings(self, updates: Dict[str, Any]) -> ApiResponse[Dict[str, Any]]:
        """
        Update application settings.

        Args:
            updates: Settings to update

        Returns:
            ApiResponse with updated app settings dictionary
        """
        try:
            settings = self.settings_manager.update_app_settings(updates)
            return create_success_response(settings.to_dict())
        except Exception as e:
            return create_error_response(e, ErrorCodes.UNKNOWN_ERROR)
