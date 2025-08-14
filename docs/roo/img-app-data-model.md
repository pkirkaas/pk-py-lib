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

### 2.5 User Profile Model
```python
@dataclass
class UserProfile:
    """User profile configuration."""
    
    # Identification
    id: int                         # Profile ID
    name: str                       # Profile name
    is_default: bool                # Default profile flag
    
    # Preferences
    theme: str                      # 'light', 'dark', 'auto'
    language: str                   # Language code
    ui_scale: float                 # UI scaling factor
    
    # Algorithm Defaults
    default_algorithms: List[str]   # Default algorithm selection
    default_threshold: float        # Default similarity threshold
    algorithm_presets: Dict[str, Dict]  # Named algorithm configs
    
    # Performance Settings
    max_threads: int                # Thread pool size
    max_memory_mb: int              # Memory limit
    cache_size_gb: float            # Cache size limit
    
    # File Handling
    included_extensions: List[str]  # File extensions to include
    excluded_patterns: List[str]    # Path patterns to exclude
    follow_symlinks: bool           # Follow symbolic links
    
    # UI Preferences
    window_geometry: Dict           # Window size/position
    panel_layout: Dict              # Panel configuration
    shortcuts: Dict[str, str]       # Custom keyboard shortcuts
    
    # History
    recent_paths: List[Path]        # Recently used paths
    recent_sessions: List[int]      # Recent session IDs
    
    # Timestamps
    created_at: datetime            # Profile creation
    modified_at: datetime           # Last modification
```

## 3. Database Schemas

### 3.1 Settings Database (settings.db)

```sql
-- Profiles table
CREATE TABLE profiles (
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

-- Meta table for schema versioning and global metadata [ID: DB-001]
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Example initial schema version entry
INSERT OR REPLACE INTO meta (key, value, notes) VALUES ('schema_version', '1.0.0', 'Initial schema');
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
-- Image metadata cache
CREATE TABLE image_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    file_created TIMESTAMP,
    file_hash TEXT,
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
CREATE INDEX idx_metadata_hash ON image_metadata(file_hash);
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
    
    migrations = {
        "0.9.0": "migration_090_to_100.sql",
        "1.0.0": "migration_100_to_110.sql",
    }
    
    def get_current_version(self, db: Database) -> str:
        """Get current schema version."""
        
    def migrate(self, db: Database, target_version: str):
        """Migrate database to target version."""
        
    def backup_before_migration(self, db: Database):
        """Create backup before migration."""
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
    
    # Size limits
    MAX_CACHE_SIZE_GB = 5.0
    MAX_THUMBNAIL_AGE_DAYS = 90
    MAX_RESULT_AGE_DAYS = 30
    
    # Eviction strategies
    EVICTION_STRATEGY = "LRU"  # LRU, LFU, FIFO
    EVICTION_BATCH_SIZE = 100
    
    # Cleanup triggers
    CLEANUP_ON_SIZE_PERCENT = 90  # Cleanup at 90% full
    CLEANUP_INTERVAL_HOURS = 24
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