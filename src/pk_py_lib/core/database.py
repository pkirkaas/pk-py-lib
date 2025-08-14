"""
src/pk_py_lib/core/database.py
DatabaseManager and SchemaManager helpers.

Provides:
- DatabaseManager: creates and initializes settings.db and cache.db with canonical schemas.
- SchemaManager: small helper to read/set schema_version in the meta table.

This module is intentionally self-contained and conservative: it creates missing tables only,
initializes a `meta(schema_version)` entry, and provides helpers for backups and migrations.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any
import shutil
import logging
import datetime

logger = logging.getLogger("pk_py_lib.core.database")


# ---------------------------------------------------------------------------
# Canonical schemas (excerpted from docs/roo/img-app-data-model.md)
# Keep the schemas minimal but explicit to ensure DB creation is deterministic.
# ---------------------------------------------------------------------------

SETTINGS_SCHEMA = """
-- Settings DB schema

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    theme TEXT DEFAULT 'light',
    language TEXT DEFAULT 'en',
    ui_scale REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (theme IN ('light', 'dark', 'auto')),
    CHECK (ui_scale BETWEEN 0.5 AND 3.0)
);

CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    type TEXT NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, category, key),
    CHECK (type IN ('string', 'int', 'float', 'bool', 'json'))
);

CREATE TABLE IF NOT EXISTS algorithm_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    algorithms JSON NOT NULL,
    threshold REAL NOT NULL,
    parameters JSON,
    is_default BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, name),
    CHECK (threshold BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS operation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    operation_type TEXT NOT NULL,
    operation_data JSON NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_undone BOOLEAN DEFAULT FALSE,
    undo_data JSON,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recent_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    item_type TEXT NOT NULL,
    item_path TEXT NOT NULL,
    item_data JSON,
    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 1,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    CHECK (item_type IN ('file', 'folder', 'session', 'export'))
);

-- Meta table for schema versioning and global metadata
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CACHE_SCHEMA = """
-- Cache DB schema

CREATE TABLE IF NOT EXISTS image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,
    file_hash TEXT,
    file_inode INTEGER,
    file_device INTEGER,
    width INTEGER,
    height INTEGER,
    format TEXT,
    color_mode TEXT,
    bit_depth INTEGER,
    exif_data JSON,
    camera_make TEXT,
    camera_model TEXT,
    lens_model TEXT,
    date_taken TIMESTAMP,
    gps_latitude REAL,
    gps_longitude REAL,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scan_version TEXT,
    is_valid BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    size INTEGER NOT NULL,
    thumbnail_path TEXT NOT NULL,
    format TEXT DEFAULT 'JPEG',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
    UNIQUE(image_id, size)
);

CREATE TABLE IF NOT EXISTS image_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    hash_value TEXT NOT NULL,
    hash_size INTEGER,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
    UNIQUE(image_id, algorithm)
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    name TEXT,
    scan_type TEXT NOT NULL,
    source_paths JSON NOT NULL,
    reference_paths JSON,
    algorithms JSON NOT NULL,
    threshold REAL NOT NULL,
    algorithm_params JSON,
    total_images INTEGER,
    processed_images INTEGER DEFAULT 0,
    groups_found INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    duration REAL,
    error_message TEXT,
    CHECK (scan_type IN ('single_set', 'dual_set')),
    CHECK (status IN ('pending', 'running', 'completed', 'cancelled', 'error')),
    CHECK (threshold BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS similarity_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    image1_id INTEGER NOT NULL,
    image2_id INTEGER NOT NULL,
    overall_score REAL NOT NULL,
    algorithm_scores JSON,
    is_reference BOOLEAN DEFAULT FALSE,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (image1_id) REFERENCES image_metadata(id),
    FOREIGN KEY (image2_id) REFERENCES image_metadata(id),
    CHECK (overall_score BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS cache_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_size_bytes INTEGER DEFAULT 0,
    thumbnail_count INTEGER DEFAULT 0,
    image_count INTEGER DEFAULT 0,
    hash_count INTEGER DEFAULT 0,
    oldest_entry TIMESTAMP,
    newest_entry TIMESTAMP,
    last_cleanup TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_metadata_path ON image_metadata(file_path);
CREATE INDEX IF NOT EXISTS idx_metadata_hash ON image_metadata(file_hash);
CREATE INDEX IF NOT EXISTS idx_thumbnails_image ON thumbnails(image_id);
CREATE INDEX IF NOT EXISTS idx_thumbnails_accessed ON thumbnails(last_accessed);
CREATE INDEX IF NOT EXISTS idx_hashes_image ON image_hashes(image_id);
CREATE INDEX IF NOT EXISTS idx_sessions_profile ON scan_sessions(profile_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON scan_sessions(status);
CREATE INDEX IF NOT EXISTS idx_results_session ON similarity_results(session_id);
CREATE INDEX IF NOT EXISTS idx_results_group ON similarity_results(session_id, group_id);
CREATE INDEX IF NOT EXISTS idx_results_images ON similarity_results(image1_id, image2_id);
"""


# ---------------------------------------------------------------------------
# Schema & DB helpers
# ---------------------------------------------------------------------------

class SchemaManager:
    """
    Manages database schema version stored in the meta table and migration helpers.

    Minimal implementation:
    - CURRENT_VERSION tracks the canonical current schema for new DBs.
    - get_current_version(conn) reads meta.schema_version.
    - set_version(conn, version) writes meta.schema_version.
    """

    CURRENT_VERSION = "1.0.0"

    def get_current_version(self, conn: sqlite3.Connection) -> Optional[str]:
        """
        Retrieve current schema version from a DB connection.

        Returns None if no schema_version key exists.
        """
        cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        return row[0] if row else None

    def set_version(self, conn: sqlite3.Connection, version: str) -> None:
        """
        Insert or update the schema_version entry in meta table.
        """
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ("schema_version", version, "Set by SchemaManager"),
        )


class DatabaseManager:
    """
    DatabaseManager creates and initializes the canonical settings and cache databases.

    Responsibilities:
    - Create application data_dir if missing.
    - Create settings.db and cache.db and apply canonical DDL.
    - Ensure `meta` table exists and set schema_version when absent.
    - Provide a safe connection context manager with commit/rollback semantics.
    - Provide a small `backup_db` helper for safe migrations.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Parameters
        ----------
        data_dir : Optional[Path]
            Base directory for application data; defaults to ~/.kdc_image_organizer.
        """
        if data_dir is None:
            self.data_dir = Path.home() / ".kdc_image_organizer"
        else:
            self.data_dir = Path(data_dir).expanduser().resolve()

        self.settings_db = self.data_dir / "settings.db"
        self.cache_db = self.data_dir / "cache.db"
        self.schema = SchemaManager()

    def initialize(self) -> None:
        """
        Ensure base directory exists and create databases and required tables.

        This is idempotent and safe to call multiple times.
        """
        logger.info("Initializing databases under %s", self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize settings DB (includes meta table)
        with self.get_connection(self.settings_db) as conn:
            conn.executescript(SETTINGS_SCHEMA)
            # Ensure meta table exists (SETTINGS_SCHEMA creates it, but be defensive)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
            if cur.fetchone() is None:
                conn.executescript(
                    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
                )
            # Set schema version if missing
            if self.schema.get_current_version(conn) is None:
                logger.info("Setting initial schema_version=%s in settings.db", self.schema.CURRENT_VERSION)
                self.schema.set_version(conn, self.schema.CURRENT_VERSION)

        # Initialize cache DB
        with self.get_connection(self.cache_db) as conn:
            conn.executescript(CACHE_SCHEMA)

    @contextmanager
    def get_connection(self, db_path: Path):
        """
        Context manager yielding a sqlite3.Connection with automatic commit/rollback.

        Usage:
            with db_mgr.get_connection(path) as conn:
                conn.execute(...)
        """
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def backup_db(self, db_path: Path, backup_dir: Optional[Path] = None) -> Path:
        """
        Create a timestamped backup of the database file and return the backup path.
        """
        if backup_dir is None:
            backup_dir = self.data_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        dest = backup_dir / f"{db_path.name}.{ts}.backup"
        shutil.copy2(db_path, dest)
        logger.info("Created DB backup %s", dest)
        return dest

# End of file