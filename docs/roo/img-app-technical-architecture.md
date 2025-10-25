
# KDC Image Organizer - Technical Architecture

## Conventions

- Cache size is configured via app_settings.cache_size_mb (units: MB). Do not use max_size_gb, MAX_CACHE_SIZE_GB, or ambiguous "GB" phrasing.
- Thresholds:
  - UI displays values on a 0–100 scale.
  - Internal logic uses 0.0–1.0.
  - Conversions: internal = ui / 100; ui = round(internal * 100).
- File extension tokens must be dot-prefixed (e.g., .png, .jpg, .jpeg, .tiff, .webp).
> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
> This document adds the centralized validator, normalization utilities, GUI-controller flow, and v1 algorithm dependencies (BLAKE3 for duplicates, pHash for similarity). Cross-references: data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), API [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md), decision §18 in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

## 1. System Architecture Overview

### 1.1 High-Level Architecture
```
┌─────────────────────────────────────────────────────┐
│                  GUI Layer (PySide6)                 │
│  ┌────────────────────────────────────────────────┐ │
│  │ Main Window │ Panels │ Dialogs │ Widgets      │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│              Application Core Layer                  │
│  ┌────────────────────────────────────────────────┐ │
│  │ Controllers │ Services │ Managers │ Models    │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│             Processing Engine Layer                  │
│  ┌────────────────────────────────────────────────┐ │
│  │ Algorithms │ Processors │ Analyzers │ Queue   │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│               Data Access Layer                      │
│  ┌────────────────────────────────────────────────┐ │
│  │ Database │ Cache │ File System │ Serializers  │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│            pk-py-lib Components Layer                │
│  ┌────────────────────────────────────────────────┐ │
│  │ GUI Widgets │ File Utils │ Image Utils │ Log  │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 1.2 Component Interaction Flow
```python
# Example similarity detection flow
User Input → GUI Event → Controller → Service → Processing Engine
                                           ↓
Database ← Cache Manager ← Result ← Algorithm Implementation
     ↓
GUI Update ← Model Update ← Controller ← Service
```

## 2. Core Components

### 2.1 Application Core (`img_app/core/`)

#### 2.1.1 Application Manager
```python
class ApplicationManager:
    """
    Central application controller managing lifecycle and coordination.

    Responsibilities:
    - Application initialization and shutdown
    - Database validation and migration
    - Component registration and dependency injection
    - Global event bus management
    - Cross-component communication
    """

    def __init__(self):
        self.config_manager: ConfigurationManager
        self.database_manager: DatabaseManager
        self.flat_cache_manager: Optional[FlatCacheManager] = None
        self.processing_engine: ProcessingEngine
        self.profile_manager: ProfileManager
        self.event_bus: EventBus
        self.data_locations: DataLocations

    def initialize(self) -> None:
        """Initialize all application components in correct order.

        Startup sequence:
        1. Initialize data locations (platformdirs or PK_IMG_APP_HOME)
        2. Check/create required databases
        3. Validate database integrity (PRAGMA checks)
        4. Run schema migrations if needed
        5. Load application settings
        6. Initialize cache manager
        7. Load default profile
        8. Initialize processing engine
        """
        # Setup data locations
        self.data_locations = DataLocations()

        # Database initialization and validation
        self.database_manager = DatabaseManager(self.data_locations)
        self.database_manager.initialize_databases()

        # Load configuration
        self.config_manager = ConfigurationManager(self.database_manager)
        app_settings = self.config_manager.get_app_settings()

        # Initialize flat cache
        self.flat_cache_manager = FlatCacheManager(
            max_size_mb=app_settings.cache_size_mb
        )

        # Initialize persistent flat cache if enabled in active profile
        active_profile = self.profile_manager.get_active_profile().json_data
        if active_profile.get("use_flat_cache", True):
            from pk_py_lib.core.flat_cache import FlatCacheManager
            self.flat_cache_manager = FlatCacheManager(
                db_path=self.data_locations.flat_cache_db
            )
        else:
            self.flat_cache_manager = None

    def startup_validation(self) -> ValidationResult:
        """Perform comprehensive startup validation.

        Checks:
        - Database existence and integrity
        - Schema version compatibility
        - Required directories writable
        - Sufficient disk space for cache
        """

    def shutdown(self) -> None:
        """Graceful shutdown with resource cleanup."""

class DataLocations:
    """Manages application data directory locations.

    Uses platformdirs for cross-platform paths, with PK_IMG_APP_HOME override.

    Vendor: "Pk"
    Application: "Img App"
    """

    def __init__(self):
        import os
        from platformdirs import user_data_dir, user_cache_dir

        # Check for environment override
        base_dir = os.environ.get('PK_IMG_APP_HOME')

        if base_dir:
            self.data_dir = Path(base_dir) / "data"
            self.cache_dir = Path(base_dir) / "cache"
        else:
            self.data_dir = Path(user_data_dir("Img App", "Pk"))
            self.cache_dir = Path(user_cache_dir("Img App", "Pk"))

        self.app_settings_file = self.data_dir / "app_settings.json"
        self.sessions_db = self.data_dir / "sessions.db"
        self.cache_db = self.cache_dir / "cache.db"
        self.flat_cache_db = self.data_dir / "flat_cache.db" # Persistent cache location
        self.backups_dir = self.data_dir / "backups"
        self.thumbnails_dir = self.cache_dir / "thumbnails"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(exist_ok=True)
        self.thumbnails_dir.mkdir(exist_ok=True)
```

#### 2.1.2 Data Directory Structure

All runtime data, configuration, caches, and logs are stored in a unified, cross-platform data directory managed by `platformdirs`.

The base directory is determined by `platformdirs.user_data_dir("pk_py_lib", "Pk")`.

**Override:** The base directory can be overridden by setting the environment variable `PK_PY_LIB_HOME`. If set, the application uses this path directly.

**Cross-Platform Examples (Base Directory):**

| OS | Example Path |
| :--- | :--- |
| Windows 10/11 | `C:\Users\<User>\AppData\Local\Pk\pk_py_lib` |
| Linux (XDG) | `~/.local/share/pk_py_lib` |
| macOS | `~/Library/Application Support/pk_py_lib` |

**Runtime Files and Directories (Relative to Base Directory):**

| Path | Purpose | Persistence |
| :--- | :--- | :--- |
| `app_settings.json` | Primary JSON file for application settings and global configuration. | Persistent |
| `search_profiles.json` | JSON file for user-defined search profiles and configurations. | Persistent |
| `sessions.db` | Database storing scan session history, results, and operation history. | Persistent |
| `cache.db` | Transient database for image metadata, similarity hashes, and thumbnail references. Subject to size limits and eviction. | Transient |
| `flat_cache.db` | Persistent cache for computed, file-stat validated metadata (e.g., perceptual hashes, quality scores). | Persistent |
| `logs/` | Directory for application log files, including terminal invocation logs. | Persistent |
| `backups/` | Directory for database backups created before schema migrations. | Persistent |
| `thumbnails/` | Directory for file-backed thumbnail images, managed by `FlatCacheManager`. | Persistent |

#### 2.1.2 Configuration Manager
```python
class ConfigurationManager:
    """
    Manages all application configuration and settings.

    Storage: SQLite database (settings.db)

    Configuration Categories:
    - Application settings (app_settings: window state, theme, language, performance)
    - Profile-scoped settings (named Profile entries: algorithm defaults, file-handling, history)
    - Algorithm configurations (presets, thresholds, parameters)
    - Runtime/transient overrides (in-memory session values)
    """

    def get_setting(
        self,
        key: str,
        default: Any = None,
        scope: Optional[str] = "profile",
        profile: Optional[str] = None
    ) -> Any:
        """
        Retrieve configuration value with fallback.

        Args:
            key: Dot-separated setting key (e.g., "performance.max_threads")
            default: Fallback value if not found
            scope: "app" to read from the application-scoped AppSettings,
                   "profile" to read a profile-scoped setting (default)
            profile: When scope='profile', the profile name (defaults to current profile)

        Returns:
            The setting value or default if not found.
        """

    def set_setting(
        self,
        key: str,
        value: Any,
        scope: Optional[str] = "profile",
        profile: Optional[str] = None,
        persist: bool = True
    ) -> None:
        """
        Update configuration value with validation.

        Args:
            key: Setting key
            value: New value to set
            scope: "app" or "profile"
            profile: Profile name when scope='profile'
            persist: If True, persist change to disk/storage; otherwise keep in-memory
        """

    def get_app_settings(self) -> "AppSettings":
        """
        Return the application-scoped AppSettings object.

        The AppSettings object contains strongly-typed global fields such as
        theme, language, ui_scale, max_threads, max_memory_mb and cache_size_mb.
        """

    def update_app_settings(self, updates: Dict[str, Any]) -> "AppSettings":
        """
        Apply a partial update to AppSettings, validate, persist, and return the
        updated AppSettings instance.

        Args:
            updates: Mapping of AppSettings field names to new values.
        """

    def load_profile(self, profile_name: str) -> "Profile":
        """Load complete profile configuration into memory and apply as active."""

    def export_profile(self, path: Path) -> None:
        """Export the currently active profile to a file (JSON)."""
```

### 2.2 Processing Engine (`img_app/processing/`)

#### 2.2.1 Similarity Detection Engine
```python
class SimilarityEngine:
    """
    Orchestrates similarity detection across multiple algorithms.

    Features:
    - Algorithm plugin system
    - Parallel processing with thread pool
    - Progress tracking and cancellation
    - Result aggregation and scoring
    """

    def __init__(self, config: AlgorithmConfig):
        self.algorithms: Dict[str, BaseAlgorithm] = {}
        self.thread_pool: ThreadPoolExecutor
        self.progress_tracker: ProgressTracker

    def register_algorithm(self, name: str, algorithm: BaseAlgorithm):
        """Register similarity algorithm implementation."""

    async def find_similar(
        self,
        images: List[Path],
        reference_images: Optional[List[Path]] = None,
        algorithms: List[str] = None,
        threshold: float = 0.85
    ) -> SimilarityResults:
        """Execute similarity detection with specified algorithms."""
```

#### 2.2.2 Algorithm Implementations
```python
class BaseAlgorithm(ABC):
    """Abstract base for similarity algorithms."""

    @abstractmethod
    def compute_hash(self, image: Image) -> Any:
        """Compute image hash/signature."""

    @abstractmethod
    def compare(self, hash1: Any, hash2: Any) -> float:
        """Compare two hashes, return similarity 0.0-1.0."""

class PerceptualHashAlgorithm(BaseAlgorithm):
    """pHash implementation using imagehash library."""

    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size

    def compute_hash(self, image: Image) -> imagehash.ImageHash:
        return imagehash.phash(image, hash_size=self.hash_size)

    def compare(self, hash1: imagehash.ImageHash, hash2: imagehash.ImageHash) -> float:
        distance = hash1 - hash2
        max_distance = self.hash_size * self.hash_size
        return 1.0 - (distance / max_distance)

class HistogramAlgorithm(BaseAlgorithm):
    """Color histogram comparison using OpenCV."""

    def compute_hash(self, image: Image) -> np.ndarray:
        # Convert to CV2 format and compute histogram
        pass

    def compare(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        # Use cv2.compareHist with correlation method
        pass
```

### 2.3 Data Management (`img_app/data/`)

#### 2.3.1 Database Manager
```python
class DatabaseManager:
    """Manages all database operations and lifecycle.

    Responsibilities:
    - Database creation and initialization
    - Integrity checking (PRAGMA quick_check, integrity_check)
    - Schema migration via Alembic
    - Backup management
    - Transaction coordination
    """

    def __init__(self, data_locations: DataLocations):
        self.locations = data_locations
        self.settings_db: Optional[Connection] = None
        self.sessions_db: Optional[Connection] = None
        self.cache_db: Optional[Connection] = None

    def initialize_databases(self) -> None:
        """Initialize all databases with validation and migration.

        For each database:
        1. Check if exists, create if not
        2. Run PRAGMA quick_check
        3. If check fails, run integrity_check
        4. If corrupt, prompt for rebuild
        5. Check schema version
        6. Run migrations if needed
        """
        # Three-database architecture per canonical decision §11
        for db_path, db_type in [
            (self.locations.settings_db, "settings"),  # User configuration
            (self.locations.sessions_db, "sessions"),  # Scan sessions & results
            (self.locations.cache_db, "cache")        # Transient cache data
        ]:
            self._initialize_database(db_path, db_type)

    def _initialize_database(self, db_path: Path, db_type: str) -> None:
        """Initialize a single database."""
        if not db_path.exists():
            self._create_database(db_path, db_type)
        else:
            # Validate existing database
            if not self._validate_database(db_path):
                self._handle_corrupt_database(db_path, db_type)

            # Check and run migrations
            if self._needs_migration(db_path):
                self._migrate_database(db_path)

    def _validate_database(self, db_path: Path) -> bool:
        """Run PRAGMA checks on database.

        Returns True if healthy, False if corrupt.
        """
        conn = sqlite3.connect(db_path)
        try:
            # Quick check first
            result = conn.execute("PRAGMA quick_check").fetchone()
            if result[0] != "ok":
                # Try full integrity check
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return result[0] == "ok"
            return True
        finally:
            conn.close()

    def _migrate_database(self, db_path: Path) -> None:
        """Run Alembic migrations with backup."""
        # Create backup first
        backup_path = self._backup_database(db_path)

        try:
            # Run Alembic migrations
            from alembic import command
            from alembic.config import Config

            alembic_cfg = Config()
            alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
            command.upgrade(alembic_cfg, "head")

            # Clean up old backups
            self._cleanup_old_backups()
        except Exception as e:
            # Restore from backup on failure
            self._restore_backup(backup_path, db_path)
            raise

    def _backup_database(self, db_path: Path) -> Path:
        """Create timestamped backup of database.

        Format: {db_name}.{ISO_timestamp}.v{schema_version}
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version = self._get_schema_version(db_path)
        backup_name = f"{db_path.stem}.{timestamp}.v{version}"
        backup_path = self.locations.backups_dir / backup_name

        import shutil
        shutil.copy2(db_path, backup_path)

        return backup_path

    def _cleanup_old_backups(self) -> None:
        """Remove backups per retention policy.

        Policy:
        - Keep 10 most recent backups per database
        - Purge backups older than 30 days
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.now() - timedelta(days=30)

        # Group backups by database
        backups_by_db = {}
        for backup in self.locations.backups_dir.glob("*.v*"):
            db_name = backup.stem.split(".")[0]
            if db_name not in backups_by_db:
                backups_by_db[db_name] = []
            backups_by_db[db_name].append(backup)

        # Apply retention policy
        for db_name, backups in backups_by_db.items():
            # Sort by modification time
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Keep 10 most recent
            for backup in backups[10:]:
                backup.unlink()

            # Remove old backups
            for backup in backups:
                if datetime.fromtimestamp(backup.stat().st_mtime) < cutoff_date:
                    backup.unlink()
```

#### 2.3.2 Database Schema
**Note on Schema Evolution**: As of flat_cache.db schema version 5.0.0, non-essential metadata columns (e.g., `file_name`, `extension`, `pool`, `format`, `color_mode`, `exif_data`, `camera_make`, `camera_model`, `date_taken`, `gps_latitude`, `gps_longitude`) have been removed from the persistent cache to streamline storage. The transient cache.db and sessions.db schemas have been updated for compatibility, retaining only core fields. These removed fields are now derived on-demand (e.g., via `Path` properties or profile configurations). Indexes `idx_pool` and `idx_date_taken` have been removed as they are no longer relevant.

```sql
-- settings.db schema

-- Settings profiles table
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    profile_version TEXT DEFAULT '1.0.0',

    -- Pool configuration
    pool_mode TEXT NOT NULL DEFAULT 'single',
    inverse_mode BOOLEAN DEFAULT FALSE,

    -- File identity detection
    hash_algo TEXT DEFAULT 'sha256',
    staged_hashing BOOLEAN DEFAULT TRUE,
    partial_hash_size_kb INTEGER DEFAULT 256,

    -- Algorithm defaults
    default_algorithms JSON,
    default_threshold REAL DEFAULT 0.85,
    algorithm_presets JSON,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (pool_mode IN ('single', 'dual')),
    CHECK (default_threshold BETWEEN 0.0 AND 1.0)
);

-- Path configurations for profiles
CREATE TABLE profile_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    pool_number INTEGER NOT NULL,  -- 1 or 2
    include_dirs JSON,
    exclude_dirs JSON,
    include_globs JSON,
    exclude_globs JSON,
    follow_symlinks BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, pool_number),
    CHECK (pool_number IN (1, 2))
);

-- App settings (single-row) table: global, typed fields for UI and performance
CREATE TABLE app_settings (
    id INTEGER PRIMARY KEY,
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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (theme IN ('light', 'dark', 'auto')),
    CHECK (ui_scale BETWEEN 0.5 AND 3.0)
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'string', 'int', 'float', 'bool', 'json'
    UNIQUE(profile_id, key)
);

CREATE TABLE operation_history (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id),
    operation_type TEXT NOT NULL,
    operation_data JSON NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_undone BOOLEAN DEFAULT FALSE
);

-- Meta table for schema versioning (in all databases)
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize schema version (required on database creation)
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('schema_version', '1.0.0', 'Initial schema version');

-- sessions.db schema
-- Contains scan sessions and results (canonical decision §11)

CREATE TABLE scan_sessions (
    id INTEGER PRIMARY KEY,
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

CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    image1_id INTEGER NOT NULL,
    image2_id INTEGER NOT NULL,
    overall_score REAL NOT NULL,
    algorithm_scores JSON,
    is_reference BOOLEAN DEFAULT FALSE,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES scan_sessions(id) ON DELETE CASCADE
);

-- cache.db schema
-- Contains transient cache data only

CREATE TABLE image_metadata (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,

    -- File identity and hashing
    file_hash_sha256 TEXT,          -- Full SHA-256 hash
    partial_hash_sha256 TEXT,       -- Partial hash for staged comparison
    file_inode INTEGER,              -- Inode (where available)
    file_device INTEGER,             -- Device ID (where available)
    hash_computed_at TIMESTAMP,
    mtime_ns INTEGER,                -- Modification time in nanoseconds

    -- Image properties
    width INTEGER,
    height INTEGER,
    bit_depth INTEGER,

    -- Metadata (streamlined for v5.0.0)
    lens_model TEXT,

    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scan_version TEXT,
    is_valid BOOLEAN DEFAULT TRUE
);

-- Indexes for file identity lookups
CREATE INDEX idx_metadata_sha256 ON image_metadata(file_hash_sha256);
CREATE INDEX idx_metadata_partial ON image_metadata(partial_hash_sha256);
CREATE INDEX idx_metadata_inode ON image_metadata(file_inode, file_device);
CREATE INDEX idx_metadata_size ON image_metadata(file_size);

-- File-backed thumbnails per canonical decision §10
-- Actual files stored at cache/thumbnails/{size}x{size}/{cache_key}.jpg
CREATE TABLE thumbnails (
    id INTEGER PRIMARY KEY,
    image_id INTEGER REFERENCES image_metadata(id),
    size INTEGER NOT NULL,
    relative_path TEXT NOT NULL,  -- Path relative to cache/thumbnails/
    format TEXT DEFAULT 'JPEG',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (image_id) REFERENCES image_metadata(id) ON DELETE CASCADE,
    UNIQUE(image_id, size),
    CHECK (size IN (256, 512, 1024))
);

CREATE TABLE similarity_cache (
    id INTEGER PRIMARY KEY,
    image1_id INTEGER REFERENCES image_metadata(id),
    image2_id INTEGER REFERENCES image_metadata(id),
    algorithm TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(image1_id, image2_id, algorithm)
);
```

#### 2.3.3 Cache Manager (Legacy/Transient)
```python
class FlatCacheManager:
    """
    Manages persistent file metadata, hashes, and quality scores with SQLite storage.

    This manager handles persistent SQLite-based caching of file metadata,
    content hashes (BLAKE3, XXH3), perceptual hashes (pHash, wHash),
    and image quality scores (BRISQUE).

    Features:
     - SQLite-based persistent storage
     - File validation (size, mtime, inode)
     - Configurable cache limits
     - Automatic cleanup and maintenance
     - Cache invalidation on file changes
     """

    def __init__(self, cache_dir: Path, max_size_mb: int = 5120):
        self.cache_dir = cache_dir
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.db_path = cache_dir / "cache.db"
        self.thumbnails_dir = cache_dir / "thumbnails"

        # Staged hashing configuration
        self.partial_hash_size = 256 * 1024  # 256KB per end
        self.min_size_for_partial = 512 * 1024  # 512KB minimum

    def get_file_hash(self, file_path: Path, staged: bool = True) -> FileHashResult:
        """Get cached or compute file hash.

        If staged=True and file >= 512KB:
        1. Check cache for existing hashes
        2. If not cached, compute partial hash (first/last 256KB)
        3. Store partial hash in cache
        4. Compute full SHA-256 only when needed for comparison
        """

    def compute_staged_hash(self, file_path: Path) -> Tuple[str, str]:
        """Compute staged SHA-256 hashes.

        Returns: (partial_hash, full_hash)
        """
        file_size = file_path.stat().st_size

        if file_size < self.min_size_for_partial:
            # Small file: compute full hash directly
            full_hash = self.compute_full_sha256(file_path)
            return (None, full_hash)
        else:
            # Large file: compute partial first
            partial_hash = self.compute_partial_sha256(file_path)
            return (partial_hash, None)

    def compute_partial_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 of first and last 256KB."""
        import hashlib

        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Hash first 256KB
            hasher.update(f.read(self.partial_hash_size))

            # Hash last 256KB
            f.seek(-self.partial_hash_size, 2)  # Seek from end
            hasher.update(f.read(self.partial_hash_size))

        return hasher.hexdigest()

    def get_thumbnail(self, image_path: Path, size: int) -> Optional[QPixmap]:
        """Retrieve cached thumbnail from file storage."""
        cache_key = self.generate_cache_key(image_path)
        thumbnail_path = self.thumbnails_dir / f"{size}x{size}" / f"{cache_key}.jpg"

        if thumbnail_path.exists():
            # Update access time in database
            self.update_access_time(image_path, size)
            return QPixmap(str(thumbnail_path))
        return None

    def invalidate_file(self, image_path: Path):
        """Invalidate cache entries when file signature changes.

        Invalidation triggers:
        - File size changed
        - mtime_ns changed
        - inode changed (where available)
        """
```

#### 2.3.4 Flat Cache Manager (Persistent Metadata)

The Flat Cache Manager (`[class FlatCacheManager](src/pk_py_lib/core/flat_cache.py:149)`) provides a persistent, file-stat validated cache for computed file metadata, specifically hashes (perceptual and content) and image quality scores.

This cache is now **enabled by default** via the `use_flat_cache` setting in the active profile. Core processing functions (e.g., similarity and quality evaluation) prioritize lookup and storage in the Flat Cache over transient caching mechanisms.

**Key Features:**
- **Unified Storage**: Stores all computed hashes and quality scores in a single SQLite database (`flat_cache.db`).
- **Validation**: Entries are validated against file size, modification date, inode, and device ID to ensure freshness.
- **Concurrency**: Uses SQLite WAL mode for improved read/write concurrency.
- **Cleanup**: Supports automatic cleanup of old/stale entries.

**Integration:**
- The `FlatCacheManager` instance is initialized by the `ApplicationManager` if the active profile enables `use_flat_cache`.
- It is passed as an optional parameter (`flat_cache_manager: Optional[FlatCacheManager]`) to core computation functions like `[compute_phash](src/pk_py_lib/core/image/similarity.py:239)` and `[ImageQualityEvaluator.evaluate](src/pk_py_lib/core/image/quality/base.py:75)`.
- See [Flat Cache Implementation](docs/roo/flat-cache-implementation.md:1) for detailed schema and API documentation.

### 2.4 GUI Components (`img_app/gui/`)

#### 2.4.1 Main Window Structure
```python
class MainWindow(QMainWindow):
    """
    Application main window with dockable panels.

    Components:
    - Menu bar with standard menus
    - Tool bars for common actions
    - Central widget (results view)
    - Dockable panels (file browser, preview, properties)
    - Status bar with progress
    """

    def __init__(self, app_manager: ApplicationManager):
        super().__init__()
        self.app_manager = app_manager
        self.setup_ui()
        self.setup_panels()
        self.setup_connections()

    def setup_panels(self):
        """Create and configure dockable panels."""
        self.file_panel = FileExplorerPanel()
        self.results_panel = ResultsPanel()  # src/img_app/gui/panels/results_panel.py
        self.preview_panel = PreviewPanel()
        self.properties_panel = PropertiesPanel()
```

#### 2.4.2 Custom Widgets
```python
class ImageComparisonWidget(QWidget):
    """
    Side-by-side image comparison with synchronized controls.

    Features:
    - Synchronized zoom/pan
    - Difference highlighting
    - Swipe comparison mode
    - Metadata overlay
    """

    def __init__(self):
        self.left_viewer: ImageViewer
        self.right_viewer: ImageViewer
        self.sync_controls = True

class ResultsTreeWidget(QTreeWidget):
    """
    Displays similarity results in grouped hierarchy.

    Features:
    - Custom item delegates for rich display
    - Lazy loading for large result sets
    - Context menus for operations
    - Keyboard navigation
    """

    def __init__(self):
        self.result_model: SimilarityResultModel
        self.selection_manager: SelectionManager
```

## 3. Threading and Concurrency

### 3.1 Thread Architecture
```python
class ThreadManager:
    """
    Manages application threading with proper Qt integration.

    Thread Types:
    1. Main GUI Thread - Qt event loop
    2. Worker Pool - CPU-bound image processing
    3. I/O Thread Pool - File operations
    4. Database Thread - Async DB operations
    """

    def __init__(self):
        self.worker_pool = QThreadPool()
        self.worker_pool.setMaxThreadCount(QThread.idealThreadCount())
        self.io_pool = ThreadPoolExecutor(max_workers=4)
        self.db_thread = DatabaseThread()

class ImageProcessingWorker(QRunnable):
    """
    Worker for image processing tasks.

    Features:
    - Progress reporting via signals
    - Cancellation support
    - Error handling with recovery
    - Memory-efficient processing
    """

    def __init__(self, task: ProcessingTask):
        self.task = task
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def run(self):
        """Execute processing with progress updates."""
        try:
            for i, image in enumerate(self.task.images):
                if self._is_cancelled:
                    break
                result = self.process_image(image)
                progress = (i + 1) / len(self.task.images) * 100
                self.signals.progress.emit(progress)
        except Exception as e:
            self.signals.error.emit(str(e))
```

## 4. Performance Optimization

### 4.1 Memory Management
```python
class MemoryManager:
    """
    Monitors and manages application memory usage.

    Strategies:
    - Lazy loading with generators
    - Image pyramid for multi-resolution
    - Aggressive garbage collection
    - Memory-mapped file access
    """

    def __init__(self, limit_mb: int = 2048):
        self.limit_bytes = limit_mb * 1024 * 1024
        self.current_usage = 0

    def load_image_lazy(self, path: Path) -> Generator[Image, None, None]:
        """Load image with minimal memory footprint."""

    def create_image_pyramid(self, image: Image) -> Dict[int, Image]:
        """Create multi-resolution pyramid for efficient display."""
```

### 4.2 Batch Processing Optimization
```python
class BatchProcessor:
    """
    Optimizes batch operations for maximum throughput.

    Techniques:
    - Vectorized operations with NumPy
    - Batch I/O operations
    - Pipeline parallelism
    - Adaptive batch sizing
    """

    def process_batch(self, images: List[Path], operation: Operation) -> Results:
        """Process image batch with optimization."""
        batch_size = self.calculate_optimal_batch_size(len(images))
        with ThreadPoolExecutor() as executor:
            futures = []
            for batch in chunks(images, batch_size):
                future = executor.submit(self.process_chunk, batch, operation)
                futures.append(future)
            return self.aggregate_results(futures)
```

## 5. Plugin Architecture

### 5.1 Plugin System Design
```python
class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.

    Plugin Types:
    - Algorithm plugins (new similarity methods)
    - Processor plugins (new batch operations)
    - Export plugins (new output formats)
    - UI plugins (custom panels/widgets)
    """

    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Plugin] = {}

    def discover_plugins(self):
        """Scan plugin directory for valid plugins."""

    def load_plugin(self, plugin_path: Path) -> Plugin:
        """Dynamically load and validate plugin."""

class Plugin(ABC):
    """Base class for all plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin display name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""

    @abstractmethod
    def initialize(self, app_context: ApplicationContext) -> None:
        """Initialize plugin with application context."""

    @abstractmethod
    def shutdown(self) -> None:
        """Clean shutdown of plugin."""
```

## 6. Error Handling and Recovery

### 6.1 Error Management Strategy
```python
class ErrorManager:
    """
    Centralized error handling with recovery strategies.

    Error Categories:
    - File System Errors (permissions, missing files)
    - Image Processing Errors (corruption, unsupported)
    - Database Errors (lock, corruption)
    - Memory Errors (out of memory)
    """

    def handle_error(self, error: Exception, context: ErrorContext) -> RecoveryAction:
        """Determine and execute recovery strategy."""

        if isinstance(error, FileNotFoundError):
            return self.handle_missing_file(error, context)
        elif isinstance(error, PermissionError):
            return self.handle_permission_error(error, context)
        elif isinstance(error, MemoryError):
            return self.handle_memory_error(error, context)
        else:
            return self.handle_generic_error(error, context)

class RecoveryAction(Enum):
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    FALLBACK = "fallback"
```

## 7. Testing Architecture

### 7.1 Test Structure
```python
# tests/test_algorithms.py
class TestSimilarityAlgorithms:
    """Test suite for similarity algorithms."""

    def test_phash_identical_images(self):
        """Test pHash with identical images returns 1.0."""

    def test_phash_different_images(self):
        """Test pHash with different images returns < threshold."""

    def test_algorithm_performance(self):
        """Benchmark algorithm performance."""

# tests/test_gui.py
class TestGUIComponents:
    """Test suite for GUI components using pytest-qt."""

    def test_main_window_initialization(self, qtbot):
        """Test main window creates correctly."""

    def test_file_selection(self, qtbot):
        """Test file selection workflow."""
```

## 8. Logging and Monitoring

### 8.1 Logging Architecture
```python
class ApplicationLogger:
    """
    Multi-level logging with structured output.

    Features:
    - Multiple outputs (console, file, GUI)
    - Structured logging with context
    - Performance metrics collection
    - Rotating file logs
    """

    def __init__(self):
        self.logger = structlog.get_logger()
        self.setup_outputs()

    def log_operation(self, operation: str, **context):
        """Log operation with structured context."""
        self.logger.info(operation, **context)

    def log_performance(self, metric: str, value: float, unit: str):
        """Log performance metric."""
        self.logger.info("performance", metric=metric, value=value, unit=unit)
```

## 9. Build and Deployment

### 9.1 Build Configuration
```python
# pyinstaller.spec
a = Analysis(
    ['img_app/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('img_app/assets', 'assets'),
        ('img_app/plugins', 'plugins'),
    ],
    hiddenimports=['PySide6', 'PIL', 'cv2', 'sklearn'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KDC Image Organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico'
)
```

## 10. Integration with pk-py-lib

### 10.1 Component Usage
```python
# Using pk-py-lib components

from pk_py_lib.gui.file_selector import FileSelector
from pk_py_lib.core.filesystem import FileWatcher, PathUtils
from pk_py_lib.core.logging import AdvancedLogger
from pk_py_lib.core.image import ImageProcessor

class ImageOrganizerApp:
    """Main application using pk-py-lib components."""

    def __init__(self):
        # Use pk-py-lib file selector
        self.file_selector = FileSelector(
            mode='multi',
            filters=['*.jpg', '*.png', '*.heic']
        )

        # Use pk-py-lib file watcher
        self.file_watcher = FileWatcher()
        self.file_watcher.file_changed.connect(self.on_file_changed)

        # Use pk-py-lib logger
        self.logger = AdvancedLogger("img_app")

        # Use pk-py-lib image processor
        self.image_processor = ImageProcessor()
```

### 10.2 Extension Points
```python
# Define interfaces for pk-py-lib integration

class IPkPyLibImageAlgorithm(Protocol):
    """Interface for pk-py-lib image algorithms."""

    def process(self, image: Image) -> Any:
        """Process image with algorithm."""

class PkPyLibAdapter:
    """Adapter for pk-py-lib components."""

    def adapt_widget(self, widget: QWidget) -> QWidget:
        """Adapt pk-py-lib widget for application."""
        return widget  # Add app-specific styling/behavior
## 11. Settings Profiles Architecture

Status: Planned

Overview
- Provide robust, reusable profile management across the library and application:
  - Core persistence and active-profile semantics
  - Thin API adapter surface for consumers
  - Reusable GUI dialog for CRUD+copy+select with validation
  - App startup modal integration to enforce a valid active profile before main UI creation

Component Boundaries and Responsibilities
- Library Core: [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1)
  - Owns profile CRUD, name validation, set-active semantics, and coordination with [ConfigurationManager](src/pk_py_lib/core/configuration.py:1) for per-profile settings.
  - Reads/writes to settings.db via [DatabaseManager](src/pk_py_lib/core/database.py:1).
  - Ensures single default profile and maintains active profile in meta.
- Library API: [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1)
  - High-level API surface (list/create/update/delete/copy/set-active/get-active/validate) for app and other consumers.
  - Returns structured results aligned with canonical API patterns in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1).
- Library GUI: [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1)
  - Reusable modal dialog with a two-pane list/detail manager, validation, and search/filter.
  - Emits selection/confirmation events; blocks until a valid active profile is confirmed or user cancels.
- App Integration: [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1)
  - Thin app-specific glue to launch the manager at startup and pass control to the main window only after success.
  - Startup wiring in [img_app/img_app/app.py](img_app/img_app/app.py:60).

Data Schema and Persistence
- Database: settings.db (SQLite), created and managed by [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:405).
- Tables used (already present):
  - profiles(id INTEGER PK, name UNIQUE, is_default BOOL, created_at, modified_at)
  - settings(profile_id, category, key, value, type ...)
  - meta(key TEXT PRIMARY KEY, value TEXT, notes, updated_at)
- Canonical meta keys for profile management:
  - active_profile_id: INTEGER → references profiles.id; determines the current active profile at startup
  - last_profile_prompted_at: TEXT (ISO8601) → optional, for analytics/UX refinement (not required for MVP)
- Default profile:
  - Exactly one row in profiles with is_default=1 (enforced by core logic; exclusivity handled by core rather than DB constraints).
- Active profile:
  - Exactly one active profile at any time; persisted in meta.active_profile_id (INTEGER).
  - On migration or missing key:
    - If a default exists: set active_profile_id to default profile id
    - Else: set to the lexicographically first profile
    - Else (no profiles): require creation on startup via modal

Validation and Naming
- Name rules:
  - Required, 1–64 characters
  - Allowed: letters, digits, spaces, underscore, hyphen
  - Uniqueness: case-insensitive unique across profiles
- Reserved names: none required for MVP; may extend later (documented in decisions)
- Threshold and other field validations follow canonical rules; e.g. thresholds (0.0–1.0 internal), see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:148)

CRUD + Copy Semantics
- Create: validate name; new profile with defaults or cloned values (when base provided)
- Update: partial field updates; name changes must preserve uniqueness
- Delete: disallow if profile is Active; disallow deleting the last remaining profile
- Copy: clone selected profile into a new one with a unique editable name
- Set Active: update meta.active_profile_id; ensure ConfigurationManager aligns (e.g., [ConfigurationManager.switch_profile()](src/pk_py_lib/core/configuration.py:399))
- Set Default: toggle profiles.is_default with exclusivity

Startup Integration Contract
- The application must enforce a valid active profile before creating the main window.
- Modal workflow:
  1) Initialize DB and configuration
  2) Launch profile manager modal [ProfileManagerDialog](src/pk_py_lib/gui/settings_manager/dialog.py:1)
  3) On success with a valid Active → proceed to create [MainWindow](img_app/img_app/main_window.py:1)
  4) On cancel without any Active profile → exit
- Rationale: downstream components (cache limits, hashing policies, UI defaults) may depend on active profile.

Fallback Persistence Strategy
- Primary: SQLite via [DatabaseManager](src/pk_py_lib/core/database.py:1).
- Fallback: JSON file under data_dir (e.g., profiles.json) used only when SQLite init fails catastrophically (rare).
  - On fallback write: persist minimal fields (id, name, is_default, and a subset of settings) to allow the app to continue.
  - On next successful DB init: import the JSON payload into DB and remove the fallback file.
  - All fallback usage should be logged as warnings.

Migration Considerations
- Ensure meta.active_profile_id exists:
  - If missing, initialize as described in Active profile section.
- Ensure profiles.name is UNIQUE (already in schema).
- No schema changes required for MVP; document future evolution under schema versioning in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:39)

Logging and Observability
- Use logger "pk_py_lib.settings_profiles" across core and API layers
- Log at INFO: create/update/delete/copy/set-active/set-default operations (profile id, name)
- Log at WARNING: validation failures, fallback persistence
- Log at ERROR: database errors, transaction rollback events

Separation of Concerns
- Core performs validation, persistence, and invariants (single default, cannot delete active, etc.)
- API exposes a minimal, stable surface for consumers and adapts exceptions to structured errors per canonical API patterns
- GUI is a thin façade over the API; it never mutates the database directly

Done Criteria (Architecture)
- A clear meta.active_profile_id contract is documented and implemented
- A reusable GUI modal exists and can be launched without app coupling
- All profile operations implement validation and invariants
- Startup flow blocks until a valid active profile is present
- Fallback persistence is documented; implementation is optional for MVP but interfaces should not preclude it

Next Steps
- Implement core manager [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1)
- Implement API adapter [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1)
- Implement GUI modal [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1)
- Wire startup in [img_app/img_app/app.py](img_app/img_app/app.py:60) via [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1)
- Add tests (unit for core/API; pytest-qt for GUI and startup flow)
<!-- Settings Manager finalized architecture additions -->

## 11A. Settings Manager — Finalized Architecture, Integration, and Persistence

Status: Approved

This section finalizes the design for the Settings/Profile Manager subsystem, superseding earlier placeholders that referenced `src/pk_py_lib/gui/settings_manager/dialog.py`. The canonical, library-first GUI module path is now `src/pk_py_lib/gui/settings_manager/`.

11A.1 Module structure (library-first, reusable)
- GUI (PySide6) under pk-py-lib:
  - [src/pk_py_lib/gui/settings_manager/__init__.py](src/pk_py_lib/gui/settings_manager/__init__.py:1)
  - [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1)
    - ProfileManagerDialog: two-pane List/Detail, search/filter, validation, blocking modal
  - [src/pk_py_lib/gui/settings_manager/controller.py](src/pk_py_lib/gui/settings_manager/controller.py:1)
    - Mediates GUI and API; executes CRUD/copy/validate; maps errors to user-visible messages
  - [src/pk_py_lib/gui/settings_manager/models.py](src/pk_py_lib/gui/settings_manager/models.py:1)
    - View-models, item models, and data adapters (e.g., ProfileVM, ValidationIssues)
  - [src/pk_py_lib/gui/settings_manager/validators.py](src/pk_py_lib/gui/settings_manager/validators.py:1)
    - Name/path/threshold validators; uses threshold helpers when applicable

- App integration (thin glue):
  - [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1)
    - Creates and runs the modal at startup; returns True only if a valid Active profile exists; otherwise exits per policy

- Core and API dependencies (implemented):
  - Core manager: [SettingsProfilesManager](src/pk_py_lib/core/settings_profiles.py:95)
    - CRUD/copy/active/default, invariants, JSON payload persistence in `settings_profiles.data`
    - Key methods:
      - [SettingsProfilesManager.create_profile()](src/pk_py_lib/core/settings_profiles.py:292)
      - [SettingsProfilesManager.update_profile()](src/pk_py_lib/core/settings_profiles.py:362)
      - [SettingsProfilesManager.delete_profile()](src/pk_py_lib/core/settings_profiles.py:439)
      - [SettingsProfilesManager.copy_profile()](src/pk_py_lib/core/settings_profiles.py:476)
      - [SettingsProfilesManager.set_active_profile()](src/pk_py_lib/core/settings_profiles.py:541)
      - [SettingsProfilesManager.set_default_profile()](src/pk_py_lib/core/settings_profiles.py:574)
      - [SettingsProfilesManager.export_profile()](src/pk_py_lib/core/settings_profiles.py:599)
      - [SettingsProfilesManager.import_profile()](src/pk_py_lib/core/settings_profiles.py:625)
  - API adapter: [SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69)
    - Returns ApiResponse; maps exceptions to ErrorCodes
    - Methods:
      - [SettingsProfilesAPI.list_profiles()](src/pk_py_lib/api/settings_profiles.py:109)
      - [SettingsProfilesAPI.get_profile()](src/pk_py_lib/api/settings_profiles.py:131)
      - [SettingsProfilesAPI.get_active()](src/pk_py_lib/api/settings_profiles.py:153)
      - [SettingsProfilesAPI.create()](src/pk_py_lib/api/settings_profiles.py:172)
      - [SettingsProfilesAPI.update()](src/pk_py_lib/api/settings_profiles.py:191)
      - [SettingsProfilesAPI.delete()](src/pk_py_lib/api/settings_profiles.py:214)
      - [SettingsProfilesAPI.copy()](src/pk_py_lib/api/settings_profiles.py:230)
      - [SettingsProfilesAPI.set_active()](src/pk_py_lib/api/settings_profiles.py:260)
      - [SettingsProfilesAPI.set_default()](src/pk_py_lib/api/settings_profiles.py:276)
      - [SettingsProfilesAPI.validate_name()](src/pk_py_lib/api/settings_profiles.py:295)
      - [SettingsProfilesAPI.export_profile()](src/pk_py_lib/api/settings_profiles.py:314)
      - [SettingsProfilesAPI.import_profile()](src/pk_py_lib/api/settings_profiles.py:329)

Note: Any earlier references to `src/pk_py_lib/gui/settings_manager/dialog.py` are superseded by the structure above.

11A.2 Persistence, storage layout, and meta keys
- Primary DB: SQLite `settings.db` created by [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:415)
- Canonical tables used:
  - `settings_profiles(id INTEGER PK, name UNIQUE COLLATE NOCASE, data TEXT JSON, is_default INT, created_at TEXT, updated_at TEXT)` — created by schema in [SETTINGS_SCHEMA](src/pk_py_lib/core/database.py:109)
  - `meta(key TEXT PRIMARY KEY, value TEXT, notes, updated_at TIMESTAMP)` — exists in schema; used for global metadata
- Active profile persistence:
  - `meta.active_profile_id` stores the Active profile id (INTEGER as text)
  - On read, the core resolves missing/dangling values: default → first-by-name → None (when no profiles)
  - See [SettingsProfilesManager.get_active_profile()](src/pk_py_lib/core/settings_profiles.py:273)
- Data payload:
  - Free-form JSON in `settings_profiles.data` for MVP; contains well-known fields (paths, hashing options, thresholds, etc.)

## 12. JSON Settings Architecture

### Overview
The application has migrated from SQLite-based settings storage to a JSON-based system for improved simplicity, maintainability, and cross-platform compatibility.

### JSON File Structure
- **app_settings.json**: Application-wide settings (theme, cache size, threading, UI preferences)
- **search_profiles.json**: User-defined search profiles for duplicate and similarity detection

### Key Components
- **JSON Settings Manager**: [`src/pk_py_lib/core/settings/json_unified_manager.py`](../src/pk_py_lib/core/settings/json_unified_manager.py:1)
 - Unified interface compatible with legacy SQLite manager
 - Manages both app settings and search profiles
 - Platform-specific settings directory handling
- **Schema Validation**: [`src/pk_py_lib/core/settings/json_schemas.py`](../src/pk_py_lib/core/settings/json_schemas.py:1)
 - Embedded JSON schemas for both settings files
 - Version management and compatibility checking
 - Runtime validation using jsonschema library

### Architecture Benefits
- **Simplified Storage**: Human-readable JSON files instead of SQLite complexity
- **Cross-Platform**: No database dependencies, works on any platform with JSON support
- **Version Management**: Schema versioning prevents compatibility issues
- **Fresh Start Approach**: No complex migration logic - corrupted files are recreated from defaults
- **Schema Validation**: Runtime validation ensures data integrity

### Settings Directory Structure
```
~/.pk-py-lib/settings/          # Platform-specific user data directory
├── app_settings.json          # Application settings (v1)
└── search_profiles.json       # Search profiles (v1)
```

### Schema Versions
- **App Settings Schema**: Version 1.0 - Basic application configuration
- **Search Profiles Schema**: Version 1.0 - Profile definitions with pools and criteria

### Error Handling Strategy
- **Fresh Start Approach**: Corrupted or incompatible settings files are deleted and recreated with defaults
- **No Migration Logic**: When schema versions change, old settings are discarded
- **Detailed Logging**: All settings operations are logged for debugging
- **Graceful Degradation**: Application continues to function with default settings if files are missing

### Backward Compatibility
- **Legacy API**: Deprecated SQLite-compatible interface maintained for compatibility
- **Unified API**: New JSON-based interface for modern usage
- **Migration Framework**: Documents the migration path from SQLite to JSON

### Integration with Application Core
The JSON settings manager integrates with the application core through:
- **Configuration Manager**: Loads and validates JSON settings on startup
- **Profile Manager**: Manages search profiles through JSON file operations
- **Application Manager**: Coordinates settings initialization and validation

Reference: [JSON Settings Architecture](#json-settings-architecture) in [architecture-plan.md](architecture-plan.md)
