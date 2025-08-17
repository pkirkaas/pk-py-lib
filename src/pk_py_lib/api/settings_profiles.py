"""
src/pk_py_lib/api/settings_profiles.py

Settings Profiles Library API (id-centric, normalized schema)

This API is a thin, documented adapter over the core SettingsProfilesManager. It exposes:
- Profile CRUD and duplicate
- Active profile selection
- Key/Value get/set/remove per profile
- Import/Export
- Validation helpers
- Bootstrap helper ensure_default_profile()

All methods return ApiResponse per the project conventions.

Persistence and invariants are owned by the core manager:
- SQLite via DatabaseManager
- Normalized tables:
    settings_profiles(id TEXT UUID PK, name TEXT UNIQUE CI, description TEXT NULL,
                      is_active INT, created_at TEXT, updated_at TEXT)
    settings_profile_items(id TEXT UUID PK, profile_id TEXT FK, key TEXT,
                           value TEXT (JSON), created_at TEXT, updated_at TEXT)
- Meta key pk.settings_profiles maintains {'schema_version': 1, 'active_profile_id': '<uuid or null>', ...}

Logging namespace: "pk_py_lib.settings_profiles"

Note: Syntax validation performed per project rules using Python ast prior to inclusion.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from ..core.database import DatabaseManager
from ..core.settings_profiles import (
    SettingsProfilesManager,
    SettingsProfile,
    ValidationError,
    AlreadyExistsError,
    NotFoundError,
    StorageError,
    ConcurrencyError,
)
from . import ApiResponse, ErrorCodes

logger = logging.getLogger("pk_py_lib.settings_profiles")


def _profile_to_dict(p: SettingsProfile, item_count: Optional[int] = None) -> Dict[str, Any]:
    """
    Convert a SettingsProfile to an API dictionary with optional item_count.

    Returns
    -------
    Dict[str, Any]
        {id, name, description, is_active, created_at, updated_at, item_count?}
    """
    d: Dict[str, Any] = {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "is_active": p.is_active,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }
    if item_count is not None:
        d["item_count"] = int(item_count)
    return d


def _map_exception(e: Exception) -> str:
    """
    Map exceptions to canonical ErrorCodes values.
    """
    if isinstance(e, ConcurrencyError):
        return ErrorCodes.LOCKED_DB.value
    if isinstance(e, (ValidationError, AlreadyExistsError, NotFoundError)):
        return ErrorCodes.INVALID_CONFIG.value
    if isinstance(e, StorageError):
        return ErrorCodes.UNKNOWN_ERROR.value
    return ErrorCodes.UNKNOWN_ERROR.value


class SettingsProfilesAPI:
    """
    High-level API for Settings Profiles (CRUD, duplicate, active selection, KV ops, import/export).

    Parameters
    ----------
    db_manager : Optional[DatabaseManager]
        If omitted, a default DatabaseManager is created and initialized.

    Examples
    --------
    >>> api = SettingsProfilesAPI()
    >>> ok = api.ensure_default_profile().success
    >>> r = api.create(name="My Flow", description="workflow", make_active=True)
    >>> r.success and r.data["is_active"]
    True
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        if db_manager is None:
            db_manager = DatabaseManager()
            db_manager.initialize()
        self.db = db_manager
        self.manager = SettingsProfilesManager(self.db)

    # ---------------------------------------------------------------------
    # Bootstrap
    # ---------------------------------------------------------------------
    def ensure_default_profile(self) -> ApiResponse[Dict[str, Any]]:
        """
        Ensure at least one profile exists and exactly one is active; create 'Default' if needed.
        """
        try:
            p = self.manager.ensure_default_profile()
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("ensure_default_profile failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Profiles: list/get/create/update/delete/duplicate
    # ---------------------------------------------------------------------
    def list_profiles(self) -> ApiResponse[List[Dict[str, Any]]]:
        """
        List profiles enriched with item_count.
        """
        try:
            items = self.manager.list_profiles_with_counts()
            # Already shaped: id, name, description, is_active, created_at, updated_at, item_count
            return ApiResponse.ok(items)
        except Exception as e:
            logger.exception("list_profiles failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def get_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Get a profile by UUID.
        """
        try:
            p = self.manager.get_profile(profile_id)
            if p is None:
                return ApiResponse.fail(f"Profile id={profile_id} not found", code=ErrorCodes.INVALID_CONFIG.value)
            # attach item_count
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("get_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def create(self, name: str, description: Optional[str] = None, make_active: bool = False) -> ApiResponse[Dict[str, Any]]:
        """
        Create a new profile.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
        """
        try:
            p = self.manager.create_profile(name=name, description=description, make_active=make_active)
            return ApiResponse.ok(_profile_to_dict(p, item_count=0))
        except Exception as e:
            logger.exception("create failed name=%s", name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def update(self, profile_id: str, name: Optional[str] = None, description: Optional[str] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Update profile's name and/or description.
        """
        try:
            p = self.manager.update_profile(profile_id=profile_id, name=name, description=description)
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("update failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def delete(self, profile_id: str) -> ApiResponse[bool]:
        """
        Delete a profile, repairing active invariant as needed.
        """
        try:
            self.manager.delete_profile(profile_id)
            return ApiResponse.ok(True)
        except Exception as e:
            logger.exception("delete failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def duplicate(
        self,
        source_profile_id: str,
        new_name: str,
        description: Optional[str] = None,
        make_active: bool = False,
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Duplicate a profile (including its items) under a new unique name.
        """
        try:
            p = self.manager.duplicate_profile(
                source_profile_id=source_profile_id,
                new_name=new_name,
                description=description,
                make_active=make_active,
            )
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("duplicate failed src_id=%s new_name=%s", source_profile_id, new_name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Active profile
    # ---------------------------------------------------------------------
    def get_active(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get the active profile; may repair invariants if missing.
        """
        try:
            p = self.manager.get_active_profile()
            if not p:
                return ApiResponse.ok(None)
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("get_active failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

        # no return

    def set_active(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Set a profile as active (single active invariant).
        """
        try:
            p = self.manager.set_active_profile(profile_id)
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("set_active failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------
    def validate_name(self, name: str) -> ApiResponse[bool]:
        """
        Validate a profile name against canonical rules.
        """
        try:
            self.manager.validate_profile_name(name)
            return ApiResponse.ok(True)
        except Exception as e:
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def validate_keys(self, keys: Iterable[str]) -> ApiResponse[bool]:
        """
        Validate keys against canonical rules.
        """
        try:
            self.manager.validate_keys(keys)
            return ApiResponse.ok(True)
        except Exception as e:
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Key/Value operations
    # ---------------------------------------------------------------------
    def get_values(self, profile_id: str, keys: Optional[List[str]] = None) -> ApiResponse[Dict[str, Any]]:
        """
        Get values for a profile (all if keys is None).
        """
        try:
            vals = self.manager.get_values(profile_id, keys)
            return ApiResponse.ok(vals)
        except Exception as e:
            logger.exception("get_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def set_values(self, profile_id: str, values: Dict[str, Any]) -> ApiResponse[Dict[str, Any]]:
        """
        Upsert key/value pairs for a profile.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            {'written': int}
        """
        try:
            n = self.manager.set_values(profile_id, values)
            return ApiResponse.ok({"written": int(n)})
        except Exception as e:
            logger.exception("set_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def remove_values(self, profile_id: str, keys: List[str]) -> ApiResponse[Dict[str, Any]]:
        """
        Remove keys for a profile.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            {'removed': int}
        """
        try:
            n = self.manager.remove_values(profile_id, keys)
            return ApiResponse.ok({"removed": int(n)})
        except Exception as e:
            logger.exception("remove_values failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Import/Export
    # ---------------------------------------------------------------------
    def export_profile(self, profile_id: str) -> ApiResponse[Dict[str, Any]]:
        """
        Export a profile into a JSON-serializable dictionary:
        {'profile': {...}, 'items': {...}}
        """
        try:
            payload = self.manager.export_profile(profile_id)
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
            {'profile': {'name': str, 'description'?: str}, 'items': dict}
        strategy : str
            'fail_on_conflict' | 'rename' | 'overwrite'
        make_active : bool
            Whether to set the imported profile active.
        """
        try:
            p = self.manager.import_profile(payload=payload, strategy=strategy, make_active=make_active)
            counts = [i for i in self.manager.list_profiles_with_counts() if i["id"] == p.id]
            item_count = counts[0]["item_count"] if counts else 0
            return ApiResponse.ok(_profile_to_dict(p, item_count=item_count))
        except Exception as e:
            logger.exception("import_profile failed strategy=%s", strategy)
            return ApiResponse.fail(str(e), code=_map_exception(e))


__all__ = ["SettingsProfilesAPI"]