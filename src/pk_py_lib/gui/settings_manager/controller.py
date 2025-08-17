"""
src/pk_py_lib/gui/settings_manager/controller.py

Controller layer for the reusable Settings Manager GUI.

- Centralizes all interactions with SettingsProfilesAPI
- Provides uniform OpResult wrapper for success/error mapping
- Offers convenience helpers for name suggestions and combined profile+values fetch

Design notes
------------
- This controller is GUI-agnostic (no Qt imports). It can be unit-tested headless.
- All writes go through this controller to keep error handling in one place.
- Validation helpers delegate to the API to ensure canonical rules.

Note: Syntax validation was performed using Python's ast module per project rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Generic, Iterable, List, Optional, Sequence, Tuple, TypeVar

from ...api import ApiResponse, ErrorCodes
from ...api.settings_profiles import SettingsProfilesAPI


T = TypeVar("T")


@dataclass
class OpResult(Generic[T]):
    """
    Result wrapper for controller operations.

    Attributes
    ----------
    success : bool
        True when the operation succeeded.
    data : Optional[T]
        Payload on success; otherwise None.
    message : Optional[str]
        Human-readable error or info message.
    code : Optional[str]
        Machine-readable error code (see ErrorCodes).
    """
    success: bool
    data: Optional[T] = None
    message: Optional[str] = None
    code: Optional[str] = None

    @staticmethod
    def from_api(resp: ApiResponse[T]) -> "OpResult[T]":
        return OpResult(success=resp.success, data=resp.data if resp.success else None, message=resp.error, code=resp.code)


class SettingsManagerController:
    """
    Orchestrates profile CRUD, duplicate, active selection, and KV operations via SettingsProfilesAPI.

    This class is intentionally free of PySide dependencies and suitable for unit-testing
    in headless environments. It should be the single point used by GUI layers to
    perform writes so error handling and mapping are consistent.

    Examples
    --------
    >>> ctrl = SettingsManagerController()
    >>> _ = ctrl.ensure_default()
    >>> r = ctrl.list_profiles()
    >>> r.success and isinstance(r.data, list)
    True
    """

    def __init__(self, api: Optional[SettingsProfilesAPI] = None):
        self.api = api or SettingsProfilesAPI()

    # -------------------------------------------------------------------------
    # Bootstrap / listing / retrieval
    # -------------------------------------------------------------------------

    def ensure_default(self) -> OpResult[Dict[str, Any]]:
        """Ensure one active profile exists (creates 'Default' if needed)."""
        return OpResult.from_api(self.api.ensure_default_profile())

    def list_profiles(self) -> OpResult[List[Dict[str, Any]]]:
        """List profiles with item_count included."""
        return OpResult.from_api(self.api.list_profiles())

    def get_profile(self, profile_id: str) -> OpResult[Dict[str, Any]]:
        """Get a profile by id, enriched with item_count."""
        return OpResult.from_api(self.api.get_profile(profile_id))

    def get_profile_with_values(self, profile_id: str) -> OpResult[Dict[str, Any]]:
        """
        Fetch a profile and its key/value items.

        Returns
        -------
        OpResult[Dict[str, Any]]
            On success, data = {'profile': {...}, 'values': {...}}
        """
        p = self.api.get_profile(profile_id)
        if not p.success or not p.data:
            return OpResult.from_api(p)  # propagate error
        vals = self.api.get_values(profile_id)
        if not vals.success:
            return OpResult.from_api(vals)
        return OpResult(success=True, data={"profile": p.data, "values": vals.data or {}})

    def get_active(self) -> OpResult[Optional[Dict[str, Any]]]:
        """Get the active profile (or None)."""
        return OpResult.from_api(self.api.get_active())

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------

    def validate_name(self, name: str) -> OpResult[bool]:
        """Validate a profile name (syntax/length)."""
        return OpResult.from_api(self.api.validate_name(name))

    def validate_keys(self, keys: Iterable[str]) -> OpResult[bool]:
        """Validate a set of keys."""
        return OpResult.from_api(self.api.validate_keys(keys))

    # -------------------------------------------------------------------------
    # Mutations — profiles
    # -------------------------------------------------------------------------

    def create_profile(self, name: str, description: Optional[str] = None, make_active: bool = False) -> OpResult[Dict[str, Any]]:
        """Create a new profile."""
        return OpResult.from_api(self.api.create(name=name, description=description, make_active=make_active))

    def rename_profile(self, profile_id: str, new_name: str) -> OpResult[Dict[str, Any]]:
        """Rename an existing profile (update name only)."""
        return OpResult.from_api(self.api.update(profile_id=profile_id, name=new_name, description=None))

    def update_description(self, profile_id: str, description: Optional[str]) -> OpResult[Dict[str, Any]]:
        """Update description only."""
        return OpResult.from_api(self.api.update(profile_id=profile_id, name=None, description=description))

    def update_profile(self, profile_id: str, name: Optional[str] = None, description: Optional[str] = None) -> OpResult[Dict[str, Any]]:
        """Update name and/or description."""
        return OpResult.from_api(self.api.update(profile_id=profile_id, name=name, description=description))

    def duplicate_profile(self, source_profile_id: str, new_name: str, description: Optional[str] = None, make_active: bool = False) -> OpResult[Dict[str, Any]]:
        """Duplicate a profile (including items)."""
        return OpResult.from_api(
            self.api.duplicate(source_profile_id=source_profile_id, new_name=new_name, description=description, make_active=make_active)
        )

    def delete_profile(self, profile_id: str) -> OpResult[bool]:
        """Delete a profile (invariant: another becomes active or default created)."""
        return OpResult.from_api(self.api.delete(profile_id))

    def set_active(self, profile_id: str) -> OpResult[Dict[str, Any]]:
        """Set a profile active."""
        return OpResult.from_api(self.api.set_active(profile_id))

    # -------------------------------------------------------------------------
    # Mutations — key/value
    # -------------------------------------------------------------------------

    def set_values(self, profile_id: str, values: Dict[str, Any]) -> OpResult[Dict[str, Any]]:
        """Upsert key/value pairs."""
        return OpResult.from_api(self.api.set_values(profile_id, values))

    def remove_values(self, profile_id: str, keys: Sequence[str]) -> OpResult[Dict[str, Any]]:
        """Remove a set of keys for a profile."""
        return OpResult.from_api(self.api.remove_values(profile_id, list(keys)))

    # -------------------------------------------------------------------------
    # Suggestions / Utilities
    # -------------------------------------------------------------------------

    def suggest_unique_name(self, base: str) -> OpResult[str]:
        """
        Suggest a non-conflicting profile name by appending " (copy)" or numbered suffixes.

        Parameters
        ----------
        base : str
            Base name to start from.

        Returns
        -------
        OpResult[str]
            On success, data is a unique suggestion. On failure, message/code populated.
        """
        # Validate base syntactically first (we will still try to propose a valid string)
        base_ok = self.api.validate_name(base)
        if not base_ok.success:
            # Try to sanitize minimally: trim, enforce allowed charset subset by stripping disallowed chars
            import re

            trimmed = (base or "").strip()
            sanitized = re.sub(r"[^A-Za-z0-9 _-]+", "", trimmed)[:64] or "Copy"
            base = sanitized

        lst = self.api.list_profiles()
        if not lst.success or lst.data is None:
            return OpResult.from_api(lst)  # propagate error
        existing_lower = {str(d.get("name", "")).lower() for d in lst.data}
        candidate = f"{base} (copy)"
        n = 2
        while candidate.lower() in existing_lower or not self.api.validate_name(candidate).success:
            candidate = f"{base} (copy) {n}"
            n += 1
            if n > 1000:
                # Safety bound
                return OpResult(success=False, message="Unable to construct a unique name", code=ErrorCodes.INVALID_CONFIG.value)
        return OpResult(success=True, data=candidate)

    def apply_changes(
        self,
        profile_id: str,
        name: Optional[str],
        description: Optional[str],
        set_values_map: Optional[Dict[str, Any]],
        remove_keys: Optional[Sequence[str]],
    ) -> OpResult[Dict[str, Any]]:
        """
        Apply pending metadata (name/description) and key/value changes in a robust order.

        Strategy
        --------
        1) Update metadata first (name/description)
        2) Remove unwanted keys (if any)
        3) Upsert values (if any)
        4) Return the refreshed profile dict

        Returns
        -------
        OpResult[Dict[str, Any]]
            data = updated profile dict (enriched with item_count)
        """
        # 1) Metadata
        if name is not None or description is not None:
            upd = self.api.update(profile_id=profile_id, name=name, description=description)
            if not upd.success:
                return OpResult.from_api(upd)

        # 2) Remove keys
        if remove_keys:
            rm = self.api.remove_values(profile_id, list(remove_keys))
            if not rm.success:
                return OpResult.from_api(rm)

        # 3) Upsert values
        if set_values_map:
            st = self.api.set_values(profile_id, set_values_map)
            if not st.success:
                return OpResult.from_api(st)

        # 4) Return latest
        return OpResult.from_api(self.api.get_profile(profile_id))