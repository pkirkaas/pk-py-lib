"""
Unified application settings manager.

Manages global application settings that apply across all profiles.
Replaces the old ConfigurationManager for app-level settings.
"""

import logging
import json
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime
from threading import Lock

from pk_py_lib.core.models.settings import AppSettings
from pk_py_lib.core.database import DatabaseManager

logger = logging.getLogger("pk_py_lib.core.managers.app_settings")


class AppSettingsManager:
    """
    Manager for application-wide settings.

    This manager handles:
    - Loading and saving global app settings
    - Validating setting values
    - Providing typed access to settings
    - Maintaining settings persistence

    Thread-safe for concurrent access.

    Examples
    --------
    >>> from pathlib import Path
    >>> manager = AppSettingsManager(Path("settings.db"))
    >>> settings = manager.load()
    >>> settings.cache_size_mb
    500
    >>> manager.set_cache_enabled(False)
    >>> manager.get_cache_enabled()
    False
    """

    def __init__(self, db_path: Path):
        """
        Initialize the app settings manager.

        Parameters
        ----------
        db_path : Path
            Path to the database file

        Examples
        --------
        >>> from pathlib import Path
        >>> manager = AppSettingsManager(Path("settings.db"))
        """
        self.db_path = db_path
        self.db = DatabaseManager(data_dir=db_path.parent)
        self._settings: Optional[AppSettings] = None
        self._lock = Lock()
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure the app_settings_v2 table exists."""
        logger.debug("Ensuring app_settings_v2 schema exists")

        try:
            with self.db.get_connection(self.db_path) as conn:
                # Create app_settings_v2 table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings_v2 (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        cache_enabled BOOLEAN NOT NULL DEFAULT 1,
                        cache_size_mb INTEGER NOT NULL DEFAULT 500,
                        max_workers INTEGER NOT NULL DEFAULT 4,
                        default_profile_id INTEGER,
                        gui_theme TEXT NOT NULL DEFAULT 'auto',
                        log_level TEXT NOT NULL DEFAULT 'INFO',
                        recent_directories TEXT,
                        window_geometry TEXT,
                        last_updated TEXT,
                        FOREIGN KEY (default_profile_id) REFERENCES settings_profiles_v2(id)
                    )
                """)

                # Check if there's a row, if not create default
                cursor = conn.execute("SELECT COUNT(*) as count FROM app_settings_v2")
                row = cursor.fetchone()
                if row['count'] == 0:
                    logger.info("Creating default app settings")
                    conn.execute("""
                        INSERT INTO app_settings_v2 (
                            id, cache_enabled, cache_size_mb, max_workers,
                            gui_theme, log_level, last_updated
                        ) VALUES (1, 1, 500, 4, 'auto', 'INFO', ?)
                    """, (datetime.now().isoformat(),))

                logger.debug("app_settings_v2 schema verified")
        except sqlite3.Error as e:
            logger.error(f"Error ensuring schema: {e}")
            raise

    def load(self) -> AppSettings:
        """
        Load application settings from database.

        Returns
        -------
        AppSettings
            AppSettings instance with current settings

        Creates default settings if none exist.

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> settings = manager.load()
        >>> settings.cache_enabled
        True
        """
        with self._lock:
            logger.debug("Loading app settings from database")

            try:
                with self.db.get_connection(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT
                            cache_enabled, cache_size_mb, max_workers,
                            default_profile_id, gui_theme, log_level,
                            recent_directories, window_geometry, last_updated
                        FROM app_settings_v2
                        WHERE id = 1
                    """)
                    row = cursor.fetchone()

                    if not row:
                        logger.warning("No app settings found, creating defaults")
                        self._ensure_schema()
                        return self.load()

                    # Parse JSON fields
                    recent_dirs = []
                    if row['recent_directories']:
                        try:
                            recent_dirs = json.loads(row['recent_directories'])
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse recent_directories")

                    window_geom = None
                    if row['window_geometry']:
                        try:
                            window_geom = json.loads(row['window_geometry'])
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse window_geometry")

                    last_upd = None
                    if row['last_updated']:
                        try:
                            last_upd = datetime.fromisoformat(row['last_updated'])
                        except (ValueError, TypeError):
                            logger.warning("Failed to parse last_updated")

                    settings = AppSettings(
                        cache_enabled=bool(row['cache_enabled']),
                        cache_size_mb=row['cache_size_mb'],
                        max_workers=row['max_workers'],
                        default_profile_id=row['default_profile_id'],
                        gui_theme=row['gui_theme'],
                        log_level=row['log_level'],
                        recent_directories=recent_dirs,
                        window_geometry=window_geom,
                        last_updated=last_upd,
                    )

                    self._settings = settings
                    logger.debug(f"Loaded app settings: cache_size={settings.cache_size_mb}MB, theme={settings.gui_theme}")
                    return settings

            except sqlite3.Error as e:
                logger.error(f"Error loading app settings: {e}")
                raise

    def save(self, settings: AppSettings) -> None:
        """
        Save application settings to database.

        Parameters
        ----------
        settings : AppSettings
            AppSettings instance to save

        Updates the last_updated timestamp automatically.

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> settings = manager.load()
        >>> settings.cache_size_mb = 1024
        >>> manager.save(settings)
        """
        with self._lock:
            logger.debug("Saving app settings to database")

            try:
                # Update timestamp
                settings.last_updated = datetime.now()

                # Prepare JSON fields
                recent_dirs_json = json.dumps(settings.recent_directories) if settings.recent_directories else None
                window_geom_json = json.dumps(settings.window_geometry) if settings.window_geometry else None

                with self.db.get_connection(self.db_path) as conn:
                    conn.execute("""
                        UPDATE app_settings_v2 SET
                            cache_enabled = ?,
                            cache_size_mb = ?,
                            max_workers = ?,
                            default_profile_id = ?,
                            gui_theme = ?,
                            log_level = ?,
                            recent_directories = ?,
                            window_geometry = ?,
                            last_updated = ?
                        WHERE id = 1
                    """, (
                        int(settings.cache_enabled),
                        settings.cache_size_mb,
                        settings.max_workers,
                        settings.default_profile_id,
                        settings.gui_theme,
                        settings.log_level,
                        recent_dirs_json,
                        window_geom_json,
                        settings.last_updated.isoformat(),
                    ))

                self._settings = settings
                logger.debug(f"Saved app settings: cache_size={settings.cache_size_mb}MB")

            except sqlite3.Error as e:
                logger.error(f"Error saving app settings: {e}")
                raise

    def get_cache_enabled(self) -> bool:
        """
        Get whether caching is enabled.

        Returns
        -------
        bool
            True if caching is enabled

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> manager.get_cache_enabled()
        True
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.cache_enabled

    def set_cache_enabled(self, enabled: bool) -> None:
        """
        Set whether caching is enabled.

        Parameters
        ----------
        enabled : bool
            True to enable caching

        Examples
        --------
        >>> manager = AppSettingsManager(Path("settings.db"))
        >>> manager.set_cache_enabled(False)
        >>> manager.get_cache_enabled()
        False
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.cache_enabled = enabled
        self.save(self._settings)

    def get_cache_size_mb(self) -> int:
        """
        Get cache size in megabytes.

        Returns
        -------
        int
            Cache size in MB
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.cache_size_mb

    def set_cache_size_mb(self, size_mb: int) -> None:
        """
        Set cache size in megabytes.

        Parameters
        ----------
        size_mb : int
            Cache size in MB (must be positive)

        Raises
        ------
        ValueError
            If size_mb is not positive
        """
        if size_mb <= 0:
            raise ValueError("Cache size must be positive")

        if self._settings is None:
            self._settings = self.load()
        self._settings.cache_size_mb = size_mb
        self.save(self._settings)

    def get_max_workers(self) -> int:
        """
        Get maximum number of worker threads.

        Returns
        -------
        int
            Maximum worker threads
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.max_workers

    def set_max_workers(self, workers: int) -> None:
        """
        Set maximum number of worker threads.

        Parameters
        ----------
        workers : int
            Maximum worker threads (must be positive)

        Raises
        ------
        ValueError
            If workers is not positive
        """
        if workers <= 0:
            raise ValueError("Max workers must be positive")

        if self._settings is None:
            self._settings = self.load()
        self._settings.max_workers = workers
        self.save(self._settings)

    def get_gui_theme(self) -> str:
        """
        Get GUI theme setting.

        Returns
        -------
        str
            Theme name ('light', 'dark', or 'auto')
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.gui_theme

    def set_gui_theme(self, theme: str) -> None:
        """
        Set GUI theme.

        Parameters
        ----------
        theme : str
            Theme name ('light', 'dark', or 'auto')

        Raises
        ------
        ValueError
            If theme is not valid
        """
        valid_themes = {'light', 'dark', 'auto'}
        if theme not in valid_themes:
            raise ValueError(f"Invalid theme: {theme}. Must be one of {valid_themes}")

        if self._settings is None:
            self._settings = self.load()
        self._settings.gui_theme = theme
        self.save(self._settings)

    def get_log_level(self) -> str:
        """
        Get logging level.

        Returns
        -------
        str
            Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.log_level

    def set_log_level(self, level: str) -> None:
        """
        Set logging level.

        Parameters
        ----------
        level : str
            Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')

        Raises
        ------
        ValueError
            If level is not valid
        """
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if level.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")

        if self._settings is None:
            self._settings = self.load()
        self._settings.log_level = level.upper()
        self.save(self._settings)

    def get_default_profile_id(self) -> Optional[int]:
        """
        Get default profile ID.

        Returns
        -------
        Optional[int]
            Default profile ID, or None if not set
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.default_profile_id

    def set_default_profile_id(self, profile_id: Optional[int]) -> None:
        """
        Set default profile ID.

        Parameters
        ----------
        profile_id : Optional[int]
            Profile ID to set as default, or None to clear
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.default_profile_id = profile_id
        self.save(self._settings)

    def add_recent_directory(self, directory: str, max_recent: int = 10) -> None:
        """
        Add a directory to recent directories list.

        Parameters
        ----------
        directory : str
            Directory path to add
        max_recent : int
            Maximum number of recent directories to keep (default: 10)
        """
        if self._settings is None:
            self._settings = self.load()

        # Remove if already exists
        if directory in self._settings.recent_directories:
            self._settings.recent_directories.remove(directory)

        # Add to front
        self._settings.recent_directories.insert(0, directory)

        # Trim to max
        if len(self._settings.recent_directories) > max_recent:
            self._settings.recent_directories = self._settings.recent_directories[:max_recent]

        self.save(self._settings)

    def get_recent_directories(self) -> list:
        """
        Get list of recent directories.

        Returns
        -------
        list
            List of recent directory paths
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.recent_directories.copy()

    def set_window_geometry(self, geometry: dict) -> None:
        """
        Save window geometry.

        Parameters
        ----------
        geometry : dict
            Dictionary with window geometry (x, y, width, height)
        """
        if self._settings is None:
            self._settings = self.load()
        self._settings.window_geometry = geometry
        self.save(self._settings)

    def get_window_geometry(self) -> Optional[dict]:
        """
        Get saved window geometry.

        Returns
        -------
        Optional[dict]
            Window geometry dictionary, or None if not saved
        """
        if self._settings is None:
            self._settings = self.load()
        return self._settings.window_geometry


__all__ = ['AppSettingsManager']
