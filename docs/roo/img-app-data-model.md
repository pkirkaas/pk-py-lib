# KDC Image Organizer - Data Model Specifications
> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
>
> This document is extended with a canonical, strongly typed Settings Profile schema and validator-driven rules for Option A. Cross-references: decision [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md) §18, UI mapping [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), API shapes [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md).

## 1. Overview

## Balanced Defaults (preset)

Purpose
- Provide a safe, broadly useful baseline for scanning and selecting images.
- Minimize surprises: include common consumer image formats; exclude RAW; skip hidden items and symlinks; recurse folders; auto-detect case sensitivity for patterns based on OS/filesystem.
- Ensure predictable normalization: omitted fields are filled with Balanced defaults.

Key behaviors (summary)
- Preset name: Balanced (this is the application default if no preset is specified).
- Paths: required; at least one existing, readable directory. No implicit default path is assumed.
- Traversal: recursive = true; maxDepth = 0 (0 = unlimited). Guard rails warn on very large scans.
- Include formats: common consumer formats only by default (.jpg, .jpeg, .png, .webp, .gif, .tiff, .bmp, .heic, .heif). RAW is excluded by default.
- Pattern case behavior: case = auto (OS/FS-aware). On Windows: insensitive. On macOS: insensitive on default APFS/HFS+ volumes; sensitive if FS reports case-sensitive. On Linux: sensitive by default.
- Exclusions: hidden = true (skip), symlinks = true (do not follow), plus common system-junk patterns.
- Normalization: API/UI accept partial configs; defaults are applied to produce a normalized config.
- Default resolution order: preset → schema defaults → environment/app defaults → user config values → CLI flags → runtime overrides. Details in docs/roo/img-app-technical-architecture.md.

Default values (conceptual)
- traversal.recursive: true
- traversal.maxDepth: 0  (0 = unlimited)
- include.patterns: ["**/*"]
- include.case: "auto"  (OS-aware)
- exclude.hidden: true   (hidden excluded via attribute; not via patterns)
- exclude.symlinks: true
- exclude.patterns: []
- file_types (case-insensitive on all OS): [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
- guards.scanEstimateWarning: 50000 items (warn; allow continue)
- guards.scanEstimateBlock: 200000 items (block in non-interactive; prompt in interactive)

JSON Schema defaults (fragment)
Note: This fragment shows defaults and types. See the full schema in this file for complete validation rules.

```json
{
  "$id": "https://example.org/schemas/img-app/scan-config.json",
  "type": "object",
  "required": ["paths"],
  "properties": {
    "preset": {
      "type": "string",
      "enum": ["Balanced"],
      "default": "Balanced",
      "description": "Name of preset to seed defaults; Balanced is the application default."
    },
    "paths": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 },
      "minItems": 1,
      "description": "Absolute or relative directories to scan. Must exist and be readable."
    },
    "traversal": {
      "type": "object",
      "properties": {
        "recursive": { "type": "boolean", "default": true },
        "maxDepth": { "type": "integer", "minimum": 0, "default": 0 }
      },
      "additionalProperties": false,
      "default": {}
    },
    "include": {
      "type": "object",
      "properties": {
        "patterns": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "default": ["**/*"]
        },
        "raw": { "type": "boolean", "default": false },
        "case": { "type": "string", "enum": ["auto", "sensitive", "insensitive"], "default": "auto" }
      },
      "additionalProperties": false,
      "default": {}
    },
    "exclude": {
      "type": "object",
      "properties": {
        "hidden": { "type": "boolean", "default": true },
        "symlinks": { "type": "boolean", "default": true },
        "patterns": {
          "type": "array",
          "items": { "type": "string", "minLength": 1 },
          "default": []
        }
      },
      "additionalProperties": false,
      "default": {}
    },
    "guards": {
      "type": "object",
      "properties": {
        "scanEstimateWarning": { "type": "integer", "minimum": 1, "default": 50000 },
        "scanEstimateBlock": { "type": "integer", "minimum": 1, "default": 200000 }
      },
      "additionalProperties": false,
      "default": {}
    }
  },
  "additionalProperties": false
}
```

Notes on OS-aware pattern case behavior
- case = auto delegates to a runtime detector:
  - Windows: insensitive.
  - macOS: detect per-volume; default APFS/HFS+ are insensitive unless explicitly case-sensitive.
  - Linux/Unix: sensitive by default.
- Extension filter matching is case-insensitive on all OS.
- For mixed environments or network mounts, detection may occur per-root path. See docs/roo/img-app-technical-architecture.md for the detection algorithm and fallbacks.

Error and warning conditions tied to Balanced defaults
- Paths missing or empty → error (E_CFG_PATHS_REQUIRED).
- Any path does not exist or is not a directory → error (E_PATH_INVALID).
- Path is a symlink and exclude.symlinks = true → error for root path; child symlinks are skipped with warnings (W_SKIPPED_SYMLINK).
- Hidden items skipped when exclude.hidden = true → aggregated warning count (W_SKIPPED_HIDDEN).
- Estimated scan exceeds guards.scanEstimateWarning → warning; may prompt in interactive mode.
- Estimated scan exceeds guards.scanEstimateBlock:
  - Non-interactive: error (E_SCAN_GUARD_BLOCKED).
  - Interactive: prompt to continue with explicit acknowledgment.

Examples

1) Minimal config using Balanced defaults (only required paths; everything else omitted → defaults applied)
```json
{
  "paths": ["./photos", "/mnt/media/Pictures"]
}
```

2) Fully explicit Balanced config (all defaults written out)
```json
{
  "preset": "Balanced",
  "paths": ["./photos", "/mnt/media/Pictures"],
  "traversal": {
    "recursive": true,
    "maxDepth": 0
  },
  "include": {
    "patterns": ["**/*.{jpg,jpeg,png,webp,gif,tiff,bmp,heic,heif}"],
    "raw": false,
    "case": "auto"
  },
  "exclude": {
    "hidden": true,
    "symlinks": true,
    "patterns": [
      "**/Thumbs.db", "**/.DS_Store", "**/desktop.ini", "**/Icon\r",
      "**/.git/**", "**/.hg/**", "**/.svn/**",
      "**/node_modules/**",
      "**/__pycache__/**", "**/.mypy_cache/**", "**/.cache/**",
      "**/.idea/**", "**/.vscode/**",
      "**/build/**", "**/dist/**", "**/target/**"
    ]
  },
  "guards": {
    "scanEstimateWarning": 50000,
    "scanEstimateBlock": 200000
  }
}
```

Implementation and cross-references
- UI initial state uses Balanced defaults; see docs/roo/img-app-ui-design.md.
- API normalization applies these defaults when fields are omitted; see docs/roo/img-app-api-specifications.md.
- Default resolution order and OS-aware case detection algorithm; see docs/roo/img-app-technical-architecture.md.
- Tests and migration steps; see docs/roo/img-app-implementation-guide.md.
- Edge cases and error messages; see docs/roo/img-app-error-handling-edge-cases.md.

### 1.1 Data Storage Architecture
```
┌─────────────────────────────────────────────────┐
│              Application Data                    │
├─────────────────────┬───────────────────────────┤
│   Persistent Data   │      Transient Data       │
├─────────────────────┼───────────────────────────┤
│ • Settings.db       │ • In-memory image cache   │
│ • Cache.db          │ • Processing queue        │
│ • Profile files     │ • UI state                │
│ • Export files      │ • Temporary results       │
└─────────────────────┴───────────────────────────┘
```

### 1.2 Database Strategy
- **Settings Database**: User preferences, profiles, history
- **Cache Database**: Image metadata, thumbnails, similarity results
- **File System**: Original images (read-only access)
- **Memory Cache**: Active session data

## 2. Core Data Models

### 2.1 Image Model
```python
@dataclass
class ImageData:
    """Core image data model."""
    
    # File Information
    id: int                          # Unique identifier
    file_path: Path                  # Absolute path to image
    file_name: str                   # Filename without path
    file_size: int                   # Size in bytes
    file_modified: datetime          # Last modification time
    file_created: datetime           # Creation time
    file_hash: str                   # SHA-256 hash of file (hex)
    file_inode: Optional[int]        # OS inode (where available) to help detect renames/moves
    file_device: Optional[int]       # Device identifier for the filesystem (where available)
    
    # Image Properties
    width: int                       # Image width in pixels
    height: int                      # Image height in pixels
    format: str                      # Image format (JPEG, PNG, etc.)
    color_mode: str                  # RGB, RGBA, Grayscale, etc.
    bit_depth: int                   # Bits per channel
    
    # Metadata
    exif_data: Dict[str, Any]       # EXIF metadata
    camera_make: Optional[str]       # Camera manufacturer
    camera_model: Optional[str]      # Camera model
    lens_model: Optional[str]        # Lens information
    date_taken: Optional[datetime]   # Photo capture date
    gps_latitude: Optional[float]    # GPS coordinates
    gps_longitude: Optional[float]   
    
    # Processing State
    thumbnail_256: Optional[bytes]   # Small thumbnail
    thumbnail_512: Optional[bytes]   # Medium thumbnail
    thumbnail_1024: Optional[bytes]  # Large thumbnail
    last_scanned: datetime           # Last analysis time
    scan_version: str                # Scanner version used
    
    # Computed Properties
    aspect_ratio: float              # Width/height ratio
    megapixels: float               # Total megapixels
    file_size_readable: str         # Human-readable size
```

### 2.2 Similarity Result Model
```python
@dataclass
class SimilarityResult:
    """Similarity comparison result."""
    
    # Identification
    id: int                          # Result ID
    session_id: int                  # Scan session reference
    group_id: int                    # Similarity group ID
    
    # Images
    image1_id: int                   # First image ID
    image2_id: int                   # Second image ID
    image1_data: ImageData          # First image data
    image2_data: ImageData          # Second image data
    
    # Similarity Scores
    overall_score: float            # Combined similarity (0.0-1.0)
    algorithm_scores: Dict[str, float]  # Per-algorithm scores
    
    # Analysis Details
    algorithms_used: List[str]      # Algorithm names
    comparison_time: float          # Processing time in seconds
    computed_at: datetime           # Computation timestamp
    
    # Grouping
    is_reference: bool              # Is reference image in group
    group_position: int             # Position within group
```

### 2.3 Similarity Group Model
```python
@dataclass
class SimilarityGroup:
    """Group of similar images."""
    
    # Identification
    id: int                         # Group ID
    session_id: int                 # Scan session reference
    
    # Group Properties
    reference_image_id: int         # Primary/reference image
    member_count: int               # Number of images in group
    members: List[ImageData]        # Group member images
    
    # Statistics
    avg_similarity: float           # Average similarity score
    min_similarity: float           # Minimum similarity score
    max_similarity: float           # Maximum similarity score
    total_size: int                 # Combined size of all images
    potential_savings: int          # Size if keeping only one
    
    # Metadata
    created_at: datetime            # Group creation time
    modified_at: datetime           # Last modification
```

### 2.4 Scan Session Model
```python
@dataclass
class ScanSession:
    """Similarity scan session."""
    
    # Identification
    id: int                         # Session ID
    profile_id: int                 # User profile reference
    name: str                       # Session name
    
    # Configuration
    scan_type: str                  # 'single_set' or 'dual_set'
    source_paths: List[Path]        # Source directories/files
    reference_paths: Optional[List[Path]]  # Reference set for dual
    
    # Algorithm Configuration
    algorithms: List[str]           # Selected algorithms
    threshold: float                # Similarity threshold (0.0-1.0)
    algorithm_params: Dict[str, Any]  # Algorithm-specific params
    
    # Processing
    total_images: int               # Total images to process
    processed_images: int           # Images processed so far
    groups_found: int               # Number of groups found
    status: str                     # 'pending', 'running', 'completed', 'error'
    
    # Timing
    started_at: datetime            # Start timestamp
    completed_at: Optional[datetime]  # Completion timestamp
    duration: Optional[float]       # Total processing time
    
    # Results
    results: List[SimilarityGroup]  # Found similarity groups
    error_message: Optional[str]    # Error if failed
```

### 2.5 Profile Model
```python
@dataclass
class Profile:
    """Settings profile configuration.

    Settings profiles represent different scanning workflows and configurations.
    Each profile contains pool settings, path configurations, and algorithm
    preferences. UI and performance settings are stored globally in AppSettings.
    """
    
    # Identification
    id: UUID                        # Profile ID (UUID primary key)
    name: str                       # Unique profile name (required)
    description: Optional[str]      # Profile description
    is_default: bool                # Default profile flag
    profile_version: str            # Profile format version
    
    # Pool Configuration
    pool_mode: str                  # 'single' or 'dual'
    inverse_mode: bool              # Only for dual mode: show non-matches
    
    # Path Configuration (per pool)
    pool1_paths: PathConfig         # Primary pool paths
    pool2_paths: Optional[PathConfig]  # Secondary pool (dual mode only)
    
    # File Identity Detection
    hash_algo: str                  # 'sha256' (default)
    staged_hashing: bool            # Enable staged pre-filtering (default: true)
    partial_hash_size_kb: int      # Size for partial hash (default: 256)
    
    # Algorithm Settings
    default_algorithms: List[str]   # Selected similarity algorithms
    default_threshold: float        # Similarity threshold (0.0-1.0)
    algorithm_presets: Dict[str, Dict]  # Algorithm-specific parameters
    
    # Cache Settings
    cache_invalidation_keys: List[str]  # ['path', 'size', 'mtime_ns', 'inode']
    
    # History
    recent_paths: List[Path]        # Recently used paths
    recent_sessions: List[int]      # Recent session IDs
    
    # Timestamps
    created_at: datetime            # Profile creation
    updated_at: datetime            # Last modification

@dataclass
class PathConfig:
    """Path configuration for a pool."""
    include_dirs: List[Path]        # Directories to scan
    exclude_dirs: List[Path]        # Directories to skip
    include_globs: List[str]        # File patterns to include (e.g., "*.jpg")
    exclude_globs: List[str]        # File patterns to exclude
    follow_symlinks: bool           # Follow symbolic links
```

### 2.6 App Settings Model
```python
@dataclass
class AppSettings:
    """Global application settings.

    AppSettings is a single-row, application-scoped model that contains UI
    preferences, performance tuning and other system-wide configuration.
    There is only one active AppSettings row per installation (scripts and
    migration tasks should ensure one row exists; defaults are provided).
    """
    
    # Identification
    id: int                         # Settings row ID (primary key) — single row expected

    # Preferences
    theme: str                      # 'light', 'dark', 'auto' (default: 'light')
    language: str                   # Language code (default: 'en')
    ui_scale: float                 # UI scaling factor (default: 1.0)

    # Performance Settings
    max_threads: int                # Thread pool size (default: 4)
    max_memory_mb: int              # Memory limit in megabytes (default: 2048)
    cache_size_mb: int              # Cache size limit in megabytes (default: 5120)

    # UI Preferences
    window_geometry: Dict           # Window size/position (JSON-serializable)
    panel_layout: Dict              # Panel configuration (JSON-serializable)
    shortcuts: Dict[str, str]       # Custom keyboard shortcuts

    # Timestamps
    created_at: datetime            # Row creation timestamp
    modified_at: datetime          # Last modification timestamp
```

Migration note:
- Historically UI preferences and some performance settings were stored per-profile (fields: theme, language, ui_scale, max_threads, max_memory_mb, cache_size_gb). These have been moved to the application-scoped AppSettings model.
- Suggested migration SQL (one-time): copy values from the default profile into app_settings and convert GB->MB for any legacy cache_size_gb values.

```sql
-- Example migration: create an app_settings row from the default profile
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
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM profiles
WHERE is_default = TRUE
LIMIT 1;
```

## 3. Database Schemas

### 3.1 Settings Database (settings.db)

#### Settings Profiles Table (Option A - JSON Payload)
```sql
-- Canonical table for Option A Settings Profiles with JSON payload
CREATE TABLE settings_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL COLLATE NOCASE,
    data TEXT NOT NULL,  -- JSON payload per Option A schema
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Meta table for active profile and schema version
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert schema version and active profile tracking
INSERT OR IGNORE INTO meta (key, value, notes) VALUES
    ('schema_version', '1.0.0', 'Database schema version'),
    ('active_profile_id', NULL, 'Currently active profile ID');
```

**Bridging Note**: The typed `profiles` and `profile_paths` tables shown below represent the legacy key/value approach. For Option A implementation, `settings_profiles` with JSON payload is canonical, storing the complete [`SettingsProfileOptionA`](docs/roo/img-app-data-model.md:1239) structure. The core manager [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:95) and API [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:69) work exclusively with the JSON-based model.

#### Legacy Profiles Tables (for reference)
```sql
-- Legacy typed approach (retained for migration reference)
CREATE TABLE profiles (
    id TEXT PRIMARY KEY,  -- UUID stored as text
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
    
    -- Cache configuration
    cache_invalidation_keys JSON DEFAULT '["path", "size", "mtime_ns", "inode"]',
    
    -- History
    recent_paths JSON,
    recent_sessions JSON,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CHECK (pool_mode IN ('single', 'dual')),
    CHECK (hash_algo IN ('sha256', 'md5', 'blake3')),
    CHECK (default_threshold BETWEEN 0.0 AND 1.0),
    CHECK (partial_hash_size_kb > 0)
);

-- Path configurations for profiles
CREATE TABLE profile_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    pool_number INTEGER NOT NULL,  -- 1 or 2
    include_dirs JSON,              -- List of directories
    exclude_dirs JSON,              -- List of exclusions
    include_globs JSON,             -- Include patterns
    exclude_globs JSON,             -- Exclude patterns
    follow_symlinks BOOLEAN DEFAULT FALSE,
    
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
    UNIQUE(profile_id, pool_number),
    CHECK (pool_number IN (1, 2))
);

-- App settings (single-row) table: global, typed fields for UI and performance
CREATE TABLE app_settings (
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

-- Settings table (key-value store)
CREATE TABLE settings (
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

-- Algorithm presets
CREATE TABLE algorithm_presets (
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

-- Operation history
CREATE TABLE operation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL,
    operation_type TEXT NOT NULL,
    operation_data JSON NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_undone BOOLEAN DEFAULT FALSE,
    undo_data JSON,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

-- Recent items
CREATE TABLE recent_items (
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

-- Meta table for schema versioning and database metadata
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize schema version (required on database creation)
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('schema_version', '1.0.0', 'Initial schema version');

-- Database creation timestamp
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('created_at', CURRENT_TIMESTAMP, 'Database creation time');

-- Application version that created/last updated the database
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('app_version', '1.0.0', 'Application version');
-- Create indexes
CREATE INDEX idx_settings_profile ON settings(profile_id);
CREATE INDEX idx_settings_lookup ON settings(profile_id, category, key);
CREATE INDEX idx_history_profile ON operation_history(profile_id);
CREATE INDEX idx_history_timestamp ON operation_history(timestamp);
CREATE INDEX idx_recent_profile ON recent_items(profile_id);
CREATE INDEX idx_recent_type ON recent_items(item_type);
```

### 3.2 Cache Database (cache.db)

```sql
-- Image metadata cache with file identity tracking
CREATE TABLE image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,
    
    -- File identity and hashing
    file_hash_sha256 TEXT,          -- Full SHA-256 hash (hex)
    partial_hash_sha256 TEXT,       -- Partial SHA-256 for staged comparison
    file_inode INTEGER,              -- Inode number (where available)
    file_device INTEGER,             -- Device ID (where available)
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

-- Meta table for cache database
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize cache database metadata
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('schema_version', '1.0.0', 'Initial cache schema');

-- Thumbnail metadata (file-backed storage per canonical decision)
-- Note: Actual thumbnail files are stored in cache/thumbnails/ directory
-- Database only stores metadata and relative file paths
CREATE TABLE thumbnails (
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
CREATE TABLE image_hashes (
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
CREATE TABLE cache_stats (
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

-- Create indexes for performance
CREATE INDEX idx_metadata_path ON image_metadata(file_path);
CREATE INDEX idx_metadata_sha256 ON image_metadata(file_hash_sha256);
CREATE INDEX idx_metadata_partial ON image_metadata(partial_hash_sha256);
CREATE INDEX idx_metadata_inode ON image_metadata(file_inode, file_device);
CREATE INDEX idx_metadata_size ON image_metadata(file_size);
CREATE INDEX idx_metadata_date ON image_metadata(date_taken);
CREATE INDEX idx_thumbnails_image ON thumbnails(image_id);
CREATE INDEX idx_thumbnails_accessed ON thumbnails(last_accessed);
CREATE INDEX idx_hashes_image ON image_hashes(image_id);
```

### 3.3 Sessions Database (sessions.db)

Per canonical decision [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:61), scan sessions and similarity results are stored in a separate sessions.db database for better separation of concerns and performance.

```sql
-- Meta table for sessions database
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Initialize sessions database metadata
INSERT OR IGNORE INTO meta (key, value, notes)
VALUES ('schema_version', '1.0.0', 'Initial sessions schema');

-- Scan sessions
CREATE TABLE scan_sessions (
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

-- Similarity results
CREATE TABLE similarity_results (
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
    CHECK (overall_score BETWEEN 0.0 AND 1.0)
);

-- Create indexes for performance
CREATE INDEX idx_sessions_profile ON scan_sessions(profile_id);
CREATE INDEX idx_sessions_status ON scan_sessions(status);
CREATE INDEX idx_results_session ON similarity_results(session_id);
CREATE INDEX idx_results_group ON similarity_results(session_id, group_id);
CREATE INDEX idx_results_images ON similarity_results(image1_id, image2_id);
```

## 4. Data Flow Diagrams

### 4.1 Image Processing Flow
```
File Selection → File Validation → Metadata Extraction
                                           ↓
                              Image Loading → Hash Computation
                                           ↓
                              Thumbnail Generation → Cache Storage
                                           ↓
                              Similarity Computation → Result Storage
```

### 4.2 Cache Management Flow
```
Request Data → Check Cache → Cache Hit? → Return Cached Data
                    ↓
                Cache Miss → Generate Data → Store in Cache
                    ↓
           Check Cache Size → Exceeds Limit? → LRU Eviction
                    ↓
              Return Data
```

## 5. Data Validation Rules

### 5.1 Image File Validation
```python
class ImageValidator:
    """Validates image files before processing."""
    
    MIN_SIZE = 1024           # Minimum 1KB
    MAX_SIZE = 500_000_000    # Maximum 500MB
    MIN_DIMENSION = 10        # Minimum 10x10 pixels
    MAX_DIMENSION = 50000     # Maximum 50000 pixels per side
    
    SUPPORTED_FORMATS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
        '.tiff', '.tif', '.webp', '.heic', '.heif'
    }
    
    def validate(self, file_path: Path) -> ValidationResult:
        """Validate image file."""
        # Check file exists
        # Check file size
        # Check extension
        # Verify file header
        # Check image dimensions
        # Return validation result
```

### 5.2 Data Integrity Rules
```python
class DataIntegrityChecker:
    """Ensures data integrity across databases."""
    
    def check_referential_integrity(self):
        """Verify all foreign key relationships."""
        
    def check_cache_consistency(self):
        """Verify cache matches file system state."""
        
    def check_hash_validity(self):
        """Verify stored hashes match current files."""
        
    def repair_inconsistencies(self):
        """Attempt to repair found issues."""
```

## 6. Data Migration

### 6.1 Schema Versioning
```python
class SchemaManager:
    """Manages database schema versions and migrations."""
    
    CURRENT_VERSION = "1.0.0"
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.backup_dir = db_path.parent / "backups"
        self.backup_dir.mkdir(exist_ok=True)
    
    def check_database_integrity(self) -> bool:
        """Run PRAGMA checks on database.
        
        1. Run PRAGMA quick_check
        2. If fails, run PRAGMA integrity_check
        3. Return True if healthy, False if corrupt
        """
        
    def get_current_version(self) -> str:
        """Get current schema version from meta table."""
        
    def needs_migration(self) -> bool:
        """Check if database needs migration."""
        
    def backup_before_migration(self) -> Path:
        """Create timestamped backup before migration.
        
        Format: {db_name}.{ISO_timestamp}.v{schema_version}
        """
        
    def migrate(self, target_version: str):
        """Migrate database using Alembic."""
        
    def cleanup_old_backups(self):
        """Remove backups older than retention policy."""
```

### 6.2 Data Import/Export
```python
class DataExporter:
    """Exports application data."""
    
    def export_session(self, session_id: int, format: str) -> Path:
        """Export scan session results."""
        # Formats: CSV, JSON, XML, HTML
        
    def export_profile(self, profile_id: int) -> Path:
        """Export user profile settings."""
        
    def export_full_backup(self) -> Path:
        """Export complete application data."""

class DataImporter:
    """Imports external data."""
    
    def import_session(self, file_path: Path) -> int:
        """Import scan session from file."""
        
    def import_profile(self, file_path: Path) -> int:
        """Import user profile settings."""
        
    def import_legacy_data(self, file_path: Path):
        """Import data from older versions."""
```

## 7. Cache Management

### 7.1 Cache Policies
```python
class CachePolicy:
    """Cache management policies."""
    
    # Size limits (application-scoped, expressed in megabytes)
    MAX_CACHE_SIZE_MB = 5120  # default 5120 MB (≈5 GB)
    MAX_THUMBNAIL_AGE_DAYS = 90
    MAX_RESULT_AGE_DAYS = 30
    
    # Staged hashing configuration
    PARTIAL_HASH_SIZE_KB = 256     # Hash first/last 256KB
    MIN_FILE_SIZE_FOR_PARTIAL = 512 * 1024  # 512KB minimum
    
    # Eviction strategies
    EVICTION_STRATEGY = "LRU"  # LRU, LFU, FIFO
    EVICTION_BATCH_SIZE = 100
    
    # Cleanup triggers
    CLEANUP_ON_SIZE_PERCENT = 90  # Cleanup at 90% full
    CLEANUP_INTERVAL_HOURS = 24
    
    # Database backup retention
    MAX_BACKUP_COUNT = 10          # Keep 10 most recent backups
    MAX_BACKUP_AGE_DAYS = 30       # Purge backups older than 30 days
```

### 7.2 Cache Operations
```python
class CacheOperations:
    """Low-level cache operations."""
    
    def get_cache_size(self) -> int:
        """Get current cache size in bytes."""
        
    def clean_expired_entries(self):
        """Remove expired cache entries."""
        
    def vacuum_database(self):
        """Optimize database file size."""
        
    def rebuild_indexes(self):
        """Rebuild database indexes."""
        
    def verify_cache_integrity(self):
        """Verify cache data integrity."""
```

## 8. Performance Considerations

### 8.1 Query Optimization
```sql
-- Optimized query for finding similar images
WITH ranked_results AS (
    SELECT 
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY r.group_id 
            ORDER BY r.overall_score DESC
        ) as rank
    FROM similarity_results r
    WHERE r.session_id = ? 
    AND r.overall_score >= ?
)
SELECT * FROM ranked_results 
WHERE rank <= 10
ORDER BY group_id, rank;
```

### 8.2 Batch Operations
```python
class BatchOperations:
    """Optimized batch database operations."""
    
    def batch_insert_metadata(self, images: List[ImageData]):
        """Insert multiple images efficiently."""
        # Use prepared statements
        # Batch in transactions
        # Disable autocommit
        
    def batch_update_thumbnails(self, thumbnails: List[Tuple]):
        """Update thumbnails in batch."""
        # Use executemany()
        # Chunk large batches
```

## 9. Data Security

### 9.1 Sensitive Data Handling
```python
class SecurityManager:
    """Manages sensitive data security."""
    
    def sanitize_paths(self, path: str) -> str:
        """Remove sensitive path information."""
        
    def anonymize_metadata(self, exif: Dict) -> Dict:
        """Remove personal information from EXIF."""
        
    def secure_delete(self, file_path: Path):
        """Securely delete file with overwrite."""
```

### 9.2 Access Control
```python
class AccessControl:
    """Controls data access permissions."""
    
    def check_read_permission(self, path: Path) -> bool:
        """Check if path is readable."""
        
    def check_write_permission(self, path: Path) -> bool:
        """Check if path is writable."""
        
    def validate_path_safety(self, path: Path) -> bool:
        """Ensure path doesn't escape sandbox."""
## 10. Settings Profiles v1 (Option A)

Note
- Updated for Settings Profiles v1 (Option A).
- Canonical decision: see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md) §18.
- UI mapping and progressive enablement: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md).
- API contracts (create/update/get/validate/run): [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md).
- Technical architecture (central validator, normalization utilities): [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md).
- Errors and UX handling: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md).

### 10.0 Balanced Defaults — v1 (Option A)

This section defines the authoritative Balanced defaults pack adopted for Settings Profiles v1 (Option A). These defaults are applied by the centralized validator whenever fields are omitted, and are encoded in the JSON Schema via "default" where applicable.

Defaults (authoritative)
- Patterns: glob (gitignore-style). Case handling is OS-aware: case-insensitive on Windows; case-sensitive on POSIX.
- Pattern semantics: patterns are evaluated relative to each pool's root_path; multiline input in the UI maps to a string array.
- Recursion: recurse=true by default.
- max_depth: 0 means unlimited recursion (default 0). Positive integers limit traversal depth; 1 = only direct children; 0 = no limit.
- follow_symlinks: false by default.
- include_hidden: false by default; hidden items are excluded unless explicitly included.
- File types: images only by default (extensions): [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]. RAW formats are off by default.
- Extension filter matching is case-insensitive on all OS (Package A).
- Similarity:
  - algorithm default: "pHash" (64-bit grayscale DCT; hash_size=8).
  - degree_ui default: 90 (UI scale 0–100); internal normalized degree in [0.0..1.0] computed as degree_ui/100.
- Duplicates: algorithm fixed to "blake3" in duplicates mode; no degree.
- Two-pool Direction: when scope.kind="two_pool", default direction is "A_TO_B".
- Path validation: pools.A.root_path (and pools.B when two_pool) MUST exist and be readable; Save/Run are blocked by the validator when invalid.

Examples (defaulting demonstration)
A0) Minimal two-pool similarity (omits fields that have defaults)
```json
{
  "id": "11111111-2222-3333-4444-555555555555",
  "name": "A→B similar (defaults)",
  "pools": {
    "A": { "root_path": "D:/Reference" },
    "B": { "root_path": "F:/Target" }
  },
  "mode": "similarity",
  "criteria": {},
  "scope": { "kind": "two_pool" },
  "output": {}
}
```
Validator will normalize to:
- criteria.algorithm="pHash"; criteria.degree_ui=90; criteria.phash.hash_size=8
- pools.*.recurse=true; max_depth=0; include=["**/*"]; exclude=[]; follow_symlinks=false; include_hidden=false; type_filters as listed above
- scope.direction="A_TO_B"
- output.mode="report_only"

Z) Fully explicit Balanced defaults (two-pool similarity)
```json
{
  "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "name": "A→B similar (Balanced explicit)",
  "schema_version": "1.0",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": {
      "root_path": "D:/Reference",
      "recurse": true,
      "max_depth": 0,
      "include": ["**/*"],
      "exclude": [],
      "follow_symlinks": false,
      "include_hidden": false,
      "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
    },
    "B": {
      "root_path": "F:/Target",
      "recurse": true,
      "max_depth": 0,
      "include": ["**/*"],
      "exclude": [],
      "follow_symlinks": false,
      "include_hidden": false,
      "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
    }
  },
  "mode": "similarity",
  "criteria": { "algorithm": "pHash", "degree_ui": 90, "phash": { "hash_size": 8 } },
  "scope": { "kind": "two_pool", "direction": "A_TO_B" },
  "output": { "mode": "report_only" }
}
```

OS-aware case behavior
- Windows: pattern matching ignores case (e.g., "*.JPG" matches ".jpg").
- POSIX (Linux/macOS default filesystems): pattern matching is case-sensitive.
- Mixed-case filesystems should follow the detected OS default unless overridden by a future profile option.

Note
- Updated for Settings Profiles v1 (Option A) — Balanced Defaults.
- The JSON Schema below encodes these defaults using "default" where applicable.

### 10.SA Set A initial-state defaults overlay (Option A)

Authoritative initial UI defaults (encode verbatim)
- Initial mode = "duplicates"
- Pool A inputs enabled (empty by default)
- Pool B inputs enabled from the start; Direction radios remain disabled until both Pool A and Pool B validate
- Single-pool clustering default = unchecked
- Save/Run disabled until Pool A path is valid and profile passes validation
- When both pools validate and scope.kind="two_pool", Direction radios enable with A_TO_B preselected

Validator interaction (cross-reference)
- Pool B may be absent or invalid initially; this does not block single-pool runs when applicable (e.g., duplicates within Pool A)
- Direction defaults are inert until both pools validate; see GUI gating in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1) and capability flags in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1)

### 10.1 Entity model (typed) — SettingsProfile (Option A)

Required identity fields
- id: string (UUID, format uuid)
- name: string (unique, pattern ^[A-Za-z0-9 _-]{1,64}$)
- description: string (optional)
- profile_version: string (default "1.0.0")
- created_at: string (ISO8601 Z)
- updated_at: string (ISO8601 Z)

Pools (A/B)
- Two logical pools; Pool A always required; Pool B required only for two-pool scope.
- Pool fields (per pool):
  - root_path: string (absolute path to directory or file collection root)
  - include: string[] (glob patterns; default ["**/*"]; relative to root_path)
  - exclude: string[] (glob patterns; default [])
  - recurse: boolean (default true)
  - max_depth: integer (0 = unlimited recursion [default]; 1 = only direct children; N ≥ 1 = depth limit)
  - follow_symlinks: boolean (default false)
  - include_hidden: boolean (default false; hidden items excluded when false)
  - type_filters: string[] (file extensions/media types; default ["jpg", "jpeg", "png", "webp", "tiff", "bmp", "gif", "heic", "heif"])
  - size_constraints: { min_bytes?: int>=0, max_bytes?: int>=0 }
  - date_constraints: { min_date?: ISO8601, max_date?: ISO8601 }

Mode and criteria
- mode: "duplicates" | "similarity"
- duplicates criteria (fixed):
  - algorithm: "blake3" (fixed)
  - degree_ui: not allowed (MUST be absent)
- similarity criteria:
  - algorithm: "pHash" (fixed in v1)
  - degree_ui: integer in [0..100] (UI); normalized internal value degree = degree_ui/100
  - phash parameters (optional): { hash_size: int in [4..64], default 8 }

Scope/direction
- scope.kind: "single_pool" | "two_pool"
- When "single_pool": clustering within Pool A (group similar/duplicate items)
- When "two_pool": scope.direction required; one of:
  - "A_TO_B": find items in B that match A (A is reference)
  - "B_TO_A": find items in A that match B (B is reference)
  - "A_WITHOUT_IN_B": items in A with no match in B
  - "B_WITHOUT_IN_A": items in B with no match in A

Output mode
- output.mode: "report_only" (v1 does not perform file actions)

Compatibility note regarding hashing
- For Option A "duplicates" runs, identity matching uses BLAKE3 (fast, low-collision) per [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md) §18. Earlier SHA‑256 guidance continues to apply to general cache identity and other non-Option‑A flows documented elsewhere in this repository.

### 10.2 Normalization rules

UI degree → internal
- degree = degree_ui / 100
- degree_ui in [0..100] maps linearly to internal [0.0..1.0]

pHash distance → degree and similarity (Package A normative)
- Let h = phash.hash_size (default 8), max distance D_max = h × h.
- For 64‑bit pHash (h=8) and Hamming distance d ∈ [0..64]:
  - degree_ui = round(100 * (1 - d/64))
  - A pair matches when degree_ui ≥ threshold_ui
- For generalization and internal computations:
  - normalized_similarity s = 1 − (d / D_max)
  - degree_normalized = threshold_ui / 100

Duplicates (BLAKE3)
- Two files are duplicates iff blake3(file1) == blake3(file2)
- No degree is applicable in duplicates mode; any provided degree MUST be ignored and flagged invalid by the validator

### 10.3 Validation rules (invariants and compatibility)

Core invariants
- name matches pattern and is unique (case-insensitive)
- Pool A must be present and valid for all scopes
- Two-pool scope requires Pool B present and valid
- When scope.kind = "single_pool", scope.direction MUST be omitted
- When scope.kind = "two_pool", scope.direction MUST be present

Mode-specific
- mode = "duplicates":
  - criteria.algorithm MUST be "blake3"
  - criteria MUST NOT include degree_ui
- mode = "similarity":
  - criteria.algorithm MUST be "pHash"
  - criteria.degree_ui MUST be present and within [0..100]

Paths and patterns
- root_path MUST exist and be accessible at validation time (validator checks)
- include/exclude patterns MUST compile (validator checks)
- type_filters members MUST be non-empty strings; recommended to start with "." extensions
- size_constraints: when both provided, min_bytes ≤ max_bytes
- date_constraints: when both provided, min_date ≤ max_date

Numeric bounds and defaults
- max_depth ≥ 0 when provided
- phash.hash_size ∈ [4..64], default 8

Mutual exclusivity
- degree_ui is incompatible with mode "duplicates"
- A_without_in_B and B_without_in_A directions are incompatible with degree_ui absence in similarity mode (degree required for similarity mode regardless of direction)

Validator enablement contract (for GUI)
- Two-pool direction choices enabled only when both pools validate
- Run/Save buttons disabled until the central validator returns is_valid = true
- See GUI states in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)

### 10.4 JSON Schema (complete) — SettingsProfile (Option A)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pk.dev/schemas/settings-profile-option-a-v1.json",
  "title": "SettingsProfileOptionA",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "name": { "type": "string", "pattern": "^[A-Za-z0-9 _-]{1,64}$" },
    "description": { "type": "string" },
    "profile_version": { "type": "string", "default": "1.0.0" },
    "created_at": { "type": "string", "format": "date-time" },
    "updated_at": { "type": "string", "format": "date-time" },
    "schema_version": { "type": "string", "default": "1.0" },

    "pools": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "A": { "$ref": "#/$defs/pool" },
        "B": { "$ref": "#/$defs/pool" }
      },
      "required": ["A"]
    },

    "mode": { "type": "string", "enum": ["duplicates", "similarity"], "default": "duplicates" },

    "criteria": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "algorithm": { "type": "string", "enum": ["blake3", "pHash"], "default": "pHash" },
        "degree_ui": { "type": "integer", "minimum": 0, "maximum": 100, "default": 90 },
        "phash": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "hash_size": { "type": "integer", "minimum": 4, "maximum": 64, "default": 8 }
          }
        }
      }
    },

    "scope": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "kind": { "type": "string", "enum": ["single_pool", "two_pool"], "default": "two_pool" },
        "direction": {
          "type": "string",
          "enum": ["A_TO_B", "B_TO_A", "A_WITHOUT_IN_B", "B_WITHOUT_IN_A"],
          "default": "A_TO_B",
          "description": "Default A_TO_B; UI enables direction choice only when both pools validate (Package A)."
        },
        "single_pool_clustering": {
          "type": "boolean",
          "default": false,
          "description": "Applies only when scope.kind='single_pool'; ignored/disallowed for two_pool. Default false."
        }
      },
      "required": ["kind"]
    },

    "output": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "mode": { "type": "string", "enum": ["report_only"], "default": "report_only" }
      },
      "required": ["mode"]
    }
  },

  "required": ["id", "name", "created_at", "updated_at", "pools", "mode", "criteria", "scope", "output"],

  "$defs": {
    "pool": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "root_path": { "type": "string", "minLength": 1 },
        "recurse": { "type": "boolean", "default": true },
        "max_depth": { "type": "integer", "minimum": 0, "default": 0 },
        "include": {
          "type": "array",
          "items": { "type": "string" },
          "default": ["**/*"]
        },
        "exclude": {
          "type": "array",
          "items": { "type": "string" },
          "default": []
        },
        "follow_symlinks": { "type": "boolean", "default": false },
        "include_hidden": { "type": "boolean", "default": false },
        "type_filters": {
          "type": "array",
          "items": { "type": "string" },
          "default": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
        },
        "size_constraints": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "min_bytes": { "type": "integer", "minimum": 0 },
            "max_bytes": { "type": "integer", "minimum": 0 }
          }
        },
        "date_constraints": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "min_date": { "type": "string", "format": "date-time" },
            "max_date": { "type": "string", "format": "date-time" }
          }
        }
      },
      "required": ["root_path"]
    }
  },

  "allOf": [
    {
      "if": { "properties": { "mode": { "const": "duplicates" } } },
      "then": {
        "properties": {
          "criteria": {
            "properties": {
              "algorithm": { "const": "blake3", "default": "blake3" }
            }
          }
        },
        "not": { "properties": { "criteria": { "required": ["degree_ui"] } } }
      }
    },
    {
      "if": { "properties": { "mode": { "const": "similarity" } } },
      "then": {
        "properties": {
          "criteria": {
            "required": ["algorithm", "degree_ui"],
            "properties": { "algorithm": { "default": "pHash" } }
          }
        }
      }
    },
    {
      "if": { "properties": { "scope": { "properties": { "kind": { "const": "two_pool" } } } } },
      "then": {
        "properties": {
          "pools": { "required": ["A", "B"] },
          "scope": {
            "required": ["kind", "direction"],
            "not": { "required": ["single_pool_clustering"] }
          }
        }
      },
      "else": {
        "properties": {
          "scope": { "not": { "required": ["direction"] } }
        }
      }
    }
  ]
}
```

Notes
- Path existence, pattern compilability, and cross-field constraints (min ≤ max) are enforced by the centralized validator at runtime; JSON Schema documents the shape and simple invariants.

### 10.5 Example profiles (JSON)

M1) Minimal single-pool duplicates (omit defaults; rely on default filling)
```json
{
  "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "name": "A only — duplicates",
  "pools": { "A": { "root_path": "C:/Photos" } },
  "mode": "duplicates",
  "criteria": { "algorithm": "blake3" },
  "scope": { "kind": "single_pool" },
  "output": { "mode": "report_only" }
}
```

M2) Minimal single-pool similarity (omit defaults; include only fields that differ)
```json
{
  "id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
  "name": "A only — similar (90%)",
  "pools": { "A": { "root_path": "C:/Photos" } },
  "mode": "similarity",
  "criteria": { "degree_ui": 90 },
  "scope": { "kind": "single_pool" },
  "output": { "mode": "report_only" }
}
```

A) Single-pool duplicates (cluster within A)
```json
{
  "id": "2a0b3c1e-3b0c-4b42-8f5e-1c2d3e4f5a6b",
  "name": "A - Exact duplicates",
  "description": "Identify byte-identical files within Pool A using BLAKE3.",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": {
      "root_path": "C:/Photos",
      "recurse": true,
      "max_depth": 0,
      "include": ["**/*.jpg", "**/*.png"],
      "exclude": ["**/tmp/**"],
      "type_filters": [".jpg", ".jpeg", ".png"]
    }
  },
  "mode": "duplicates",
  "criteria": { "algorithm": "blake3" },
  "scope": { "kind": "single_pool" },
  "output": { "mode": "report_only" }
}
```

B) Single-pool similarity (cluster within A)
```json
{
  "id": "3bedb1d1-9c63-4a7a-9e1b-12f75b5c7b0e",
  "name": "A - Similar (pHash 85%)",
  "description": "Group similar images within Pool A at ~85% threshold.",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": {
      "root_path": "D:/Archive",
      "recurse": true,
      "include": ["**/*.jpg", "**/*.jpeg", "**/*.png"]
    }
  },
  "mode": "similarity",
  "criteria": { "algorithm": "pHash", "degree_ui": 85, "phash": { "hash_size": 8 } },
  "scope": { "kind": "single_pool" },
  "output": { "mode": "report_only" }
}
```

C) Two-pool duplicates (A→B)
```json
{
  "id": "4c5d6e7f-1234-4abc-9876-abcdefabcdef",
  "name": "A→B exact duplicates",
  "description": "Find files in B that are duplicates of files in A.",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": { "root_path": "C:/Masters", "recurse": true, "include": ["**/*"] },
    "B": { "root_path": "E:/WorkingSet", "recurse": true, "include": ["**/*"] }
  },
  "mode": "duplicates",
  "criteria": { "algorithm": "blake3" },
  "scope": { "kind": "two_pool", "direction": "A_TO_B" },
  "output": { "mode": "report_only" }
}
```

D) Two-pool similarity (A→B) and “A without matches in B”
```json
{
  "id": "9b0d3f12-0d0a-4a3b-8e0f-4c1d2e3f4a5b",
  "name": "A→B similar (90%) and A uniques",
  "description": "Compare A against B at 90%; also support A items with no matches in B.",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": { "root_path": "D:/Reference", "recurse": true, "include": ["**/*.jpg"] },
    "B": { "root_path": "F:/Target", "recurse": true, "include": ["**/*.jpg"] }
  },
  "mode": "similarity",
  "criteria": { "algorithm": "pHash", "degree_ui": 90 },
  "scope": { "kind": "two_pool", "direction": "A_TO_B" },
  "output": { "mode": "report_only" }
}
```

To produce “A without matches in B”, change only:
```json
"scope": { "kind": "two_pool", "direction": "A_WITHOUT_IN_B" }
```

### 10.6 Terminology (glossary)

- Pool A: Primary/reference pool; always required. In two-pool A→B, A is the reference set.
- Pool B: Secondary/target pool; required only for two-pool scope.
- Mode: Either "duplicates" (exact identity) or "similarity" (perceptual).
- Criteria: Algorithm and parameters governing matches; fixed to blake3 for duplicates and pHash for similarity in v1.
- Degree (UI): User-entered 0–100 threshold for similarity; normalized internally to [0.0..1.0].
- Direction: Two-pool query vector (A→B, B→A) and negative matches ("without").
- Output: Report-only in v1 (no mutations).

### 10.7 Validation matrix (concise)

- One pool × duplicates:
  - Valid: Pool A present; mode=duplicates; criteria.algorithm=blake3; degree absent; scope=single_pool
- One pool × similarity:
  - Valid: Pool A present; mode=similarity; criteria.algorithm=pHash; degree_ui ∈ [0..100]; scope=single_pool
- Two pools × duplicates:
  - Valid: Pools A and B present; mode=duplicates; criteria.algorithm=blake3; degree absent; scope.two_pool with direction set
- Two pools × similarity:
  - Valid: Pools A and B present; mode=similarity; criteria.algorithm=pHash; degree_ui ∈ [0..100]; scope.two_pool with direction set
- Invalid (examples):
  - degree_ui present when mode=duplicates
  - scope.two_pool without Pool B
  - Missing or out-of-range degree_ui when mode=similarity
  - Unrecognized patterns (compile failures), nonexistent paths, inverted min/max bounds

Cross-references
- Progressive UI enablement and resolved preview layout: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- Validator shape and normalized view in API responses: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Central validator responsibilities and location: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
E) Two-pool similarity (A without matches in B)
```json
{
  "id": "c7d0a4b2-6f38-4e6f-9c3a-90a1b2c3d4e5",
  "name": "A uniques vs B (90%)",
  "description": "List items in A that have no similar matches in B at 90% threshold.",
  "profile_version": "1.0.0",
  "created_at": "2025-08-19T00:00:00Z",
  "updated_at": "2025-08-19T00:00:00Z",
  "pools": {
    "A": { "root_path": "D:/Reference", "recurse": true, "include": ["**/*.jpg", "**/*.png"] },
    "B": { "root_path": "F:/Target", "recurse": true, "include": ["**/*.jpg", "**/*.png"] }
  },
  "mode": "similarity",
  "criteria": { "algorithm": "pHash", "degree_ui": 90, "phash": { "hash_size": 8 } },
  "scope": { "kind": "two_pool", "direction": "A_WITHOUT_IN_B" },
  "output": { "mode": "report_only" }
}
```