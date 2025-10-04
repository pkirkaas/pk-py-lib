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

from pk_py_lib.api import ApiResponse, ErrorCodes
from pk_py_lib.api.settings_profiles import SettingsProfilesAPI

from pk_py_lib.core.logging.logger import get_logger
logger = get_logger(__name__)

 

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

    # -------------------------------------------------------------------------
    # Structured (JSON) profile helpers for the GUI (Option A)
    # -------------------------------------------------------------------------
    def create_structured_profile(self, profile_json: Dict[str, Any], make_active: bool = False) -> OpResult[Dict[str, Any]]:
        """
        Create a new JSON-format (structured) profile.

        Behavior:
        - Passes name/description at top-level to the API
        - Sends json_data=profile_json
        - After create success, aligns json_data['id'] with the DB id by issuing a follow-up update
        - Sanitizes json_data to ensure schema-required types (e.g., description is a string) and fills generated fields
        """
        try:
            # Defensive copy and sanitization
            payload = dict(profile_json or {})

            # Ensure name/description are strings (no None)
            name = str((payload.get("name") or "")).strip()
            desc = payload.get("description")
            desc = "" if desc is None else str(desc)

            payload["name"] = name
            payload["description"] = desc

            # Add generated fields required by schema if missing
            from uuid import uuid4
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            if not payload.get("id"):
                payload["id"] = str(uuid4())
            payload.setdefault("created_at", now)
            payload.setdefault("updated_at", now)
            payload.setdefault("profile_version", "1.0.0")
            payload.setdefault("schema_version", "1.0")

            from pk_py_lib.core.settings_schema import normalize_settings
            logger.info(f"create_structured_profile before normalize: similarity_hash_algorithm={payload.get('criteria', {}).get('similarity_hash_algorithm')}, algorithm={payload.get('criteria', {}).get('algorithm')}")
            payload = normalize_settings(payload)
            logger.info(f"create_structured_profile after normalize: similarity_hash_algorithm={payload.get('criteria', {}).get('similarity_hash_algorithm')}, algorithm={payload.get('criteria', {}).get('algorithm')}")
            # Initial create
            resp = self.api.create(name=name, description=desc, make_active=make_active, json_data=payload)
            if not resp.success or not resp.data:
                return OpResult.from_api(resp)

            created = resp.data
            new_id = created.get("id")
            if not new_id:
                return OpResult(success=False, message="Create returned no id", code=ErrorCodes.UNKNOWN_ERROR.value)

            # Align json_data.id with DB id if needed
            try:
                if payload.get("id") != new_id:
                    payload["id"] = new_id
                    # Refresh updated_at for alignment update
                    payload["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    upd = self.api.update(profile_id=new_id, name=name, description=desc, json_data=payload)
                    if not upd.success:
                        # Non-fatal; return the created profile
                        return OpResult.from_api(resp)
                    return OpResult.from_api(upd)
            except Exception:
                # Non-fatal alignment failure
                return OpResult.from_api(resp)
            return OpResult.from_api(resp)
        except Exception as e:
            return OpResult(success=False, message=str(e), code=ErrorCodes.UNKNOWN_ERROR.value)

    def update_structured_profile(self, profile_id: str, profile_json: Dict[str, Any]) -> OpResult[Dict[str, Any]]:
        """
        Update an existing JSON-format (structured) profile.

        Behavior:
        - Extracts name and description from profile_json and passes via API
        - Ensures json_data['id'] == profile_id for schema consistency
        - Sanitizes json_data to avoid None for string fields and fill required generated fields if absent
        """
        try:
            # Read current to preserve created_at and defaults where appropriate
            existing = self.api.get_profile(profile_id)
            if not existing.success or not existing.data:
                return OpResult.from_api(existing)

            current = existing.data
            cur_json = dict(current.get("json_data") or {})

            # Build payload and sanitize
            payload = dict(profile_json or {})
            name = str((payload.get("name") or current.get("name", ""))).strip()
            desc = payload.get("description", current.get("description", ""))
            desc = "" if desc is None else str(desc)

            payload["id"] = profile_id
            payload["name"] = name
            payload["description"] = desc

            # Preserve or set generated fields
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            # Keep created_at if present; otherwise fallback to cur_json or current
            payload.setdefault("created_at", cur_json.get("created_at") or current.get("created_at") or now)
            # updated_at reflects this update
            payload["updated_at"] = now
            payload.setdefault("profile_version", cur_json.get("profile_version") or "1.0.0")
            payload.setdefault("schema_version", cur_json.get("schema_version") or "1.0")

            from pk_py_lib.core.settings_schema import normalize_settings
            logger.info(f"update_structured_profile before normalize: similarity_hash_algorithm={payload.get('criteria', {}).get('similarity_hash_algorithm')}, algorithm={payload.get('criteria', {}).get('algorithm')}")
            payload = normalize_settings(payload)
            logger.info(f"update_structured_profile after normalize: similarity_hash_algorithm={payload.get('criteria', {}).get('similarity_hash_algorithm')}, algorithm={payload.get('criteria', {}).get('algorithm')}")
            resp = self.api.update(profile_id=profile_id, name=name, description=desc, json_data=payload)
            if resp.success and resp.data:
                loaded = resp.data.get('json_data', {}).get('criteria', {}).get('similarity_hash_algorithm')
                logger.info(f"After update: loaded similarity_hash_algorithm={loaded}")
            return OpResult.from_api(resp)
        except Exception as e:
            return OpResult(success=False, message=str(e), code=ErrorCodes.UNKNOWN_ERROR.value)

    def duplicate_structured_profile(
        self,
        source_profile_id: str,
        new_name: str,
        description: Optional[str] = None,
        make_active: bool = False
    ) -> OpResult[Dict[str, Any]]:
        """
        Duplicate a profile in JSON format when possible.

        Strategy:
        - If source is JSON format: fetch it, copy its json_data, override name/description,
          clear/replace embedded id, create new via API, then align json_data.id with DB id.
        - Else (legacy): fall back to API.duplicate, then rename per new_name.
        """
        try:
            src = self.api.get_profile(source_profile_id)
            if not src.success or not src.data:
                return OpResult.from_api(src)

            src_data = src.data
            if src_data.get("format") == "json" and "json_data" in src_data:
                # Structured duplicate
                payload = dict(src_data.get("json_data") or {})
                payload["name"] = new_name
                payload["description"] = description or ""
                # Remove or reset id so the create path generates a new one
                payload.pop("id", None)

                created = self.create_structured_profile(payload, make_active=make_active)
                return created
            else:
                # Legacy duplicate fallback
                dup = self.api.duplicate(source_profile_id=source_profile_id, new_name=new_name, description=description, make_active=make_active)
                return OpResult.from_api(dup)
        except Exception as e:
            return OpResult(success=False, message=str(e), code=ErrorCodes.UNKNOWN_ERROR.value)