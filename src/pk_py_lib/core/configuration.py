"""
src/pk_py_lib/core/configuration.py

Configuration Manager for managing app-level and profile-level settings.

This module provides a unified interface for managing configuration settings
that can exist at either the application level (global, single-row app_settings)
or the profile level (per-workflow profile settings).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .database import DatabaseManager

logger = logging.getLogger("pk_py_lib.core.configuration")


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
    """
    # UI Preferences
    theme: str = "light"  # 'light', 'dark', 'auto'
    language: str = "en"
    ui_scale: float = 1.0
    
    # Performance Settings
    max_threads: int = 4
    max_memory_mb: int = 2048
    cache_size_mb: int = 5120  # 5120 MB (≈5 GB) default
    logging_to_user_dir: bool = False  # False: project root logs; True: user data dir logs
    development: bool = False  # Development mode: enables features like Unix line endings (LF) in log files on Windows
    
    # UI Layout (stored as JSON)
    window_geometry: Optional[Dict[str, Any]] = None
    panel_layout: Optional[Dict[str, Any]] = None
    shortcuts: Optional[Dict[str, str]] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None


@dataclass
class Profile:
    """
    Profile settings representing a named workflow configuration.
    
    Multiple profiles can exist, each with their own algorithm defaults,
    file handling preferences, and processing history.
    """
    id: Optional[int] = None
    name: str = "Default"
    is_default: bool = False
    
    # Algorithm Defaults (stored in settings table)
    algorithm_defaults: Dict[str, Any] = field(default_factory=dict)
    
    # File Handling Preferences (stored in settings table)
    file_handling: Dict[str, Any] = field(default_factory=lambda: {
        "auto_scan": True,
        "watch_folders": [],
        "exclude_patterns": [".*", "__pycache__", "*.tmp"],
        "include_hidden": False
    })
    
    # Processing History (stored in settings table)
    history: Dict[str, Any] = field(default_factory=lambda: {
        "recent_folders": [],
        "recent_searches": [],
        "last_export_path": None
    })
    
    # Timestamps
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None


class ConfigurationManager:
    """
    Manages application and profile configuration settings.
    
    This class provides a unified interface for:
    - Managing global app settings (single row in app_settings table)
    - Managing multiple named profiles with their own settings
    - Getting/setting individual configuration values with scope awareness
    - Profile switching and management
    
    Example usage:
    --------------
    >>> config = ConfigurationManager(db_manager)
    >>> 
    >>> # Get app-level setting
    >>> theme = config.get_app_setting("theme")
    >>> 
    >>> # Update app-level setting
    >>> config.set_app_setting("cache_size_mb", 10240)
    >>> 
    >>> # Get current profile
    >>> profile = config.get_current_profile()
    >>> 
    >>> # Get profile-specific setting
    >>> auto_scan = config.get_profile_setting("file_handling.auto_scan")
    >>> 
    >>> # Switch profiles
    >>> config.switch_profile("Photo Processing")
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the ConfigurationManager.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
        self._current_profile_id: Optional[int] = None
        self._app_settings_cache: Optional[AppSettings] = None
        self._profile_cache: Dict[int, Profile] = {}
        
        # Ensure database is initialized
        self._ensure_initialized()
        
        # Load default profile
        self._load_default_profile()
    
    def _ensure_initialized(self) -> None:
        """Ensure database tables and default data exist."""
        with self.db.get_connection(self.db.settings_db) as conn:
            # Ensure logging_to_user_dir column exists in app_settings
            cur = conn.execute("""
                SELECT COUNT(*) FROM pragma_table_info('app_settings')
                WHERE name = 'logging_to_user_dir'
            """)
            if cur.fetchone()[0] == 0:
                conn.execute("""
                    ALTER TABLE app_settings
                    ADD COLUMN logging_to_user_dir BOOLEAN DEFAULT FALSE
                """)
            
            # Ensure development column exists in app_settings
            cur = conn.execute("""
                SELECT COUNT(*) FROM pragma_table_info('app_settings')
                WHERE name = 'development'
            """)
            if cur.fetchone()[0] == 0:
                conn.execute("""
                    ALTER TABLE app_settings
                    ADD COLUMN development BOOLEAN DEFAULT FALSE
                """)
            
            # Check if app_settings has a row
            cur = conn.execute("SELECT COUNT(*) FROM app_settings")
            if cur.fetchone()[0] == 0:
                # Create default app settings
                conn.execute("""
                    INSERT INTO app_settings (
                        theme, language, ui_scale,
                        max_threads, max_memory_mb, cache_size_mb, logging_to_user_dir, development
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, ("light", "en", 1.0, 4, 2048, 5120, False, False))
            
            # Check if default profile exists
            cur = conn.execute("SELECT COUNT(*) FROM profiles WHERE is_default = 1")
            if cur.fetchone()[0] == 0:
                # Create default profile
                conn.execute("""
                    INSERT INTO profiles (name, is_default) VALUES (?, ?)
                """, ("Default", True))
    
    def _load_default_profile(self) -> None:
        """Load the default profile as the current profile."""
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("""
                SELECT id FROM profiles WHERE is_default = 1 LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                self._current_profile_id = row[0]
            else:
                # Fallback to first profile
                cur = conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 1")
                row = cur.fetchone()
                if row:
                    self._current_profile_id = row[0]
    
    # -------------------------------------------------------------------------
    # App Settings Methods
    # -------------------------------------------------------------------------
    
    def get_app_settings(self) -> AppSettings:
        """
        Get the complete application settings.
        
        Returns:
            AppSettings object with current values
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
            
            # Should not happen if _ensure_initialized worked
            return AppSettings()
    
    def update_app_settings(self, **kwargs) -> None:
        """
        Update application settings.
        
        Args:
            **kwargs: Setting names and values to update
            
        Example:
            config.update_app_settings(theme="dark", cache_size_mb=10240)
        """
        settings = self.get_app_settings()
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
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
        
        Args:
            key: Setting name (e.g., "theme", "cache_size_mb")
            
        Returns:
            Setting value or None if not found
        """
        settings = self.get_app_settings()
        return getattr(settings, key, None)
    
    def set_app_setting(self, key: str, value: Any) -> None:
        """
        Set a single app-level setting value.
        
        Args:
            key: Setting name
            value: New value
        """
        self.update_app_settings(**{key: value})
    
    # -------------------------------------------------------------------------
    # Profile Methods
    # -------------------------------------------------------------------------
    
    def get_current_profile(self) -> Profile:
        """
        Get the currently active profile.
        
        Returns:
            Current Profile object
        """
        if self._current_profile_id is None:
            self._load_default_profile()
        
        if self._current_profile_id in self._profile_cache:
            return self._profile_cache[self._current_profile_id]
        
        return self._load_profile(self._current_profile_id)
    
    def _load_profile(self, profile_id: int) -> Profile:
        """
        Load a profile from the database.
        
        Args:
            profile_id: Profile ID to load
            
        Returns:
            Profile object
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            # Load basic profile info
            cur = conn.execute("""
                SELECT name, is_default, created_at, modified_at
                FROM profiles
                WHERE id = ?
            """, (profile_id,))
            row = cur.fetchone()
            
            if not row:
                raise ValueError(f"Profile {profile_id} not found")
            
            profile = Profile(
                id=profile_id,
                name=row[0],
                is_default=bool(row[1]),
                created_at=datetime.fromisoformat(row[2]) if row[2] else None,
                modified_at=datetime.fromisoformat(row[3]) if row[3] else None
            )
            
            # Load profile settings from settings table
            cur = conn.execute("""
                SELECT category, key, value, type
                FROM settings
                WHERE profile_id = ?
            """, (profile_id,))
            
            for category, key, value, type_str in cur.fetchall():
                # Deserialize value based on type
                if type_str == "json":
                    value = json.loads(value)
                elif type_str == "int":
                    value = int(value)
                elif type_str == "float":
                    value = float(value)
                elif type_str == "bool":
                    value = value.lower() in ("true", "1", "yes")
                
                # Store in appropriate profile field
                if category == "algorithm_defaults":
                    profile.algorithm_defaults[key] = value
                elif category == "file_handling":
                    profile.file_handling[key] = value
                elif category == "history":
                    profile.history[key] = value
            
            # Cache the profile
            self._profile_cache[profile_id] = profile
            return profile
    
    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        List all available profiles.
        
        Returns:
            List of profile info dictionaries
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("""
                SELECT id, name, is_default, created_at, modified_at
                FROM profiles
                ORDER BY name
            """)
            
            profiles = []
            for row in cur.fetchall():
                profiles.append({
                    "id": row[0],
                    "name": row[1],
                    "is_default": bool(row[2]),
                    "is_current": row[0] == self._current_profile_id,
                    "created_at": row[3],
                    "modified_at": row[4]
                })
            
            return profiles
    
    def switch_profile(self, profile_name: str) -> Profile:
        """
        Switch to a different profile.
        
        Args:
            profile_name: Name of the profile to switch to
            
        Returns:
            The newly active Profile object
            
        Raises:
            ValueError: If profile not found
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("""
                SELECT id FROM profiles WHERE name = ?
            """, (profile_name,))
            row = cur.fetchone()
            
            if not row:
                raise ValueError(f"Profile '{profile_name}' not found")
            
            self._current_profile_id = row[0]
            return self.get_current_profile()
    
    def create_profile(self, name: str, copy_from: Optional[str] = None) -> Profile:
        """
        Create a new profile.
        
        Args:
            name: Name for the new profile
            copy_from: Optional name of profile to copy settings from
            
        Returns:
            The newly created Profile object
            
        Raises:
            ValueError: If profile name already exists
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            # Check if name exists
            cur = conn.execute("SELECT id FROM profiles WHERE name = ?", (name,))
            if cur.fetchone():
                raise ValueError(f"Profile '{name}' already exists")
            
            # Create new profile
            cur = conn.execute("""
                INSERT INTO profiles (name, is_default)
                VALUES (?, ?)
            """, (name, False))
            new_id = cur.lastrowid
            
            # Copy settings if requested
            if copy_from:
                cur = conn.execute("""
                    SELECT id FROM profiles WHERE name = ?
                """, (copy_from,))
                row = cur.fetchone()
                if row:
                    source_id = row[0]
                    conn.execute("""
                        INSERT INTO settings (profile_id, category, key, value, type)
                        SELECT ?, category, key, value, type
                        FROM settings
                        WHERE profile_id = ?
                    """, (new_id, source_id))
            
            return self._load_profile(new_id)
    
    def delete_profile(self, name: str) -> None:
        """
        Delete a profile.
        
        Args:
            name: Name of the profile to delete
            
        Raises:
            ValueError: If trying to delete default or current profile
        """
        with self.db.get_connection(self.db.settings_db) as conn:
            cur = conn.execute("""
                SELECT id, is_default FROM profiles WHERE name = ?
            """, (name,))
            row = cur.fetchone()
            
            if not row:
                raise ValueError(f"Profile '{name}' not found")
            
            profile_id, is_default = row
            
            if is_default:
                raise ValueError("Cannot delete the default profile")
            
            if profile_id == self._current_profile_id:
                raise ValueError("Cannot delete the current profile")
            
            # Delete profile and cascade will handle settings
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
            
            # Clear from cache
            if profile_id in self._profile_cache:
                del self._profile_cache[profile_id]
    
    def get_profile_setting(self, key: str, profile: Optional[Profile] = None) -> Any:
        """
        Get a profile-specific setting value.
        
        Args:
            key: Setting path (e.g., "file_handling.auto_scan")
            profile: Profile to get from (defaults to current)
            
        Returns:
            Setting value or None if not found
        """
        if profile is None:
            profile = self.get_current_profile()
        
        # Parse key path
        parts = key.split(".")
        if len(parts) == 1:
            # Direct attribute
            return getattr(profile, key, None)
        elif len(parts) == 2:
            # Nested in dict
            category, subkey = parts
            if category == "algorithm_defaults":
                return profile.algorithm_defaults.get(subkey)
            elif category == "file_handling":
                return profile.file_handling.get(subkey)
            elif category == "history":
                return profile.history.get(subkey)
        
        return None
    
    def set_profile_setting(self, key: str, value: Any, profile: Optional[Profile] = None) -> None:
        """
        Set a profile-specific setting value.
        
        Args:
            key: Setting path (e.g., "file_handling.auto_scan")
            value: New value
            profile: Profile to update (defaults to current)
        """
        if profile is None:
            profile = self.get_current_profile()
        
        # Parse key path and update
        parts = key.split(".")
        if len(parts) == 2:
            category, subkey = parts
            
            # Update in-memory
            if category == "algorithm_defaults":
                profile.algorithm_defaults[subkey] = value
            elif category == "file_handling":
                profile.file_handling[subkey] = value
            elif category == "history":
                profile.history[subkey] = value
            else:
                logger.warning(f"Unknown profile setting category: {category}")
                return
            
            # Determine value type for database
            if isinstance(value, bool):
                type_str = "bool"
                db_value = str(value)
            elif isinstance(value, int):
                type_str = "int"
                db_value = str(value)
            elif isinstance(value, float):
                type_str = "float"
                db_value = str(value)
            elif isinstance(value, (dict, list)):
                type_str = "json"
                db_value = json.dumps(value)
            else:
                type_str = "string"
                db_value = str(value)
            
            # Save to database
            with self.db.get_connection(self.db.settings_db) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO settings
                    (profile_id, category, key, value, type)
                    VALUES (?, ?, ?, ?, ?)
                """, (profile.id, category, subkey, db_value, type_str))
                
                # Update profile modified timestamp
                conn.execute("""
                    UPDATE profiles
                    SET modified_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (profile.id,))
    
    # -------------------------------------------------------------------------
    # Generic Methods (scope-aware)
    # -------------------------------------------------------------------------
    
    def get_setting(self, key: str, scope: Optional[SettingScope] = None) -> Any:
        """
        Get a setting value, determining scope automatically if not specified.
        
        Args:
            key: Setting key
            scope: Optional scope hint (APP or PROFILE)
            
        Returns:
            Setting value or None if not found
        """
        if scope == SettingScope.APP:
            return self.get_app_setting(key)
        elif scope == SettingScope.PROFILE:
            return self.get_profile_setting(key)
        else:
            # Try to determine scope automatically
            app_settings = self.get_app_settings()
            if hasattr(app_settings, key):
                return self.get_app_setting(key)
            else:
                return self.get_profile_setting(key)
    
    def set_setting(self, key: str, value: Any, scope: Optional[SettingScope] = None) -> None:
        """
        Set a setting value, determining scope automatically if not specified.
        
        Args:
            key: Setting key
            value: New value
            scope: Optional scope hint (APP or PROFILE)
        """
        if scope == SettingScope.APP:
            self.set_app_setting(key, value)
        elif scope == SettingScope.PROFILE:
            self.set_profile_setting(key, value)
        else:
            # Try to determine scope automatically
            app_settings = self.get_app_settings()
            if hasattr(app_settings, key):
                self.set_app_setting(key, value)
            else:
                self.set_profile_setting(key, value)