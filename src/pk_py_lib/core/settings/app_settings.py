"""
Unified application settings manager.

Manages global application settings that apply across all profiles.
"""

import logging
import json
import sqlite3
from pathlib import Path
from typing import Optional
from datetime import datetime
from threading import Lock

from ..models.settings import AppSettings
from ..database import DatabaseManager

logger = logging.getLogger("pk_py_lib.core.settings.app_settings")


class AppSettingsManager:
    """
    Manager for application-wide settings.
    """

    def __init__(self, db_path: Path):
        """
        Initialize the app settings manager.
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

                    recent_dirs = json.loads(row['recent_directories']) if row['recent_directories'] else []
                    window_geom = json.loads(row['window_geometry']) if row['window_geometry'] else None
                    last_upd = datetime.fromisoformat(row['last_updated']) if row['last_updated'] else None

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
                    return settings

            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error(f"Error loading app settings: {e}")
                raise

    def save(self, settings: AppSettings) -> None:
        """
        Save application settings to database.
        """
        with self._lock:
            logger.debug("Saving app settings to database")

            try:
                settings.last_updated = datetime.now()
                recent_dirs_json = json.dumps(settings.recent_directories)
                window_geom_json = json.dumps(settings.window_geometry)

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

            except sqlite3.Error as e:
                logger.error(f"Error saving app settings: {e}")
                raise
