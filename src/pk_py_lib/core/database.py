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
from platformdirs import user_data_dir, user_cache_dir

logger = logging.getLogger("pk_py_lib.core.database")


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
VALUES ('schema_version', '1.1.0', 'Add pool column to image_metadata');

-- Image metadata cache with file identity tracking
CREATE TABLE IF NOT EXISTS image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,

    -- Pool membership (A or B)
    pool TEXT NOT NULL DEFAULT 'A' CHECK (pool IN ('A','B')),

    -- File identity and hashing
    file_hash_sha256 TEXT,          -- Full SHA-256 hash (hex)
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

-- Image hashes for different algorithms
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

    CURRENT_VERSION = "1.2.0"  # Updated for normalized settings_profiles v2

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
            Base directory for application data (settings, backups). When not provided,
            it defaults to platformdirs.user_data_dir('Img App', 'Pk') unless PK_IMG_APP_HOME is set.
        cache_dir : Optional[Path]
            Base directory for cache data (cache.db, thumbnails). When not provided,
            it defaults to platformdirs.user_cache_dir('Img App', 'Pk') unless PK_IMG_APP_HOME is set.

        Behavior
        --------
        - If PK_IMG_APP_HOME is set and neither data_dir nor cache_dir is provided, use:
            data_dir = $PK_IMG_APP_HOME/data
            cache_dir = $PK_IMG_APP_HOME/cache
        - If data_dir is provided but cache_dir is not, default cache_dir = data_dir / 'cache'
          (useful for tests and ephemeral environments).
        """
        # Resolve locations with environment override when explicit dirs are not provided
        if data_dir is None and cache_dir is None:
            base = os.environ.get("PK_IMG_APP_HOME")
            if base:
                base_path = Path(base).expanduser().resolve()
                self.data_dir = base_path / "data"
                self.cache_dir = base_path / "cache"
            else:
                self.data_dir = Path(user_data_dir("Img App", "Pk")).expanduser().resolve()
                self.cache_dir = Path(user_cache_dir("Img App", "Pk")).expanduser().resolve()
        else:
            if data_dir is None:
                self.data_dir = Path(user_data_dir("Img App", "Pk")).expanduser().resolve()
            else:
                self.data_dir = Path(data_dir).expanduser().resolve()

            if cache_dir is None:
                # Preserve test behavior: keep cache under data_dir when an explicit data_dir is supplied
                self.cache_dir = self.data_dir / "cache"
            else:
                self.cache_dir = Path(cache_dir).expanduser().resolve()

        self.settings_db = self.data_dir / "settings.db"
        self.cache_db = self.cache_dir / "cache.db"
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
        with self.get_connection(self.settings_db) as conn:
            conn.executescript(SETTINGS_SCHEMA)
            # Ensure meta table exists (SETTINGS_SCHEMA creates it, but be defensive)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
            if cur.fetchone() is None:
                conn.executescript(
                    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, notes TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
                )
            # Check and handle schema versioning/migration
            current_version = self.schema.get_current_version(conn)

            if current_version is None:
                # Fresh install or legacy DB without schema_version:
                # Run sequential migrations to normalize schema deterministically.
                self.schema.migrate_to_1_1_0(conn)
                self.schema.migrate_to_1_2_0(conn)

            elif current_version == "1.0.0":
                # Sequential migrations
                self.schema.migrate_to_1_1_0(conn)
                self.schema.migrate_to_1_2_0(conn)

            elif current_version == "1.1.0":
                self.schema.migrate_to_1_2_0(conn)

            elif current_version != self.schema.CURRENT_VERSION:
                logger.warning(
                    "Unknown schema version %s (expected %s). Database may need manual migration.",
                    current_version, self.schema.CURRENT_VERSION
                )

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

# End of file