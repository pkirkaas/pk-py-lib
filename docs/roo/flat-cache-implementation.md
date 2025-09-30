# Flat Cache Implementation

## Overview

The Flat Cache subsystem, implemented by the [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) class, provides a unified, persistent, file-based metadata cache for computed file properties such as content hashes (BLAKE3, XXH3) and perceptual hashes (pHash, wHash), as well as image quality scores (BRISQUE, NIQE, PIQE).

This implementation uses a single SQLite database file, leveraging SQLite's robustness and speed for local, single-user applications. It is designed to replace the older, in-memory/time-limited cache system (CacheManager) for persistent data storage.

### Design Rationale (Pros/Cons)

| Feature | Rationale |
| :--- | :--- |
| **Flat SQLite DB** | Simple, zero-configuration persistence. Avoids complex database setup (e.g., PostgreSQL, MySQL). |
| **File Stat Validation** | Ensures cache freshness. Entries are validated against current file size, modification time (`mtime`), inode, and device ID. If any stat changes, the entry is considered stale and recomputed. |
| **WAL Mode** | The database is configured to use Write-Ahead Logging (`PRAGMA journal_mode=WAL`) to improve concurrency, especially on Windows, allowing multiple readers while a writer is active. |
| **Unified Schema** | All computed metadata (hashes, quality scores) for a single file path are stored in one row, simplifying lookups and updates. |
| **Concurrency Warning (Windows)** | While WAL mode helps, SQLite concurrency can still be a bottleneck if multiple processes attempt heavy writes simultaneously. This is mitigated by the application's single-threaded processing model for core tasks. |
| **Schema Evolution** | As of schema version 5.0.0, non-essential metadata columns (e.g., `file_name`, `extension`, `pool`, `format`, `color_mode`, `exif_data`, `camera_make`, `camera_model`, `date_taken`, `gps_latitude`, `gps_longitude`) have been removed to streamline the cache. These fields are now handled on-demand during processing or derived from the filesystem (e.g., `extension` from `Path.suffix`, `pool` from profile paths). This reduces storage overhead and simplifies maintenance while preserving core validation and computed data. Indexes `idx_pool` and `idx_date_taken` have also been removed as they are no longer relevant. |

## Configuration and Integration

The Flat Cache is an optional feature controlled by the application settings profile.

### Settings Toggle

The Flat Cache is now **enabled by default** for all new profiles, providing persistent, file-stat validated storage for computed metadata.

**Schema Definition (from [`settings_schema.py`](src/pk_py_lib/core/settings_schema.py:134)):**
```json
"use_flat_cache": {
    "type": "boolean",
    "default": true,
    "description": "Enable flat SQLite cache for hashes and quality metrics (stored per file path/stats). Enabled by default for improved persistence."
}
```

### Integration Flow

The [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) is instantiated once per application run if `use_flat_cache` is enabled. It is then passed down to core computation functions in modules like [`similarity.py`](src/pk_py_lib/core/image/similarity.py:1) and the Image Quality Evaluators.

1.  **Lookup Priority**: When a hash or quality score is requested, the computation function (e.g., `compute_phash`) first checks the Flat Cache.
2.  **Validation**: If an entry is found, it is immediately validated against the current file system stats.
3.  **Cache Hit**: If valid, the cached value is returned, skipping expensive computation.
4.  **Cache Miss/Stale**: If the entry is missing or fails validation, the value is computed, and the cache entry is updated/inserted via [`set_entry()`](src/pk_py_lib/core/flat_cache.py:376).

## Database Schema

The cache uses a single table, `flat_cache_entries`, indexed by the normalized file path. The schema version is now 5.0.0, reflecting the removal of non-core metadata columns to focus on essential file stats, dimensions, and computed hashes/quality data.

**Table Definition (from [`flat_cache.py`](src/pk_py_lib/core/flat_cache.py:212)):**
```sql
CREATE TABLE IF NOT EXISTS flat_cache_entries (
    path TEXT PRIMARY KEY NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    mtime_ns TEXT,
    file_inode TEXT,
    file_device TEXT,
    width INTEGER,
    height INTEGER,
    bit_depth INTEGER,
    lens_model TEXT,
    last_scanned REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    scan_version TEXT,
    is_valid INTEGER NOT NULL DEFAULT 1 CHECK (is_valid IN (0, 1)),
    hash_data TEXT,
    created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    updated_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
);

-- Indexes for performance and queries
CREATE INDEX IF NOT EXISTS idx_size ON flat_cache_entries (size);
CREATE INDEX IF NOT EXISTS idx_last_scanned ON flat_cache_entries (last_scanned);
CREATE INDEX IF NOT EXISTS idx_updated_at ON flat_cache_entries (updated_at);
CREATE INDEX IF NOT EXISTS idx_is_valid ON flat_cache_entries (is_valid);
```

| Column | Type | Description |
| :--- | :--- | :--- |
| `path` | `TEXT` | Normalized, absolute POSIX path of the file (Primary Key). |
| `size` | `INTEGER` | File size in bytes (for validation). |
| `mtime` | `REAL` | Modification time (mtime) as Unix timestamp float (for validation). |
| `mtime_ns` | `TEXT` | Modification time in nanoseconds (stored as string to handle large values). |
| `file_inode` | `TEXT` | File inode number (stored as string to handle large values, for identity validation). |
| `file_device` | `TEXT` | File device ID (stored as string to handle large values, for identity validation). |
| `width` | `INTEGER` | Image width in pixels. |
| `height` | `INTEGER` | Image height in pixels. |
| `bit_depth` | `INTEGER` | Bit depth. |
| `lens_model` | `TEXT` | Lens model. |
| `last_scanned` | `REAL` | Last scan timestamp. |
| `scan_version` | `TEXT` | Scan version identifier. |
| `is_valid` | `INTEGER` | Validity flag (0 or 1, DEFAULT 1). |
| `hash_data` | `TEXT` | JSON-serialized dictionary of computed hashes and quality data (e.g., {'phash': 'abc123...', 'brisque_score': 75.5}). |
| `created_at` | `REAL` | Unix timestamp when entry was created. |
| `updated_at` | `REAL` | Unix timestamp of last update. |

**FlatCacheEntry Dataclass (from [`flat_cache.py`](src/pk_py_lib/core/flat_cache.py:64)):**

The `FlatCacheEntry` dataclass has been updated to reflect the streamlined schema in version 5.0.0. It now includes only the retained fields for core validation and computed data:

```python
@dataclass
class FlatCacheEntry:
    path: str
    size: int
    mtime: float
    mtime_ns: Optional[str] = None
    file_inode: Optional[str] = None
    file_device: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bit_depth: Optional[int] = None
    lens_model: Optional[str] = None
    last_scanned: float = field(default_factory=lambda: time.time())
    scan_version: Optional[str] = None
    is_valid: bool = True
    hash_data: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
```

Removed fields (e.g., `file_name`, `extension`, `pool`) are no longer stored in the cache and are derived dynamically when needed (e.g., via `Path` object properties or profile configurations).

## Validation Criteria and Edge Cases

Cache validation is critical to ensure that cached data corresponds to the current state of the file on disk.

The [`_validate_entry`](src/pk_py_lib/core/flat_cache.py:527) method performs four checks against the current file system statistics (`os.stat`):

1.  **Size Check**: `current_size == entry.size`
2.  **Modification Date Check**: `current_mtime == entry.mtime` (with float tolerance for precision)
3.  **Inode Check**: `current_inode == entry.file_inode` (if present)
4.  **Device Check**: `current_device == entry.file_device` (if present)

If any of these checks fail, a [`FlatCacheValidationError`](src/pk_py_lib/core/flat_cache.py:48) is raised, indicating a cache miss and forcing recomputation.

### Handling File System Changes

-   **File Content Change**: Changes to file content typically update `size` and `mod_date`, causing validation failure.
-   **File Move/Rename (within same device)**: On POSIX systems, moving a file often preserves the `inode` but changes the `file` path. Since the cache key is the normalized path, a move results in a cache miss (not found), forcing a new entry creation.
-   **File Copy/Hard Link**: A copy results in a new path, new `inode`, and new `mod_date`, resulting in a cache miss (not found). Hard links are not explicitly handled but would likely result in a cache miss due to path mismatch.

### Error Handling

-   If `os.stat` raises `FileNotFoundError`, validation fails, and the entry is treated as stale/invalid.
-   If `os.stat` raises `PermissionError` (e.g., access denied), validation fails, forcing recomputation if possible, or logging a warning.
-   Database errors (e.g., connection issues, corruption) are wrapped in [`FlatCacheDBError`](src/pk_py_lib/core/flat_cache.py:36) and typically result in a fallback to computation or a graceful failure, depending on the calling function.
-   EXIF extraction in [`_extract_image_metadata`](src/pk_py_lib/core/flat_cache.py:947) now includes serialization via [`_serialize_exif`](src/pk_py_lib/core/flat_cache.py:946) to convert non-JSON-serializable types (e.g., IFDRational to (numerator, denominator) tuples, bytes to UTF-8 strings) before JSON storage, preventing serialization errors during cache updates. Note: Full EXIF data is no longer cached; only essential fields like `lens_model` are retained, with others computed on-demand.

## API Reference (FlatCacheManager)

The [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) is the primary interface for interacting with the cache.

### `__init__(self, db_path: Optional[Path | str] = None, logger: Optional[logging.Logger] = None)`

Initializes the manager, resolves the database path, and ensures the database file and schema exist (including migration to version 5.0.0 if needed).

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `db_path` | `Path` or `str` | The full path to the SQLite database file. |
| `logger` | `Optional[logging.Logger]` | Custom logger instance. |

### `get_entry(self, file_path: str) -> Optional[FlatCacheEntry]`

Queries the cache for an entry by file path and performs file stat validation.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `file_path` | `str` | The path to the file. |

**Returns**: `Optional[FlatCacheEntry]`. The valid entry, or `None` if not found or invalid (stale).

### `set_entry(self, entry: FlatCacheEntry) -> bool`

Inserts or replaces a cache entry (UPSERT). Automatically normalizes the path, updates the `computed_at` timestamp, and fetches current file stats before saving. The entry must conform to the updated schema (version 5.0.0).

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `entry` | [`FlatCacheEntry`](src/pk_py_lib/core/flat_cache.py:64) | The entry object to store. |

**Returns**: `bool`. `True` if the operation succeeded, `False` otherwise (e.g., file inaccessible).

**Example Usage (from [`similarity.py`](src/pk_py_lib/core/image/similarity.py:429)):**
```python
# Get current entry or create a new one with file stats
current_entry = flat_cache_manager.get_entry(image_path)
if current_entry is None:
    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
    current_entry = FlatCacheEntry(
        path=image_path, size=size, mtime=mtime, file_inode=inode, file_device=device
    )

current_entry.hash_data = {'phash': hash_str}
flat_cache_manager.set_entry(current_entry)
```

### `batch_set(self, entries: List[FlatCacheEntry]) -> int`

Performs a transactional batch UPSERT of multiple cache entries, optimizing database performance. Skips entries for inaccessible files. Entries must use the updated `FlatCacheEntry` structure.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `entries` | `List[FlatCacheEntry]` | A list of entries to store. |

**Returns**: `int`. The number of entries successfully inserted/updated.

### `get_uncached_files(self, paths: List[str]) -> List[str]`

Identifies which files in a provided list are either missing from the cache or have an invalid (stale) cache entry.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `paths` | `List[str]` | A list of file paths to check. |

**Returns**: `List[str]`. A list of normalized file paths that require recomputation.

### `cleanup_old_entries(self, days: int = 30) -> int`

Deletes cache entries older than the specified number of days based on the `updated_at` timestamp.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `days` | `int` | The age threshold in days. Defaults to 30 days. |

**Returns**: `int`. The number of entries deleted.

## Testing

The Flat Cache implementation is covered by [`tests/test_flat_cache.py`](tests/test_flat_cache.py:1), which includes comprehensive unit tests for:

-   Database initialization and connection handling (including WAL mode verification and schema migration to 5.0.0).
-   File stat retrieval and error handling (`FileNotFoundError`, `PermissionError`).
-   Cache validation logic, ensuring mismatches in size, `mtime`, `inode`, or `device` result in cache misses.
-   CRUD operations (`get_entry`, `set_entry`, `invalidate_entry`).
-   Batch operations (`batch_set`, `get_uncached_files`).
-   Cleanup functionality (`cleanup_old_entries`).
-   Data retrieval by hash algorithm (`get_all_hashes_by_algorithm`).
-   Compatibility with the updated `FlatCacheEntry` dataclass and schema.