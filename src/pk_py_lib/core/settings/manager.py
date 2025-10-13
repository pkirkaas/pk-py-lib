"""
src/pk_py_lib/core/settings/manager.py

Unified Settings Manager consolidating functionality from both
ConfigurationManager and SettingsProfilesManager.

This module provides a single, unified interface for managing:
- Global application settings (AppSettings)
- Named profile settings with JSON schema support
- Backward compatibility with legacy key-value profiles

Note: This module was syntax-validated using Python's ast module per project rules.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
import warnings
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from ..database import DatabaseManager
from .schema import (
    SETTINGS_PROFILE_SCHEMA,
    validate_settings_schema,
    normalize_settings,
    create_default_profile,
    is_valid_for_save,
    is_valid_for_run,
    SettingsValidationError
)

logger = logging.getLogger("pk_py_lib.settings.manager")


# ---------------------------------------------------------------------------
# Enums and Data Models
# ---------------------------------------------------------------------------

class SettingScope(Enum):
    """Defines the scope of a configuration setting."""
    APP = "app"        # Global application settings
    PROFILE = "profile"  # Profile-specific settings


@dataclass
class AppSettings:
    """
    Application-wide settings (single row in app_settings table).

    These settings apply globally to the entire application regardless
    of which profile is active.

    Attributes
    ----------
    theme : str
        UI theme preference ('light', 'dark', 'auto')
    language : str
        Application language code
    ui_scale : float
        UI scaling factor
    max_threads : int
        Maximum worker threads for processing
    max_memory_mb : int
        Maximum memory usage in MB
    cache_size_mb : int
        Cache size limit in MB
    logging_to_user_dir : bool
        Whether to write logs to user directory instead of project root
    development : bool
        Development mode flag
    window_geometry : Optional[Dict[str, Any]]
        Window size/position data
    panel_layout : Optional[Dict[str, Any]]
        Panel layout configuration
    shortcuts : Optional[Dict[str, str]]
        Keyboard shortcuts mapping
    created_at : Optional[datetime]
        Creation timestamp
    modified_at : Optional[datetime]
        Last modification timestamp

    Examples
    --------
    >>> settings = AppSettings(theme="dark", cache_size_mb=10240)
    >>> settings.theme
    'dark'
    """
    # UI Preferences
    theme: str = "light"
    language: str = "en"
    ui_scale: float = 1.0

    # Performance Settings
    max_threads: int = 4
    max_memory_mb: int = 2048
    cache_size_mb: int = 5120
    logging_to_user_dir: bool = False
    development: bool = False

    # UI Layout (stored as JSON)
    window_geometry: Optional[Dict[str, Any]] = None
    panel_layout: Optional[Dict[str, Any]] = None
    shortcuts: Optional[Dict[str, str]] = None

    # Timestamps
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None


@dataclass
class SettingsProfile:
    """
    Strongly-typed in-memory representation of a Settings Profile.

    Supports both legacy key-value and new JSON schema formats.

    Attributes
    ----------
    id : str
        UUID string serving as the primary key
    name : str
        Human-friendly unique name (case-insensitive unique)
    description : Optional[str]
        Optional longer description
    is_active : bool
        Whether this profile is currently active
    created_at : str
        Creation timestamp in UTC ISO8601 with 'Z' suffix
    updated_at : str
        Update timestamp in UTC ISO8601 with 'Z' suffix
    json_data : Optional[Dict[str, Any]]
        Structured profile data in JSON schema format (None for legacy profiles)
    legacy_items : Optional[Dict[str, Any]]
        Legacy key-value items (None for JSON schema profiles)

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
# Error Classes
# ---------------------------------------------------------------------------

class SettingsError(Exception):
    """Base class for settings errors."""

class ValidationError(SettingsError):
    """Raised when validation rules are violated."""

class AlreadyExistsError(SettingsError):
    """Raised on case-insensitive uniqueness conflicts (e.g., name or key)."""

class NotFoundError(SettingsError):
    """Raised when a requested profile or item does not exist."""

class StorageError(SettingsError):
    """Raised for underlying storage/SQLite failures."""

class MigrationError(SettingsError):
    """Raised on migration/meta corruption scenarios."""

class ConcurrencyError(SettingsError):
    """Raised on optimistic concurrency or lock conflicts."""


# ---------------------------------------------------------------------------
# Unified Settings Manager (Consolidated)
# ---------------------------------------------------------------------------

class SettingsManager:
    """
    Unified manager for application and profile settings.

    This class consolidates functionality from both ConfigurationManager
    and SettingsProfilesManager to provide a single, coherent interface
    for managing:
    - Global application settings (AppSettings)
    - Named profile settings with JSON schema support
    - Backward compatibility with legacy key-value profiles

    Key Features:
    - Unified API for both app and profile settings
    - Modern JSON schema-based profile management
    - Backward compatibility with legacy profiles
    - Proper validation and error handling
    - Automatic profile migration capabilities

    Examples
    --------
    >>> db = DatabaseManager()
    >>> db.initialize()
    >>> settings = SettingsManager(db)

    >>> # Manage app settings
    >>> app_settings = settings.get_app_settings()
    >>> settings.update_app_settings(theme="dark", cache_size_mb=10240)

    >>> # Manage profiles
    >>> profile = settings.ensure_default_profile()
    >>> settings.set_active_profile(profile.id)

    >>> # Create structured profile
    >>> json_data = create_default_profile("My Profile")
    >>> profile = settings.create_structured_profile(json_data)
    """

    NAME_REGEX = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")
    KEY_REGEX = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the unified settings manager.

        Parameters
        ----------
        db_manager : DatabaseManager
            Database manager providing connection helpers
        """
        self.db = db_manager
        self._app_settings_cache: Optional[AppSettings] = None
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Ensure database tables and default data exist."""
        with self.db.get_connection(self.db.settings_db) as conn:
            # Ensure app_settings table exists with required columns
            self._ensure_app_settings_table(conn)

            # Ensure settings_profiles table exists with json_data column
            self._ensure_profiles_table(conn)

            # Ensure default app settings exist
            self._ensure_default_app_settings(conn)

            # Ensure default profile exists
            self._ensure_default_profile(conn)

    def _ensure_app_settings_table(self, conn: sqlite3.Connection) -> None:
        """Ensure app_settings table exists with all required columns."""
        # First check if app_settings table exists
        cur = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='app_settings'
        """)
        table_exists = cur.fetchone()[0] > 0

        if not table_exists:
            # Table doesn't exist - it should be created by SETTINGS_SCHEMA
            # This shouldn't happen if database.py initialization is working correctly
            logger.warning("app_settings table does not exist - this indicates a database initialization issue")
            return

        # Check if logging_to_user_dir column exists
        cur = conn.execute("""
            SELECT COUNT(*) FROM pragma_table_info('app_settings')
            WHERE name = 'logging_to_user_dir'
        """)
        if cur.fetchone()[0] == 0:
            conn.execute("""
                ALTER TABLE app_settings
                ADD COLUMN logging_to_user_dir BOOLEAN DEFAULT FALSE
            """)

        # Check if development column exists
        cur = conn.execute("""
            SELECT COUNT(*) FROM pragma_table_info('app_settings')
            WHERE name = 'development'
        """)
        if cur.fetchone()[0] == 0:
            conn.execute("""
                ALTER TABLE app_settings
                ADD COLUMN development BOOLEAN DEFAULT FALSE
            """)

        # Ensure app_settings has a row
        cur = conn.execute("SELECT COUNT(*) FROM app_settings")
        if cur.fetchone()[0] == 0:
            conn.execute("""
                INSERT INTO app_settings (
                    theme, language, ui_scale,
                    max_threads, max_memory_mb, cache_size_mb, logging_to_user_dir, development
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("light", "en", 1.0, 4, 2048, 5120, False, False))
            logger.info("Created default app_settings row")

    def _ensure_profiles_table(self, conn: sqlite3.Connection) -> None:
        """Ensure settings_profiles table exists with json_data column."""
        try:
            # First check if table exists
            cur = conn.execute("""
                SELECT COUNT(*) FROM sqlite_master
                WHERE type='table' AND name='settings_profiles'
            """)
            table_exists = cur.fetchone()[0] > 0

            if not table_exists:
                logger.warning("settings_profiles table does not exist - this indicates a database initialization issue")
                return

            conn.execute("SELECT json_data FROM settings_profiles LIMIT 1")
        except sqlite3.OperationalError as e:
            if "no such column: json_data" in str(e):
                # Column doesn't exist, add it
                conn.execute("ALTER TABLE settings_profiles ADD COLUMN json_data TEXT")
                logger.info("Added json_data column to settings_profiles table")
            else:
                logger.error("Error checking settings_profiles table: %s", e)
                raise

    def _ensure_default_app_settings(self, conn: sqlite3.Connection) -> None:
        """Ensure default application settings exist."""
        cur = conn.execute("SELECT COUNT(*) FROM app_settings")
        if cur.fetchone()[0] == 0:
            conn.execute("""
                INSERT INTO app_settings (
                    theme, language, ui_scale,
                    max_threads, max_memory_mb, cache_size_mb, logging_to_user_dir, development
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ("light", "en", 1.0, 4, 2048, 5120, False, False))

    def _ensure_default_profile(self, conn: sqlite3.Connection) -> None:
        """Ensure at least one profile exists."""
        cur = conn.execute("SELECT id FROM settings_profiles LIMIT 1")
        if not cur.fetchone():
            pid = str(uuid.uuid4())
            ts = self._now_iso()
            conn.execute(
                "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at) VALUES (?, 'Default', NULL, 1, ?, ?)",
                (pid, ts, ts),
            )
            logger.info("Created default settings profile id=%s", pid)

    @staticmethod
    def _now_iso() -> str:
        """Current UTC time as ISO8601 without microseconds, suffixed 'Z'."""
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _jdumps(value: Any) -> str:
        """Canonical JSON serializer: UTF-8, sorted keys, compact separators."""
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def validate_profile_name(cls, name: str) -> None:
        """Validate profile name against canonical rules."""
        if not isinstance(name, str):
            raise ValidationError("Profile name must be a string")
        if not cls.NAME_REGEX.match(name):
            raise ValidationError("Invalid profile name: must match ^[A-Za-z0-9 _-]{1,64}$")

    @classmethod
    def validate_keys(cls, keys: Iterable[str]) -> None:
        """Validate a set of keys against canonical rules."""
        for k in keys:
            if not isinstance(k, str):
                raise ValidationError("Keys must be strings")
            if not cls.KEY_REGEX.match(k):
                raise ValidationError(f"Invalid key '{k}': must match ^[A-Za-z0-9_.:-]{{1,128}}$")


# ---------------------------------------------------------------------------
# Application Settings Methods
# ---------------------------------------------------------------------------

    def get_app_settings(self) -> AppSettings:
        """
        Get the complete application settings.

        Returns
        -------
        AppSettings
            Current application settings

        Examples
        --------
        >>> settings = manager.get_app_settings()
        >>> print(settings.theme)
        'dark'
        """
        if self._app_settings_cache is not None:
            return self._app_settings_cache

        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("""
                SELECT theme, language, ui_scale,
                       max_threads, max_memory_mb, cache_size_mb, logging_to_user_dir, development,
                       window_geometry, panel_layout, shortcuts,
                       created_at, modified_at
                FROM app_settings
                LIMIT 1
            """)
            row = cur.fetchone()

            if row:
                settings = AppSettings(
                    theme=row[0],
                    language=row[1],
                    ui_scale=row[2],
                    max_threads=row[3],
                    max_memory_mb=row[4],
                    cache_size_mb=row[5],
                    logging_to_user_dir=bool(row[6]),
                    development=bool(row[7]),
                    window_geometry=json.loads(row[8]) if row[8] else None,
                    panel_layout=json.loads(row[9]) if row[9] else None,
                    shortcuts=json.loads(row[10]) if row[10] else None,
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None,
                    modified_at=datetime.fromisoformat(row[12]) if row[12] else None
                )
                self._app_settings_cache = settings
                return settings

            return AppSettings()

    def update_app_settings(self, **kwargs) -> None:
        """
        Update application settings.

        Parameters
        ----------
        **kwargs
            Setting names and values to update

        Examples
        --------
        >>> manager.update_app_settings(theme="dark", cache_size_mb=10240)
        """
        settings = self.get_app_settings()

        # Update fields
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key)
            else:
                logger.warning(f"Unknown app setting: {key}")

        # Save to database
        with self.db.get_connection(self.db.settings_db) as conn:
            conn.execute("""
                UPDATE app_settings SET
                    theme = ?, language = ?, ui_scale = ?,
                    max_threads = ?, max_memory_mb = ?, cache_size_mb = ?, logging_to_user_dir = ?, development = ?,
                    window_geometry = ?, panel_layout = ?, shortcuts = ?,
                    modified_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM app_settings LIMIT 1)
            """, (
                settings.theme,
                settings.language,
                settings.ui_scale,
                settings.max_threads,
                settings.max_memory_mb,
                settings.cache_size_mb,
                settings.logging_to_user_dir,
                settings.development,
                json.dumps(settings.window_geometry) if settings.window_geometry else None,
                json.dumps(settings.panel_layout) if settings.panel_layout else None,
                json.dumps(settings.shortcuts) if settings.shortcuts else None
            ))

        # Clear cache
        self._app_settings_cache = None

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
        >>> theme = manager.get_app_setting("theme")
        """
        settings = self.get_app_settings()
        return getattr(settings, key, None)

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
        >>> manager.set_app_setting("theme", "dark")
        """
        self.update_app_settings(**{key: value})


# ---------------------------------------------------------------------------
# Profile Management Methods (Consolidated from SettingsProfilesManager)
# ---------------------------------------------------------------------------

    def ensure_default_profile(self) -> SettingsProfile:
        """
        Ensure at least one profile exists. If none, create 'Default' and set it active.

        Returns
        -------
        SettingsProfile
            The ensured (or newly created) active profile

        Examples
        --------
        >>> profile = manager.ensure_default_profile()
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
                logger.info("Created default settings profile id=%s", pid)
            active = self._ensure_single_active_locked(conn)
            if not active:
                raise StorageError("Failed to ensure an active default profile")
            return active

    def list_profiles(self) -> List[SettingsProfile]:
        """
        List all profiles ordered by name (case-insensitive).

        Returns
        -------
        List[SettingsProfile]
            List of all profiles

        Examples
        --------
        >>> profiles = manager.list_profiles()
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute(
                "SELECT id, name, description, is_active, created_at, updated_at FROM settings_profiles ORDER BY name COLLATE NOCASE"
            )
            return [self._row_to_profile(r) for r in cur.fetchall()]

    def get_profile(self, profile_id: str, include_items: bool = True, _conn: Optional[sqlite3.Connection] = None) -> Optional[SettingsProfile]:
        """
        Retrieve profile by id.

        Parameters
        ----------
        profile_id : str
            UUID of the profile
        include_items : bool
            Whether to include items/JSON data in the response
        _conn : Optional[sqlite3.Connection]
            Optional database connection for internal use

        Returns
        -------
        Optional[SettingsProfile]
            The profile or None if not found

        Examples
        --------
        >>> profile = manager.get_profile("550e8400-e29b-41d4-a716-446655440000")
        """
        def _get(conn: sqlite3.Connection) -> Optional[SettingsProfile]:
            if include_items:
                cur = conn.execute(
                    "SELECT id, name, description, is_active, created_at, updated_at, json_data FROM settings_profiles WHERE id = ?",
                    (profile_id,),
                )
            else:
                cur = conn.execute(
                    "SELECT id, name, description, is_active, created_at, updated_at, json_data FROM settings_profiles WHERE id = ?",
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

        Returns
        -------
        Optional[SettingsProfile]
            The active profile or None if table empty

        Examples
        --------
        >>> profile = manager.get_active_profile()
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

        Parameters
        ----------
        profile_id : str
            Profile ID to set as active

        Returns
        -------
        SettingsProfile
            The newly active profile

        Raises
        ------
        NotFoundError
            If the profile does not exist

        Examples
        --------
        >>> profile = manager.set_active_profile("550e8400-e29b-41d4-a716-446655440000")
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            p = self.get_profile(profile_id, _conn=conn)
            if not p:
                raise NotFoundError(f"Profile id={profile_id} not found")
            conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (profile_id,))
            logger.info("Active profile set to id=%s name=%s", p.id, p.name)
            return self.get_profile(profile_id, _conn=conn) or p

    def create_profile(self, name: str, description: Optional[str] = None,
                      make_active: bool = False, json_data: Optional[Dict[str, Any]] = None) -> SettingsProfile:
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
        SettingsProfile
            The created profile

        Raises
        ------
        ValidationError, AlreadyExistsError, StorageError

        Examples
        --------
        >>> profile = manager.create_profile("My Profile", description="Custom settings")
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

        Examples
        --------
        >>> json_data = create_default_profile("My Profile")
        >>> profile = manager.create_structured_profile(json_data)
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

    def _profile_exists_by_name(self, conn: sqlite3.Connection, name: str, exclude_id: Optional[str] = None) -> bool:
        if exclude_id is None:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) LIMIT 1", (name,))
        else:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE lower(name) = lower(?) AND id != ? LIMIT 1", (name, exclude_id))
        return cur.fetchone() is not None

    def _ensure_single_active_locked(self, conn: sqlite3.Connection) -> Optional[SettingsProfile]:
        """Ensure exactly one active profile exists."""
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
            # Use first by name
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
            p = self.get_profile(chosen, _conn=conn)
            return p
        return None

    def get_values(self, profile_id: str, keys: Optional[Iterable[str]] = None, _conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """Get legacy key-value items for a profile."""
        def _get(conn: sqlite3.Connection) -> Dict[str, Any]:
            profile = self.get_profile(profile_id, _conn=conn, include_items=False)
            if not profile:
                raise NotFoundError(f"Profile id={profile_id} not found")

            # For JSON format profiles, return empty dict
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
                    out[str(k)] = v
            return out

        if _conn is not None:
            return _get(_conn)
        with self.db.get_connection(self.db.settings_db) as conn:
            return _get(conn)


# ---------------------------------------------------------------------------
# Unified Setting Access Methods
# ---------------------------------------------------------------------------

    def get_setting(self, key: str, scope: Optional[SettingScope] = None) -> Any:
        """
        Get a setting value, determining scope automatically if not specified.

        Parameters
        ----------
        key : str
            Setting key
        scope : Optional[SettingScope]
            Optional scope hint (APP or PROFILE)

        Returns
        -------
        Any
            Setting value or None if not found

        Examples
        --------
        >>> theme = manager.get_setting("theme")  # Auto-detect scope
        >>> theme = manager.get_setting("theme", SettingScope.APP)  # Explicit scope
        """
        if scope == SettingScope.APP:
            return self.get_app_setting(key)
        elif scope == SettingScope.PROFILE:
            # For profile settings, we need to get the active profile
            profile = self.get_active_profile()
            if profile and profile.is_json_format():
                return profile.json_data.get(key) if profile.json_data else None
            else:
                # For legacy profiles, this would need more complex logic
                return None
        else:
            # Try to determine scope automatically
            app_settings = self.get_app_settings()
            if hasattr(app_settings, key):
                return self.get_app_setting(key)
            else:
                # Try profile settings
                profile = self.get_active_profile()
                if profile and profile.is_json_format() and profile.json_data:
                    return profile.json_data.get(key)
                return None

    def set_setting(self, key: str, value: Any, scope: Optional[SettingScope] = None) -> None:
        """
        Set a setting value, determining scope automatically if not specified.

        Parameters
        ----------
        key : str
            Setting key
        value : Any
            New value
        scope : Optional[SettingScope]
            Optional scope hint (APP or PROFILE)

        Examples
        --------
        >>> manager.set_setting("theme", "dark")  # Auto-detect scope
        >>> manager.set_setting("theme", "dark", SettingScope.APP)  # Explicit scope
        """
        if scope == SettingScope.APP:
            self.set_app_setting(key, value)
        elif scope == SettingScope.PROFILE:
            # For profile settings, update the active profile
            profile = self.get_active_profile()
            if profile:
                if profile.is_json_format() and profile.json_data:
                    profile.json_data[key] = value
                    # Update the profile in database
                    self.update_profile(profile.id, json_data=profile.json_data)
                else:
                    # For legacy profiles, this is more complex
                    logger.warning("Cannot set profile settings on legacy profiles")
        else:
            # Try to determine scope automatically
            app_settings = self.get_app_settings()
            if hasattr(app_settings, key):
                self.set_app_setting(key, value)
            else:
                # Try profile settings
                profile = self.get_active_profile()
                if profile and profile.is_json_format() and profile.json_data is not None:
                    profile.json_data[key] = value
                    self.update_profile(profile.id, json_data=profile.json_data)
                else:
                    logger.warning(f"Could not determine scope for setting: {key}")

    def update_profile(self, profile_id: str, name: Optional[str] = None,
                      description: Optional[str] = None, json_data: Optional[Dict[str, Any]] = None) -> SettingsProfile:
        """
        Update profile metadata and/or JSON data.

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
        SettingsProfile
            The updated profile

        Raises
        ------
        NotFoundError, ValidationError, AlreadyExistsError, StorageError

        Examples
        --------
        >>> profile = manager.update_profile("profile-id", name="New Name")
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


# ---------------------------------------------------------------------------
# Backward Compatibility Functions
# ---------------------------------------------------------------------------

def get_active_profile_settings() -> dict:
    """
    Get the settings from the active profile.

    This function provides backward compatibility for code that expects
    to get profile settings directly.

    Returns
    -------
    dict
        The active profile's settings (json_data for JSON format profiles,
        or converted legacy items for legacy profiles)

    Raises
    ------
    RuntimeError
        If no active profile can be determined or settings retrieval fails

    Examples
    --------
    >>> settings = get_active_profile_settings()
    """
    from ..database import DatabaseManager

    try:
        db = DatabaseManager()
        mgr = SettingsManager(db)
        active_profile = mgr.get_active_profile()

        if active_profile is None:
            # Ensure default profile exists
            active_profile = mgr.ensure_default_profile()

        # If profile is in legacy format, return empty dict for compatibility
        # (legacy profiles should be migrated)
        if active_profile.is_json_format():
            return active_profile.json_data or {}
        else:
            return {}

    except Exception as e:
        raise RuntimeError(f"Failed to get active profile settings: {e}") from e


# ---------------------------------------------------------------------------
# Import re-exports for backward compatibility
# ---------------------------------------------------------------------------

# Re-export key classes and functions for backward compatibility
__all__ = [
    "SettingsManager",
    "AppSettings",
    "SettingsProfile",
    "SettingScope",
    "ValidationError",
    "AlreadyExistsError",
    "NotFoundError",
    "StorageError",
    "get_active_profile_settings",
    # Schema functions
    "validate_settings_schema",
    "normalize_settings",
    "create_default_profile",
    "is_valid_for_save",
    "is_valid_for_run",
]
