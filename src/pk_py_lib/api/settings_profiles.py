"""
src/pk_py_lib/api/settings_profiles.py

DEPRECATED: Legacy Settings Profiles API

This module is deprecated. Use src.pk_py_lib.api.settings.UnifiedSettingsAPI instead.

This API is maintained for backward compatibility and now acts as a thin wrapper
around the unified settings API.

All methods return ApiResponse per the project conventions.

Logging namespace: "pk_py_lib.settings_profiles"

Note: Syntax validation performed per project rules using Python ast prior to inclusion.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, Iterable, List, Optional

# Import the unified API
from .settings.unified_api import UnifiedSettingsAPI
from . import ApiResponse


class SettingsProfilesAPI:
    """
    DEPRECATED: High-level API for Settings Profiles

    This class is deprecated. Use src.pk_py_lib.api.settings.UnifiedSettingsAPI instead.

    This class is maintained for backward compatibility and now acts as a wrapper
    around the unified settings API.

    Parameters
    ----------
    db_manager : Optional[DatabaseManager]
        If omitted, a default DatabaseManager is created and initialized.

    Examples
    --------
    >>> api = SettingsProfilesAPI()  # DEPRECATED - use UnifiedSettingsAPI instead
    >>> ok = api.ensure_default_profile().success
    >>> r = api.create(name="My Flow", description="workflow", make_active=True)
    >>> r.success and r.data["is_active"]
    True
    """

    def __init__(self, db_manager: Optional["DatabaseManager"] = None):
        """
        Initialize the deprecated settings profiles API.

        Parameters
        ----------
        db_manager : Optional[DatabaseManager]
            Database manager instance. If None, creates and initializes a default one.
        """
        warnings.warn(
            "SettingsProfilesAPI is deprecated. Use src.pk_py_lib.api.settings.UnifiedSettingsAPI instead.",
            DeprecationWarning,
            stacklevel=2
        )

        if db_manager is None:
            from ..core.database import DatabaseManager
            db_manager = DatabaseManager()
            db_manager.initialize()
        self.db = db_manager
        self.unified_api = UnifiedSettingsAPI(db_manager)

    def ensure_default_profile(self) -> ApiResponse[Dict[str, Any]]:
        """Ensure at least one profile exists and exactly one is active; create 'Default' if needed."""
        warnings.warn(
            "ensure_default_profile is deprecated. Use UnifiedSettingsAPI.ensure_default_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.ensure_default_profile()

    def list_profiles(self) -> ApiResponse[List[Dict[str, Any]]]:
        """List profiles enriched with item_count."""
        warnings.warn(
            "list_profiles is deprecated. Use UnifiedSettingsAPI.list_profiles instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.list_profiles()

    def get_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Get a profile by UUID."""
        warnings.warn(
            "get_profile is deprecated. Use UnifiedSettingsAPI.get_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.get_profile(profile_id)

    def create(self, name: str, description: Optional[str] = None,
               make_active: bool = False, json_data: Optional[Dict[str, Any]] = None) -> ApiResponse[Dict[str, Any]]:
        """Create a new profile."""
        warnings.warn(
            "create is deprecated. Use UnifiedSettingsAPI.create_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.create_profile(name, description, make_active, json_data)

    def update(self, profile_id: str, name: Optional[str] = None,
               description: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None) -> ApiResponse[Dict[str, Any]]:
        """Update profile's name, description, and/or JSON data."""
        warnings.warn(
            "update is deprecated. Use UnifiedSettingsAPI.update_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.update_profile(profile_id, name, description, json_data)

    def delete(self, profile_id: str) -> ApiResponse[bool]:
        """Delete a profile."""
        warnings.warn(
            "delete is deprecated. Use UnifiedSettingsAPI.delete_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.delete_profile(profile_id)

    def duplicate(self, source_profile_id: str, new_name: str,
                  description: Optional[str] = None, make_active: bool = False) -> ApiResponse[Dict[str, Any]]:
        """Duplicate a profile under a new unique name."""
        warnings.warn(
            "duplicate is deprecated. Use UnifiedSettingsAPI.duplicate_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.duplicate_profile(source_profile_id, new_name, description, make_active)

    def get_active(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """Get the active profile."""
        warnings.warn(
            "get_active is deprecated. Use UnifiedSettingsAPI.get_active_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.get_active_profile()

    def set_active(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Set a profile as active."""
        warnings.warn(
            "set_active is deprecated. Use UnifiedSettingsAPI.set_active_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.set_active_profile(profile_id)

    def validate_name(self, name: str) -> ApiResponse[bool]:
        """Validate a profile name."""
        warnings.warn(
            "validate_name is deprecated. Use UnifiedSettingsAPI.validate_profile_name instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.validate_profile_name(name)

    def validate_keys(self, keys: Iterable[str]) -> ApiResponse[bool]:
        """Validate keys against canonical rules."""
        warnings.warn(
            "validate_keys is deprecated. Use UnifiedSettingsAPI.validate_keys instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.validate_keys(keys)

    def get_values(self, profile_id: str, keys: Optional[List[str]] = None) -> ApiResponse[Dict[str, Any]]:
        """Get values for a profile."""
        warnings.warn(
            "get_values is deprecated. Use UnifiedSettingsAPI.get_profile_values instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.get_profile_values(profile_id, keys)

    def set_values(self, profile_id: str, values: Dict[str, Any]) -> ApiResponse[Dict[str, Any]]:
        """Upsert key/value pairs for a profile."""
        warnings.warn(
            "set_values is deprecated. Use UnifiedSettingsAPI.set_profile_values instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.set_profile_values(profile_id, values)

    def remove_values(self, profile_id: str, keys: List[str]) -> ApiResponse[Dict[str, Any]]:
        """Remove keys for a profile."""
        warnings.warn(
            "remove_values is deprecated. Use UnifiedSettingsAPI.remove_profile_values instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.remove_profile_values(profile_id, keys)

    def export_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Export a profile into a JSON-serializable dictionary."""
        warnings.warn(
            "export_profile is deprecated. Use UnifiedSettingsAPI.export_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.export_profile(profile_id)

    def import_profile(self, payload: Dict[str, Any], strategy: str = "rename", make_active: bool = False) -> ApiResponse[Dict[str, Any]]:
        """Import a profile payload."""
        warnings.warn(
            "import_profile is deprecated. Use UnifiedSettingsAPI.import_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.import_profile(payload, strategy, make_active)

    def migrate_to_json_format(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Migrate a legacy profile to JSON format."""
        warnings.warn(
            "migrate_to_json_format is deprecated. Use UnifiedSettingsAPI.migrate_to_json_format instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.migrate_to_json_format(profile_id)

    def validate_profile_for_save(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Validate if a profile is valid for saving."""
        warnings.warn(
            "validate_profile_for_save is deprecated. Use UnifiedSettingsAPI.validate_profile_for_save instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.validate_profile_for_save(profile_id)

    def validate_profile_for_run(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """Validate if a profile is valid for running."""
        warnings.warn(
            "validate_profile_for_run is deprecated. Use UnifiedSettingsAPI.validate_profile_for_run instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.validate_profile_for_run(profile_id)

    def get_json_schema(self) -> ApiResponse[Dict[str, Any]]:
        """Get the JSON schema for SettingsProfileOptionA."""
        warnings.warn(
            "get_json_schema is deprecated. Use UnifiedSettingsAPI.get_json_schema instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.get_json_schema()

    def create_default_json_profile(self, name: str, description: Optional[str] = None) -> ApiResponse[Dict[str, Any]]:
        """Create a new profile with default JSON schema values."""
        warnings.warn(
            "create_default_json_profile is deprecated. Use UnifiedSettingsAPI.create_default_json_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.create_default_json_profile(name, description)

    def suggest_unique_name(self, base_name: str) -> ApiResponse[str]:
        """Suggest a unique profile name based on the given base name."""
        warnings.warn(
            "suggest_unique_name is deprecated. Use UnifiedSettingsAPI.suggest_unique_name instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.unified_api.suggest_unique_name(base_name)


__all__ = ["SettingsProfilesAPI"]
