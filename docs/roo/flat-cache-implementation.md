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

The cache uses a single table, `flat_cache_entries`, indexed by the normalized file path.

**Table Definition (from [`flat_cache.py`](src/pk_py_lib/core/flat_cache.py:122)):**

```sql
CREATE TABLE IF NOT EXISTS flat_cache_entries (
    file TEXT PRIMARY KEY NOT NULL,
    size INTEGER NOT NULL,
    mod_date INTEGER NOT NULL,
    file_inode TEXT NOT NULL,
    file_device TEXT NOT NULL,
    blake3_hash TEXT,
    xxh3_hash TEXT,
    phash TEXT,
    whash TEXT,
    color_phash TEXT,
    brisque_score REAL,
    niqe_score REAL,
    piqe_score REAL,
    quality_algorithm TEXT,
    computed_at INTEGER NOT NULL,
    entry_version INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_computed_at ON flat_cache_entries (computed_at);
```

| Column | Type | Description |
| :--- | :--- | :--- |
| `file` | `TEXT` | Normalized, absolute POSIX path of the file (Primary Key). |
| `size` | `INTEGER` | File size in bytes (for validation). |
| `mod_date` | `INTEGER` | Unix timestamp of last modification time (`mtime`) (for validation). |
| `file_inode` | `TEXT` | File system inode number (for robust identity check). |
| `file_device` | `TEXT` | Device ID (for robust identity check across mounts). |
| `blake3_hash` | `TEXT` | Content hash (e.g., for exact duplicates). |
| `xxh3_hash` | `TEXT` | Content hash (e.g., for exact duplicates). |
| `phash` | `TEXT` | Perceptual hash (DCT-based). |
| `whash` | `TEXT` | Wavelet hash (DWT-based). |
| `color_phash` | `TEXT` | Color-aware perceptual hash. |
| `brisque_score` | `REAL` | BRISQUE image quality score. |
| `niqe_score` | `REAL` | NIQE image quality score. |
| `piqe_score` | `REAL` | PIQE image quality score. |
| `quality_algorithm` | `TEXT` | Name of the algorithm used for the quality score (e.g., 'brisque'). |
| `computed_at` | `INTEGER` | Unix timestamp of when the entry was last updated. |
| `entry_version` | `INTEGER` | Internal schema version of the entry structure. |

## Validation Criteria and Edge Cases

Cache validation is critical to ensure that cached data corresponds to the current state of the file on disk.

The [`_validate_entry`](src/pk_py_lib/core/flat_cache.py:284) method performs four checks against the current file system statistics (`os.stat`):

1.  **Size Check**: `current_size == entry.size`
2.  **Modification Date Check**: `current_mtime == entry.mod_date`
3.  **Inode Check**: `current_inode == entry.file_inode`
4.  **Device Check**: `current_device == entry.file_device`

If any of these checks fail, a [`FlatCacheValidationError`](src/pk_py_lib/core/flat_cache.py:48) is raised, indicating a cache miss and forcing recomputation.

### Handling File System Changes

-   **File Content Change**: Changes to file content typically update `size` and `mod_date`, causing validation failure.
-   **File Move/Rename (within same device)**: On POSIX systems, moving a file often preserves the `inode` but changes the `file` path. Since the cache key is the normalized path, a move results in a cache miss (not found), forcing a new entry creation.
-   **File Copy/Hard Link**: A copy results in a new path, new `inode`, and new `mod_date`, resulting in a cache miss (not found). Hard links are not explicitly handled but would likely result in a cache miss due to path mismatch.

### Error Handling

-   If `os.stat` raises `FileNotFoundError`, validation fails, and the entry is treated as stale/invalid.
-   If `os.stat` raises `PermissionError` (e.g., access denied), validation fails, forcing recomputation if possible, or logging a warning.
-   Database errors (e.g., connection issues, corruption) are wrapped in [`FlatCacheDBError`](src/pk_py_lib/core/flat_cache.py:36) and typically result in a fallback to computation or a graceful failure, depending on the calling function.

## API Reference (FlatCacheManager)

The [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) is the primary interface for interacting with the cache.

### `__init__(self, db_path: Path | str, logger: Optional[logging.Logger] = None)`

Initializes the manager, resolves the database path, and ensures the database file and schema exist.

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

Inserts or replaces a cache entry (UPSERT). Automatically normalizes the path, updates the `computed_at` timestamp, and fetches current file stats before saving.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `entry` | [`FlatCacheEntry`](src/pk_py_lib/core/flat_cache.py:64) | The entry object to store. |

**Returns**: `bool`. `True` if the operation succeeded, `False` otherwise (e.g., file inaccessible).

**Example Usage (from [`similarity.py`](src/pk_py_lib/core/image/similarity.py:327)):**

```python
# Get current entry or create a new one with file stats
current_entry = flat_cache_manager.get_entry(image_path)
if current_entry is None:
    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
    current_entry = FlatCacheEntry(
        file=image_path, size=size, mod_date=mtime, file_inode=inode, file_device=device
    )

current_entry.phash = hash_str
flat_cache_manager.set_entry(current_entry)
```

### `batch_set(self, entries: List[FlatCacheEntry]) -> int`

Performs a transactional batch UPSERT of multiple cache entries, optimizing database performance. Skips entries for inaccessible files.

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

Deletes cache entries older than the specified number of days based on the `computed_at` timestamp.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `days` | `int` | The age threshold in days. Defaults to 30 days. |

**Returns**: `int`. The number of entries deleted.

## Testing

The Flat Cache implementation is covered by [`tests/test_flat_cache.py`](tests/test_flat_cache.py:1), which includes comprehensive unit tests for:

-   Database initialization and connection handling (including WAL mode verification).
-   File stat retrieval and error handling (`FileNotFoundError`, `PermissionError`).
-   Cache validation logic, ensuring mismatches in size, `mtime`, `inode`, or `device` result in cache misses.
-   CRUD operations (`get_entry`, `set_entry`, `invalidate_entry`).
-   Batch operations (`batch_set`, `get_uncached_files`).
-   Cleanup functionality (`cleanup_old_entries`).
-   Data retrieval by hash algorithm (`get_all_hashes_by_algorithm`).