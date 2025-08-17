# KDC Image Organizer - Data Model Specifications

## 1. Overview

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

```sql
-- Settings profiles table
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

-- Thumbnail cache
CREATE TABLE thumbnails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL,
    size INTEGER NOT NULL,
    thumbnail_data BLOB NOT NULL,
    format TEXT DEFAULT 'JPEG',
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
    FOREIGN KEY (image1_id) REFERENCES image_metadata(id),
    FOREIGN KEY (image2_id) REFERENCES image_metadata(id),
    CHECK (overall_score BETWEEN 0.0 AND 1.0)
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