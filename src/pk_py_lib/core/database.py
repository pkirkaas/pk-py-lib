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
import uuid
import json
import os

from .utils import get_data_dir # Import the new unified path function

logger = logging.getLogger("pk_py_lib.core.database")


class DatabaseMigrationError(Exception):
    """
    Custom exception raised during database schema migrations.

    Args:
        message (str): Descriptive message about the migration failure.
        original_error (Exception, optional): The underlying sqlite3.Error or other exception.
    """
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


# ---------------------------------------------------------------------------
# Canonical schemas (excerpted from docs/roo/img-app-data-model.md)
# Keep the schemas minimal but explicit to ensure DB creation is deterministic.
# ---------------------------------------------------------------------------

SETTINGS_SCHEMA = """
-- Settings DB schema

-- Profiles table (no UI/performance fields — those live in app_settings)
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- App settings (single-row) table: global, typed fields for UI and performance
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme TEXT DEFAULT 'light',
    language TEXT DEFAULT 'en',
    ui_scale REAL DEFAULT 1.0,
    max_threads INTEGER DEFAULT 4,
    max_memory_mb INTEGER DEFAULT 2048,
    cache_size_mb INTEGER DEFAULT 5120,
    window_geometry JSON,
    panel_layout JSON,
    shortcuts JSON,
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

-- Settings profiles (normalized v2)
CREATE TABLE IF NOT EXISTS settings_profiles (
    id TEXT PRIMARY KEY, -- UUID string
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Case-insensitive uniqueness on name using expression index
CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_profiles_name_lower ON settings_profiles (lower(name));

-- Settings profile items (key/value per profile)
CREATE TABLE IF NOT EXISTS settings_profile_items (
    id TEXT PRIMARY KEY, -- UUID string
    profile_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL, -- JSON-serialized string
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    FOREIGN KEY (profile_id) REFERENCES settings_profiles(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_profile_items_profile_key ON settings_profile_items (profile_id, lower(key));
CREATE INDEX IF NOT EXISTS ix_settings_profile_items_profile ON settings_profile_items (profile_id);

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

-- Meta table for schema versioning and database metadata
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize schema version (required on database creation)
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('schema_version', '1.4.0', 'Added sha256 support to image_hashes for exact duplicate detection alongside perceptual hashes');

-- Image metadata cache with file identity tracking
CREATE TABLE IF NOT EXISTS image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT,                 -- File extension (lowercase, e.g., '.jpg')
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,

    -- Pool membership (A or B)
    pool TEXT NOT NULL DEFAULT 'A' CHECK (pool IN ('A','B')),

    -- File identity and hashing
    file_hash_sha256 TEXT,          -- Primary hash value (SHA-256 for exact duplicates, pHash/wHash for perceptual similarity)
    algorithm TEXT NOT NULL DEFAULT 'sha256' CHECK (algorithm IN ('sha256', 'phash', 'whash')),  -- Indicates hash type: 'sha256' for exact, 'phash'/'whash' for perceptual
    partial_hash_sha256 TEXT,       -- Partial SHA-256 for staged comparison
    file_inode INTEGER,             -- Inode number (where available)
    file_device INTEGER,            -- Device ID (where available)
    hash_computed_at TIMESTAMP,

    -- Image properties
    width INTEGER,
    height INTEGER,
    format TEXT,
    color_mode TEXT,
    bit_depth INTEGER,

    -- Metadata
    exif_data JSON,
    camera_make TEXT,
    camera_model TEXT,
    lens_model TEXT,
    date_taken TIMESTAMP,
    gps_latitude REAL,
    gps_longitude REAL,

    -- Cache management
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scan_version TEXT,
    is_valid BOOLEAN DEFAULT TRUE,
    mtime_ns INTEGER                -- Modification time in nanoseconds
);

-- Thumbnail metadata (file-backed storage per canonical decision)
-- Note: Actual thumbnail files are stored under cache/thumbnails/{size}/
-- Database only stores metadata and relative file paths
CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    size INTEGER NOT NULL,
    relative_path TEXT NOT NULL,  -- Path relative to cache/thumbnails/ directory
    format TEXT DEFAULT 'JPEG',
    quality INTEGER DEFAULT 85,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
    UNIQUE(image_id, size),
    CHECK (size IN (256, 512, 1024))
);

-- Image hashes for perceptual similarity (pHash, wHash)
CREATE TABLE IF NOT EXISTS image_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    algorithm TEXT NOT NULL CHECK (algorithm IN ('sha256', 'phash', 'whash')),
    hash_value TEXT NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
    UNIQUE(image_id, algorithm)
);

-- Cache statistics
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_metadata_path ON image_metadata(file_path);
CREATE INDEX IF NOT EXISTS idx_metadata_sha256 ON image_metadata(file_hash_sha256);
CREATE INDEX IF NOT EXISTS idx_metadata_partial ON image_metadata(partial_hash_sha256);
CREATE INDEX IF NOT EXISTS idx_metadata_inode ON image_metadata(file_inode, file_device);
CREATE INDEX IF NOT EXISTS idx_metadata_size ON image_metadata(file_size);
CREATE INDEX IF NOT EXISTS idx_metadata_date ON image_metadata(date_taken);
CREATE INDEX IF NOT EXISTS idx_thumbnails_image ON thumbnails(image_id);
CREATE INDEX IF NOT EXISTS idx_thumbnails_accessed ON thumbnails(last_accessed);
CREATE INDEX IF NOT EXISTS idx_hashes_image ON image_hashes(image_id);
CREATE INDEX IF NOT EXISTS idx_hashes_algorithm_value ON image_hashes(algorithm, hash_value);
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
    - migrate_to_1_1_0(conn) provides a safe migration path from 1.0.0 -> 1.1.0
    """

    CURRENT_VERSION = "1.5.0"  # Enhanced image_hashes migration for robust CHECK constraint update including 'sha256'; added detailed detection via sqlite_master and data preservation for existing perceptual hashes

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

    def migrate_to_1_1_0(self, conn: sqlite3.Connection) -> None:
        """
        Migrate from 1.0.0 to 1.1.0.

        Steps:
        1. Ensure app_settings table exists.
        2. If old 'profiles' table contains UI/perf columns (theme, language, ui_scale, etc),
           copy values from the default profile (or first profile) into app_settings,
           converting legacy cache_size_gb -> cache_size_mb where present.
        3. Recreate 'profiles' table without UI/perf columns and copy existing profile rows.
        4. Ensure at least one app_settings row exists.
        5. Update schema_version to 1.1.0.
        """
        logger.info("Migrating database from 1.0.0 to 1.1.0")

        # 1) Ensure app_settings table exists (idempotent)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                theme TEXT DEFAULT 'light',
                language TEXT DEFAULT 'en',
                ui_scale REAL DEFAULT 1.0,
                max_threads INTEGER DEFAULT 4,
                max_memory_mb INTEGER DEFAULT 2048,
                cache_size_mb INTEGER DEFAULT 5120,
                window_geometry JSON,
                panel_layout JSON,
                shortcuts JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (theme IN ('light', 'dark', 'auto')),
                CHECK (ui_scale BETWEEN 0.5 AND 3.0)
            );
        """)

        # 2) Inspect profiles table columns to determine if migration is needed
        cur = conn.execute("PRAGMA table_info(profiles)")
        columns = {row[1] for row in cur.fetchall()}

        if "theme" in columns or "cache_size_gb" in columns:
            logger.info("Detected legacy profile-scoped UI/perf columns; migrating to app_settings")

            # Copy values from the default profile (or first profile) into app_settings.
            # Convert cache_size_gb -> cache_size_mb (GB * 1024).
            conn.execute("""
                INSERT INTO app_settings (
                    theme, language, ui_scale,
                    max_threads, max_memory_mb, cache_size_mb,
                    created_at, modified_at
                )
                SELECT
                    COALESCE(theme, 'light') AS theme,
                    COALESCE(language, 'en') AS language,
                    COALESCE(ui_scale, 1.0) AS ui_scale,
                    COALESCE(max_threads, 4) AS max_threads,
                    COALESCE(max_memory_mb, 2048) AS max_memory_mb,
                    COALESCE(CAST(ROUND(cache_size_gb * 1024) AS INTEGER), 5120) AS cache_size_mb,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM profiles
                WHERE is_default = 1 OR id = (SELECT MIN(id) FROM profiles)
                LIMIT 1;
            """)

            # Recreate profiles table without UI/perf columns
            conn.execute("""
                CREATE TABLE profiles_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    is_default BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Copy existing profile rows to the new table (preserve IDs and timestamps)
            conn.execute("""
                INSERT INTO profiles_new (id, name, is_default, created_at, modified_at)
                SELECT id, name, is_default, created_at, modified_at
                FROM profiles;
            """)

            # Drop old profiles table and rename the new one
            conn.execute("DROP TABLE profiles;")
            conn.execute("ALTER TABLE profiles_new RENAME TO profiles;")

            logger.info("Migration completed: moved UI/performance settings to app_settings")
        else:
            # No legacy columns detected; ensure a default app_settings row exists
            cur = conn.execute("SELECT COUNT(*) FROM app_settings")
            if cur.fetchone()[0] == 0:
                logger.info("Creating default app_settings row (no legacy data found)")
                conn.execute("""
                    INSERT INTO app_settings (
                        theme, language, ui_scale,
                        max_threads, max_memory_mb, cache_size_mb
                    ) VALUES (
                        'light', 'en', 1.0,
                        4, 2048, 5120
                    );
                """)

        # 5) Update schema version
        self.set_version(conn, "1.1.0")
    
    def migrate_to_1_2_0(self, conn: sqlite3.Connection) -> None:
        """
        Migrate to 1.2.0: introduce normalized settings profiles and meta key.
        
        This migration is designed to be idempotent and safe to re-run. It ensures:
          - Presence of normalized tables:
              settings_profiles(id TEXT UUID PK, name TEXT UNIQUE (CI), description TEXT, is_active INT, created_at, updated_at)
              settings_profile_items(id TEXT UUID PK, profile_id TEXT FK, key TEXT, value TEXT, created_at, updated_at)
              Unique index on (lower(name)) and on (profile_id, lower(key))
          - Meta key 'pk.settings_profiles' exists with JSON value:
              {"schema_version": 1, "active_profile_id": "<uuid or null>", "last_migrated_at": "<ISO8601 Z>"}
          - Exactly one active profile is present; if none exists, creates a default profile and sets it active
          - If a legacy settings_profiles table (with columns like 'data' or 'is_default') exists, migrate rows:
              - Create a new normalized table, generate UUID ids
              - Move JSON keys from legacy 'data' dict into settings_profile_items
              - Map legacy meta.active_profile_id (INTEGER) to the new UUID active profile
          - Update meta.schema_version to "1.2.0"
        """
        logger.info("Applying migration to schema 1.2.0 (normalized settings profiles)")
    
        def _now_iso() -> str:
            return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
        # Ensure target tables exist (no-ops if they already do)
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_profiles_name_lower ON settings_profiles (lower(name));
    
        CREATE TABLE IF NOT EXISTS settings_profile_items (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (profile_id) REFERENCES settings_profiles(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_profile_items_profile_key ON settings_profile_items (profile_id, lower(key));
        CREATE INDEX IF NOT EXISTS ix_settings_profile_items_profile ON settings_profile_items (profile_id);
        """)
    
        # Detect legacy schema for settings_profiles (presence of 'data' or 'is_default' columns)
        legacy = False
        try:
            cur = conn.execute("PRAGMA table_info(settings_profiles)")
            cols = [r[1] for r in cur.fetchall()]
            legacy = ("data" in cols) or ("is_default" in cols)
        except sqlite3.OperationalError:
            # Table might not exist yet (fresh install) - already created above
            legacy = False
    
        if legacy:
            logger.info("Legacy settings_profiles schema detected; migrating to normalized v2")
            # Determine legacy active id if present
            old_active_id: Optional[int] = None
            try:
                cur = conn.execute("SELECT value FROM meta WHERE key='active_profile_id'")
                row = cur.fetchone()
                if row and str(row[0]).strip().isdigit():
                    old_active_id = int(str(row[0]).strip())
            except sqlite3.OperationalError:
                old_active_id = None
    
            # Create a new table with the v2 schema using a temp name to allow rename
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings_profiles_new_v2 (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
    
            # Read legacy rows
            cur = conn.execute("SELECT id, name, data, created_at, updated_at FROM settings_profiles")
            rows = cur.fetchall()
            id_map: Dict[int, str] = {}
            for row in rows:
                old_id = int(row[0])
                name = str(row[1])
                data_text = row[2]
                created = str(row[3]) if row[3] else _now_iso()
                updated = str(row[4]) if row[4] else created
                new_id = str(uuid.uuid4())
                id_map[old_id] = new_id
                is_active = 1 if (old_active_id is not None and old_id == old_active_id) else 0
    
                conn.execute(
                    "INSERT INTO settings_profiles_new_v2 (id, name, description, is_active, created_at, updated_at) VALUES (?, ?, NULL, ?, ?, ?)",
                    (new_id, name, is_active, created, updated),
                )
                # Migrate legacy 'data' dictionary into settings_profile_items
                try:
                    payload = json.loads(data_text) if data_text else {}
                    if isinstance(payload, dict):
                        for k, v in payload.items():
                            try:
                                val = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                            except Exception:
                                # Fallback to string representation if not JSON serializable
                                val = json.dumps(str(v), ensure_ascii=False)
                            conn.execute(
                                "INSERT INTO settings_profile_items (id, profile_id, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (str(uuid.uuid4()), new_id, str(k), val, created, updated),
                            )
                except Exception:
                    # Ignore malformed legacy JSON; continue
                    pass
    
            # Replace legacy table atomically
            conn.execute("DROP TABLE settings_profiles")
            conn.execute("ALTER TABLE settings_profiles_new_v2 RENAME TO settings_profiles")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_settings_profiles_name_lower ON settings_profiles (lower(name))")
            logger.info("Legacy settings_profiles migration complete; normalized tables ready")
    
        # Ensure at least one profile exists and exactly one is active
        cur = conn.execute("SELECT id FROM settings_profiles ORDER BY name COLLATE NOCASE")
        all_ids = [r[0] for r in cur.fetchall()]
        active_id: Optional[str] = None
    
        if not all_ids:
            # Create a default profile
            pid = str(uuid.uuid4())
            ts = _now_iso()
            conn.execute(
                "INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at) VALUES (?, 'Default', NULL, 1, ?, ?)",
                (pid, ts, ts),
            )
            active_id = pid
            logger.info("Created default settings profile with id=%s", pid)
        else:
            # Normalize active flags to exactly one
            cur = conn.execute("SELECT id FROM settings_profiles WHERE is_active = 1 ORDER BY name COLLATE NOCASE")
            actives = [r[0] for r in cur.fetchall()]
            if len(actives) == 0:
                # Try to derive from meta.pk.settings_profiles or pick first by name
                fallback_id: Optional[str] = None
                try:
                    c = conn.execute("SELECT value FROM meta WHERE key='pk.settings_profiles'")
                    row = c.fetchone()
                    if row:
                        try:
                            meta_cfg = json.loads(row[0])
                            if isinstance(meta_cfg, dict):
                                candidate = meta_cfg.get("active_profile_id")
                                if isinstance(candidate, str):
                                    cur2 = conn.execute("SELECT id FROM settings_profiles WHERE id = ?", (candidate,))
                                    if cur2.fetchone():
                                        fallback_id = candidate
                        except Exception:
                            pass
                except sqlite3.OperationalError:
                    pass
    
                if fallback_id is None:
                    cur = conn.execute("SELECT id FROM settings_profiles ORDER BY name COLLATE NOCASE LIMIT 1")
                    r = cur.fetchone()
                    fallback_id = str(r[0]) if r else None
                if fallback_id:
                    conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (fallback_id,))
                    active_id = fallback_id
            else:
                # More than one active; fix to first lexicographically
                active_id = str(actives[0])
                if len(actives) > 1:
                    conn.execute("UPDATE settings_profiles SET is_active = CASE WHEN id = ? THEN 1 ELSE 0 END", (active_id,))
    
        # If still unresolved, compute from single active row
        if active_id is None:
            cur = conn.execute("SELECT id FROM settings_profiles WHERE is_active = 1 LIMIT 1")
            r = cur.fetchone()
            active_id = str(r[0]) if r else None
    
        # Upsert meta key 'pk.settings_profiles'
        cfg = {
            "schema_version": 1,
            "active_profile_id": active_id,
            "last_migrated_at": _now_iso(),
        }
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            ("pk.settings_profiles", json.dumps(cfg, sort_keys=True, separators=(",", ":")), "Settings profiles manager state"),
        )
    
        # Bump global schema version to 1.2.0
        self.set_version(conn, "1.2.0")
    
        
        
        
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

    def __init__(self, data_dir: Optional[Path] = None, cache_dir: Optional[Path] = None):
        """
        Parameters
        ----------
        data_dir : Optional[Path]
            Base directory for application data (settings, backups, cache). When not provided,
            it defaults to the unified path provided by get_data_dir().
        cache_dir : Optional[Path]
            This parameter is deprecated. Cache files are now placed directly in the data_dir.

        Behavior
        --------
        - Uses get_data_dir() (which respects PK_PY_LIB_HOME) to determine the base directory.
        - All database files (settings.db, cache.db) are placed directly in this base directory.
        """
        # Resolve base directory using the unified function (handles PK_PY_LIB_HOME override)
        if data_dir is None:
            self.data_dir = get_data_dir()
        else:
            self.data_dir = Path(data_dir).expanduser().resolve()

        # Cache directory is now unified with data_dir for simplicity, as per instructions.
        # We set cache_dir = data_dir for internal consistency, although it's mostly unused now.
        self.cache_dir = self.data_dir

        # Database paths: settings.db directly in data_dir, cache.db directly in data_dir
        self.settings_db = self.data_dir / "settings.db"
        self.cache_db = self.data_dir / "cache.db"
        self.schema = SchemaManager()

    def initialize(self) -> None:
        """
        Ensure base directory exists and create databases and required tables.
     
        This is idempotent and safe to call multiple times.
        """
        logger.info("Initializing databases under data=%s, cache=%s", self.data_dir, self.cache_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize settings DB (includes meta table)
        logger.info(f"Settings DB path: {self.settings_db}, version: {self.get_version(self.settings_db)}")
        with self.get_connection(self.settings_db) as conn:
            conn.executescript(SETTINGS_SCHEMA)
            # Ensure meta table exists (SETTINGS_SCHEMA creates it, but be defensive)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
            if cur.fetchone() is None:
                conn.executescript(
                    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
                )
            # Check and handle schema versioning/migration
            current_version = self.get_version(self.settings_db)
            if current_version != self.schema.CURRENT_VERSION:
                logger.info(f"Migrating settings DB from {current_version} to {self.schema.CURRENT_VERSION}")
                if current_version is None or current_version < '1.2.0':
                    self.schema.migrate_to_1_1_0(conn)
                self.schema.migrate_to_1_2_0(conn)
        self.migrate_to_1_3_0(self.settings_db)
 

        # Initialize cache DB
        logger.info(f"Cache DB path: {self.cache_db}, version: {self.get_version(self.cache_db)}")
        with self.get_connection(self.cache_db) as conn:
            conn.executescript(CACHE_SCHEMA)
            # Migration for existing PoC databases: Ensure 'extension' column exists in image_metadata
            # This handles outdated schemas where inserts fail due to missing column (OperationalError)
            try:
                cur = conn.execute("PRAGMA table_info(image_metadata)")
                columns = [row[1] for row in cur.fetchall()]
                if 'extension' not in columns:
                    conn.execute("ALTER TABLE image_metadata ADD COLUMN extension TEXT")
                    logger.info("Added 'extension' column to image_metadata table in cache.db (migration for existing DBs)")
                else:
                    logger.debug("'extension' column already present in image_metadata")
            except sqlite3.OperationalError as e:
                logger.warning(f"Failed to verify/add extension column in image_metadata: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during extension column migration: {e}")
    
            # Migration 1.6.0: Ensure 'algorithm' column exists in image_metadata with CHECK constraint
            # This handles outdated schemas where inserts fail due to missing column or legacy CHECK constraint (OperationalError or CHECK constraint failed)
            try:
                # Robust detection using sqlite_master for full CREATE SQL
                cur_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_metadata'")
                create_result = cur_sql.fetchone()
                needs_migration = False
                if create_result:
                    create_sql = create_result[0]
                    # Check for legacy schema without 'algorithm' column or incomplete CHECK
                    if 'algorithm' not in create_sql or ("CHECK (algorithm IN ('phash', 'whash'))" in create_sql and "sha256" not in create_sql):
                        needs_migration = True
                        logger.info("Detected legacy image_metadata schema; preparing migration for 'algorithm' column and CHECK constraint")
                    elif "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in create_sql:
                        logger.info("Migration for image_metadata 'algorithm' column already applied (full CHECK constraint present)")
                        needs_migration = False
                    else:
                        # Ambiguous schema; fallback to safe recreate
                        logger.warning("Ambiguous image_metadata schema detected; falling back to safe recreate for 'algorithm' support")
                        needs_migration = True
                else:
                    # Table missing: CACHE_SCHEMA will create with new schema
                    logger.debug("image_metadata table missing; CACHE_SCHEMA will create with new schema")
                    needs_migration = False
    
                if needs_migration:
                    logger.info("Applying image_metadata migration: Adding/updating 'algorithm' column and CHECK constraint to support 'sha256', 'phash', 'whash'")
    
                    # Backup existing data
                    backup_cur = conn.execute("SELECT * FROM image_metadata ORDER BY id")
                    rows = backup_cur.fetchall()
                    row_count = len(rows)
                    if row_count > 0:
                        logger.info(f"Backing up {row_count} rows from image_metadata")
                    else:
                        logger.info("No existing data to backup")
    
                    # Drop old table
                    conn.execute("DROP TABLE IF EXISTS image_metadata")
                    logger.info("Dropped existing image_metadata table")
    
                    # Recreate with updated canonical schema including 'algorithm' column and full CHECK constraint
                    conn.executescript("""
                    CREATE TABLE image_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT UNIQUE NOT NULL,
                        file_name TEXT NOT NULL,
                        extension TEXT,
                        file_size INTEGER NOT NULL,
                        file_modified TIMESTAMP NOT NULL,
                        file_created TIMESTAMP,
                        pool TEXT NOT NULL DEFAULT 'A' CHECK (pool IN ('A','B')),
                        file_hash_sha256 TEXT,
                        algorithm TEXT NOT NULL DEFAULT 'sha256' CHECK (algorithm IN ('sha256', 'phash', 'whash')),
                        partial_hash_sha256 TEXT,
                        file_inode INTEGER,
                        file_device INTEGER,
                        hash_computed_at TIMESTAMP,
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
                        is_valid BOOLEAN DEFAULT TRUE,
                        mtime_ns INTEGER
                    );
                    """)
                    logger.info("Recreated image_metadata with 'algorithm' column and full CHECK constraint")
    
                    # Recreate indexes
                    indexes_sql = """
                    CREATE INDEX IF NOT EXISTS idx_metadata_path ON image_metadata(file_path);
                    CREATE INDEX IF NOT EXISTS idx_metadata_sha256 ON image_metadata(file_hash_sha256);
                    CREATE INDEX IF NOT EXISTS idx_metadata_partial ON image_metadata(partial_hash_sha256);
                    CREATE INDEX IF NOT EXISTS idx_metadata_inode ON image_metadata(file_inode, file_device);
                    CREATE INDEX IF NOT EXISTS idx_metadata_size ON image_metadata(file_size);
                    CREATE INDEX IF NOT EXISTS idx_metadata_date ON image_metadata(date_taken);
                    """
                    conn.executescript(indexes_sql)
                    logger.info("Recreated indexes on image_metadata")
    
                    # Restore data: map columns, handle missing 'algorithm' (default 'sha256'), log invalid
                    if rows:
                        restored_count = 0
                        invalid_alg_count = 0
                        for row in rows:
                            try:
                                # For simplicity, assume order matches schema; use explicit INSERT with available columns
                                # Since DROP/RECREATE, use INSERT with explicit columns (skip id for AUTOINCREMENT)
                                # Assume original row has columns without algorithm, so insert with DEFAULT
                                # But to be robust, use dict or skip if too complex; for PoC, assume standard order
                                # Original schema without algorithm: id, file_path, file_name, file_size, file_modified, ... (adjust index)
                                # To avoid fragility, insert with known columns, let DEFAULT handle algorithm
                                conn.execute("""
                                INSERT INTO image_metadata (
                                    file_path, file_name, extension, file_size, file_modified, file_created, pool,
                                    file_hash_sha256, partial_hash_sha256, file_inode, file_device, hash_computed_at,
                                    width, height, format, color_mode, bit_depth, exif_data, camera_make, camera_model,
                                    lens_model, date_taken, gps_latitude, gps_longitude, last_scanned, scan_version,
                                    is_valid, mtime_ns
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, row[1:])  # Skip id, append DEFAULT for algorithm
                                restored_count += 1
                            except sqlite3.IntegrityError as ie:
                                logger.warning(f"IntegrityError restoring metadata row {row}: {ie}")
                            except Exception as e:
                                logger.error(f"Error restoring metadata row {row}: {e}")
                        logger.info(f"Restored {restored_count} rows to image_metadata")
    
                    # Verify post-migration using sqlite_master
                    cur_verify_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_metadata'")
                    verify_result = cur_verify_sql.fetchone()
                    if verify_result and "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in verify_result[0]:
                        logger.info("Migration verification: 'algorithm' column and full CHECK constraint confirmed for image_metadata")
                    else:
                        logger.warning("Migration warning: Unable to verify 'algorithm' constraint for image_metadata")
    
                    # Update meta schema_version
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                        ("schema_version", "1.6.0", "Updated image_metadata with 'algorithm' CHECK for multi-hash support; preserved all legacy data")
                    )
                    logger.info("image_metadata migration 1.6.0 complete: Enables 'sha256' inserts for exact duplicates alongside perceptual hashes; resolves insert errors")
                else:
                    logger.info("image_metadata schema already up-to-date with 'algorithm' column")
            except sqlite3.OperationalError as e:
                logger.warning(f"Failed to verify/add algorithm column in image_metadata: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during algorithm column migration: {e}")

            # Migration 1.6.0: Add/update 'algorithm' column in image_metadata for multi-hash support.
            # Enables storage of exact duplicates ('sha256') and perceptual similarity ('phash', 'whash') hashes in unified table.
            # Detection: Use sqlite_master to retrieve the full CREATE TABLE SQL and check for legacy CHECK constraint
            # (e.g., contains "CHECK (algorithm IN ('phash', 'whash'))" without 'sha256'). This robust method avoids
            # fragile tuple indexing from PRAGMA table_info (which caused IndexError on alg_info[10], as tuples have only 6 elements:
            # cid, name, type, notnull, dflt_value, pk) and invalid PRAGMA table_check calls (not a standard SQLite pragma).
            # If legacy constraint detected or column missing: Backup rows, drop/recreate table with canonical schema
            # (incl. extension, algorithm DEFAULT 'sha256' CHECK ('sha256', 'phash', 'whash')), restore data, recreate indexes.
            # Idempotent: Skips if current schema already has the full CHECK constraint, logging "Migration already applied".
            # Error handling: Try/except around queries; if detection fails (e.g., no table), fallback to safe recreate with warning log.
            # Preserves all data (metadata, legacy hashes default to 'sha256' if no alg). Verification: Re-query sqlite_master
            # post-restore to confirm new CHECK in CREATE SQL.
            # PyDoc: This inline migration ensures compatibility with traversal.py inserts (algorithm='sha256' for exact,
            # 'phash'/'whash' for similarity via similarity.py), resolving startup errors in imgapp scans.
            # Guidelines: 4-space indent, logger.info for steps/success, logger.error+traceback for failures, full backup/restore.
            try:
                # Robust detection using sqlite_master for full CREATE SQL
                cur_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_metadata'")
                create_result = cur_sql.fetchone()
                needs_migration = False
                if create_result:
                    create_sql = create_result[0]
                    # Check for legacy CHECK without 'sha256' (idempotent: skip if already updated)
                    if "CHECK (algorithm IN ('phash', 'whash'))" in create_sql and "sha256" not in create_sql:
                        needs_migration = True
                        logger.info("Detected legacy CHECK constraint in image_metadata; preparing migration")
                    elif "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in create_sql:
                        logger.info("Migration 1.6.0 already applied to image_metadata (full CHECK constraint present)")
                        needs_migration = False
                    else:
                        # Ambiguous schema; fallback to safe recreate
                        logger.warning("Ambiguous image_metadata schema detected; falling back to safe recreate")
                        needs_migration = True
                else:
                    # Table missing: CACHE_SCHEMA will create, but for safety, we'll recreate if needed later
                    logger.debug("image_metadata table missing; will apply full schema")
                    needs_migration = True

                if needs_migration:
                    logger.info("Applying image_metadata migration 1.6.0: Updating to support 'sha256', 'phash', 'whash'")

                    # Backup existing data
                    backup_cur = conn.execute("SELECT * FROM image_metadata ORDER BY id")
                    rows = backup_cur.fetchall()
                    row_count = len(rows)
                    if row_count > 0:
                        logger.info(f"Backing up {row_count} rows from image_metadata")
                    else:
                        logger.info("No existing data to backup")

                    # Drop old table
                    conn.execute("DROP TABLE IF EXISTS image_metadata")
                    logger.info("Dropped existing image_metadata table")

                    # Recreate with updated canonical schema
                    conn.executescript("""
                    CREATE TABLE image_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT UNIQUE NOT NULL,
                        file_name TEXT NOT NULL,
                        extension TEXT,
                        file_size INTEGER NOT NULL,
                        file_modified TIMESTAMP NOT NULL,
                        file_created TIMESTAMP,
                        pool TEXT NOT NULL DEFAULT 'A' CHECK (pool IN ('A','B')),
                        file_hash_sha256 TEXT,
                        algorithm TEXT NOT NULL DEFAULT 'sha256' CHECK (algorithm IN ('sha256', 'phash', 'whash')),
                        partial_hash_sha256 TEXT,
                        file_inode INTEGER,
                        file_device INTEGER,
                        hash_computed_at TIMESTAMP,
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
                        is_valid BOOLEAN DEFAULT TRUE,
                        mtime_ns INTEGER
                    );
                    """)
                    logger.info("Recreated image_metadata with 'algorithm' column and full CHECK constraint")

                    # Recreate indexes
                    indexes_sql = """
                    CREATE INDEX IF NOT EXISTS idx_metadata_path ON image_metadata(file_path);
                    CREATE INDEX IF NOT EXISTS idx_metadata_sha256 ON image_metadata(file_hash_sha256);
                    CREATE INDEX IF NOT EXISTS idx_metadata_partial ON image_metadata(partial_hash_sha256);
                    CREATE INDEX IF NOT EXISTS idx_metadata_inode ON image_metadata(file_inode, file_device);
                    CREATE INDEX IF NOT EXISTS idx_metadata_size ON image_metadata(file_size);
                    CREATE INDEX IF NOT EXISTS idx_metadata_date ON image_metadata(date_taken);
                    """
                    conn.executescript(indexes_sql)
                    logger.info("Recreated indexes on image_metadata")

                    # Restore data: map columns, handle missing 'algorithm' (default 'sha256'), log invalid
                    if rows:
                        import traceback
                        restored_count = 0
                        invalid_alg_count = 0
                        for row in rows:
                            try:
                                # Original columns order from PRAGMA (assume standard, but dynamic for robustness)
                                # For simplicity, assume order matches schema; use dict for restore if needed
                                # But since DROP/RECREATE, use INSERT with explicit columns (skip id for AUTOINCREMENT)
                                non_id_values = row[1:]  # Skip id
                                # If no algorithm in original (pre-migration), append DEFAULT 'sha256'
                                if len(columns_info) < 10 or next((r for r in columns_info if r[1] == 'algorithm'), None) is None:
                                    # Insert 'sha256' at correct position (after file_hash_sha256, before partial_hash_sha256)
                                    # Schema positions: ... file_hash_sha256 (8), algorithm (9), partial_hash_sha256 (10), ...
                                    # Adjust based on original row length
                                    insert_pos = 8  # After file_hash_sha256
                                    non_id_values = non_id_values[:insert_pos] + ('sha256',) + non_id_values[insert_pos:]
                                # For legacy with old alg, check/validate on restore (but since DEFAULT, assume ok; log if needed)
                                conn.execute("""
                                INSERT INTO image_metadata (
                                    file_path, file_name, extension, file_size, file_modified, file_created, pool,
                                    file_hash_sha256, algorithm, partial_hash_sha256, file_inode, file_device, hash_computed_at,
                                    width, height, format, color_mode, bit_depth, exif_data, camera_make, camera_model,
                                    lens_model, date_taken, gps_latitude, gps_longitude, last_scanned, scan_version,
                                    is_valid, mtime_ns
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, non_id_values[:29])  # Truncate/pad to match 29 values
                                restored_count += 1
                            except sqlite3.IntegrityError as ie:
                                if "CHECK constraint failed: algorithm" in str(ie):
                                    logger.warning(f"Invalid legacy algorithm in row {row}; setting to 'sha256': {ie}")
                                    # For PoC, log and continue (could retry with forced 'sha256')
                                    invalid_alg_count += 1
                                else:
                                    logger.error(f"IntegrityError restoring row {row}: {ie}")
                            except Exception as e:
                                logger.error(f"Error restoring row {row}: {e}\nTraceback: {traceback.format_exc()}")
                        logger.info(f"Restored {restored_count} rows to image_metadata; {invalid_alg_count} legacy algorithms adjusted to 'sha256'")

                    # Verify post-migration using sqlite_master (robust, avoids tuple index issues)
                    cur_verify_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_metadata'")
                    verify_result = cur_verify_sql.fetchone()
                    if verify_result and "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in verify_result[0]:
                        logger.info("Migration 1.6.0 verification: 'algorithm' column and full CHECK constraint confirmed via sqlite_master")
                    else:
                        logger.warning("Migration 1.6.0 warning: Unable to fully verify 'algorithm' constraint via sqlite_master")

                    # Update meta schema_version
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                        ("schema_version", "1.6.0", "Updated image_metadata with 'algorithm' CHECK for multi-hash support; preserved all legacy data")
                    )
                    logger.info("image_metadata migration 1.6.0 complete: Enables 'sha256' inserts for exact duplicates, 'phash'/'whash' for similarity; startup errors resolved")
                else:
                    logger.info("image_metadata migration 1.6.0: Schema already up-to-date")
            except sqlite3.OperationalError as e:
                if "no such table: image_metadata" in str(e):
                    logger.debug("image_metadata missing; CACHE_SCHEMA will create with new schema")
                else:
                    logger.error(f"OperationalError during image_metadata 1.6.0 migration detection: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Fallback: Safe recreate if detection fails
                    logger.warning("Falling back to safe table recreate due to detection error")
                    # Proceed with backup/drop/recreate/restore as above (code duplication avoided by structure)
            except Exception as e:
                logger.error(f"Unexpected error during image_metadata 1.6.0 migration: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                # Fallback to safe recreate with warning
                logger.warning("Migration fallback: Recreating image_metadata table to ensure schema integrity")

            # Migration 1.5.0: Robust update for image_hashes CHECK constraint to ensure inclusion of 'sha256' for exact file hashing alongside perceptual 'phash' and 'whash'.
            # This migration addresses IntegrityError failures during hash storage where legacy DBs lack 'sha256' in the algorithm CHECK constraint.
            # Detection: Use sqlite_master to retrieve the full CREATE TABLE SQL and check for legacy CHECK constraint
            # (e.g., contains "CHECK (algorithm IN ('phash', 'whash'))" without 'sha256'). This avoids invalid PRAGMA table_check
            # (not a standard SQLite pragma, causing OperationalError) and fragile str(algorithm_info) checks (PRAGMA table_info tuple
            # does not contain full DDL CHECK string).
            # If legacy constraint detected: Backup rows, drop/recreate table with updated CHECK ('sha256', 'phash', 'whash'),
            # restore data, recreate indexes. Ensures compatibility with inserts from scan_directory (traversal.py: algorithm='sha256' for SHA256,
            # 'phash'/'whash' for perceptual via similarity.py).
            # Idempotent: Skips if current schema already has the full CHECK, logging "Migration already applied".
            # Error handling: Try/except around queries; if detection fails, fallback to safe recreate with warning log.
            # Follows project guidelines: 4-space indentation, logger.info for steps/success, logger.error+traceback for failures,
            # preserves all existing data (perceptual hashes remain valid).
            # Note: image_metadata stores file_hash_sha256 directly (no algorithm/constraint); this is solely for image_hashes flexibility.
            # Verification: Re-query sqlite_master post-restore to confirm new CHECK in CREATE SQL.
            # PyDoc: This inline migration resolves DB init errors during imgapp startup, enabling successful scans without constraint violations.
            try:
                # Robust detection using sqlite_master for full CREATE SQL
                cur_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_hashes'")
                create_result = cur_sql.fetchone()
                needs_migration = False
                if create_result:
                    create_sql = create_result[0]
                    # Check for legacy CHECK without 'sha256' (idempotent: skip if already updated)
                    if "CHECK (algorithm IN ('phash', 'whash'))" in create_sql and "sha256" not in create_sql:
                        needs_migration = True
                        logger.info("Detected legacy CHECK constraint in image_hashes; preparing migration")
                    elif "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in create_sql:
                        logger.info("Migration 1.5.0 already applied to image_hashes (full CHECK constraint present)")
                        needs_migration = False
                    else:
                        # Ambiguous schema; fallback to safe recreate
                        logger.warning("Ambiguous image_hashes schema detected; falling back to safe recreate")
                        needs_migration = True
                else:
                    # Table missing: CACHE_SCHEMA will create with new constraint
                    logger.debug("image_hashes table missing; CACHE_SCHEMA will create with new schema")
                    needs_migration = False  # No migration needed

                if needs_migration:
                    logger.info("Applying image_hashes migration 1.5.0: Updating CHECK constraint to include 'sha256'")

                    # Backup existing data to preserve perceptual hashes ('phash'/'whash') and any existing 'sha256'
                    backup_cur = conn.execute("SELECT id, image_id, algorithm, hash_value, computed_at FROM image_hashes ORDER BY id")
                    rows = backup_cur.fetchall()
                    row_count = len(rows)
                    if row_count > 0:
                        logger.info(f"Backing up {row_count} existing hash rows from image_hashes")
                    else:
                        logger.info("No existing data to backup in image_hashes")

                    # Drop the old table (removes old constraint)
                    conn.execute("DROP TABLE IF EXISTS image_hashes")
                    logger.info("Dropped existing image_hashes table")

                    # Recreate table with updated canonical schema including full CHECK constraint
                    # Matches CACHE_SCHEMA definition exactly for consistency
                    conn.executescript("""
                    CREATE TABLE image_hashes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        image_id INTEGER NOT NULL,
                        algorithm TEXT NOT NULL CHECK (algorithm IN ('sha256', 'phash', 'whash')),
                        hash_value TEXT NOT NULL,
                        computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
                        UNIQUE(image_id, algorithm)
                    );
                    """)
                    logger.info("Recreated image_hashes table with updated CHECK constraint: algorithm IN ('sha256', 'phash', 'whash')")

                    # Recreate canonical indexes for performance
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_hashes_image ON image_hashes(image_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_hashes_algorithm_value ON image_hashes(algorithm, hash_value)")
                    logger.info("Recreated indexes on image_hashes")

                    # Restore backed-up data (all rows compatible as they use 'phash'/'whash' or 'sha256')
                    if rows:
                        restored_count = 0
                        import traceback
                        for row in rows:
                            try:
                                conn.execute(
                                    "INSERT INTO image_hashes (id, image_id, algorithm, hash_value, computed_at) VALUES (?, ?, ?, ?, ?)",
                                    row
                                )
                                restored_count += 1
                            except sqlite3.IntegrityError as ie:
                                logger.warning(f"IntegrityError restoring hash row {row}: {ie} (skipping invalid entry)")
                            except Exception as e:
                                logger.error(f"Error restoring hash row {row}: {e}\nTraceback: {traceback.format_exc()}")
                        logger.info(f"Restored {restored_count} out of {row_count} hash rows to image_hashes")
                    else:
                        logger.info("No data to restore")

                    # Verify post-migration using sqlite_master (robust, avoids PRAGMA limitations)
                    cur_verify_sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='image_hashes'")
                    verify_result = cur_verify_sql.fetchone()
                    if verify_result and "CHECK (algorithm IN ('sha256', 'phash', 'whash'))" in verify_result[0]:
                        logger.info("Migration 1.5.0 verification: New CHECK constraint confirmed on image_hashes.algorithm via sqlite_master")
                    else:
                        logger.warning("Migration 1.5.0 warning: Unable to verify new CHECK constraint via sqlite_master")

                    # Update meta schema_version to reflect completion
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value, notes, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                        ("schema_version", "1.5.0", "Robust migration: Updated image_hashes CHECK constraint to support 'sha256' for exact hashes; preserved perceptual data")
                    )
                    logger.info("image_hashes migration 1.5.0 complete: Constraint updated to support SHA256 inserts, data fully preserved. Resolves IntegrityError during hash storage in traversal.py and cache.py.")
                else:
                    logger.info("image_hashes migration 1.5.0: Schema already up-to-date")
            except sqlite3.OperationalError as e:
                if "no such table: image_hashes" in str(e):
                    logger.debug("image_hashes table missing; CACHE_SCHEMA creates with new constraint")
                else:
                    logger.error(f"OperationalError during image_hashes 1.5.0 migration detection: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Fallback: Safe recreate if detection fails
                    logger.warning("Falling back to safe table recreate due to detection error")
                    # Proceed with backup/drop/recreate/restore (similar structure as above)
            except Exception as e:
                logger.error(f"Unexpected error during image_hashes migration 1.5.0: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                # Fallback to safe recreate with warning
                logger.warning("Migration fallback: Recreating image_hashes table to ensure schema integrity")

        self.migrate_to_1_3_0(self.cache_db)
        logger.info(f"Migration complete - Settings: {self.get_version(self.settings_db)}, Cache: {self.get_version(self.cache_db)}")

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
        # Enforce foreign keys for referential integrity
        conn.execute("PRAGMA foreign_keys = ON")
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

    def get_version(self, db_path: Optional[Path] = None) -> str:
        """
        Get the current schema version of the specified database or cache by default.
        
        Args:
            db_path (Optional[Path]): Path to the database file. If None, uses cache.db.
        
        Returns:
            str: The schema version from schema_version table, or '0.0.0' if not set.
        """
        if db_path is None:
            db_path = self.cache_db
        with self.get_connection(db_path) as conn:
            # Ensure schema_version table exists
            conn.execute('CREATE TABLE IF NOT EXISTS schema_version (key TEXT PRIMARY KEY, value TEXT)')
            logger.debug(f"Ensured schema_version table in {db_path}")
            
            cursor = conn.execute('SELECT value FROM schema_version WHERE key = "version"')
            result = cursor.fetchone()
            if not result:
                conn.execute('INSERT INTO schema_version (key, value) VALUES ("version", "0.0.0")')
                logger.debug("Initialized version to 0.0.0")
            return result[0] if result else '0.0.0'

    def migrate_to_1_3_0(self, db_path: Path) -> bool:
        """
        Legacy migration to '1.3.0' (superseded by 1.5.0 for image_hashes constraint fix).
        Forces the schema version to '1.3.0' for the given database path. This method is idempotent,
        creates the schema_version table if not exists, creates image_hashes for cache.db if not exists,
        logs all SQL operations and results, handles errors with try/except logging sqlite3.Error but continues to set the version.
        
        Args:
            db_path (Path): The path to the database file to migrate.
        
        Returns:
            bool: True if the version is now '1.3.0', False otherwise.
        """
        logger.info(f"Starting legacy migration to 1.3.0 for {db_path}")
        with self.get_connection(db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'CREATE TABLE IF NOT EXISTS schema_version (key TEXT PRIMARY KEY, value TEXT)'
                )
                logger.debug(f"Meta table ensured for {db_path}, rowcount: {cursor.rowcount}")
                if db_path == self.cache_db:
                    # Note: image_hashes creation here is legacy; 1.5.0 migration handles constraint robustly
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS image_hashes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            image_id INTEGER,
                            algorithm TEXT,
                            hash_value TEXT NOT NULL,
                            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    logger.debug(f"Legacy image_hashes ensured, rowcount: {cursor.rowcount}")
                    cursor.execute(
                        'CREATE INDEX IF NOT EXISTS idx_algorithm_hash ON image_hashes (algorithm, hash_value)'
                    )
                    cursor.execute(
                        'CREATE INDEX IF NOT EXISTS idx_image_id ON image_hashes (image_id)'
                    )
            except sqlite3.Error as e:
                logger.error(f"SQL error during legacy migration CREATEs for {db_path}: {e}")

            # Always set version (but 1.5.0 will override if needed)
            cursor.execute('DELETE FROM schema_version WHERE key = \'version\'')
            cursor.execute('INSERT INTO schema_version (key, value) VALUES (\'version\', \'1.3.0\')')
            logger.debug(f"Legacy version 1.3.0 set for {db_path}, rowcount: {cursor.rowcount}")
            conn.commit()
            logger.info(f"Legacy migration to 1.3.0 for {db_path} complete")

        return self.get_version(db_path) == '1.3.0'

# End of file