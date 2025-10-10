"""
Unified settings profiles manager.

Manages named configuration profiles for image similarity detection.
Replaces the old SettingsProfilesManager with improved functionality.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from threading import Lock

from pk_py_lib.core.models.settings import SettingsProfile, DEFAULT_PROFILES
from pk_py_lib.core.database import DatabaseManager

logger = logging.getLogger("pk_py_lib.core.managers.profiles")


class ProfilesManager:
    """
    Manager for settings profiles.

    This manager handles:
    - CRUD operations for profiles
    - Profile validation
    - Default profile management
    - System profile protection

    Thread-safe for concurrent access.

    Examples
    --------
    >>> from pathlib import Path
    >>> manager = ProfilesManager(Path("settings.db"))
    >>> profiles = manager.get_all()
    >>> default = manager.get_default()
    >>> new_profile = SettingsProfile(name="Custom", similarity_threshold=0.90)
    >>> created = manager.create(new_profile)
    """

    def __init__(self, db_path: Path):
        """
        Initialize the profiles manager.

        Parameters
        ----------
        db_path : Path
            Path to the database file

        Examples
        --------
        >>> from pathlib import Path
        >>> manager = ProfilesManager(Path("settings.db"))
        """
        self.db_path = db_path
        self.db = DatabaseManager(data_dir=db_path.parent)
        self._lock = Lock()
        self._ensure_schema()
        self._ensure_default_profiles()

    def _ensure_schema(self):
        """Ensure the settings_profiles_v2 table exists."""
        logger.debug("Ensuring settings_profiles_v2 schema exists")

        try:
            with self.db.get_connection(self.db_path) as conn:
                # Create settings_profiles_v2 table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings_profiles_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        description TEXT NOT NULL DEFAULT '',
                        hash_algorithm TEXT NOT NULL DEFAULT 'phash',
                        hash_size INTEGER NOT NULL DEFAULT 8,
                        similarity_threshold REAL NOT NULL DEFAULT 0.95,
                        min_resolution INTEGER,
                        max_resolution INTEGER,
                        color_mode BOOLEAN NOT NULL DEFAULT 0,
                        clustering_method TEXT NOT NULL DEFAULT 'dbscan',
                        quality_threshold REAL,
                        is_default BOOLEAN NOT NULL DEFAULT 0,
                        is_system BOOLEAN NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        CHECK (similarity_threshold >= 0.0 AND similarity_threshold <= 1.0),
                        CHECK (hash_algorithm IN ('phash', 'whash', 'blake3', 'xxh3')),
                        CHECK (clustering_method IN ('dbscan', 'agglomerative'))
                    )
                """)

                logger.debug("settings_profiles_v2 schema verified")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring schema: {e}")
            raise

    def _ensure_default_profiles(self):
        """Ensure default system profiles exist."""
        logger.debug("Ensuring default profiles exist")

        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM settings_profiles_v2")
                row = cursor.fetchone()

                if row['count'] == 0:
                    logger.info("Creating default system profiles")
                    now = datetime.now().isoformat()

                    for profile in DEFAULT_PROFILES:
                        conn.execute("""
                            INSERT INTO settings_profiles_v2 (
                                name, description, hash_algorithm, hash_size,
                                similarity_threshold, color_mode, clustering_method,
                                is_default, is_system, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            profile.name,
                            profile.description,
                            profile.hash_algorithm,
                            profile.hash_size,
                            profile.similarity_threshold,
                            int(profile.color_mode),
                            profile.clustering_method,
                            int(profile.is_default),
                            int(profile.is_system),
                            now,
                            now,
                        ))

                    logger.info(f"Created {len(DEFAULT_PROFILES)} default profiles")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring default profiles: {e}")
            raise

    def create(self, profile: SettingsProfile) -> SettingsProfile:
        """
        Create a new profile.

        Parameters
        ----------
        profile : SettingsProfile
            Profile to create (without ID)

        Returns
        -------
        SettingsProfile
            Created profile with assigned ID

        Raises
        ------
        ValueError
            If profile name already exists

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = SettingsProfile(name="Custom", similarity_threshold=0.90)
        >>> created = manager.create(profile)
        >>> created.id is not None
        True
        """
        with self._lock:
            logger.debug(f"Creating profile: {profile.name}")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    # Check for name conflict
                    cursor = conn.execute(
                        "SELECT id FROM settings_profiles_v2 WHERE LOWER(name) = LOWER(?)",
                        (profile.name,)
                    )
                    if cursor.fetchone():
                        raise ValueError(f"Profile with name '{profile.name}' already exists")

                    # Set timestamps
                    now = datetime.now().isoformat()

                    # Insert profile
                    cursor = conn.execute("""
                        INSERT INTO settings_profiles_v2 (
                            name, description, hash_algorithm, hash_size,
                            similarity_threshold, min_resolution, max_resolution,
                            color_mode, clustering_method, quality_threshold,
                            is_default, is_system, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        profile.name,
                        profile.description,
                        profile.hash_algorithm,
                        profile.hash_size,
                        profile.similarity_threshold,
                        profile.min_resolution,
                        profile.max_resolution,
                        int(profile.color_mode),
                        profile.clustering_method,
                        profile.quality_threshold,
                        int(profile.is_default),
                        int(profile.is_system),
                        now,
                        now,
                    ))

                    profile_id = cursor.lastrowid

                    # If this is marked as default, unmark others
                    if profile.is_default:
                        conn.execute(
                            "UPDATE settings_profiles_v2 SET is_default = 0 WHERE id != ?",
                            (profile_id,)
                        )

                    logger.info(f"Created profile: {profile.name} (ID: {profile_id})")

                    # Return created profile
                    return self.get_by_id(profile_id)

            except sqlite3.IntegrityError as e:
                logger.error(f"Integrity error creating profile: {e}")
                raise ValueError(f"Profile name '{profile.name}' already exists") from e
            except sqlite3.Error as e:
                logger.error(f"Error creating profile: {e}")
                raise

    def get_by_id(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get profile by ID.

        Parameters
        ----------
        profile_id : int
            Profile ID

        Returns
        -------
        Optional[SettingsProfile]
            Profile with the given ID, or None if not found

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = manager.get_by_id(1)
        >>> profile.name if profile else None
        'Exact Duplicates'
        """
        logger.debug(f"Getting profile by ID: {profile_id}")

        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        id, name, description, hash_algorithm, hash_size,
                        similarity_threshold, min_resolution, max_resolution,
                        color_mode, clustering_method, quality_threshold,
                        is_default, is_system, created_at, updated_at
                    FROM settings_profiles_v2
                    WHERE id = ?
                """, (profile_id,))

                row = cursor.fetchone()
                if not row:
                    return None

                return self._row_to_profile(row)

        except sqlite3.Error as e:
            logger.error(f"Error getting profile by ID: {e}")
            raise

    def get_by_name(self, name: str) -> Optional[SettingsProfile]:
        """
        Get profile by name (case-insensitive).

        Parameters
        ----------
        name : str
            Profile name

        Returns
        -------
        Optional[SettingsProfile]
            Profile with the given name, or None if not found

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = manager.get_by_name("Exact Duplicates")
        >>> profile.is_system if profile else None
        True
        """
        logger.debug(f"Getting profile by name: {name}")

        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        id, name, description, hash_algorithm, hash_size,
                        similarity_threshold, min_resolution, max_resolution,
                        color_mode, clustering_method, quality_threshold,
                        is_default, is_system, created_at, updated_at
                    FROM settings_profiles_v2
                    WHERE LOWER(name) = LOWER(?)
                """, (name,))

                row = cursor.fetchone()
                if not row:
                    return None

                return self._row_to_profile(row)

        except sqlite3.Error as e:
            logger.error(f"Error getting profile by name: {e}")
            raise

    def get_all(self) -> List[SettingsProfile]:
        """
        Get all profiles.

        Returns
        -------
        List[SettingsProfile]
            List of all profiles, ordered by name

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profiles = manager.get_all()
        >>> len(profiles) >= 3  # At least the default system profiles
        True
        """
        logger.debug("Getting all profiles")

        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        id, name, description, hash_algorithm, hash_size,
                        similarity_threshold, min_resolution, max_resolution,
                        color_mode, clustering_method, quality_threshold,
                        is_default, is_system, created_at, updated_at
                    FROM settings_profiles_v2
                    ORDER BY name COLLATE NOCASE
                """)

                profiles = [self._row_to_profile(row) for row in cursor.fetchall()]
                logger.debug(f"Found {len(profiles)} profiles")
                return profiles

        except sqlite3.Error as e:
            logger.error(f"Error getting all profiles: {e}")
            raise

    def get_default(self) -> SettingsProfile:
        """
        Get the default profile.

        Returns
        -------
        SettingsProfile
            The default profile

        Raises
        ------
        RuntimeError
            If no default profile exists

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> default = manager.get_default()
        >>> default.is_default
        True
        """
        logger.debug("Getting default profile")

        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT
                        id, name, description, hash_algorithm, hash_size,
                        similarity_threshold, min_resolution, max_resolution,
                        color_mode, clustering_method, quality_threshold,
                        is_default, is_system, created_at, updated_at
                    FROM settings_profiles_v2
                    WHERE is_default = 1
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No default profile found")

                return self._row_to_profile(row)

        except sqlite3.Error as e:
            logger.error(f"Error getting default profile: {e}")
            raise

    def update(self, profile: SettingsProfile) -> None:
        """
        Update an existing profile.

        Parameters
        ----------
        profile : SettingsProfile
            Profile to update (must have ID)

        Raises
        ------
        ValueError
            If trying to modify system profile
            If profile doesn't exist
            If ID is not set

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = manager.get_by_name("Custom")
        >>> if profile:
        ...     profile.similarity_threshold = 0.85
        ...     manager.update(profile)
        """
        if profile.id is None:
            raise ValueError("Profile ID must be set for update")

        with self._lock:
            logger.debug(f"Updating profile: {profile.name} (ID: {profile.id})")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    # Check if profile exists and is not system
                    cursor = conn.execute(
                        "SELECT is_system FROM settings_profiles_v2 WHERE id = ?",
                        (profile.id,)
                    )
                    row = cursor.fetchone()

                    if not row:
                        raise ValueError(f"Profile with ID {profile.id} not found")

                    if row['is_system']:
                        raise ValueError("Cannot modify system profiles")

                    # Check for name conflict with other profiles
                    cursor = conn.execute(
                        "SELECT id FROM settings_profiles_v2 WHERE LOWER(name) = LOWER(?) AND id != ?",
                        (profile.name, profile.id)
                    )
                    if cursor.fetchone():
                        raise ValueError(f"Profile with name '{profile.name}' already exists")

                    # Update profile
                    now = datetime.now().isoformat()
                    conn.execute("""
                        UPDATE settings_profiles_v2 SET
                            name = ?,
                            description = ?,
                            hash_algorithm = ?,
                            hash_size = ?,
                            similarity_threshold = ?,
                            min_resolution = ?,
                            max_resolution = ?,
                            color_mode = ?,
                            clustering_method = ?,
                            quality_threshold = ?,
                            is_default = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        profile.name,
                        profile.description,
                        profile.hash_algorithm,
                        profile.hash_size,
                        profile.similarity_threshold,
                        profile.min_resolution,
                        profile.max_resolution,
                        int(profile.color_mode),
                        profile.clustering_method,
                        profile.quality_threshold,
                        int(profile.is_default),
                        now,
                        profile.id,
                    ))

                    # If this is marked as default, unmark others
                    if profile.is_default:
                        conn.execute(
                            "UPDATE settings_profiles_v2 SET is_default = 0 WHERE id != ?",
                            (profile.id,)
                        )

                    logger.info(f"Updated profile: {profile.name} (ID: {profile.id})")

            except sqlite3.IntegrityError as e:
                logger.error(f"Integrity error updating profile: {e}")
                raise ValueError(f"Profile name '{profile.name}' already exists") from e
            except sqlite3.Error as e:
                logger.error(f"Error updating profile: {e}")
                raise

    def delete(self, profile_id: int) -> bool:
        """
        Delete a profile.

        Parameters
        ----------
        profile_id : int
            ID of profile to delete

        Returns
        -------
        bool
            True if deleted, False if not found

        Raises
        ------
        ValueError
            If trying to delete system profile or default profile

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = SettingsProfile(name="Temp", similarity_threshold=0.80)
        >>> created = manager.create(profile)
        >>> manager.delete(created.id)
        True
        """
        with self._lock:
            logger.debug(f"Deleting profile ID: {profile_id}")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    # Check if profile exists and is not system or default
                    cursor = conn.execute(
                        "SELECT is_system, is_default, name FROM settings_profiles_v2 WHERE id = ?",
                        (profile_id,)
                    )
                    row = cursor.fetchone()

                    if not row:
                        logger.warning(f"Profile ID {profile_id} not found")
                        return False

                    if row['is_system']:
                        raise ValueError("Cannot delete system profiles")

                    if row['is_default']:
                        raise ValueError("Cannot delete the default profile. Set another profile as default first.")

                    # Delete profile
                    conn.execute("DELETE FROM settings_profiles_v2 WHERE id = ?", (profile_id,))

                    logger.info(f"Deleted profile: {row['name']} (ID: {profile_id})")
                    return True

            except sqlite3.Error as e:
                logger.error(f"Error deleting profile: {e}")
                raise

    def set_default(self, profile_id: int) -> None:
        """
        Set a profile as the default.

        Parameters
        ----------
        profile_id : int
            ID of profile to set as default

        Raises
        ------
        ValueError
            If profile doesn't exist

        Examples
        --------
        >>> manager = ProfilesManager(Path("settings.db"))
        >>> profile = manager.get_by_name("Very Similar")
        >>> if profile:
        ...     manager.set_default(profile.id)
        """
        with self._lock:
            logger.debug(f"Setting profile ID {profile_id} as default")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    # Check if profile exists
                    cursor = conn.execute(
                        "SELECT name FROM settings_profiles_v2 WHERE id = ?",
                        (profile_id,)
                    )
                    row = cursor.fetchone()

                    if not row:
                        raise ValueError(f"Profile with ID {profile_id} not found")

                    # Unmark all as default
                    conn.execute("UPDATE settings_profiles_v2 SET is_default = 0")

                    # Mark this one as default
                    conn.execute(
                        "UPDATE settings_profiles_v2 SET is_default = 1 WHERE id = ?",
                        (profile_id,)
                    )

                    logger.info(f"Set {row['name']} (ID: {profile_id}) as default profile")

            except sqlite3.Error as e:
                logger.error(f"Error setting default profile: {e}")
                raise

    def _row_to_profile(self, row: sqlite3.Row) -> SettingsProfile:
        """
        Convert database row to SettingsProfile.

        Parameters
        ----------
        row : sqlite3.Row
            Database row

        Returns
        -------
        SettingsProfile
            Profile instance
        """
        # Parse timestamps
        created_at = None
        if row['created_at']:
            try:
                created_at = datetime.fromisoformat(row['created_at'])
            except (ValueError, TypeError):
                pass

        updated_at = None
        if row['updated_at']:
            try:
                updated_at = datetime.fromisoformat(row['updated_at'])
            except (ValueError, TypeError):
                pass

        return SettingsProfile(
            id=row['id'],
            name=row['name'],
            description=row['description'] if row['description'] else '',
            hash_algorithm=row['hash_algorithm'],
            hash_size=row['hash_size'],
            similarity_threshold=row['similarity_threshold'],
            min_resolution=row['min_resolution'],
            max_resolution=row['max_resolution'],
            color_mode=bool(row['color_mode']),
            clustering_method=row['clustering_method'],
            quality_threshold=row['quality_threshold'],
            is_default=bool(row['is_default']),
            is_system=bool(row['is_system']),
            created_at=created_at,
            updated_at=updated_at,
        )


__all__ = ['ProfilesManager']
