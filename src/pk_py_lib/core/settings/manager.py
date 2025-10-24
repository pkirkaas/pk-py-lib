"""
Unified settings manager for pk-py-lib.

This module provides a unified interface for managing application settings
and profiles with support for both JSON and legacy formats.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from ...core.logging.logger import get_logger
from ...core.api.response import ApiResponse, ErrorCodes, create_success_response, create_error_response
from ..database import DatabaseManager
from .models import AppSettings, SettingsProfile, DEFAULT_PROFILES


logger = get_logger(__name__)


class UnifiedSettingsManager:
    """
    Unified settings manager for application and profile settings.

    This manager provides a single interface for managing both application-wide
    settings and user profiles, with support for JSON schema validation and
    legacy format compatibility.
    """

    def __init__(self, database_manager: Optional[DatabaseManager] = None):
        """
        Initialize the settings manager.

        Args:
            database_manager: Optional database manager instance
        """
        self.database_manager = database_manager or DatabaseManager()
        self.logger = get_logger(__name__)

    def initialize(self) -> None:
        """Initialize the settings system."""
        self.database_manager.initialize()

    def get_app_settings(self) -> AppSettings:
        """
        Get current application settings.

        Returns:
            Current AppSettings instance
        """
        try:
            conn = self.database_manager.get_connection()
            cursor = conn.execute("""
                SELECT * FROM app_settings WHERE id = 1
            """)

            row = cursor.fetchone()
            if row:
                return AppSettings(
                    id=row['id'],
                    theme=row['theme'],
                    language=row['language'],
                    ui_scale=row['ui_scale'],
                    max_threads=row['max_threads'],
                    max_memory_mb=row['max_memory_mb'],
                    cache_size_mb=row['cache_size_mb'],
                    window_geometry=json.loads(row['window_geometry']) if row['window_geometry'] else None,
                    panel_layout=json.loads(row['panel_layout']) if row['panel_layout'] else None,
                    shortcuts=json.loads(row['shortcuts']) if row['shortcuts'] else None,
                    created_at=datetime.fromisoformat(row['created_at']),
                    modified_at=datetime.fromisoformat(row['modified_at'])
                )
            else:
                # Create default settings
                default_settings = AppSettings()
                self._save_app_settings(default_settings)
                return default_settings

        except Exception as e:
            self.logger.error(f"Failed to get app settings: {e}")
            # Return defaults on error
            return AppSettings()

    def update_app_settings(self, updates: Dict[str, Any]) -> AppSettings:
        """
        Update application settings.

        Args:
            updates: Dictionary of settings to update

        Returns:
            Updated AppSettings instance
        """
        try:
            current = self.get_app_settings()

            # Apply updates
            for key, value in updates.items():
                if hasattr(current, key):
                    setattr(current, key, value)

            # Update timestamp
            current.modified_at = datetime.now()

            # Save to database
            self._save_app_settings(current)
            return current

        except Exception as e:
            self.logger.error(f"Failed to update app settings: {e}")
            raise

    def _save_app_settings(self, settings: AppSettings) -> None:
        """Save application settings to database."""
        conn = self.database_manager.get_connection()

        conn.execute("""
            INSERT OR REPLACE INTO app_settings (
                id, theme, language, ui_scale, max_threads, max_memory_mb, cache_size_mb,
                window_geometry, panel_layout, shortcuts, created_at, modified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            settings.id,
            settings.theme,
            settings.language,
            settings.ui_scale,
            settings.max_threads,
            settings.max_memory_mb,
            settings.cache_size_mb,
            json.dumps(settings.window_geometry) if settings.window_geometry else None,
            json.dumps(settings.panel_layout) if settings.panel_layout else None,
            json.dumps(settings.shortcuts) if settings.shortcuts else None,
            settings.created_at.isoformat(),
            settings.modified_at.isoformat()
        ))

    def list_profiles(self) -> List[SettingsProfile]:
        """
        List all available settings profiles.

        Returns:
            List of SettingsProfile instances
        """
        try:
            conn = self.database_manager.get_connection()
            cursor = conn.execute("""
                SELECT * FROM settings_profiles ORDER BY name
            """)

            profiles = []
            for row in cursor.fetchall():
                profile = SettingsProfile(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    is_active=bool(row['is_active']),
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    json_data=json.loads(row['json_data']) if row['json_data'] else None
                )
                profiles.append(profile)

            return profiles

        except Exception as e:
            self.logger.error(f"Failed to list profiles: {e}")
            return []

    def get_profile(self, profile_id: str) -> Optional[SettingsProfile]:
        """
        Get a specific profile by ID.

        Args:
            profile_id: Profile ID to retrieve

        Returns:
            SettingsProfile instance or None if not found
        """
        try:
            conn = self.database_manager.get_connection()
            cursor = conn.execute("""
                SELECT * FROM settings_profiles WHERE id = ?
            """, (profile_id,))

            row = cursor.fetchone()
            if row:
                return SettingsProfile(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    is_active=bool(row['is_active']),
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    json_data=json.loads(row['json_data']) if row['json_data'] else None
                )

        except Exception as e:
            self.logger.error(f"Failed to get profile {profile_id}: {e}")

        return None

    def get_active_profile(self) -> Optional[SettingsProfile]:
        """
        Get the currently active profile.

        Returns:
            Active SettingsProfile instance or None if none active
        """
        try:
            conn = self.database_manager.get_connection()
            cursor = conn.execute("""
                SELECT * FROM settings_profiles WHERE is_active = 1
            """)

            row = cursor.fetchone()
            if row:
                return SettingsProfile(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    is_active=True,
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    json_data=json.loads(row['json_data']) if row['json_data'] else None
                )

        except Exception as e:
            self.logger.error(f"Failed to get active profile: {e}")

        return None

    def set_active_profile(self, profile_id: str) -> bool:
        """
        Set a profile as active.

        Args:
            profile_id: Profile ID to activate

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.database_manager.get_connection()

            # Clear all active flags
            conn.execute("UPDATE settings_profiles SET is_active = 0")

            # Set the specified profile as active
            conn.execute("""
                UPDATE settings_profiles SET is_active = 1 WHERE id = ?
            """, (profile_id,))

            self.logger.info(f"Set active profile to: {profile_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to set active profile {profile_id}: {e}")
            return False

    def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Optional[SettingsProfile]:
        """
        Create a new settings profile.

        Args:
            name: Profile name
            description: Optional description
            json_data: Optional JSON configuration data

        Returns:
            Created SettingsProfile instance or None if failed
        """
        try:
            # Validate name
            if not self._validate_profile_name(name):
                return None

            profile_id = str(uuid.uuid4())
            now = datetime.now().isoformat() + "Z"

            conn = self.database_manager.get_connection()
            conn.execute("""
                INSERT INTO settings_profiles (id, name, description, is_active, json_data, created_at, updated_at)
                VALUES (?, ?, ?, 0, ?, ?, ?)
            """, (
                profile_id,
                name,
                description,
                json.dumps(json_data) if json_data else None,
                now,
                now
            ))

            self.logger.info(f"Created profile: {name} ({profile_id})")
            return self.get_profile(profile_id)

        except Exception as e:
            self.logger.error(f"Failed to create profile {name}: {e}")
            return None

    def update_profile(
        self,
        profile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update an existing profile.

        Args:
            profile_id: Profile ID to update
            name: Optional new name
            description: Optional new description
            json_data: Optional new JSON data

        Returns:
            True if successful, False otherwise
        """
        try:
            updates = []
            params = []

            if name is not None:
                # Validate new name
                if not self._validate_profile_name(name):
                    return False
                updates.append("name = ?")
                params.append(name)

            if description is not None:
                updates.append("description = ?")
                params.append(description)

            if json_data is not None:
                updates.append("json_data = ?")
                params.append(json.dumps(json_data))

            if updates:
                updates.append("updated_at = ?")
                params.append(datetime.now().isoformat() + "Z")
                params.append(profile_id)

                conn = self.database_manager.get_connection()
                conn.execute(f"""
                    UPDATE settings_profiles SET {', '.join(updates)} WHERE id = ?
                """, params)

                self.logger.info(f"Updated profile: {profile_id}")
                return True

        except Exception as e:
            self.logger.error(f"Failed to update profile {profile_id}: {e}")

        return False

    def delete_profile(self, profile_id: str) -> bool:
        """
        Delete a profile.

        Args:
            profile_id: Profile ID to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if this is the active profile
            active_profile = self.get_active_profile()
            if active_profile and active_profile.id == profile_id:
                self.logger.error("Cannot delete active profile")
                return False

            conn = self.database_manager.get_connection()
            conn.execute("DELETE FROM settings_profiles WHERE id = ?", (profile_id,))

            self.logger.info(f"Deleted profile: {profile_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete profile {profile_id}: {e}")
            return False

    def _validate_profile_name(self, name: str) -> bool:
        """
        Validate profile name.

        Args:
            name: Name to validate

        Returns:
            True if valid, False otherwise
        """
        if not name or not isinstance(name, str):
            return False

        if len(name.strip()) < 1 or len(name.strip()) > 64:
            return False

        # Check for valid characters
        import re
        if not re.match(r'^[A-Za-z0-9 _-]+$', name.strip()):
            return False

        # Check for uniqueness
        try:
            conn = self.database_manager.get_connection()
            cursor = conn.execute("""
                SELECT COUNT(*) FROM settings_profiles WHERE name = ?
            """, (name.strip(),))

            count = cursor.fetchone()[0]
            return count == 0

        except Exception as e:
            self.logger.error(f"Failed to validate profile name: {e}")
            return False

    def ensure_default_profile(self) -> str:
        """
        Ensure a default profile exists.

        Returns:
            Name of the default profile
        """
        try:
            # Check if any profiles exist
            profiles = self.list_profiles()
            if profiles:
                # Check if any profile is active
                active = self.get_active_profile()
                if active:
                    return active.name

                # Set first profile as active
                self.set_active_profile(profiles[0].id)
                return profiles[0].name

            # Create default profile
            default_profile = DEFAULT_PROFILES[0]
            created = self.create_profile(
                default_profile.name,
                default_profile.description,
                default_profile.json_data
            )

            if created:
                self.set_active_profile(created.id)
                return created.name

        except Exception as e:
            self.logger.error(f"Failed to ensure default profile: {e}")

        return "Default Profile"
