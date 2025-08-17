"""
src/pk_py_lib/api/settings_profiles.py

Library API adapter for settings profile management (non-GUI).

This module exposes a thin, consistent API surface that delegates to the core
SettingsProfilesManager for persistence and invariants. It returns structured
ApiResponse objects per the canonical API patterns.

Notes
- Persistence: SQLite settings.db via DatabaseManager.initialize()
- Active profile id persisted under meta.active_profile_id (INTEGER as text)
- Naming rules and invariants enforced by the core manager
- Logging namespace (canonical): "pk_py_lib.settings_profiles"

Syntax validation: This module has been validated for Python syntax via ast parsing
prior to inclusion (see project rules).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import asdict
from typing import Any, Callable, Dict, List, Optional

from ..core.database import DatabaseManager
from ..core.settings_profiles import SettingsProfilesManager, SettingsProfile
from . import ApiResponse, ErrorCodes

# Use canonical logger name for observability
logger = logging.getLogger("pk_py_lib.settings_profiles")


def _profile_to_dict(p: SettingsProfile) -> Dict[str, Any]:
    """
    Convert SettingsProfile dataclass to a plain dictionary suitable for JSON.

    Returns
    -------
    Dict[str, Any]
        Dict with id, name, data, is_default, created_at, updated_at
    """
    # asdict is safe here because SettingsProfile contains only JSON-serializable fields
    return asdict(p)


def _map_exception(e: Exception) -> str:
    """
    Map Python/SQLite exceptions to canonical ErrorCodes for API responses.

    Returns
    -------
    str
        Error code value (ErrorCodes.*.value).
    """
    if isinstance(e, ValueError):
        return ErrorCodes.INVALID_CONFIG.value
    if isinstance(e, PermissionError):
        return ErrorCodes.PERMISSION_DENIED.value
    if isinstance(e, sqlite3.OperationalError):
        msg = str(e).lower()
        if "locked" in msg:
            return ErrorCodes.LOCKED_DB.value
        return ErrorCodes.UNKNOWN_ERROR.value
    return ErrorCodes.UNKNOWN_ERROR.value


class SettingsProfilesAPI:
    """
    High-level API for Settings Profiles (CRUD, copy, set-active/default, import/export).

    Responsibilities
    ---------------
    - Provide a stable, documented API for profile management
    - Translate exceptions into ApiResponse with canonical ErrorCodes
    - Keep all writes transactional (delegated to core manager)

    Parameters
    ----------
    db_manager : Optional[DatabaseManager]
        If omitted, a default DatabaseManager is created and initialized.
    on_active_change : Optional[Callable[[SettingsProfile], None]]
        Optional callback fired after the active profile changes. This can be used
        by the caller to keep in-process configuration state aligned.

    Examples
    --------
    >>> api = SettingsProfilesAPI()
    >>> r = api.create(name="My Workflow", data={"threshold": 0.9}, make_active=True, make_default=True)
    >>> r.success, r.data["name"], r.data["is_default"]
    (True, 'My Workflow', True)
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        on_active_change: Optional[Callable[[SettingsProfile], None]] = None,
    ):
        if db_manager is None:
            db_manager = DatabaseManager()
            db_manager.initialize()
        self.db = db_manager
        self.manager = SettingsProfilesManager(self.db, on_active_change=on_active_change)

    # ---------------------------------------------------------------------
    # Listing and retrieval
    # ---------------------------------------------------------------------
    def list_profiles(self) -> ApiResponse[List[Dict[str, Any]]]:
        """
        List all profiles with is_active flag computed from meta.active_profile_id.

        Returns
        -------
        ApiResponse[List[Dict[str, Any]]]
            On success, a list of profile dicts enriched with 'is_active' boolean.
        """
        try:
            active = self.manager.get_active_profile()
            active_id = active.id if active else None
            items = []
            for p in self.manager.list_profiles():
                d = _profile_to_dict(p)
                d["is_active"] = (p.id == active_id)
                items.append(d)
            return ApiResponse.ok(items)
        except Exception as e:
            logger.exception("list_profiles failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def get_profile(self, profile_id: int) -> ApiResponse[Dict[str, Any]]:
        """
        Get a profile by id.

        Parameters
        ----------
        profile_id : int
            Target id.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
        """
        try:
            p = self.manager.get_profile(profile_id)
            if p is None:
                return ApiResponse.fail(f"Profile id={profile_id} not found", code=ErrorCodes.INVALID_CONFIG.value)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("get_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def get_active(self) -> ApiResponse[Optional[Dict[str, Any]]]:
        """
        Get the active profile, computing a default if the meta key is missing.

        Returns
        -------
        ApiResponse[Optional[Dict[str, Any]]]
            data is None when no profiles exist.
        """
        try:
            p = self.manager.get_active_profile()
            return ApiResponse.ok(_profile_to_dict(p) if p else None)
        except Exception as e:
            logger.exception("get_active failed")
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Create / Update / Delete / Copy
    # ---------------------------------------------------------------------
    def create(
        self,
        name: str,
        data: Optional[Dict[str, Any]] = None,
        make_active: bool = False,
        make_default: bool = False,
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Create a new profile with optional Active/Default flags.

        See core invariants and validation rules for details.
        """
        try:
            p = self.manager.create_profile(name=name, data=data, make_active=make_active, make_default=make_default)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("create failed name=%s", name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def update(
        self,
        profile_id: int,
        name: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        make_default: Optional[bool] = None,
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Update profile fields (name/data) and optionally default status.

        Behavior
        --------
        - make_default=True sets this profile default and clears all others.
        - make_default=False unsets default on this profile.
        - make_default=None leaves default flag unchanged.
        """
        try:
            p = self.manager.update_profile(profile_id, name=name, data=data, make_default=make_default)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("update failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def delete(self, profile_id: int) -> ApiResponse[bool]:
        """
        Delete a profile.

        Invariants (enforced by core)
        -----------------------------
        - Cannot delete the Active profile
        - Cannot delete the last remaining profile
        """
        try:
            self.manager.delete_profile(profile_id)
            return ApiResponse.ok(True)
        except Exception as e:
            logger.exception("delete failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def copy(
        self,
        source_profile_id: int,
        new_name: str,
        make_active: bool = False,
        make_default: bool = False,
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Copy an existing profile into a new one.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The newly created profile.
        """
        try:
            p = self.manager.copy_profile(
                source_profile_id=source_profile_id,
                new_name=new_name,
                make_active=make_active,
                make_default=make_default,
            )
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("copy failed src_id=%s new_name=%s", source_profile_id, new_name)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Active / Default management
    # ---------------------------------------------------------------------
    def set_active(self, profile_id: int) -> ApiResponse[Dict[str, Any]]:
        """
        Set a profile as Active (updates meta.active_profile_id transactionally).

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The active profile after the change.
        """
        try:
            p = self.manager.set_active_profile(profile_id)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("set_active failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def set_default(self, profile_id: int) -> ApiResponse[Dict[str, Any]]:
        """
        Set exactly one Default profile (clears is_default on others).

        Returns
        -------
        ApiResponse[Dict[str, Any]]
            The profile marked as default.
        """
        try:
            p = self.manager.set_default_profile(profile_id)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("set_default failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------
    def validate_name(self, name: str) -> ApiResponse[bool]:
        """
        Validate a proposed profile name against canonical rules.

        Rules
        -----
        - Required, 1–64 characters
        - Allowed: letters, digits, space, underscore, hyphen
        - Uniqueness is enforced at persistence time; this method only validates syntax/length.
        """
        try:
            self.manager.validate_name(name)
            return ApiResponse.ok(True)
        except Exception as e:
            return ApiResponse.fail(str(e), code=_map_exception(e))

    # ---------------------------------------------------------------------
    # Import / Export
    # ---------------------------------------------------------------------
    def export_profile(self, profile_id: int) -> ApiResponse[Dict[str, Any]]:
        """
        Export a profile into a portable JSON-serializable dictionary.

        Returns
        -------
        ApiResponse[Dict[str, Any]]
        """
        try:
            payload = self.manager.export_profile(profile_id)
            return ApiResponse.ok(payload)
        except Exception as e:
            logger.exception("export_profile failed id=%s", profile_id)
            return ApiResponse.fail(str(e), code=_map_exception(e))

    def import_profile(self, payload: Dict[str, Any], strategy: str = "fail_on_conflict") -> ApiResponse[Dict[str, Any]]:
        """
        Import a profile payload using a configurable conflict strategy.

        Parameters
        ----------
        payload : Dict[str, Any]
            Expected to include at least: {'name': str, 'data': dict, 'is_default': bool?}
        strategy : str
            One of "fail_on_conflict" | "rename" | "overwrite"
        """
        try:
            p = self.manager.import_profile(payload=payload, strategy=strategy)
            return ApiResponse.ok(_profile_to_dict(p))
        except Exception as e:
            logger.exception("import_profile failed strategy=%s", strategy)
            return ApiResponse.fail(str(e), code=_map_exception(e))


__all__ = ["SettingsProfilesAPI"]