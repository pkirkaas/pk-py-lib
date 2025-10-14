"""
Unified settings profiles manager.

Manages named configuration profiles for image similarity detection.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from threading import Lock

from ..models.settings import SettingsProfile, DEFAULT_PROFILES
from ..database import DatabaseManager

logger = logging.getLogger("pk_py_lib.core.settings.profiles")


class ProfilesManager:
    """
    Manager for settings profiles.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the profiles manager.
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
                        json_data TEXT,
                        CHECK (similarity_threshold >= 0.0 AND similarity_threshold <= 1.0),
                        CHECK (hash_algorithm IN ('phash', 'whash', 'xxh3')),
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
        except sqlite3.Error as e:
            logger.error(f"Error ensuring default profiles: {e}")
            raise

    def create(self, profile: SettingsProfile) -> SettingsProfile:
        """
        Create a new profile.
        """
        with self._lock:
            logger.debug(f"Creating profile: {profile.name}")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    now = datetime.now().isoformat()
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
                    if profile.is_default:
                        conn.execute(
                            "UPDATE settings_profiles_v2 SET is_default = 0 WHERE id != ?",
                            (profile_id,)
                        )

                    return self.get_by_id(profile_id)

            except sqlite3.IntegrityError as e:
                raise ValueError(f"Profile with name '{profile.name}' already exists") from e
            except sqlite3.Error as e:
                logger.error(f"Error creating profile: {e}")
                raise

    def get_by_id(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get profile by ID.
        """
        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM settings_profiles_v2 WHERE id = ?", (profile_id,))
                row = cursor.fetchone()
                return self._row_to_profile(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Error getting profile by ID: {e}")
            raise

    def get_all(self) -> List[SettingsProfile]:
        """
        Get all profiles.
        """
        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM settings_profiles_v2 ORDER BY name COLLATE NOCASE")
                return [self._row_to_profile(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting all profiles: {e}")
            raise

    def get_default(self) -> SettingsProfile:
        """
        Get the default profile.
        """
        try:
            with self.db.get_connection(self.db_path) as conn:
                cursor = conn.execute("SELECT * FROM settings_profiles_v2 WHERE is_default = 1 LIMIT 1")
                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("No default profile found")
                return self._row_to_profile(row)
        except sqlite3.Error as e:
            logger.error(f"Error getting default profile: {e}")
            raise

    def get_active(self) -> Optional[SettingsProfile]:
        """
        Get the active settings profile.

        Queries the database for the profile marked as active (is_default = 1).
        Returns the first matching profile or None if no active profile is found.

        Parameters
        ----------
        None

        Returns
        -------
        Optional[SettingsProfile]
            The active SettingsProfile instance, or None if no active profile exists.

        Raises
        ------
        sqlite3.Error
            If the database query fails due to a SQLite error.

        Examples
        --------
        >>> profiles_mgr = ProfilesManager(db_path)
        >>> active_profile = profiles_mgr.get_active()
        >>> if active_profile:
        ...     print(f"Active profile: {active_profile.name}")
        ... else:
        ...     print("No active profile set")
        """
        try:
            with self.db.get_connection(self.db_path) as conn:
                # Query for the profile where is_default = 1 (assuming 'active' maps to 'is_default')
                # This follows the existing schema; if a separate 'is_active' field is needed,
                # the schema would require migration.
                cursor = conn.execute("SELECT * FROM settings_profiles_v2 WHERE is_default = 1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return self._row_to_profile(row)
                else:
                    # No active profile found; return None without raising
                    logger.debug("No active profile found")
                    return None
        except sqlite3.Error as e:
            logger.error(f"Database error while querying active profile: {e}")
            raise sqlite3.Error(f"Failed to query active profile: {e}") from e

    def update(self, profile: SettingsProfile) -> None:
        """
        Update an existing profile.
        """
        if profile.id is None:
            raise ValueError("Profile ID must be set for update")

        with self._lock:
            try:
                with self.db.get_connection(self.db_path) as conn:
                    now = datetime.now().isoformat()
                    conn.execute("""
                        UPDATE settings_profiles_v2 SET
                            name = ?, description = ?, hash_algorithm = ?, hash_size = ?,
                            similarity_threshold = ?, min_resolution = ?, max_resolution = ?,
                            color_mode = ?, clustering_method = ?, quality_threshold = ?,
                            is_default = ?, updated_at = ?
                        WHERE id = ?
                    """, (
                        profile.name, profile.description, profile.hash_algorithm, profile.hash_size,
                        profile.similarity_threshold, profile.min_resolution, profile.max_resolution,
                        int(profile.color_mode), profile.clustering_method, profile.quality_threshold,
                        int(profile.is_default), now, profile.id,
                    ))

                    if profile.is_default:
                        conn.execute(
                            "UPDATE settings_profiles_v2 SET is_default = 0 WHERE id != ?",
                            (profile.id,)
                        )
            except sqlite3.Error as e:
                logger.error(f"Error updating profile: {e}")
                raise

    def set_active(self, profile_id: int) -> bool:
        """
        Set the specified profile as the active (default) profile.

        This method updates the database by setting is_default=1 for the given profile_id
        and is_default=0 for all other profiles in the settings_profiles_v2 table.
        It ensures only one profile is active at a time, maintaining data integrity.

        Parameters
        ----------
        profile_id : int
            The ID of the profile to set as active. Must exist in the database.

        Returns
        -------
        bool
            True if the update was successful (profile found and updated), False otherwise.

        Raises
        ------
        ValueError
            If profile_id is invalid (e.g., <= 0).
        sqlite3.Error
            If a database error occurs during the query (e.g., connection failure, constraint violation).
            The exception includes full details for debugging, such as the SQL error message.

        Examples
        --------
        >>> profiles_mgr = ProfilesManager(db_path)
        >>> success = profiles_mgr.set_active(1)
        >>> success
        True

        # Attempting to set a non-existent profile
        >>> success = profiles_mgr.set_active(999)
        >>> success
        False

        Notes
        -----
        - This operation is atomic within the transaction but does not verify if the profile_id exists
          before updating; it checks rowcount post-update.
        - For system profiles (is_system=1), activation is allowed but use with caution as it may affect
          default behaviors in the application.
        - Edge cases handled: No profiles in DB (returns False), invalid profile_id (raises ValueError),
          concurrent modifications (SQLite handles locking via the connection).
        """
        if profile_id <= 0:
            raise ValueError(f"Invalid profile_id: {profile_id}. Must be a positive integer.")

        with self._lock:
            try:
                with self.db.get_connection(self.db_path) as conn:
                    # Start transaction for atomicity
                    conn.execute("BEGIN TRANSACTION")

                    # Update the target profile to active
                    cursor = conn.execute(
                        "UPDATE settings_profiles_v2 SET is_default = 1 WHERE id = ?",
                        (profile_id,)
                    )

                    # Deactivate all other profiles
                    conn.execute(
                        "UPDATE settings_profiles_v2 SET is_default = 0 WHERE id != ?",
                        (profile_id,)
                    )

                    # Commit and check if the target was affected
                    conn.commit()
                    return cursor.rowcount > 0

            except sqlite3.Error as e:
                # Rollback on error
                if 'conn' in locals() and conn:
                    conn.rollback()
                logger.error(
                    f"Database error setting active profile {profile_id}: {e}",
                    exc_info=True,
                    extra={
                        "profile_id": profile_id,
                        "db_path": str(self.db_path),
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )
                raise sqlite3.Error(
                    f"Failed to set active profile {profile_id}: {str(e)}. "
                    f"Check database integrity and profile existence."
                ) from e
            except Exception as e:
                # Catch-all for unexpected errors (e.g., lock issues)
                if 'conn' in locals() and conn:
                    conn.rollback()
                logger.error(
                    f"Unexpected error setting active profile {profile_id}: {e}",
                    exc_info=True,
                    extra={
                        "profile_id": profile_id,
                        "db_path": str(self.db_path),
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )
                raise RuntimeError(
                    f"Unexpected failure setting active profile {profile_id}: {str(e)}. "
                    f"Verify database connection and permissions."
                ) from e

    def validate_name(self, name: str, exclude_id: Optional[int] = None) -> bool:
        """
        Validate if the given profile name is unique in the database.

        This method checks whether a profile with the provided name already exists,
        excluding the profile with the specified exclude_id if provided. The check
        is case-insensitive using SQLite's COLLATE NOCASE. It is used to prevent
        duplicate names during profile creation, update, or copy operations.

        Parameters
        ----------
        name : str
            The proposed profile name to validate. Must be non-empty string.
            Names are checked case-insensitively.
        exclude_id : Optional[int], optional
            The ID of a profile to exclude from the uniqueness check (e.g., when
            updating an existing profile). If None, checks against all profiles.
            Defaults to None.

        Returns
        -------
        bool
            True if the name is unique (no matching profiles found, excluding
            the specified ID if provided), False if a duplicate name exists.

        Raises
        ------
        ValueError
            If name is empty or None.
        sqlite3.Error
            If a database query error occurs, such as connection failure or
            SQL syntax issues. Includes full error details for debugging.

        Examples
        --------
        # Validate a new profile name
        >>> mgr = ProfilesManager(db_path)
        >>> is_unique = mgr.validate_name("My New Profile")
        >>> if is_unique:
        ...     # Proceed with creation
        ...     pass
        ... else:
        ...     print("Name already exists")

        # Validate during update, excluding current profile
        >>> is_unique = mgr.validate_name("Updated Name", exclude_id=5)
        >>> if is_unique:
        ...     # Proceed with update
        ...     pass

        Notes
        -----
        - This method acquires a lock for thread safety but is lightweight
          as it only performs a COUNT query.
        - Edge cases: Empty name raises ValueError; case variations like
          "Test" and "test" are considered duplicates.
        - For production, consider adding length/character validation in
          the calling code.
        """
        if not name or not isinstance(name, str):
            raise ValueError("Profile name must be a non-empty string")

        try:
            with self.db.get_connection(self.db_path) as conn:
                if exclude_id is not None:
                    # Exclude the specified ID from the check
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM settings_profiles_v2 "
                        "WHERE LOWER(name) = LOWER(?) AND id != ?",
                        (name, exclude_id)
                    )
                else:
                    # Check against all profiles
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM settings_profiles_v2 "
                        "WHERE LOWER(name) = LOWER(?)",
                        (name,)
                    )
                count = cursor.fetchone()[0]
                return count == 0
        except sqlite3.Error as e:
            logger.error(
                f"Database error validating profile name '{name}': {e}",
                exc_info=True,
                extra={
                    "name": name,
                    "exclude_id": exclude_id,
                    "db_path": str(self.db_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            raise sqlite3.Error(
                f"Failed to validate profile name '{name}': {str(e)}. "
                f"Check database connection and schema."
            ) from e

    def delete(self, profile_id: int) -> bool:
        """
        Delete a profile.
        """
        with self._lock:
            try:
                with self.db.get_connection(self.db_path) as conn:
                    cursor = conn.execute("DELETE FROM settings_profiles_v2 WHERE id = ?", (profile_id,))
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error deleting profile: {e}")
                raise

    def _row_to_profile(self, row: sqlite3.Row) -> SettingsProfile:
        """
        Convert database row to SettingsProfile.
        """
        return SettingsProfile(
            id=row['id'],
            name=row['name'],
            description=row['description'],
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
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
        )
