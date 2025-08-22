"""
src/pk_py_lib/core/settings_profiles.py

Settings Profiles core manager with JSON schema support.

This module implements the canonical Settings Profiles subsystem with support for both
legacy key-value storage and new JSON schema-based profiles.

Features:
- Backward compatibility with existing key-value profiles
- Support for new structured JSON schema (SettingsProfileOptionA)
- Automatic migration from key-value to JSON format
- Validation using JSON schema and custom rules

The system maintains two storage formats during transition:
1. Legacy: Key-value items in settings_profile_items table
2. New: Structured JSON in settings_profiles.json_data column

Note: This module was syntax-validated using Python's ast module per project rules.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .database import DatabaseManager
from .settings_schema import (
    SETTINGS_PROFILE_SCHEMA,
    validate_settings_schema,
    normalize_settings,
    create_default_profile,
    is_valid_for_save,
    is_valid_for_run,
    SettingsValidationError
)

logger = logging.getLogger("pk_py_lib.settings_profiles")

# ---------------------------------------------------------------------------
# Errors (minimal local definitions; can be refactored into a shared module)
# ---------------------------------------------------------------------------

class SettingsProfilesError(Exception):
    """Base class for settings profiles errors."""

class ValidationError(SettingsProfilesError):
    """Raised when validation rules are violated."""

class AlreadyExistsError(SettingsProfilesError):
    """Raised on case-insensitive uniqueness conflicts (e.g., name or key)."""

class NotFoundError(SettingsProfilesError):
    """Raised when a requested profile or item does not exist."""

class StorageError(SettingsProfilesError):
    """Raised for underlying storage/SQLite failures."""

class MigrationError(SettingsProfilesError):
    """Raised on migration/meta corruption scenarios."""

class ConcurrencyError(SettingsProfilesError):
    """Raised on optimistic concurrency or lock conflicts."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SettingsProfile:
    """
    Strongly-typed in-memory representation of a Settings Profile.

    Supports both legacy key-value and new JSON schema formats.

    Attributes
    ----------
    id : str
        UUID string serving as the primary key (text).
    name : str
        Human-friendly unique name (case-insensitive unique), regex ^[A-Za-z0-9 _-]{1,64}$.
    description : Optional[str]
        Optional longer description.
    is_active : bool
        Whether this profile is currently active.
    created_at : str
        Creation timestamp in UTC ISO8601 with 'Z' suffix.
    updated_at : str
        Update timestamp in UTC ISO8601 with 'Z' suffix.
    json_data : Optional[Dict[str, Any]]
        Structured profile data in JSON schema format (None for legacy profiles).
    legacy_items : Optional[Dict[str, Any]]
        Legacy key-value items (None for JSON schema profiles).

    Examples
    --------
    >>> p = SettingsProfile(id="...", name="Default", description=None, is_active=True,
    ...                     created_at="2025-08-17T00:00:00Z", updated_at="2025-08-17T00:00:00Z",
    ...                     json_data={...}, legacy_items=None)
    """

    id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str
    json_data: Optional[Dict[str, Any]] = None
    legacy_items: Optional[Dict[str, Any]] = None

    def is_json_format(self) -> bool:
        """Return True if this profile uses the new JSON schema format."""
        return self.json_data is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary representation."""
        base = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        
        if self.json_data:
            base["json_data"] = self.json_data
        if self.legacy_items:
            base["legacy_items"] = self.legacy_items
            
        return base


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class SettingsProfilesManager:
    """
    Manager for normalized Settings Profiles.

    Responsibilities
    ----------------
    - CRUD operations on profiles
    - Manage active profile semantics and meta 'pk.settings_profiles'
    - Key/Value get/set/remove for profile items (JSON-serialized)
    - Import/Export payloads
    - Validation helpers

    Usage
    -----
    >>> db = DatabaseManager()
    >>> db.initialize()
    >>> mgr = SettingsProfilesManager(db)
    >>> prof = mgr.ensure_default_profile()
    >>> mgr.set_values(prof.id, {"threshold": 0.9, "algorithms": ["phash", "dhash"]})
    >>> mgr.get_active_profile().id == prof.id
    True
    """

    NAME_REGEX = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")
    KEY_REGEX = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize manager.

        Parameters
        ----------
        db_manager : DatabaseManager
            Database manager providing connection helpers (settings.db).
        """
        self.db = db_manager
        self._ensure_json_column()

    # -------------------------------
    # Helpers
    # -------------------------------

    def _ensure_json_column(self) -> None:
        """Ensure the json_data column exists in settings_profiles table."""
        with self.db.get_connection(self.db.settings_db) as conn:
            # Check if json_data column exists
            try:
                conn.execute("SELECT json_data FROM settings_profiles LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                conn.execute("ALTER TABLE settings_profiles ADD COLUMN json_data TEXT")
                logger.info("Added json_data column to settings_profiles table")

    @staticmethod
    def _now_iso() -> str:
        """Current UTC time as ISO8601 without microseconds, suffixed 'Z'."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _jdumps(value: Any) -> str:
        """
        Canonical JSON serializer: UTF-8, sorted keys, compact separators.

        Returns
        -------
        str
            JSON string ready for storage in TEXT columns.
        """
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def validate_profile_name(cls, name: str) -> None:
        """
        Validate profile name against canonical rules.

        Raises
        ------
        ValidationError
            On invalid type or regex/length violations.
        """
        if not isinstance(name, str):
            raise ValidationError("Profile name must be a string")
        if not cls.NAME_REGEX.match(name):
            raise ValidationError("Invalid profile name: must match ^[A-Za-z0-9 _-]{1,64}$")

    @classmethod
    def validate_keys(cls, keys: Iterable[str]) -> None:
        """
        Validate a set of keys against canonical rules.

        Raises
        ------
        ValidationError
            On any invalid key (type or regex/length).
        """
        for k in keys:
            if not isinstance(k, str):
                raise ValidationError("Keys must be strings")
            if not cls.KEY_REGEX.match(k):
                raise ValidationError(f"Invalid key '{k}': must match ^[A-Za-z0-9_.:-]{{1,128}}$")

    def _row_to_profile(self, row: sqlite3.Row, include_items: bool = True, _conn: Optional[sqlite3.Connection] = None) -> SettingsProfile:
        """Convert database row to SettingsProfile object."""
        profile = SettingsProfile(
            id=str(row["id"]),
            name=str(row["name"]),
            description=str(row["description"]) if row["description"] is not None else None,
            is_active=bool(row["is_active"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        
        # Check if this is a JSON format profile
        if "json_data" in row.keys() and row["json_data"] is not None:
            try:
                profile.json_data = json.loads(row["json_data"])
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse json_data for profile %s", profile.id)
                profile.json_data = None
        
        # Load legacy items if requested and profile is not in JSON format
        if include_items and not profile.is_json_format():
            profile.legacy_items = self.get_values(profile.id, _conn=_conn)
            
        return profile

    @staticmethod
    def _read_meta(conn: sqlite3.Connection) -> Dict[str, Any]:
        cur = conn.execute("SELECT value FROM meta WHERE key='pk.settings_profiles'")
        row = cur.fetchone()
        if not row:
            return {}
        try:
            data = json.loads(row[0])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_meta_active(self, conn: sqlite3.Connection, active_profile_id: Optional[str]) -> None:
        cfg = self._read_meta(conn)
        cfg["schema_version"] = 1
        cfg["active_profile_id"] = active_profile_id
        cfg["last_migrated_at"] = self._now_iso()
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ("pk.settings_profiles", self._jdumps(cfg), "Settings profiles manager state"),
        )

    def _profile_exists_by_name(self, conn: sqlite3.Connection, name: str, exclude_id: Optional[str] = None) -> bool:
        if exclude_id is None:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) LIMIT 1", (name,))
        else:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) AND id != ? LIMIT 1", (name, exclude_id))
        return cur.fetchone() is not None

    def _ensure_single_active_locked(self, conn: sqlite3.Connection) -> Optional[SettingsProfile]:
        """
        Ensure exactly one active profile exists.

        Behavior:
        - If zero active rows:
            * Use one referenced by meta.active_profile_id when valid
            * Else first-by-name
        - If multiple active rows: keep first-by-name
        - Update both table flags and meta

        Returns
        -------
        Optional[SettingsProfile]
            The resolved active profile, or None if table empty.
        """
        cur = conn.execute("SELECT id FROM settings_profiles ORDER BY name COLLATE NOCASE")
        all_ids = [str(r[0]) for r in cur.fetchall()]
        if not all_ids:
            return None

        cur = conn.execute("SELECT id FROM settings_profiles WHERE is_active = 1 ORDER BY name COLLATE NOCASE")
        actives = [str(r[0]) for r in cur.fetchall()]
        chosen: Optional[str]
        if len(actives) == 1:
            chosen = actives[0]
        elif len(actives) == 0:
            meta = self._read_meta(conn)
            candidate = meta.get("active_profile_id")
            chosen = candidate if isinstance(candidate, str) and candidate in all_ids else None
            if chosen is None:
                cur = conn.execute("SELECT id FROM settings_profiles ORDER BY name COLLATE NOCASE LIMIT 1")
                r = cur.fetchone()
                chosen = str(r[0]) if r else None
        else:
            # Multiple actives; reduce to first-by-name
            cur = conn.execute("SELECT id FROM settings_profiles WHERE is_active = 1 ORDER BY name COLLATE NOCASE LIMIT 1")
            r = cur.fetchone()
            chosen = str(r[0]) if r else None

        if chosen:
            conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (chosen,))
            self._write_meta_active(conn, chosen)
            p = self.get_profile(chosen, _conn=conn)
            return p
        return None

    # -------------------------------
    # Public API
    # -------------------------------

    def ensure_default_profile(self) -> SettingsProfile:
        """
        Ensure at least one profile exists. If none, create 'Default' and set it active.

        Returns
        -------
        SettingsProfile
            The ensured (or newly created) active profile.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("SELECT id FROM settings_profiles LIMIT 1")
            row = cur.fetchone()
            if not row:
                pid = str(uuid.uuid4())
                ts = self._now_iso()
                conn.execute(
                    "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at) VALUES (?, 'Default', NULL, 1, ?, ?)",
                    (pid, ts, ts),
                )
                self._write_meta_active(conn, pid)
                logger.info("Created default settings profile id=%s", pid)
            active = self._ensure_single_active_locked(conn)
            if not active:
                raise StorageError("Failed to ensure an active default profile")
            return active

    def list_profiles(self) -> List[SettingsProfile]:
        """
        List all profiles ordered by name (case-insensitive).
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute(
                "SELECT id, name, description, is_active, created_at, updated_at FROM settings_profiles ORDER BY name COLLATE NOCASE"
            )
            return [self._row_to_profile(r) for r in cur.fetchall()]

    def list_profiles_with_counts(self) -> List[Dict[str, Any]]:
        """
        List all profiles with item_count included for each profile.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute(
                """
                SELECT p.id, p.name, p.description, p.is_active, p.created_at, p.updated_at,
                       COALESCE((SELECT COUNT(*) FROM settings_profile_items spi WHERE spi.profile_id = p.id), 0) AS item_count
                FROM settings_profiles p
                ORDER BY p.name COLLATE NOCASE
                """
            )
            items = []
            for r in cur.fetchall():
                p = SettingsProfile(
                    id=str(r["id"]),
                    name=str(r["name"]),
                    description=str(r["description"]) if r["description"] is not None else None,
                    is_active=bool(r["is_active"]),
                    created_at=str(r["created_at"]),
                    updated_at=str(r["updated_at"]),
                )
                items.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "description": p.description,
                        "is_active": p.is_active,
                        "created_at": p.created_at,
                        "updated_at": p.updated_at,
                        "item_count": int(r["item_count"]),
                    }
                )
            return items

    def get_profile(self, profile_id: str, _conn: Optional[sqlite3.Connection] = None,
                   include_items: bool = True) -> Optional[SettingsProfile]:
        """
        Retrieve profile by id.

        Parameters
        ----------
        profile_id : str
            UUID of the profile.
        include_items : bool
            Whether to include items/JSON data in the response.
        _conn : Optional[sqlite3.Connection]
            Optional existing connection.

        Returns
        -------
        Optional[SettingsProfile]
        """
        def _get(conn: sqlite3.Connection) -> Optional[SettingsProfile]:
            if include_items:
                cur = conn.execute(
                    "SELECT id, name, description, is_active, created_at, updated_at, json_data FROM settings_profiles WHERE id = ?",
                    (profile_id,),
                )
            else:
                cur = conn.execute(
                    "SELECT id, name, description, is_active, created_at, updated_at FROM settings_profiles WHERE id = ?",
                    (profile_id,),
                )
            row = cur.fetchone()
            return self._row_to_profile(row, include_items, _conn=conn) if row else None

        if _conn is not None:
            return _get(_conn)
        with self.db.get_connection(self.db.settings_db) as conn:
            return _get(conn)

    def get_active_profile(self) -> Optional[SettingsProfile]:
        """
        Get current active profile, repairing invariants if necessary.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            # Fast path
            cur = conn.execute(
                "SELECT id, name, description, is_active, created_at, updated_at FROM settings_profiles WHERE is_active = 1 ORDER BY name COLLATE NOCASE LIMIT 1"
            )
            row = cur.fetchone()
            if row:
                return self._row_to_profile(row)
            # Repair
            return self._ensure_single_active_locked(conn)

    def set_active_profile(self, profile_id: str) -> SettingsProfile:
        """
        Set exactly one active profile.

        Raises
        ------
        NotFoundError
            If the profile does not exist.
        StorageError
            On storage errors.
        """
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                p = self.get_profile(profile_id, _conn=conn)
                if not p:
                    raise NotFoundError(f"Profile id={profile_id} not found")
                conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (profile_id,))
                self._write_meta_active(conn, profile_id)
                logger.info("Active profile set to id=%s name=%s", p.id, p.name)
                return self.get_profile(profile_id, _conn=conn) or p
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    def create_profile(self, name: str, description: Optional[str] = None,
                      make_active: bool = False, json_data: Optional[Dict[str, Any]] = None) -> SettingsProfile:
        """
        Create a new profile.

        - Validates name
        - Enforces case-insensitive uniqueness
        - If make_active=True, ensures exactly one active (others cleared)
        - Supports both legacy and JSON format profiles

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

        Raises
        ------
        ValidationError, AlreadyExistsError, StorageError
        """
        self.validate_profile_name(name)
        
        # Validate JSON data if provided
        if json_data is not None:
            is_valid, errors = validate_settings_schema(json_data)
            if not is_valid:
                raise ValidationError(f"Invalid JSON schema: {', '.join(errors)}")
        
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                if self._profile_exists_by_name(conn, name):
                    raise AlreadyExistsError(f"A profile named '{name}' already exists (case-insensitive).")
                
                pid = str(uuid.uuid4())
                ts = self._now_iso()
                is_active = 1 if make_active else 0
                
                # Prepare JSON data for storage
                json_data_str = None
                if json_data is not None:
                    json_data_str = self._jdumps(json_data)
                
                conn.execute(
                    "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at, json_data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (pid, name, description, is_active, ts, ts, json_data_str),
                )
                
                if make_active:
                    conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (pid,))
                    self._write_meta_active(conn, pid)
                
                # If no active row exists, make this one active
                cur = conn.execute("SELECT COUNT(*) FROM settings_profiles WHERE is_active = 1")
                if int(cur.fetchone()[0]) == 0:
                    conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (pid,))
                    self._write_meta_active(conn, pid)
                
                logger.info("Created profile id=%s name=%s format=%s", pid, name,
                           "JSON" if json_data else "legacy")
                
                return self.get_profile(pid, _conn=conn) or SettingsProfile(
                    id=pid, name=name, description=description, is_active=bool(is_active),
                    created_at=ts, updated_at=ts, json_data=json_data
                )
        except sqlite3.IntegrityError as e:
            raise AlreadyExistsError(f"Profile name '{name}' conflicts") from e
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    def update_profile(self, profile_id: str, name: Optional[str] = None,
                      description: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None) -> SettingsProfile:
        """
        Update profile name, description, and/or JSON data.

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

        Raises
        ------
        NotFoundError, ValidationError, AlreadyExistsError, StorageError
        """
        if name is None and description is None and json_data is None:
            raise ValidationError("Nothing to update")
        
        if name is not None:
            self.validate_profile_name(name)
        
        # Validate JSON data if provided
        if json_data is not None:
            is_valid, errors = validate_settings_schema(json_data)
            if not is_valid:
                raise ValidationError(f"Invalid JSON schema: {', '.join(errors)}")
        
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                current = self.get_profile(profile_id, _conn=conn, include_items=False)
                if not current:
                    raise NotFoundError(f"Profile id={profile_id} not found")
                
                if name is not None and self._profile_exists_by_name(conn, name, exclude_id=profile_id):
                    raise AlreadyExistsError(f"A profile named '{name}' already exists (case-insensitive).")
                
                updates: List[str] = []
                params: List[Any] = []
                
                if name is not None:
                    updates.append("name = ?")
                    params.append(name)
                
                if description is not None:
                    updates.append("description = ?")
                    params.append(description)
                
                if json_data is not None:
                    updates.append("json_data = ?")
                    params.append(self._jdumps(json_data))
                
                updates.append("updated_at = ?")
                params.append(self._now_iso())
                params.append(profile_id)
                
                sql = f"UPDATE settings_profiles SET {', '.join(updates)} WHERE id = ?"
                cur = conn.execute(sql, tuple(params))
                
                if cur.rowcount != 1:
                    raise ConcurrencyError("Profile update affected an unexpected number of rows")
                
                logger.info("Updated profile id=%s name->%s json_updated=%s",
                           profile_id, name or current.name, json_data is not None)
                
                return self.get_profile(profile_id, _conn=conn) or current
        except sqlite3.IntegrityError as e:
            raise AlreadyExistsError(f"Profile name '{name}' conflicts") from e
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    def delete_profile(self, profile_id: str) -> None:
        """
        Delete a profile. If the deleted profile was active, another is made active,
        or a default is created to maintain the invariant of exactly one active profile.

        Raises
        ------
        NotFoundError, StorageError
        """
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                current = self.get_profile(profile_id, _conn=conn)
                if not current:
                    raise NotFoundError(f"Profile id={profile_id} not found")
                # Count profiles before delete
                cur = conn.execute("SELECT COUNT(*) FROM settings_profiles")
                total = int(cur.fetchone()[0])
                conn.execute("DELETE FROM settings_profiles WHERE id = ?", (profile_id,))
                logger.info("Deleted profile id=%s name=%s", current.id, current.name)
                # Ensure exactly one active remains
                if total <= 1:
                    # Create a fresh default
                    pid = str(uuid.uuid4())
                    ts = self._now_iso()
                    conn.execute(
                        "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at) VALUES (?, 'Default', NULL, 1, ?, ?)",
                        (pid, ts, ts),
                    )
                    self._write_meta_active(conn, pid)
                else:
                    # Normalize actives
                    self._ensure_single_active_locked(conn)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    def duplicate_profile(self, source_profile_id: str, new_name: str, description: Optional[str] = None, make_active: bool = False) -> SettingsProfile:
        """
        Duplicate a profile (including its items) under a new unique name.

        Raises
        ------
        NotFoundError, ValidationError, AlreadyExistsError, StorageError
        """
        self.validate_profile_name(new_name)
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                src = self.get_profile(source_profile_id, _conn=conn)
                if not src:
                    raise NotFoundError(f"Source profile id={source_profile_id} not found")
                if self._profile_exists_by_name(conn, new_name):
                    raise AlreadyExistsError(f"A profile named '{new_name}' already exists (case-insensitive).")
                pid = str(uuid.uuid4())
                ts = self._now_iso()
                act = 1 if make_active else 0
                conn.execute(
                    "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (pid, new_name, description, act, ts, ts),
                )
                # Copy items
                cur = conn.execute("SELECT key, value, created_at, updated_at FROM settings_profile_items WHERE profile_id = ?", (src.id,))
                for key, value, c_at, u_at in cur.fetchall():
                    conn.execute(
                        "INSERT INTO settings_profile_items (id, profile_id, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), pid, str(key), str(value), c_at or ts, u_at or ts),
                    )
                if make_active:
                    conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (pid,))
                    self._write_meta_active(conn, pid)
                # Ensure there is an active profile
                self._ensure_single_active_locked(conn)
                logger.info("Duplicated profile %s -> id=%s name=%s", src.id, pid, new_name)
                return self.get_profile(pid, _conn=conn) or SettingsProfile(
                    id=pid, name=new_name, description=description, is_active=bool(act), created_at=ts, updated_at=ts
                )
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    # -------------------------------
    # Key/Value operations
    # -------------------------------

    def get_values(self, profile_id: str, keys: Optional[Iterable[str]] = None, _conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """
        Read key/value items for a profile. When keys is None, returns all.

        For JSON format profiles, this returns an empty dict as items are stored
        in the json_data column instead.

        Parameters
        ----------
        profile_id : str
            Profile ID to get values for
        keys : Optional[Iterable[str]]
            Optional list of keys to retrieve
        _conn : Optional[sqlite3.Connection]
            Optional existing database connection

        Returns
        -------
        Dict[str, Any]
            Mapping of key -> deserialized Python value.
        """
        def _get(conn: sqlite3.Connection) -> Dict[str, Any]:
            profile = self.get_profile(profile_id, _conn=conn, include_items=False)
            if not profile:
                raise NotFoundError(f"Profile id={profile_id} not found")
            
            # For JSON format profiles, return empty dict (items are in json_data)
            if profile.is_json_format():
                return {}
            
            # For legacy profiles, fetch from items table
            if keys is None:
                cur = conn.execute("SELECT key, value FROM settings_profile_items WHERE profile_id = ? ORDER BY key COLLATE NOCASE", (profile_id,))
            else:
                self.validate_keys(keys)
                placeholders = ",".join("?" for _ in keys)
                params: List[Any] = [profile_id] + [k for k in keys]
                cur = conn.execute(
                    f"SELECT key, value FROM settings_profile_items WHERE profile_id = ? AND lower(key) IN ({','.join('lower(?)' for _ in keys)}) ORDER BY key COLLATE NOCASE",
                    tuple(params),
                )
            out: Dict[str, Any] = {}
            for k, v in cur.fetchall():
                try:
                    out[str(k)] = json.loads(v)
                except Exception:
                    # Fallback in case of corrupted JSON
                    out[str(k)] = v
            return out

        if _conn is not None:
            return _get(_conn)
        with self.db.get_connection(self.db.settings_db) as conn:
            return _get(conn)

    def set_values(self, profile_id: str, values: Dict[str, Any]) -> int:
        """
        Upsert a dictionary of key -> value for a profile.

        Note: For JSON format profiles, this method is a no-op and returns 0,
        as items should be updated via update_profile() with json_data.

        Returns
        -------
        int
            Number of keys written (0 for JSON format profiles).
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            profile = self.get_profile(profile_id, _conn=conn, include_items=False)
            if not profile:
                raise NotFoundError(f"Profile id={profile_id} not found")
            
            # For JSON format profiles, return 0 (items are stored in json_data)
            if profile.is_json_format():
                logger.warning("set_values called on JSON format profile %s, ignoring", profile_id)
                return 0
            
            # For legacy profiles, update items table
            if not isinstance(values, dict):
                raise ValidationError("values must be a dict")
            
            self.validate_keys(values.keys())
            ts = self._now_iso()
            written = 0
            
            for k, v in values.items():
                data = self._jdumps(v)
                # Try update (case-insensitive match)
                cur = conn.execute(
                    "UPDATE settings_profile_items SET value = ?, updated_at = ? WHERE profile_id = ? AND lower(key) = lower(?)",
                    (data, ts, profile_id, k),
                )
                if cur.rowcount == 0:
                    # Insert new
                    conn.execute(
                        "INSERT INTO settings_profile_items (id, profile_id, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), profile_id, k, data, ts, ts),
                    )
                written += 1
            
            return written

    def remove_values(self, profile_id: str, keys: Iterable[str]) -> int:
        """
        Remove keys for a profile.

        Returns
        -------
        int
            Number of rows deleted.
        """
        keys = list(keys)
        self.validate_keys(keys)
        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                if not self.get_profile(profile_id, _conn=conn):
                    raise NotFoundError(f"Profile id={profile_id} not found")
                placeholders = ",".join("?" for _ in keys)
                params: List[Any] = [profile_id] + [k for k in keys]
                cur = conn.execute(
                    f"DELETE FROM settings_profile_items WHERE profile_id = ? AND lower(key) IN ({','.join('lower(?)' for _ in keys)})",
                    tuple(params),
                )
                return int(cur.rowcount or 0)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    # -------------------------------
    # Import/Export
    # -------------------------------

    def export_profile(self, profile_id: str) -> Dict[str, Any]:
        """
        Export a profile to a JSON-serializable dict containing metadata and items.

        For JSON format profiles, the json_data is included instead of items.

        Returns
        -------
        Dict[str, Any]
            {
                "profile": {id, name, description, is_active, created_at, updated_at},
                "items": {key: value} OR "json_data": {structured_data}
            }
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            prof = self.get_profile(profile_id, _conn=conn, include_items=True)
            if not prof:
                raise NotFoundError(f"Profile id={profile_id} not found")
            
            result = {
                "profile": {
                    "id": prof.id,
                    "name": prof.name,
                    "description": prof.description,
                    "is_active": prof.is_active,
                    "created_at": prof.created_at,
                    "updated_at": prof.updated_at,
                }
            }
            
            if prof.is_json_format():
                result["json_data"] = prof.json_data
            else:
                result["items"] = prof.legacy_items or {}
            
            return result

    def import_profile(
        self,
        payload: Dict[str, Any],
        strategy: str = "rename",
        make_active: bool = False,
    ) -> SettingsProfile:
        """
        Import a profile payload.

        Parameters
        ----------
        payload : Dict[str, Any]
            Must include:
              - profile: {name: str, description?: str}
              - items: dict[str, Any] OR json_data: dict for structured profiles
        strategy : str
            Conflict strategy on name:
              - "fail_on_conflict": raise AlreadyExistsError
              - "rename": append " (copy)" or numbered suffix until unique (default)
              - "overwrite": overwrite the existing profile's items (clear-then-set)
        make_active : bool
            Whether to set the imported profile active after import.

        Returns
        -------
        SettingsProfile
        """
        if not isinstance(payload, dict):
            raise ValidationError("payload must be a dict")
        
        prof_meta = payload.get("profile") or {}
        items = payload.get("items") or {}
        json_data = payload.get("json_data")
        name = prof_meta.get("name")
        description = prof_meta.get("description")
        
        # Validate that we have either items or json_data, not both
        if items and json_data:
            raise ValidationError("Payload cannot contain both 'items' and 'json_data'")
        
        if not isinstance(items, dict) and json_data is None:
            raise ValidationError("Payload must contain either 'items' dict or 'json_data'")
        
        self.validate_profile_name(name)

        strategy = (strategy or "rename").strip().lower()
        if strategy not in ("fail_on_conflict", "rename", "overwrite"):
            raise ValidationError("Invalid import strategy")

        try:
            with self.db.get_connection(self.db.settings_db) as conn:
                cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?)", (name,))
                row = cur.fetchone()
                
                if row is None:
                    # New create - use JSON data if available, otherwise legacy items
                    if json_data is not None:
                        created = self.create_profile(name=name, description=description,
                                                    make_active=make_active, json_data=json_data)
                    else:
                        created = self.create_profile(name=name, description=description,
                                                    make_active=make_active)
                        # Set items for legacy profile
                        if items:
                            self.set_values(created.id, items)
                    return created

                existing_id = str(row[0])
                if strategy == "fail_on_conflict":
                    raise AlreadyExistsError(f"Profile named '{name}' already exists")
                elif strategy == "rename":
                    base = name
                    suffix = " (copy)"
                    candidate = f"{base}{suffix}"
                    n = 2
                    while self._profile_exists_by_name(conn, candidate):
                        candidate = f"{base}{suffix} {n}"
                        n += 1
                    
                    if json_data is not None:
                        created = self.create_profile(name=candidate, description=description,
                                                    make_active=make_active, json_data=json_data)
                    else:
                        created = self.create_profile(name=candidate, description=description,
                                                    make_active=make_active)
                        if items:
                            self.set_values(created.id, items)
                    return created
                else:
                    # overwrite: clear existing data and update
                    existing_profile = self.get_profile(existing_id, _conn=conn, include_items=False)
                    
                    if json_data is not None:
                        # Update with JSON data
                        self.update_profile(existing_id, name=name, description=description, json_data=json_data)
                        # Clear legacy items if any
                        conn.execute("DELETE FROM settings_profile_items WHERE profile_id = ?", (existing_id,))
                    else:
                        # Update with legacy items
                        self.update_profile(existing_id, name=name, description=description)
                        # Clear existing items and set new ones
                        conn.execute("DELETE FROM settings_profile_items WHERE profile_id = ?", (existing_id,))
                        if items:
                            self.set_values(existing_id, items)
                    
                    if make_active:
                        self.set_active_profile(existing_id)
                    
                    return self.get_profile(existing_id, _conn=conn) or SettingsProfile(
                        id=existing_id, name=name, description=description, is_active=False,
                        created_at=self._now_iso(), updated_at=self._now_iso()
                    )
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                raise ConcurrencyError("Database is locked") from e
            raise StorageError(str(e)) from e

    # ---------------------------------------------------------------------------
    # New JSON Schema Methods
    # ---------------------------------------------------------------------------

    def migrate_to_json_format(self, profile_id: str) -> SettingsProfile:
        """
        Migrate a legacy profile to JSON format.
        
        Parameters
        ----------
        profile_id : str
            ID of the profile to migrate
            
        Returns
        -------
        SettingsProfile
            The migrated profile in JSON format
            
        Raises
        ------
        NotFoundError, ValidationError, StorageError
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            profile = self.get_profile(profile_id, _conn=conn, include_items=True)
            if not profile:
                raise NotFoundError(f"Profile id={profile_id} not found")
            
            if profile.is_json_format():
                logger.info("Profile %s is already in JSON format", profile_id)
                return profile
            
            # Convert legacy items to JSON format
            json_data = self._convert_legacy_to_json(profile.legacy_items or {})
            
            # Update profile with JSON data
            self.update_profile(profile_id, json_data=json_data, _conn=conn)
            
            # Clear legacy items
            conn.execute("DELETE FROM settings_profile_items WHERE profile_id = ?", (profile_id,))
            
            logger.info("Migrated profile %s to JSON format", profile_id)
            return self.get_profile(profile_id, _conn=conn, include_items=True)
    
    def _convert_legacy_to_json(self, legacy_items: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy key-value items to JSON schema format.
        
        Parameters
        ----------
        legacy_items : Dict[str, Any]
            Legacy key-value items
            
        Returns
        -------
        Dict[str, Any]
            JSON schema compatible data
        """
        # This is a basic conversion - should be customized based on actual legacy structure
        json_data = create_default_profile("Temporary")
        json_data["id"] = str(uuid.uuid4())  # Will be replaced by actual ID
        
        # Map legacy keys to JSON structure (example mapping)
        # This should be customized based on actual legacy key structure
        if "pool1_path" in legacy_items:
            json_data["pools"]["A"]["root_path"] = legacy_items["pool1_path"]
        if "pool2_path" in legacy_items:
            json_data["pools"]["B"]["root_path"] = legacy_items["pool2_path"]
        if "algorithm" in legacy_items:
            json_data["criteria"]["algorithm"] = legacy_items["algorithm"]
        if "similarity_threshold" in legacy_items:
            json_data["criteria"]["degree_ui"] = legacy_items["similarity_threshold"]
        
        return normalize_settings(json_data)
    
    def validate_profile_for_save(self, profile_id: str) -> Tuple[bool, List[str]]:
        """
        Validate if a profile is valid for saving.
        
        Parameters
        ----------
        profile_id : str
            Profile ID to validate
            
        Returns
        -------
        Tuple[bool, List[str]]
            (is_valid, error_messages)
        """
        profile = self.get_profile(profile_id, include_items=True)
        if not profile:
            return False, [f"Profile {profile_id} not found"]
        
        if profile.is_json_format():
            return is_valid_for_save(profile.json_data or {})
        else:
            # Legacy profiles are always considered valid for save
            # (they might not pass JSON validation but we want to preserve them)
            return True, []
    
    def validate_profile_for_run(self, profile_id: str) -> Tuple[bool, List[str]]:
        """
        Validate if a profile is valid for running.
        
        Parameters
        ----------
        profile_id : str
            Profile ID to validate
            
        Returns
        -------
        Tuple[bool, List[str]]
            (is_valid, error_messages)
        """
        profile = self.get_profile(profile_id, include_items=True)
        if not profile:
            return False, [f"Profile {profile_id} not found"]
        
        if profile.is_json_format():
            return is_valid_for_run(profile.json_data or {})
        else:
            # For legacy profiles, we need to convert to JSON format first for validation
            try:
                json_data = self._convert_legacy_to_json(profile.legacy_items or {})
                return is_valid_for_run(json_data)
            except Exception as e:
                return False, [f"Legacy profile validation failed: {str(e)}"]

    # ---------------------------------------------------------------------------
    # Structured Profile Specific Methods
    # ---------------------------------------------------------------------------

    def create_structured_profile(self, json_data: Dict[str, Any], make_active: bool = False) -> SettingsProfile:
        """
        Create a new profile with structured JSON data.
        
        Parameters
        ----------
        json_data : Dict[str, Any]
            JSON schema data for the profile
        make_active : bool
            Whether to make this profile active
            
        Returns
        -------
        SettingsProfile
            The created profile
            
        Raises
        ------
        ValidationError, AlreadyExistsError, StorageError
        """
        # Validate the JSON data
        is_valid, errors = validate_settings_schema(json_data)
        if not is_valid:
            raise ValidationError(f"Invalid JSON schema: {', '.join(errors)}")
            
        # Extract name from JSON data
        name = json_data.get("name")
        if not name or not isinstance(name, str):
            raise ValidationError("JSON data must contain a valid 'name' field")
            
        description = json_data.get("description")
        
        return self.create_profile(name=name, description=description,
                                 make_active=make_active, json_data=json_data)

    def update_structured_profile(self, profile_id: str, json_data: Dict[str, Any]) -> SettingsProfile:
        """
        Update a profile's structured JSON data.
        
        Parameters
        ----------
        profile_id : str
            Profile ID to update
        json_data : Dict[str, Any]
            New JSON schema data
            
        Returns
        -------
        SettingsProfile
            The updated profile
            
        Raises
        ------
        NotFoundError, ValidationError, AlreadyExistsError, StorageError
        """
        # Validate the JSON data
        is_valid, errors = validate_settings_schema(json_data)
        if not is_valid:
            raise ValidationError(f"Invalid JSON schema: {', '.join(errors)}")
            
        # Extract name from JSON data
        name = json_data.get("name")
        if not name or not isinstance(name, str):
            raise ValidationError("JSON data must contain a valid 'name' field")
            
        description = json_data.get("description")
        
        return self.update_profile(profile_id, name=name, description=description, json_data=json_data)

    def duplicate_structured_profile(self, source_profile_id: str, new_name: str,
                                   description: Optional[str] = None,
                                   make_active: bool = False) -> SettingsProfile:
        """
        Duplicate a structured profile with a new name.
        
        Parameters
        ----------
        source_profile_id : str
            Source profile ID to duplicate
        new_name : str
            New profile name
        description : Optional[str]
            New description (optional)
        make_active : bool
            Whether to make the new profile active
            
        Returns
        -------
        SettingsProfile
            The duplicated profile
            
        Raises
        ------
        NotFoundError, ValidationError, AlreadyExistsError, StorageError
        """
        source_profile = self.get_profile(source_profile_id, include_items=True)
        if not source_profile:
            raise NotFoundError(f"Source profile id={source_profile_id} not found")
            
        if not source_profile.is_json_format():
            raise ValidationError("Source profile is not in JSON format")
            
        # Create new JSON data with updated name and description
        new_json_data = source_profile.json_data.copy()
        new_json_data["name"] = new_name
        if description is not None:
            new_json_data["description"] = description
        else:
            new_json_data.pop("description", None)
            
        # Generate new ID for the duplicate
        new_json_data["id"] = str(uuid.uuid4())
        new_json_data["created_at"] = self._now_iso()
        new_json_data["updated_at"] = self._now_iso()
        
        return self.create_structured_profile(new_json_data, make_active=make_active)

    def suggest_unique_name(self, base_name: str) -> str:
        """
        Suggest a unique profile name based on a base name.
        
        Parameters
        ----------
        base_name : str
            Base name to start with
            
        Returns
        -------
        str
            Unique profile name
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            candidate = base_name
            n = 1
            while self._profile_exists_by_name(conn, candidate):
                candidate = f"{base_name} ({n})"
                n += 1
            return candidate