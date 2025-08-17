"""
src/pk_py_lib/core/settings_profiles.py

Core settings profile management: persistent profiles with Active/Default semantics.

This module provides:
- SettingsProfile dataclass: a simple in-memory representation
- SettingsProfilesManager: CRUD, copy, set-active/default, import/export, validation

Persistence model (canonical subset for MVP):
- Table: settings_profiles(id INTEGER PK AUTOINCREMENT,
                           name TEXT UNIQUE COLLATE NOCASE,
                           data TEXT JSON,
                           is_default INTEGER,
                           created_at TEXT ISO8601,
                           updated_at TEXT ISO8601)
- Active profile id stored in meta table under key 'active_profile_id' (stringified integer)

Invariants:
- Name validation: ^[A-Za-z0-9 _-]{1,64}$ (case-insensitive unique)
- Single default at most (logic-enforced; zero or one)
- Cannot delete the active profile
- Cannot delete the last remaining profile

Transactions:
- All mutating operations execute inside DatabaseManager.get_connection context,
  which commits on success and rolls back on exception.

Logging:
- Logger name: "pk_py_lib.settings_profiles"
- INFO for create/update/delete/copy/set-active/set-default
- WARNING for validation failures
- ERROR for DB/persistence failures

Note: Syntax validation via ast performed (see project rules).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from .database import DatabaseManager

logger = logging.getLogger("pk_py_lib.settings_profiles")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SettingsProfile:
    """
    In-memory representation of a settings profile.

    Parameters
    ----------
    id : Optional[int]
        Database primary key. None for not-yet-persisted instances.
    name : str
        Human-friendly, unique name. Rules: ^[A-Za-z0-9 _-]{1,64}$ (case-insensitive unique).
    data : Dict[str, Any]
        Arbitrary JSON-serializable settings payload for the profile (algorithm defaults, paths, etc).
    is_default : bool
        Whether this profile is the designated "Default" for future app launches (at most one).
    created_at : Optional[str]
        ISO8601 timestamp (UTC, Z-suffixed) when the profile was created.
    updated_at : Optional[str]
        ISO8601 timestamp (UTC, Z-suffixed) when the profile was last updated.

    Examples
    --------
    >>> p = SettingsProfile(name="My Flow", data={"algorithms": ["phash"]})
    >>> p.is_default
    False
    """
    id: Optional[int] = None
    name: str = "Default"
    data: Dict[str, Any] = field(default_factory=dict)
    is_default: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class SettingsProfilesManager:
    """
    Manage persistent settings profiles and active/default semantics.

    This manager uses the settings_profiles table for storage and the meta table
    ('active_profile_id' key) for the current active profile id.

    Integration hooks
    -----------------
    - on_active_change: Optional[Callable[[SettingsProfile], None]]
      Called after a successful set_active_profile(), create_profile(make_active=True),
      or copy_profile(make_active=True) with the active SettingsProfile instance.
      The GUI or application may use this to align any in-process state.

    Usage
    -----
    >>> db = DatabaseManager()
    >>> db.initialize()
    >>> mgr = SettingsProfilesManager(db)
    >>> created = mgr.create_profile("Work", {"threshold": 0.9}, make_active=True, make_default=True)
    >>> active = mgr.get_active_profile()
    >>> assert active and active.name == "Work"
    """

    NAME_REGEX = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")

    def __init__(self, db_manager: DatabaseManager, on_active_change: Optional[Callable[[SettingsProfile], None]] = None):
        """
        Initialize the manager.

        Parameters
        ----------
        db_manager : DatabaseManager
            Database manager providing connection helpers.
        on_active_change : Optional[Callable[[SettingsProfile], None]]
            Callback invoked after active profile changes (optional).
        """
        self.db = db_manager
        self.on_active_change = on_active_change

    # -------------------------------
    # Helpers
    # -------------------------------
    @staticmethod
    def _now_iso() -> str:
        """Return current UTC time as ISO8601 string without microseconds, suffixed with 'Z'."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @classmethod
    def validate_name(cls, name: str) -> None:
        """
        Validate profile name.

        Rules:
        - Required, 1–64 characters
        - Allowed: letters, digits, space, underscore, hyphen
        - Case-insensitive uniqueness enforced at persistence time

        Raises
        ------
        ValueError
            If name violates rules.
        """
        if not isinstance(name, str):
            raise ValueError("Profile name must be a string")
        if not cls.NAME_REGEX.match(name):
            raise ValueError("Invalid profile name. Allowed: letters, digits, space, _ or -, length 1–64.")

    def _exists_name(self, conn: sqlite3.Connection, name: str, exclude_id: Optional[int] = None) -> bool:
        """Return True if another profile with same name (case-insensitive) exists."""
        if exclude_id is None:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) LIMIT 1", (name,))
        else:
            cur = conn.execute(
                "SELECT id FROM settings_profiles WHERE lower(name) = lower(?) AND id != ? LIMIT 1",
                (name, exclude_id),
            )
        return cur.fetchone() is not None

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> SettingsProfile:
        """Convert row to SettingsProfile."""
        data_obj: Dict[str, Any]
        try:
            data_obj = json.loads(row["data"]) if row["data"] else {}
            if not isinstance(data_obj, dict):
                data_obj = {"_": data_obj}
        except Exception:
            data_obj = {}
        return SettingsProfile(
            id=int(row["id"]),
            name=str(row["name"]),
            data=data_obj,
            is_default=bool(row["is_default"]),
            created_at=str(row["created_at"]) if row["created_at"] is not None else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] is not None else None,
        )

    def _load_profile_by_id(self, conn: sqlite3.Connection, profile_id: int) -> Optional[SettingsProfile]:
        cur = conn.execute("SELECT id, name, data, is_default, created_at, updated_at FROM settings_profiles WHERE id = ?", (profile_id,))
        row = cur.fetchone()
        return self._row_to_profile(row) if row else None

    def _ensure_active_meta_if_possible(self, conn: sqlite3.Connection) -> Optional[SettingsProfile]:
        """
        Ensure meta.active_profile_id exists when profiles exist.

        Behavior:
        - If key missing:
          - Use default profile if present
          - Else use lexicographically-first by name
          - Persist chosen id into meta
        - Return the corresponding SettingsProfile, or None if no profiles exist.
        """
        cur = conn.execute("SELECT value FROM meta WHERE key='active_profile_id'")
        row = cur.fetchone()
        if row and row[0]:
            try:
                pid = int(str(row[0]))
            except Exception:
                pid = None
            if pid is not None:
                prof = self._load_profile_by_id(conn, pid)
                if prof:
                    return prof
            # Fallthrough if dangling/malformed

        # Choose default or first
        cur = conn.execute("SELECT id FROM settings_profiles WHERE is_default = 1 ORDER BY name COLLATE NOCASE LIMIT 1")
        r = cur.fetchone()
        if not r:
            cur = conn.execute("SELECT id FROM settings_profiles ORDER BY name COLLATE NOCASE LIMIT 1")
            r = cur.fetchone()
        if not r:
            return None

        pid = int(r[0])
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES ('active_profile_id', ?, NULL, CURRENT_TIMESTAMP)",
            (str(pid),),
        )
        return self._load_profile_by_id(conn, pid)

    # -------------------------------
    # Public API
    # -------------------------------
    def list_profiles(self) -> List[SettingsProfile]:
        """
        List all settings profiles sorted by name.

        Returns
        -------
        List[SettingsProfile]
            In-memory dataclass instances.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute(
                "SELECT id, name, data, is_default, created_at, updated_at FROM settings_profiles ORDER BY name COLLATE NOCASE"
            )
            return [self._row_to_profile(r) for r in cur.fetchall()]

    def get_profile(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Retrieve a profile by id.

        Parameters
        ----------
        profile_id : int
            Primary key id.

        Returns
        -------
        Optional[SettingsProfile]
            Profile instance if found; otherwise None.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            return self._load_profile_by_id(conn, profile_id)

    def get_active_profile(self) -> Optional[SettingsProfile]:
        """
        Get the active profile.

        Behavior:
        - Return profile referenced by meta.active_profile_id when valid
        - If missing/dangling:
          - Use default if present, else first-by-name when any exist
          - Persist selection into meta
        - If no profiles exist, return None

        Returns
        -------
        Optional[SettingsProfile]
            Active profile or None when table empty.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            return self._ensure_active_meta_if_possible(conn)

    def create_profile(self, name: str, data: Optional[Dict[str, Any]] = None,
                       make_active: bool = False, make_default: bool = False) -> SettingsProfile:
        """
        Create a new profile.

        Parameters
        ----------
        name : str
            Profile name (validated; case-insensitive unique).
        data : Optional[Dict[str, Any]]
            Arbitrary JSON-serializable payload. Defaults to {}.
        make_active : bool
            If True, set the newly created profile as Active.
        make_default : bool
            If True, set the newly created profile as Default (clears previous default).

        Returns
        -------
        SettingsProfile
            Newly created profile instance.

        Raises
        ------
        ValueError
            If validation fails or name collides (case-insensitive).
        """
        self.validate_name(name)
        payload = data or {}
        if not isinstance(payload, dict):
            raise ValueError("Profile data must be a dictionary")

        created = self._now_iso()
        with self.db.get_connection(self.db.settings_db) as conn:
            # Uniqueness
            if self._exists_name(conn, name):
                raise ValueError(f"A profile named '{name}' already exists (case-insensitive).")

            # Insert
            cur = conn.execute(
                """
                INSERT INTO settings_profiles (name, data, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, json.dumps(payload, ensure_ascii=False), 1 if make_default else 0, created, created),
            )
            new_id = int(cur.lastrowid)
            logger.info("Created settings profile id=%s name=%s default=%s", new_id, name, bool(make_default))

            # If default requested, clear others
            if make_default:
                conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (new_id,))
                conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (new_id,))

            # Make active if requested
            new_prof = self._load_profile_by_id(conn, new_id)
            if make_active and new_prof:
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES ('active_profile_id', ?, NULL, CURRENT_TIMESTAMP)",
                    (str(new_id),),
                )
                logger.info("Set active_profile_id=%s", new_id)
                if self.on_active_change:
                    try:
                        self.on_active_change(new_prof)
                    except Exception:
                        logger.exception("on_active_change callback failed for id=%s name=%s", new_id, name)

            return new_prof if new_prof else SettingsProfile(id=new_id, name=name, data=payload, is_default=bool(make_default),
                                                            created_at=created, updated_at=created)

    def update_profile(self, profile_id: int, name: Optional[str] = None, data: Optional[Dict[str, Any]] = None,
                       make_default: Optional[bool] = None) -> SettingsProfile:
        """
        Update profile's name/data and optionally its default flag.

        Parameters
        ----------
        profile_id : int
            Target profile id.
        name : Optional[str]
            New name (validated; must remain unique).
        data : Optional[Dict[str, Any]]
            New JSON payload to replace existing (full replacement).
        make_default : Optional[bool]
            - True: set as default and clear default on others
            - False: explicitly unset default on this profile
            - None: leave default unchanged

        Returns
        -------
        SettingsProfile
            Updated profile.

        Raises
        ------
        ValueError
            If profile does not exist, name invalid/collides, or data type invalid.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            current = self._load_profile_by_id(conn, profile_id)
            if not current:
                raise ValueError(f"Profile id={profile_id} not found")

            new_name = current.name
            new_data = current.data

            if name is not None:
                self.validate_name(name)
                if self._exists_name(conn, name, exclude_id=profile_id):
                    raise ValueError(f"A profile named '{name}' already exists (case-insensitive).")
                new_name = name

            if data is not None:
                if not isinstance(data, dict):
                    raise ValueError("Profile data must be a dictionary")
                new_data = data

            updates: List[str] = []
            params: List[Any] = []
            if new_name != current.name:
                updates.append("name = ?")
                params.append(new_name)
            if new_data != current.data:
                updates.append("data = ?")
                params.append(json.dumps(new_data, ensure_ascii=False))
            if make_default is True:
                # handled after basic update for exclusivity
                pass
            elif make_default is False:
                updates.append("is_default = 0")

            if updates:
                updates.append("updated_at = ?")
                params.append(self._now_iso())
                params.append(profile_id)
                conn.execute(f"UPDATE settings_profiles SET {', '.join(updates)} WHERE id = ?", tuple(params))

            if make_default is True:
                conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (profile_id,))
                conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (profile_id,))
                logger.info("Set default profile id=%s name=%s", profile_id, new_name)

            updated = self._load_profile_by_id(conn, profile_id)
            assert updated is not None
            logger.info("Updated settings profile id=%s name=%s", profile_id, updated.name)
            return updated

    def delete_profile(self, profile_id: int) -> None:
        """
        Delete a profile by id.

        Invariants
        ----------
        - Cannot delete the active profile
        - Cannot delete the last remaining profile

        Raises
        ------
        ValueError
            If invariants would be violated or record does not exist.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            # Ensure it exists
            cur = conn.execute("SELECT id, name, is_default FROM settings_profiles WHERE id = ?", (profile_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Profile id={profile_id} not found")

            # Cannot delete active
            cur = conn.execute("SELECT value FROM meta WHERE key='active_profile_id'")
            r = cur.fetchone()
            active_id = int(r[0]) if r and str(r[0]).isdigit() else None
            if active_id == profile_id:
                raise ValueError("Cannot delete the active profile. Switch to another profile first.")

            # Cannot delete last remaining
            cur = conn.execute("SELECT COUNT(*) FROM settings_profiles")
            total = int(cur.fetchone()[0])
            if total <= 1:
                raise ValueError("Cannot delete the last remaining profile. Create another profile first.")

            conn.execute("DELETE FROM settings_profiles WHERE id = ?", (profile_id,))
            logger.info("Deleted settings profile id=%s name=%s", int(row[0]), str(row[1]))

    def copy_profile(self, source_profile_id: int, new_name: str,
                     make_active: bool = False, make_default: bool = False) -> SettingsProfile:
        """
        Copy a profile into a new profile with a unique name.

        Parameters
        ----------
        source_profile_id : int
            Source profile id to copy.
        new_name : str
            Proposed name for the copy (validated; must be unique).
        make_active : bool
            If True, make the new copy active.
        make_default : bool
            If True, set the new copy as default (clears others).

        Returns
        -------
        SettingsProfile
            Newly created profile.

        Raises
        ------
        ValueError
            On invalid name, collision, or missing source.
        """
        self.validate_name(new_name)
        with self.db.get_connection(self.db.settings_db) as conn:
            src = self._load_profile_by_id(conn, source_profile_id)
            if not src:
                raise ValueError(f"Source profile id={source_profile_id} not found")
            if self._exists_name(conn, new_name):
                raise ValueError(f"A profile named '{new_name}' already exists (case-insensitive).")

            created = self._now_iso()
            cur = conn.execute(
                """
                INSERT INTO settings_profiles (name, data, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_name, json.dumps(src.data, ensure_ascii=False), 1 if make_default else 0, created, created),
            )
            new_id = int(cur.lastrowid)
            logger.info("Copied profile id=%s -> new id=%s name=%s", source_profile_id, new_id, new_name)

            if make_default:
                conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (new_id,))
                conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (new_id,))

            new_prof = self._load_profile_by_id(conn, new_id)
            if make_active and new_prof:
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES ('active_profile_id', ?, NULL, CURRENT_TIMESTAMP)",
                    (str(new_id),),
                )
                logger.info("Set active_profile_id=%s", new_id)
                if self.on_active_change:
                    try:
                        self.on_active_change(new_prof)
                    except Exception:
                        logger.exception("on_active_change callback failed for id=%s name=%s", new_id, new_name)

            return new_prof if new_prof else SettingsProfile(id=new_id, name=new_name, data=src.data, is_default=bool(make_default),
                                                            created_at=created, updated_at=created)

    def set_active_profile(self, profile_id: int) -> SettingsProfile:
        """
        Set a profile as Active by id and update meta.active_profile_id.

        Returns
        -------
        SettingsProfile
            The active profile after the change.

        Raises
        ------
        ValueError
            If the profile id does not exist.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            prof = self._load_profile_by_id(conn, profile_id)
            if not prof:
                raise ValueError(f"Profile id={profile_id} not found")

            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES ('active_profile_id', ?, NULL, CURRENT_TIMESTAMP)",
                (str(profile_id),),
            )
            logger.info("Set active_profile_id=%s (name=%s)", profile_id, prof.name)

            if self.on_active_change:
                try:
                    self.on_active_change(prof)
                except Exception:
                    logger.exception("on_active_change callback failed for id=%s name=%s", profile_id, prof.name)

            return prof

    def set_default_profile(self, profile_id: int) -> SettingsProfile:
        """
        Set exactly one Default profile (logic-enforced exclusivity).

        Returns
        -------
        SettingsProfile
            The profile marked as default.

        Raises
        ------
        ValueError
            If profile id does not exist.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            prof = self._load_profile_by_id(conn, profile_id)
            if not prof:
                raise ValueError(f"Profile id={profile_id} not found")

            conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (profile_id,))
            conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (profile_id,))
            logger.info("Set default profile id=%s name=%s", profile_id, prof.name)

            return self._load_profile_by_id(conn, profile_id) or prof

    def export_profile(self, profile_id: int) -> Dict[str, Any]:
        """
        Export a profile into a portable dictionary.

        Payload includes:
        - id, name, is_default
        - data (deep copy of JSON payload)

        Raises
        ------
        ValueError
            If profile not found.
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            prof = self._load_profile_by_id(conn, profile_id)
            if not prof:
                raise ValueError(f"Profile id={profile_id} not found")
            return {
                "id": prof.id,
                "name": prof.name,
                "is_default": prof.is_default,
                "data": json.loads(json.dumps(prof.data)),  # deep copy via json
                "created_at": prof.created_at,
                "updated_at": prof.updated_at,
            }

    def import_profile(self, payload: Dict[str, Any], strategy: str = "fail_on_conflict") -> SettingsProfile:
        """
        Import a profile payload.

        Parameters
        ----------
        payload : Dict[str, Any]
            Dictionary containing at least 'name' and 'data' (dict).
        strategy : str
            One of:
            - 'fail_on_conflict': raise error if name exists
            - 'rename': append " (copy)" or " (copy N)" to create a unique name
            - 'overwrite': replace existing profile's data/name defaults with incoming

        Returns
        -------
        SettingsProfile
            The imported (created or updated) profile.

        Raises
        ------
        ValueError
            On invalid payload, unknown strategy, or conflicts when 'fail_on_conflict'.
        """
        if not isinstance(payload, dict):
            raise ValueError("Invalid profile payload (must be a dict)")
        name = payload.get("name")
        data = payload.get("data", {})
        is_default = bool(payload.get("is_default", False))
        self.validate_name(name)
        if not isinstance(data, dict):
            raise ValueError("Payload 'data' must be a dictionary")

        strategy = str(strategy or "fail_on_conflict").strip().lower()
        if strategy not in ("fail_on_conflict", "rename", "overwrite"):
            raise ValueError("Invalid import strategy. Use: fail_on_conflict | rename | overwrite")

        with self.db.get_connection(self.db.settings_db) as conn:
            # Conflict check
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) LIMIT 1", (name,))
            row = cur.fetchone()

            if row is None:
                # Create new
                created = self._now_iso()
                cur = conn.execute(
                    """
                    INSERT INTO settings_profiles (name, data, is_default, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, json.dumps(data, ensure_ascii=False), 1 if is_default else 0, created, created),
                )
                new_id = int(cur.lastrowid)
                if is_default:
                    conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (new_id,))
                    conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (new_id,))
                logger.info("Imported new profile id=%s name=%s", new_id, name)
                return self._load_profile_by_id(conn, new_id) or SettingsProfile(id=new_id, name=name, data=data, is_default=is_default, created_at=created, updated_at=created)

            # Conflict handling
            existing_id = int(row[0])
            if strategy == "fail_on_conflict":
                raise ValueError(f"A profile named '{name}' already exists.")
            elif strategy == "rename":
                base = name
                suffix = " (copy)"
                candidate = f"{base}{suffix}"
                n = 2
                while self._exists_name(conn, candidate):
                    candidate = f"{base}{suffix} {n}"
                    n += 1
                created = self._now_iso()
                cur = conn.execute(
                    "INSERT INTO settings_profiles (name, data, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (candidate, json.dumps(data, ensure_ascii=False), 1 if is_default else 0, created, created),
                )
                new_id = int(cur.lastrowid)
                if is_default:
                    conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (new_id,))
                    conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (new_id,))
                logger.info("Imported profile with rename id=%s old_name=%s new_name=%s", new_id, name, candidate)
                return self._load_profile_by_id(conn, new_id) or SettingsProfile(id=new_id, name=candidate, data=data, is_default=is_default, created_at=created, updated_at=created)
            else:
                # overwrite
                updated = self._now_iso()
                conn.execute(
                    "UPDATE settings_profiles SET data = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(data, ensure_ascii=False), updated, existing_id),
                )
                if is_default:
                    conn.execute("UPDATE settings_profiles SET is_default = 0 WHERE id != ?", (existing_id,))
                    conn.execute("UPDATE settings_profiles SET is_default = 1 WHERE id = ?", (existing_id,))
                logger.info("Imported profile with overwrite id=%s name=%s", existing_id, name)
                return self._load_profile_by_id(conn, existing_id) or SettingsProfile(id=existing_id, name=name, data=data, is_default=is_default, updated_at=updated)

# End of file