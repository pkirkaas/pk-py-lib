"""
Database migration utilities for settings consolidation.

Provides tools to migrate from the old dual-system architecture
(ConfigurationManager + SettingsProfilesManager) to the new unified
settings architecture.

This module implements Phase 1 preparation - the actual migration
logic will be implemented in later phases.
"""

import logging
import sqlite3
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger("pk_py_lib.migrations.settings")


class SettingsMigration:
    """
    Handles migration from old settings architecture to new unified system.

    This class provides tools to:
    - Detect which old system(s) are in use
    - Back up existing data
    - Migrate data to new schema
    - Validate migration success
    - Rollback if needed

    The migration process is designed to be:
    - Idempotent (safe to run multiple times)
    - Reversible (can rollback on failure)
    - Non-destructive (preserves old data during transition)

    Attributes
    ----------
    db_path : Path
        Path to the database file being migrated
    backup_path : Optional[Path]
        Path to the backup file (set after creating backup)

    Examples
    --------
    >>> migration = SettingsMigration(Path("settings.db"))
    >>> if migration.needs_migration():
    ...     backup = migration.create_backup()
    ...     success = migration.migrate()
    ...     if not success:
    ...         migration.rollback()
    """

    def __init__(self, db_path: Path):
        """
        Initialize migration handler.

        Parameters
        ----------
        db_path : Path
            Path to the database file to migrate

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> migration.db_path
        PosixPath('settings.db')
        """
        self.db_path = db_path
        self.backup_path: Optional[Path] = None

    def needs_migration(self) -> bool:
        """
        Check if database needs migration to new schema.

        Examines the database to determine if it uses the old
        dual-system architecture and needs migration to the
        unified v2 schema.

        Returns
        -------
        bool
            True if migration is needed, False if already on new schema

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> if migration.needs_migration():
        ...     print("Migration required")

        Notes
        -----
        Checks for:
        - Presence of old 'profiles' and 'settings' tables
        - Absence of or old version of 'app_settings_v2' table
        - Schema version in schema_version table
        """
        if not self.db_path.exists():
            logger.info("Database does not exist, no migration needed")
            return False

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check for schema_version table
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schema_version'
            """)
            has_version_table = cursor.fetchone() is not None

            if has_version_table:
                # Check schema version
                cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    version = row[0]
                    logger.info(f"Found schema version: {version}")
                    # If version >= 2, we're on new schema
                    if version >= 2:
                        logger.info("Schema version >= 2, no migration needed")
                        conn.close()
                        return False

            # Check for new v2 tables
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='app_settings_v2'
            """)
            has_new_app_settings = cursor.fetchone() is not None

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='settings_profiles_v2'
            """)
            has_new_profiles = cursor.fetchone() is not None

            # If both new tables exist, no migration needed
            if has_new_app_settings and has_new_profiles:
                logger.info("New v2 tables already exist, no migration needed")
                conn.close()
                return False

            # Check for old tables
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name IN ('app_settings', 'profiles', 'settings', 'settings_profiles', 'settings_profile_items')
            """)
            old_tables = [row[0] for row in cursor.fetchall()]

            conn.close()

            # Migration needed if we have old tables but not new ones
            needs_mig = len(old_tables) > 0 and not (has_new_app_settings and has_new_profiles)

            if needs_mig:
                logger.info(f"Migration needed - found old tables: {old_tables}")
            else:
                logger.info("No migration needed")

            return needs_mig

        except sqlite3.Error as e:
            logger.error(f"Error checking migration status: {e}")
            # If we can't check, assume no migration needed to be safe
            return False

    def create_backup(self) -> Path:
        """
        Create backup of current database.

        Creates a timestamped backup of the entire database file
        before attempting any migration operations. This allows
        for safe rollback if migration fails.

        Returns
        -------
        Path
            Path to the backup file

        Raises
        ------
        IOError
            If backup creation fails (insufficient permissions, disk full, etc.)

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> backup_path = migration.create_backup()
        >>> backup_path.exists()
        True
        """
        if not self.db_path.exists():
            raise IOError(f"Database file does not exist: {self.db_path}")

        # Create backups directory
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{self.db_path.stem}_backup_{timestamp}.db"
        backup_path = backup_dir / backup_filename

        logger.info(f"Creating backup: {backup_path}")

        try:
            # Copy database file
            shutil.copy2(self.db_path, backup_path)

            # Verify backup integrity by trying to open it
            test_conn = sqlite3.connect(str(backup_path))
            test_conn.execute("SELECT 1")
            test_conn.close()

            self.backup_path = backup_path
            logger.info(f"Backup created successfully: {backup_path}")

            return backup_path

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # Clean up partial backup if it exists
            if backup_path.exists():
                backup_path.unlink()
            raise IOError(f"Backup creation failed: {e}") from e

    def migrate_app_settings(self) -> Dict[str, Any]:
        """
        Migrate application settings from old ConfigurationManager format.

        Extracts app-level settings from the old 'app_settings' table
        and prepares them for the new unified format.

        Returns
        -------
        Dict[str, Any]
            Dictionary of migrated app settings

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> settings = migration.migrate_app_settings()
        >>> 'cache_size_mb' in settings
        True
        """
        logger.info("Migrating app settings from old schema")

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check if old app_settings table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='app_settings'
            """)
            if not cursor.fetchone():
                logger.info("No old app_settings table found, using defaults")
                conn.close()
                return {
                    'cache_enabled': True,
                    'cache_size_mb': 500,
                    'max_workers': 4,
                    'gui_theme': 'auto',
                    'log_level': 'INFO',
                    'recent_directories': [],
                    'window_geometry': None,
                }

            # Read from old app_settings table
            cursor.execute("""
                SELECT theme, language, ui_scale, max_threads, max_memory_mb,
                       cache_size_mb, logging_to_user_dir, development,
                       window_geometry, panel_layout, shortcuts,
                       created_at, modified_at
                FROM app_settings LIMIT 1
            """)
            row = cursor.fetchone()
            conn.close()

            if not row:
                logger.warning("Old app_settings table is empty, using defaults")
                return {
                    'cache_enabled': True,
                    'cache_size_mb': 500,
                    'max_workers': 4,
                    'gui_theme': 'auto',
                    'log_level': 'INFO',
                    'recent_directories': [],
                    'window_geometry': None,
                }

            # Map old settings to new format
            settings = {
                'cache_enabled': True,  # Always enabled in new system
                'cache_size_mb': row['cache_size_mb'] if row['cache_size_mb'] else 500,
                'max_workers': row['max_threads'] if row['max_threads'] else 4,
                'gui_theme': row['theme'] if row['theme'] else 'auto',
                'log_level': 'DEBUG' if row.get('development') else 'INFO',
                'recent_directories': [],  # Will be populated from profile history
                'window_geometry': json.loads(row['window_geometry']) if row['window_geometry'] else None,
            }

            logger.info(f"Migrated app settings: {settings}")
            return settings

        except sqlite3.Error as e:
            logger.error(f"Error migrating app settings: {e}")
            # Return defaults on error
            return {
                'cache_enabled': True,
                'cache_size_mb': 500,
                'max_workers': 4,
                'gui_theme': 'auto',
                'log_level': 'INFO',
                'recent_directories': [],
                'window_geometry': None,
            }

    def migrate_profiles(self) -> List[Dict[str, Any]]:
        """
        Migrate settings profiles from old SettingsProfilesManager format.

        Extracts profile metadata and settings from the old schema
        (either 'profiles'+'settings' or 'settings_profiles'+'settings_profile_items')
        and prepares them for the new unified format.

        Returns
        -------
        List[Dict[str, Any]]
            List of migrated profile dictionaries

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> profiles = migration.migrate_profiles()
        >>> len(profiles) > 0
        True
        >>> profiles[0]['name']
        'Default'
        """
        from pk_py_lib.core.models.settings import DEFAULT_PROFILES

        logger.info("Migrating profiles from old schema")
        migrated_profiles = []

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check for settings_profiles table (newer format)
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='settings_profiles'
            """)
            has_settings_profiles = cursor.fetchone() is not None

            # Check for profiles table (older format)
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='profiles'
            """)
            has_profiles = cursor.fetchone() is not None

            if has_settings_profiles:
                # Migrate from settings_profiles + settings_profile_items format
                logger.info("Migrating from settings_profiles format")
                cursor.execute("""
                    SELECT id, name, description, is_active, created_at, updated_at
                    FROM settings_profiles
                    ORDER BY name
                """)
                for row in cursor.fetchall():
                    profile = {
                        'id': None,  # Will be auto-assigned
                        'name': row['name'],
                        'description': row['description'] if row['description'] else '',
                        'is_default': bool(row['is_active']),
                        'is_system': False,
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                    }
                    migrated_profiles.append(profile)

            elif has_profiles:
                # Migrate from profiles + settings format
                logger.info("Migrating from profiles format")
                cursor.execute("""
                    SELECT id, name, is_default, created_at, modified_at
                    FROM profiles
                    ORDER BY name
                """)
                for row in cursor.fetchall():
                    profile = {
                        'id': None,  # Will be auto-assigned
                        'name': row['name'],
                        'description': '',
                        'is_default': bool(row['is_default']),
                        'is_system': False,
                        'created_at': row['created_at'],
                        'updated_at': row.get('modified_at', row['created_at']),
                    }
                    migrated_profiles.append(profile)

            conn.close()

            # If no profiles found, use defaults
            if not migrated_profiles:
                logger.info("No old profiles found, using default profiles")
                for default_profile in DEFAULT_PROFILES:
                    profile = {
                        'id': None,
                        'name': default_profile.name,
                        'description': default_profile.description,
                        'hash_algorithm': default_profile.hash_algorithm,
                        'hash_size': default_profile.hash_size,
                        'similarity_threshold': default_profile.similarity_threshold,
                        'is_default': default_profile.is_default,
                        'is_system': default_profile.is_system,
                        'created_at': datetime.now().isoformat(),
                        'updated_at': datetime.now().isoformat(),
                    }
                    migrated_profiles.append(profile)

            # Ensure exactly one profile is marked as default
            default_count = sum(1 for p in migrated_profiles if p['is_default'])
            if default_count == 0:
                # Mark first profile as default
                if migrated_profiles:
                    migrated_profiles[0]['is_default'] = True
                    logger.info(f"Marked {migrated_profiles[0]['name']} as default")
            elif default_count > 1:
                # Only keep first default
                found_default = False
                for profile in migrated_profiles:
                    if profile['is_default']:
                        if not found_default:
                            found_default = True
                        else:
                            profile['is_default'] = False

            logger.info(f"Migrated {len(migrated_profiles)} profiles")
            return migrated_profiles

        except sqlite3.Error as e:
            logger.error(f"Error migrating profiles: {e}")
            # Return default profiles on error
            return [{
                'id': None,
                'name': p.name,
                'description': p.description,
                'hash_algorithm': p.hash_algorithm,
                'hash_size': p.hash_size,
                'similarity_threshold': p.similarity_threshold,
                'is_default': p.is_default,
                'is_system': p.is_system,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            } for p in DEFAULT_PROFILES]

    def validate_migration(self) -> bool:
        """
        Validate that migration was successful.

        Performs comprehensive validation of the migrated data
        to ensure integrity and completeness.

        Returns
        -------
        bool
            True if validation passes, False otherwise

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> migration.create_backup()
        >>> migration.migrate()
        >>> migration.validate_migration()
        True
        """
        logger.info("Validating migration")

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check that new tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='app_settings_v2'
            """)
            if not cursor.fetchone():
                logger.error("app_settings_v2 table not found")
                conn.close()
                return False

            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='settings_profiles_v2'
            """)
            if not cursor.fetchone():
                logger.error("settings_profiles_v2 table not found")
                conn.close()
                return False

            # Check that app_settings_v2 has data
            cursor.execute("SELECT COUNT(*) as count FROM app_settings_v2")
            row = cursor.fetchone()
            if not row or row['count'] == 0:
                logger.error("app_settings_v2 table is empty")
                conn.close()
                return False

            # Check that settings_profiles_v2 has at least one profile
            cursor.execute("SELECT COUNT(*) as count FROM settings_profiles_v2")
            row = cursor.fetchone()
            if not row or row['count'] == 0:
                logger.error("settings_profiles_v2 table is empty")
                conn.close()
                return False

            # Check that exactly one profile is marked as default
            cursor.execute("SELECT COUNT(*) as count FROM settings_profiles_v2 WHERE is_default = 1")
            row = cursor.fetchone()
            default_count = row['count'] if row else 0
            if default_count != 1:
                logger.error(f"Expected 1 default profile, found {default_count}")
                conn.close()
                return False

            # Check schema version
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schema_version'
            """)
            if cursor.fetchone():
                cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                row = cursor.fetchone()
                if row and row['version'] >= 2:
                    logger.info(f"Schema version validated: {row['version']}")
                else:
                    logger.warning("Schema version not updated correctly")

            conn.close()
            logger.info("Migration validation passed")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error validating migration: {e}")
            return False

    def rollback(self) -> bool:
        """
        Rollback to pre-migration state from backup.

        Restores the database to its state before migration
        using the backup file created by create_backup().

        Returns
        -------
        bool
            True if rollback successful, False otherwise

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> backup = migration.create_backup()
        >>> # ... migration fails ...
        >>> migration.rollback()
        True

        Raises
        ------
        ValueError
            If no backup has been created (backup_path is None)
        IOError
            If rollback operation fails
        """
        if self.backup_path is None:
            raise ValueError("No backup available for rollback")

        if not self.backup_path.exists():
            raise IOError(f"Backup file not found: {self.backup_path}")

        logger.warning(f"Rolling back migration from backup: {self.backup_path}")

        try:
            # Verify backup integrity before rollback
            test_conn = sqlite3.connect(str(self.backup_path))
            test_conn.execute("SELECT 1")
            test_conn.close()

            # Remove current database if it exists
            if self.db_path.exists():
                self.db_path.unlink()

            # Restore from backup
            shutil.copy2(self.backup_path, self.db_path)

            # Verify restored database
            test_conn = sqlite3.connect(str(self.db_path))
            test_conn.execute("SELECT 1")
            test_conn.close()

            logger.info("Rollback completed successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise IOError(f"Rollback failed: {e}") from e

    def get_migration_report(self) -> Dict[str, Any]:
        """
        Generate detailed migration report.

        Provides comprehensive information about the migration
        process, including statistics and any issues encountered.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing migration statistics and status

        Examples
        --------
        >>> migration = SettingsMigration(Path("settings.db"))
        >>> migration.migrate()
        >>> report = migration.get_migration_report()
        >>> report['profiles_migrated']
        3
        >>> report['success']
        True

        Notes
        -----
        TODO: Implement report generation
        Should include:
        - Number of profiles migrated
        - Number of settings migrated
        - Any warnings or errors
        - Migration timestamp
        - Schema version (old -> new)
        - Backup location
        - Validation results
        """
        # TODO: Implement report generation
        # Collect migration statistics
        # Include any warnings/errors
        # Return comprehensive report dict
        logger.info("TODO: Implement get_migration_report() logic")
        return {
            'success': False,
            'profiles_migrated': 0,
            'settings_migrated': 0,
            'errors': ['Migration not yet implemented'],
        }


__all__ = ['SettingsMigration']
