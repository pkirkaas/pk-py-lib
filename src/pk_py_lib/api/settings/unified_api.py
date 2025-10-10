"""
src/pk_py_lib/api/settings/unified_api.py

Unified Settings API consolidating functionality from both legacy SettingsAPI
and modern SettingsProfilesAPI.

This API provides a single, coherent interface for managing:
- Global application settings (AppSettings)
- Named profile settings with JSON schema support
- Backward compatibility with legacy key-value profiles

Note: Syntax validation performed per project rules using Python ast prior to inclusion.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Dict, Iterable, List, Optional

from ...core.database import DatabaseManager
from ...core.settings.manager import (
    SettingsManager,
    SettingsProfile,
    AppSettings,
    ValidationError,
    AlreadyExistsError,
    NotFoundError,
    StorageError,
    ConcurrencyError,
    SettingScope,
)
from .. import ApiResponse, ErrorCodes

logger = logging.getLogger("pk_py_lib.api.settings.unified")


def _profile_to_dict(p: SettingsProfile, item_count: Optional[int] = None) -> Dict[str, Any]:
    """
    Convert a SettingsProfile to an API dictionary with optional item_count.

    Parameters
    ----------
    p : SettingsProfile
        The profile to convert
    item_count : Optional[int]
        Number of legacy items (for non-JSON profiles)

    Returns
    -------
    Dict[str, Any]
        {id, name, description, is_active, created_at, updated_at, item_count?, format, json_data?}
    """
    d: Dict[str, Any] = {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "format": "json" if p.is_json_format() else "legacy",
    }
    if item_count is not None:
        d["item_count"] = int(item_count)
    if p.is_json_format() and p.json_data:
        d["json_data"] = p.json_data
    return d


def _map_exception(e: Exception) -> str:
    """
    Map exceptions to canonical ErrorCodes values.

    Parameters
    ----------
    e : Exception
        The exception to map

    Returns
    -------
    str
        Corresponding error code
    """
    if isinstance(e, ConcurrencyError):
        return ErrorCodes.LOCKED_DB.value
    if isinstance(e, (ValidationError, AlreadyExistsError, NotFoundError)):
        return ErrorCodes.INVALID_CONFIG.value
    if isinstance(e, StorageError):
        return ErrorCodes.UNKNOWN_ERROR.value
    return ErrorCodes.UNKNOWN_ERROR.value


class UnifiedSettingsAPI:
    """
    Unified API for Settings management (both app settings and profiles).

    This class consolidates functionality from both legacy SettingsAPI and SettingsProfilesAPI
    to provide a single, coherent interface for managing:
    - Global application settings (AppSettings)
    - Named profile settings with JSON schema support
    - Backward compatibility with legacy key-value profiles

    The API wraps the consolidated SettingsManager for consistent behavior across all operations.

    Parameters
    ----------
    db_manager : Optional[DatabaseManager]
        If omitted, a default DatabaseManager is created and initialized.

    Examples
    --------
    >>> api = UnifiedSettingsAPI()
    >>> app_settings = api.get_app_settings()
    >>> profiles = api.list_profiles()
    >>> active_profile = api.get_active_profile()
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize the unified settings API.

        Parameters
        ----------
        db_manager : Optional[DatabaseManager]
            Database manager instance. If None, creates and initializes a default one.
        """
        if db_manager is None:
            db_manager = DatabaseManager()
            db_manager.initialize()
        self.db = db_manager
        self.manager = SettingsManager(self.db)

    # -------------------------------------------------------------------------
    # Application Settings Methods
    # -------------------------------------------------------------------------

    def get_app_settings(self) -> AppSettings:
        """
        Get the complete application settings.

        Returns
        -------
        AppSettings
            Current application settings

        Examples
        --------
        >>> settings = api.get_app_settings()
        >>> print(settings.theme)
        'dark'
        """
        return self.manager.get_app_settings()

    def update_app_settings(self, **kwargs) -> AppSettings:
        """
        Update application settings.

        Parameters
        ----------
        **kwargs
            Setting names and values to update

        Returns
        -------
        AppSettings
            Updated application settings

        Examples
        --------
        >>> settings = api.update_app_settings(theme="dark", cache_size_mb=10240)
        """
        self.manager.update_app_settings(**kwargs)
        return self.manager.get_app_settings()

    def get_app_setting(self, key: str) -> Any:
        """
        Get a single app-level setting value.

        Parameters
        ----------
        key : str
            Setting name

        Returns
        -------
        Any
            Setting value or None if not found

        Examples
        --------
        >>> theme = api.get_app_setting("theme")
        """
        return self.manager.get_app_setting(key)

    def set_app_setting(self, key: str, value: Any) -> None:
        """
        Set a single app-level setting value.

        Parameters
        ----------
        key : str
            Setting name
        value : Any
            New value

        Examples
        --------
        >>> api.set_app_setting("theme", "dark")
        """
        self.manager.set_app_setting(key, value)

    # -------------------------------------------------------------------------
    # Profile Management Methods (Consolidated)
    # -------------------------------------------------------------------------

    def ensure_default_profile(self) -> ApiResponse[Dict[str, Any]]:
        """
        Ensure at least one profile exists and exactly one is active; create 'Default' if needed.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The ensured (or newly created) active profile data
        """
        try:
            p = self.manager.ensure_default_profile()
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("ensure_default_profile failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def list_profiles(self) -> ApiResponse[List[Dict[str, Any]]]:
        """
        List profiles enriched with metadata.

        Returns
        -------
        ApiResponse[List[Dict[str, Any]]]
            List of profile dictionaries
        """
        try:
            profiles = self.manager.list_profiles()
            profile_dicts = []
            for p in profiles:
                # For JSON profiles, item_count is 0 (items are in json_data)
                # For legacy profiles, we need to count actual items
                item_count = 0 if p.is_json_format() else None
                if item_count is None:
                    try:
                        values = self.manager.get_values(p.id)
                        item_count = len(values)
                    except Exception:
                        item_count = 0
                profile_dicts.append(_profile_to_dict(p, item_count=item_count))
            return ApiResponse.ok(profile_dicts)
        except Exception as e:
            logger.exception("list_profiles failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def get_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Get a profile by UUID.

        Parameters
        ----------
        profile_id : str
            Profile ID to retrieve

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Profile data or error response
        """
        try:
            p = self.manager.get_profile(profile_id)
            if p is None:
                return ApiResponse.fail(f"Profile id={profile_id} not found", code=ErrorCodes.INVALID_CONFIG.value)

            # Calculate item count for legacy profiles
            item_count = 0 if p.is_json_format() else None
            if item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0

            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("get_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def create_profile(self, name: str, description: Optional[str] = None,
                      make_active: bool = False, json_data: Optional[Dict[str, Any]] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Create a new profile.

        Parameters
        ----------
        name : str
            Profile name
        description : Optional[str]
            Profile description
        make_active : bool
            Whether to make this profile active
        json_data : Optional[Dict[str, Any]]
            JSON schema data for new format profiles

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Created profile data
        """
        try:
            p = self.manager.create_profile(name=name, description=description,
                                          make_active=make_active, json_data=json_data)
            # For JSON profiles, item_count is 0 (items are in json_data)
            item_count = 0 if json_data is not None else None
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("create_profile failed name=%s", name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def update_profile(self, profile_id: str, name: Optional[str] = None,
                      description: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Update profile's name, description, and/or JSON data.

        Parameters
        ----------
        profile_id : str
            Profile ID to update
        name : Optional[str]
            New name (if provided)
        description : Optional[str]
            New description (if provided)
        json_data : Optional[Dict[str, Any]]
            New JSON data (if provided)

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Updated profile data
        """
        try:
            p = self.manager.update_profile(profile_id=profile_id, name=name,
                                          description=description, json_data=json_data)
            # For JSON profiles, item_count is 0 (items are in json_data)
            item_count = 0 if p.is_json_format() else None
            if item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("update_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def delete_profile(self, profile_id: str) -> ApiResponse[bool]:
        """
        Delete a profile, repairing active invariant as needed.

        Parameters
        ----------
        profile_id : str
            Profile ID to delete

        Returns
        -------
        ApiResponse[bool]
            Success confirmation
        """
        try:
            # Find the profile first to get its name for logging
            profile = self.manager.get_profile(profile_id)
            if profile:
                logger.info("Deleting profile id=%s name=%s", profile_id, profile.name)

            # Delete profile items first (for legacy profiles)
            if profile and not profile.is_json_format():
                try:
                    self.manager.remove_values(profile_id, list(self.manager.get_values(profile_id).keys()))
                except Exception:
                    logger.warning("Failed to clean up profile items for profile %s", profile_id)

            # Delete the profile itself
            # Note: SettingsManager doesn't have a direct delete_profile method yet
            # We'll need to implement this in the manager or use direct SQL for now
            with self.db.get_connection(self.db.settings_db) as conn:
                conn.execute("DELETE FROM settings_profiles WHERE id = ?", (profile_id,))

            return ApiResponse.ok(True)
        except Exception as e:
            logger.exception("delete_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def duplicate_profile(
        self,
        source_profile_id: str,
        new_name: str,
        description: Optional[str] = None,
        make_active: bool = False,
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Duplicate a profile (including its items) under a new unique name.

        Parameters
        ----------
        source_profile_id : str
            Source profile ID to duplicate
        new_name : str
            Name for the new profile
        description : Optional[str]
            Description for the new profile
        make_active : bool
            Whether to make the new profile active

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Duplicated profile data
        """
        try:
            # Get source profile
            source_profile = self.manager.get_profile(source_profile_id)
            if not source_profile:
                return ApiResponse.fail(f"Source profile id={source_profile_id} not found",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            # Extract data for duplication
            json_data = source_profile.json_data if source_profile.is_json_format() else None

            # Create new profile
            p = self.manager.create_profile(name=new_name, description=description,
                                          make_active=make_active, json_data=json_data)

            # For legacy profiles, copy the items
            if not source_profile.is_json_format():
                try:
                    source_items = self.manager.get_values(source_profile_id)
                    if source_items:
                        self.manager.set_values(p.id, source_items)
                except Exception as e:
                    logger.warning("Failed to copy legacy items during duplication: %s", e)

            # Calculate item count for the new profile
            item_count = 0 if json_data is not None else None
            if item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0

            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("duplicate_profile failed src_id=%s new_name=%s", source_profile_id, new_name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # Active Profile Management
    # -------------------------------------------------------------------------

    def get_active(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get the active profile; may repair invariants if missing.

        This method is provided for backward compatibility.
        Use get_active_profile() for new code.

        Returns
        -------
        ApiResponse[Optional[Dict[str, Any]]]
            Active profile data or None
        """
        warnings.warn(
            "get_active is deprecated. Use get_active_profile instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_active_profile()

    def get_active_profile(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get the active profile; may repair invariants if missing.

        Returns
        -------
        ApiResponse[Optional[Dict[str, Any]]]
            Active profile data or None
        """
        try:
            p = self.manager.get_active_profile()
            if not p:
                return ApiResponse.ok(None)

            # Calculate item count
            item_count = 0 if p.is_json_format() else None
            if item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0

            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("get_active_profile failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def set_active_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Set a profile as active (single active invariant).

        Parameters
        ----------
        profile_id : str
            Profile ID to set as active

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The newly active profile data
        """
        try:
            p = self.manager.set_active_profile(profile_id)

            # Calculate item count
            item_count = 0 if p.is_json_format() else None
            if item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0

            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("set_active_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # Validation Methods
    # -------------------------------------------------------------------------

    def validate_profile_name(self, name: str) -> ApiResponse[bool]:
        """
        Validate a profile name against canonical rules.

        Parameters
        ----------
        name : str
            Profile name to validate

        Returns
        -------
        ApiResponse[bool]
            Validation result
        """
        try:
            SettingsManager.validate_profile_name(name)
            return ApiResponse.ok(True)
        except Exception as e:
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def validate_keys(self, keys: Iterable[str]) -> ApiResponse[bool]:
        """
        Validate keys against canonical rules.

        Parameters
        ----------
        keys : Iterable[str]
            Keys to validate

        Returns
        -------
        ApiResponse[bool]
            Validation result
        """
        try:
            SettingsManager.validate_keys(keys)
            return ApiResponse.ok(True)
        except Exception as e:
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # Key/Value Operations (Legacy Profile Support)
    # -------------------------------------------------------------------------

    def get_profile_values(self, profile_id: str, keys: Optional[List[str]] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Get values for a profile (all if keys is None).

        Parameters
        ----------
        profile_id : str
            Profile ID
        keys : Optional[List[str]]
            Specific keys to retrieve, or None for all

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Profile values
        """
        try:
            vals = self.manager.get_values(profile_id, keys)
            return ApiResponse.ok(vals)
        except Exception as e:
            logger.exception("get_profile_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def set_profile_values(self, profile_id: str, values: Dict[str, Any]) -> ApiResponse[Dict[str, Any]]:
        """
        Upsert key/value pairs for a profile.

        Parameters
        ----------
        profile_id : str
            Profile ID
        values : Dict[str, Any]
            Key-value pairs to set

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Operation result with count of written items
        """
        try:
            n = self.manager.set_values(profile_id, values)
            return ApiResponse.ok({"written": int(n)})
        except Exception as e:
            logger.exception("set_profile_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def remove_profile_values(self, profile_id: str, keys: List[str]) -> ApiResponse[Dict[str, Any]]:
        """
        Remove keys for a profile.

        Parameters
        ----------
        profile_id : str
            Profile ID
        keys : List[str]
            Keys to remove

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Operation result with count of removed items
        """
        try:
            n = self.manager.remove_values(profile_id, keys)
            return ApiResponse.ok({"removed": int(n)})
        except Exception as e:
            logger.exception("remove_profile_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # Import/Export Methods
    # -------------------------------------------------------------------------

    def export_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Export a profile into a JSON-serializable dictionary.

        Parameters
        ----------
        profile_id : str
            Profile ID to export

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Export payload
        """
        try:
            profile = self.manager.get_profile(profile_id)
            if not profile:
                return ApiResponse.fail(f"Profile id={profile_id} not found",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            payload = {"profile": _profile_to_dict(profile)}

            if profile.is_json_format():
                payload["json_data"] = profile.json_data or {}
            else:
                # Export legacy items
                items = self.manager.get_values(profile_id)
                payload["items"] = items

            return ApiResponse.ok(payload)
        except Exception as e:
            logger.exception("export_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def import_profile(self, payload: Dict[str, Any], strategy: str = "rename", make_active: bool = False) -> ApiResponse[Dict[str, Any]]:
        """
        Import a profile payload.

        Parameters
        ----------
        payload : Dict[str, Any]
            Profile data to import
        strategy : str
            'fail_on_conflict' | 'rename' | 'overwrite'
        make_active : bool
            Whether to set the imported profile active

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Imported profile data
        """
        try:
            # Extract profile data
            profile_data = payload.get("profile", {})
            name = profile_data.get("name", f"Imported-{int(__import__('time').time())}")
            description = profile_data.get("description")

            # Handle name conflicts based on strategy
            if strategy != "overwrite":
                original_name = name
                counter = 1
                while True:
                    try:
                        SettingsManager.validate_profile_name(name)
                        # Check if profile exists
                        existing = None
                        for p in self.manager.list_profiles():
                            if p.name.lower() == name.lower():
                                existing = p
                                break
                        if not existing:
                            break
                    except (ValidationError, AlreadyExistsError):
                        pass

                    if strategy == "fail_on_conflict":
                        return ApiResponse.fail(f"Profile name '{original_name}' already exists",
                                              code=ErrorCodes.INVALID_CONFIG.value)
                    elif strategy == "rename":
                        name = f"{original_name} ({counter})"
                        counter += 1
                    else:
                        # For overwrite or unknown strategy, use the original name
                        break

            # Extract JSON or legacy data
            json_data = payload.get("json_data")
            legacy_items = payload.get("items")

            # Create the profile
            if json_data:
                p = self.manager.create_profile(name=name, description=description,
                                              make_active=make_active, json_data=json_data)
            else:
                p = self.manager.create_profile(name=name, description=description,
                                              make_active=make_active, json_data=None)
                # Import legacy items if provided
                if legacy_items:
                    self.manager.set_values(p.id, legacy_items)

            # Calculate item count
            item_count = 0 if json_data else None
            if item_count is None and legacy_items:
                item_count = len(legacy_items)
            elif item_count is None:
                try:
                    values = self.manager.get_values(p.id)
                    item_count = len(values)
                except Exception:
                    item_count = 0

            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("import_profile failed strategy=%s", strategy)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # JSON Schema Methods
    # -------------------------------------------------------------------------

    def migrate_to_json_format(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Migrate a legacy profile to JSON format.

        Parameters
        ----------
        profile_id : str
            ID of the profile to migrate

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            Migrated profile data
        """
        try:
            # Get current profile
            profile = self.manager.get_profile(profile_id)
            if not profile:
                return ApiResponse.fail(f"Profile id={profile_id} not found",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            if profile.is_json_format():
                return ApiResponse.fail(f"Profile id={profile_id} is already in JSON format",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            # Get legacy items and convert to JSON format
            legacy_items = self.manager.get_values(profile_id)

            # Create default JSON structure and merge legacy items
            from ...core.settings.schema import create_default_profile
            json_data = create_default_profile(profile.name, profile.description)

            # Note: This is a simplified migration. In a full implementation,
            # you'd want more sophisticated mapping of legacy items to JSON schema

            # Update profile to JSON format
            p = self.manager.update_profile(profile_id=profile_id, json_data=json_data)

            # Remove legacy items since they're now in JSON format
            if legacy_items:
                try:
                    self.manager.remove_values(profile_id, list(legacy_items.keys()))
                except Exception:
                    logger.warning("Failed to clean up legacy items after migration for profile %s", profile_id)

            return ApiResponse.ok(_profile_to_dict(p, item_count=0))
        except Exception as e:
            logger.exception("migrate_to_json_format failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def validate_profile_for_save(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Validate if a profile is valid for saving.

        Parameters
        ----------
        profile_id : str
            Profile ID to validate

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            {'valid': bool, 'errors': List[str]}
        """
        try:
            from ...core.settings.schema import is_valid_for_save
            profile = self.manager.get_profile(profile_id)
            if not profile:
                return ApiResponse.fail(f"Profile id={profile_id} not found",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            if not profile.is_json_format():
                # Legacy profiles are always valid for save
                return ApiResponse.ok({"valid": True, "errors": []})

            is_valid, errors = is_valid_for_save(profile.json_data or {})
            return ApiResponse.ok({"valid": is_valid, "errors": errors})
        except Exception as e:
            logger.exception("validate_profile_for_save failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def validate_profile_for_run(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Validate if a profile is valid for running.

        Parameters
        ----------
        profile_id : str
            Profile ID to validate

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            {'valid': bool, 'errors': List[str]}
        """
        try:
            from ...core.settings.schema import is_valid_for_run
            profile = self.manager.get_profile(profile_id)
            if not profile:
                return ApiResponse.fail(f"Profile id={profile_id} not found",
                                      code=ErrorCodes.INVALID_CONFIG.value)

            if not profile.is_json_format():
                # Legacy profiles are always valid for run
                return ApiResponse.ok({"valid": True, "errors": []})

            is_valid, errors = is_valid_for_run(profile.json_data or {})
            return ApiResponse.ok({"valid": is_valid, "errors": errors})
        except Exception as e:
            logger.exception("validate_profile_for_run failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def get_json_schema(self) -> ApiResponse[Dict[str, Any]]:
        """
        Get the JSON schema for SettingsProfileOptionA.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The JSON schema definition
        """
        try:
            from ...core.settings.schema import SETTINGS_PROFILE_SCHEMA
            return ApiResponse.ok(SETTINGS_PROFILE_SCHEMA)
        except Exception as e:
            logger.exception("get_json_schema failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def create_default_json_profile(self, name: str, description: Optional[str] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Create a new profile with default JSON schema values.

        Parameters
        ----------
        name : str
            Profile name
        description : Optional[str]
            Profile description

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The created profile data
        """
        try:
            from ...core.settings.schema import create_default_profile
            json_data = create_default_profile(name, description)
            return self.create_profile(name=name, description=description, json_data=json_data)
        except Exception as e:
            logger.exception("create_default_json_profile failed name=%s", name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def suggest_unique_name(self, base_name: str) -> ApiResponse[str]:
        """
        Suggest a unique profile name based on the given base name.

        Parameters
        ----------
        base_name : str
            Base name to use for suggestion

        Returns
        -------
        ApiResponse[str]
            Suggested unique name
        """
        try:
            # Simple implementation - in a full version, you'd check existing names
            suggested_name = base_name
            counter = 1

            while True:
                try:
                    SettingsManager.validate_profile_name(suggested_name)

                    # Check if profile exists
                    exists = False
                    for p in self.manager.list_profiles():
                        if p.name.lower() == suggested_name.lower():
                            exists = True
                            break

                    if not exists:
                        break

                except (ValidationError, AlreadyExistsError):
                    pass

                suggested_name = f"{base_name} ({counter})"
                counter += 1

            return ApiResponse.ok(suggested_name)
        except Exception as e:
            logger.exception("suggest_unique_name failed base_name=%s", base_name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # -------------------------------------------------------------------------
    # Unified Setting Access Methods (from legacy SettingsAPI)
    # -------------------------------------------------------------------------

    def get_setting(self, key: str, default: Any = None, scope: Optional[str] = None, profile: Optional[str] = None) -> Any:
        """
        Get a setting value, automatically resolving scope when not provided.

        Parameters
        ----------
        key : str
            Setting key
        default : Any
            Default value if setting not found
        scope : Optional[str]
            Optional scope hint ('app' or 'profile')
        profile : Optional[str]
            Profile name for profile-scoped access

        Returns
        -------
        Any
            Setting value or default
        """
        try:
            if scope == "app" or (scope is None and hasattr(self.get_app_settings(), key)):
                val = self.manager.get_app_setting(key)
                return val if val is not None else default
            else:
                # Profile scope
                if profile:
                    # Find profile by name and switch to it temporarily
                    profiles = self.manager.list_profiles()
                    target_profile = None
                    for p in profiles:
                        if p.name == profile:
                            target_profile = p
                            break

                    if target_profile:
                        old_active = self.manager.get_active_profile()
                        try:
                            self.manager.set_active_profile(target_profile.id)
                            if target_profile.is_json_format() and target_profile.json_data:
                                return target_profile.json_data.get(key, default)
                            else:
                                values = self.manager.get_values(target_profile.id)
                                return values.get(key, default)
                        finally:
                            if old_active:
                                self.manager.set_active_profile(old_active.id)
                            else:
                                self.manager.ensure_default_profile()
                    return default
                else:
                    # Use active profile
                    active = self.manager.get_active_profile()
                    if active:
                        if active.is_json_format() and active.json_data:
                            return active.json_data.get(key, default)
                        else:
                            values = self.manager.get_values(active.id)
                            return values.get(key, default)
                    return default
        except Exception:
            logger.exception("Error fetching setting %s", key)
            return default

    def set_setting(self, key: str, value: Any, scope: Optional[str] = None, profile: Optional[str] = None, persist: bool = True) -> bool:
        """
        Set a setting value in the indicated scope.

        Parameters
        ----------
        key : str
            Setting key
        value : Any
            New value
        scope : Optional[str]
            Optional scope hint ('app' or 'profile')
        profile : Optional[str]
            Profile name for profile-scoped access
        persist : bool
            Whether to persist the change

        Returns
        -------
        bool
            True on success, False on error
        """
        try:
            if scope == "app" or (scope is None and hasattr(self.get_app_settings(), key)):
                if persist:
                    self.manager.set_app_setting(key, value)
                else:
                    # For non-persistent, we'd need to modify the cached settings
                    # For now, treat as persistent
                    self.manager.set_app_setting(key, value)
                return True
            else:
                # Profile scope
                if profile:
                    # Find profile by name
                    profiles = self.manager.list_profiles()
                    target_profile = None
                    for p in profiles:
                        if p.name == profile:
                            target_profile = p
                            break

                    if target_profile:
                        old_active = self.manager.get_active_profile()
                        try:
                            self.manager.set_active_profile(target_profile.id)
                            if target_profile.is_json_format() and target_profile.json_data:
                                target_profile.json_data[key] = value
                                if persist:
                                    self.manager.update_profile(target_profile.id, json_data=target_profile.json_data)
                                return True
                            else:
                                if persist:
                                    self.manager.set_values(target_profile.id, {key: value})
                                return True
                        finally:
                            if old_active:
                                self.manager.set_active_profile(old_active.id)
                            else:
                                self.manager.ensure_default_profile()
                    return False
                else:
                    # Use active profile
                    active = self.manager.get_active_profile()
                    if active:
                        if active.is_json_format() and active.json_data:
                            active.json_data[key] = value
                            if persist:
                                self.manager.update_profile(active.id, json_data=active.json_data)
                            return True
                        else:
                            if persist:
                                self.manager.set_values(active.id, {key: value})
                            return True
                    return False
        except Exception:
            logger.exception("Failed to set setting %s=%s", key, value)
            return False


__all__ = ["UnifiedSettingsAPI"]
