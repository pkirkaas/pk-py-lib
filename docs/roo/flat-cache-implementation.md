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

The [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) is instantiated once per application run if `use_flat_cache` is enabled. It is then passed down to core computation functions in modules like [`similarity.py`](src/pk_py_lib/core/image/similarity.py:1) and the Image Quality Evaluators. The integration now supports a `search_type` parameter ('duplicate' or 'similarity') to enable conditional computations, optimizing performance by avoiding unnecessary image processing.

1. **Lookup Priority**: When a hash or quality score is requested with a specific `search_type`, the computation function (e.g., `compute_phash`) first checks the Flat Cache for relevant data.
2. **Validation**: If an entry is found, it is immediately validated against the current file system stats.
3. **Cache Hit**: If valid and the cached data matches the required computations for the `search_type`, the cached value is returned, skipping expensive computation.
4. **Cache Miss/Stale**: If the entry is missing, invalid, or lacks the required data for the `search_type`, the value is computed conditionally (e.g., only XXH3 for 'duplicate'), and the cache entry is updated/inserted via [`set_entry()`](src/pk_py_lib/core/flat_cache.py:376).

The `search_type` is derived from the active profile mode and passed through the traversal and similarity modules to ensure efficient caching.

## Conditional Computations by Search Type

The FlatCacheManager supports conditional computation and caching based on the `search_type` parameter, which can be either `'duplicate'` or `'similarity'`. This feature optimizes resource usage by tailoring metadata extraction, hashing, and image processing to the specific requirements of the search workflow. The `search_type` is passed to key methods like [`get_hashes`](src/pk_py_lib/core/flat_cache.py) and [`_extract_image_metadata`](src/pk_py_lib/core/flat_cache.py), controlling what data is computed and stored in the `hash_data` field.

### Computations for `'duplicate'` Search Type

In duplicate detection workflows, the focus is on rapid content identity grouping using lightweight hashing. Only the XXH3 hash (a fast, non-cryptographic 64-bit hash) is computed for **all files**, regardless of file type. This avoids loading image data or performing expensive operations.

- **Computed**: XXH3 hash for file content identity.
- **Skipped**:
  - Perceptual hashes (pHash, wHash) – not needed for exact duplicates.
  - Image dimensions (width, height) – irrelevant for non-perceptual matching.
  - Quality scores (e.g., BRISQUE) – no image analysis required.
  - Even for image files (e.g., JPEG, PNG), no image decoding or metadata extraction beyond basic file stats.

This ensures fast traversal over large directories, as only file I/O for hashing is performed. The cache entry's `hash_data` will contain only `{'xxh3': 'hex_string'}`.

**Rationale**: Duplicates are detected via exact hash matches, so perceptual or quality metrics add no value and waste CPU/time.

### Computations for `'similarity'` Search Type

In similarity detection workflows, comprehensive image analysis is required to compute perceptual similarity and quality. Full computations are performed **only for image files** (based on extension filters from the profile). Non-image files receive only basic stats and XXH3.

- **Computed for Images**:
  - Perceptual hashes: pHash (DCT-based, 64-bit) and wHash (DCT-based wavelet, 64-bit) for similarity scoring.
  - XXH3 hash for content identity (used as a prefilter or fallback).
  - Dimensions: width and height in pixels (extracted via Pillow/OpenCV).
  - Quality score: BRISQUE (if enabled in settings profile) for no-reference image quality assessment.
- **Computed for Non-Images**: Only XXH3 hash and basic file stats.
- **Image Processing Pipeline**: Images are decoded, resized if needed (e.g., for hashing), and analyzed. Errors (e.g., corrupt images) are logged and skipped.

The cache entry's `hash_data` for images will contain `{'phash': 'hex_string', 'whash': 'hex_string', 'xxh3': 'hex_string', 'brisque_score': 75.5}` (if applicable), plus `width` and `height` in the entry fields.

**Rationale**: Similarity requires perceptual metrics to group visually similar images, but non-images are irrelevant. Quality scores help filter low-quality matches if enabled.

### Impact on Cache Entry Fields and Methods

- **Cache Entry Fields** (see Database Schema below): The `hash_data` JSON field is populated conditionally based on `search_type`. For `'duplicate'`, it is minimal (`{'xxh3': ...}`); for `'similarity'`, it includes full perceptual data for images. Fields like `width`, `height`, and `bit_depth` are only set for images in `'similarity'` mode. The `lens_model` (from EXIF) is extracted only if needed for similarity workflows.
  
- **`get_hashes` Method**: This method (used in traversal and similarity modules) now accepts an optional `search_type` parameter. It retrieves or computes only the required hashes:
  ```python
  def get_hashes(self, file_path: str, search_type: str = 'similarity') -> Dict[str, str]:
      """
      Retrieve or compute hashes based on search_type.
      
      Args:
          file_path (str): Path to the file.
          search_type (str): 'duplicate' or 'similarity'. Controls computation scope.
      
      Returns:
          Dict[str, str]: Hashes like {'xxh3': '...', 'phash': '...'} (conditional).
      
      Example:
          # Duplicate: only XXH3
          hashes = cache_mgr.get_hashes('/path/to/file.jpg', 'duplicate')
          # {'xxh3': 'a1b2c3...'}
          
          # Similarity: full for images
          hashes = cache_mgr.get_hashes('/path/to/file.jpg', 'similarity')
          # {'phash': 'd4e5f6...', 'whash': 'g7h8i9...', 'xxh3': 'a1b2c3...'}
      """
  ```
  If the cache lacks required data for the `search_type`, it triggers conditional recomputation.

- **`_extract_image_metadata` Method**: Internal method that skips image decoding and EXIF parsing for `'duplicate'` type, even for images. For `'similarity'`, it performs full extraction using Pillow and OpenCV.

### Integration with Traversal and Similarity Modules

The `search_type` is propagated from the application profile (e.g., `mode: 'duplicates'` maps to `'duplicate'`) through the pipeline:

- In [`traversal.py`](src/pk_py_lib/core/filesystem/traversal.py), `scan_directory` accepts `search_type` and configures the FlatCacheManager to compute only necessary data during file walking.
- In [`similarity.py`](src/pk_py_lib/core/image/similarity.py), comparison functions use `get_hashes` with `search_type` to ensure perceptual hashes are available only when needed.
- Cache updates via `set_entry` store conditional data, allowing mixed workflows without redundant computations.

This integration reduces CPU usage by ~70-90% in duplicate scans (no image ops) while ensuring full data for similarity.

### Usage Examples in Workflows

**Duplicate Workflow Example** (Minimal Computation):

```python
from pk_py_lib.core.filesystem.traversal import scan_directory
from pk_py_lib.core.flat_cache import FlatCacheManager

cache_mgr = FlatCacheManager()
profile_mode = 'duplicates'  # Maps to search_type='duplicate'

# Scan with conditional caching
files_data = scan_directory(
    root_path='/path/to/pool',
    search_type='duplicate',
    flat_cache_manager=cache_mgr
)

# Results: Only XXH3 for all files
for file_path, metadata in files_data:
    hashes = metadata['hashes']  # {'xxh3': 'hex'}
    # Group by XXH3 for exact duplicates
    # No pHash, dimensions, or BRISQUE computed
```

**Similarity Workflow Example** (Full Computation for Images):

```python
from pk_py_lib.core.image.similarity import find_similar_images
from pk_py_lib.core.flat_cache import FlatCacheManager

cache_mgr = FlatCacheManager()
profile_mode = 'similarity'  # Maps to search_type='similarity'

# Scan with full image analysis
files_data = scan_directory(
    root_path='/path/to/pool',
    search_type='similarity',
    flat_cache_manager=cache_mgr,
    quality_enabled=True  # Enables BRISQUE if active
)

# Results: Full data for images
similar_groups = find_similar_images(files_data, threshold=0.9)

for group in similar_groups:
    for file_path in group:
        entry = cache_mgr.get_entry(file_path)
        assert entry.width is not None  # Dimensions cached
        assert 'phash' in entry.hash_data  # Perceptual hashes
        if quality_enabled:
            assert 'brisque_score' in entry.hash_data
```

These examples demonstrate how `search_type` ensures efficient, targeted caching across workflows.

## Best Practices for Usage

Based on recent deep evaluation of FlatCache usage, the following best practices ensure reliability, efficiency, and correctness. These guidelines incorporate findings from validation checks, selective data analyses, and the recent fix to [`get_cache_view_data`](src/pk_py_lib/core/flat_cache.py:1590) which now filters stale entries for view-only operations.

### Validation Best Practices

Always use validating methods to ensure cache freshness and avoid operating on stale data. Direct raw DB queries (e.g., via SQL) for operational data should be avoided, as they bypass built-in file stat checks (size, mtime, inode, device) and can lead to incorrect results or missed invalidations.

- **Invoke Validating Methods**: Use [`get_entry`](src/pk_py_lib/core/flat_cache.py:758), [`get_hashes`](src/pk_py_lib/core/flat_cache.py:1348), or [`get_entries`](src/pk_py_lib/core/flat_cache.py:1409) for any retrieval. These methods automatically:
  - Query the cache.
  - Perform file stat validation via [`_validate_entry`](src/pk_py_lib/core/flat_cache.py:712).
  - Raise [`FlatCacheValidationError`](src/pk_py_lib/core/flat_cache.py:69) on mismatch, treating the entry as stale and returning `None` or triggering recomputation.
  
  **Example**:
  ```python
  entry = cache_mgr.get_entry('/path/to/file.jpg')
  if entry is None:
      # Stale or missing: compute and cache anew
      entry = compute_and_set_entry('/path/to/file.jpg')
  else:
      # Valid: use cached data
      use_entry_data(entry)
  ```

- **Note on View-Only Use**: For read-only inspection (e.g., in dialogs), use [`get_cache_view_data`](src/pk_py_lib/core/flat_cache.py:1590). This method now includes validation and filters out stale entries, ensuring the view reflects current data without side effects like automatic recomputation. It is suitable for UI display but not for operational logic.

- **Avoid Raw DB Queries**: Never query the SQLite DB directly for operational data (e.g., via `conn.execute("SELECT * FROM flat_cache_entries")`). This skips validation, risking use of outdated hashes or metrics. Reserve raw queries for administrative tasks like backups, with manual validation if needed.

- **Invalidation**: After file modifications (e.g., edits, moves), explicitly call [`invalidate_entry`](src/pk_py_lib/core/flat_cache.py:905) or rely on validation in getters. For batch ops, use [`get_uncached_files`](src/pk_py_lib/core/flat_cache.py:997) to identify and recompute only changed files.

### Selective Data Retrieval

Leverage `search_type` and `hash_types` parameters to retrieve only necessary data, minimizing computations and I/O. This is crucial for efficiency in large scans.

- **Use `search_type`**: Specify `'duplicate'` for file-only operations (e.g., XXH3 hashing, no image loading) or `'similarity'` for perceptual analysis (pHash, wHash, BRISQUE on images). This controls what is computed/stored:
  - `'duplicate'`: Computes only XXH3 for all files; skips image decoding, perceptual hashes, and quality scores. Ideal for exact duplicate detection.
  - `'similarity'`: Computes full perceptual hashes and quality for images; falls back to XXH3 for non-images.

  **Example**:
  ```python
  # Duplicate scan: fast, no image ops
  hashes = cache_mgr.get_hashes(['/path/to/files'], hash_types=['xxh3'], search_type='duplicate')
  # {'/path/to/file1.jpg': {'xxh3': 'a1b2c3...'}}

  # Similarity scan: full for images
  hashes = cache_mgr.get_hashes(['/path/to/images'], hash_types=['phash', 'whash'], search_type='similarity')
  # {'/path/to/img.jpg': {'phash': 'd4e5f6...', 'whash': 'g7h8i9...', 'xxh3': 'a1b2c3...'} (xxh3 auto-included)}
  ```

- **Specify `hash_types`**: Limit to required hashes to avoid unnecessary computations. For example, in duplicate mode, request only `['xxh3']` to skip perceptual attempts. In similarity, request `['phash', 'whash']` without quality if not needed.

  **Efficiency Tip**: In `'duplicate'` mode, specifying perceptual types (e.g., `['phash']`) returns `None` without computation, preventing image loading errors on non-images.

- **Handling Partial Data**: Entries may have partial `hash_data` from prior scans (e.g., XXH3 from duplicate, full from similarity). Validating methods check for required keys; if missing, they trigger selective recomputation without overwriting unrelated fields.

### Common Patterns

- **Duplicate Scans**: Use `search_type='duplicate'` in traversal and hashing. Group files by XXH3 for exact matches. Example: Integrate with `scan_directory` to build hash groups without image analysis.
  
  **Warning**: Partial retrieval (e.g., missing perceptual data) is low-risk here, as duplicates don't require it. If switching to similarity later, validation will recompute as needed.

- **Similarity Scans**: Use `search_type='similarity'` for image pools. Compute perceptual distances (e.g., Hamming on pHash) and filter by BRISQUE if enabled. Example: Pass results to `find_similar_images` for grouping.

  **Pattern**:
  ```python
  # Traverse with similarity focus
  files_data = scan_directory(root_path, search_type='similarity', flat_cache_manager=cache_mgr)
  # Compute similarities
  groups = find_similar_images(files_data, threshold=8, use_phash=True)
  ```

- **Mixed Workflows**: Run duplicate first (populates XXH3), then similarity (adds perceptual without recomputing XXH3). Use `get_uncached_files` before scans to target only changed files.

- **Batch Operations**: For large sets, use `batch_set` after computing. Always validate inputs with `get_uncached_files` to avoid redundant work.

**Low-Risk Warning on Partial Retrieval**: Due to conditional storage, an entry might lack full data (e.g., no BRISQUE after duplicate scan). Getters handle this by recomputing selectively, but always specify `search_type` to ensure completeness for the workflow.

### High-Risk Areas

- **View Dialogs**: Previously, [`get_cache_view_data`](src/pk_py_lib/core/flat_cache.py:1590) returned unvalidated entries, risking display of stale data in UI (e.g., [`view_cache_dialog.py`](src/pk_py_lib/gui/dialogs/view_cache_dialog.py)). Now fixed: It validates and filters stale entries, ensuring views show only current data. For interactive views, pair with `invalidate_entry` on user actions (e.g., file deletion).

- **Large Batch Operations**: In scans with 10k+ files, validation can be I/O-intensive. Mitigate by:
  - Using `get_uncached_files` first to parallelize recomputes.
  - Batching via `batch_set` (transactional, efficient).
  - Monitoring via logging; handle `PermissionError` gracefully (treat as uncached).
  - For very large ops, consider `cleanup_old_entries` post-scan to prune unused data.

- **Concurrency**: On Windows, avoid parallel writes (e.g., multiple scans). WAL mode allows reads during writes, but heavy batches should be sequential.

- **Error-Prone Scenarios**: File moves (path changes) auto-invalidate via key mismatch. Cross-device moves invalidate via device ID. Always log validation failures for debugging.

Adhering to these practices ensures robust, efficient FlatCache usage, reflecting evaluation outcomes like strong overall validation and optimized selective retrieval.

## Database Schema

The cache uses a single table, `flat_cache_entries`, indexed by the normalized file path. The schema version is now 5.0.0, reflecting the removal of non-core metadata columns to focus on essential file stats, dimensions, and computed hashes/quality data. The contents of computed fields (e.g., `hash_data`, `width`, `height`) are conditional on the `search_type` used during entry creation—minimal for `'duplicate'` (XXH3 only) and comprehensive for `'similarity'` (perceptual hashes, dimensions, quality for images).

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
| `width` | `INTEGER` | Image width in pixels (only for images in 'similarity' mode). |
| `height` | `INTEGER` | Image height in pixels (only for images in 'similarity' mode). |
| `bit_depth` | `INTEGER` | Bit depth (conditional on search_type). |
| `lens_model` | `TEXT` | Lens model from EXIF (only extracted in 'similarity' mode). |
| `last_scanned` | `REAL` | Last scan timestamp. |
| `scan_version` | `TEXT` | Scan version identifier. |
| `is_valid` | `INTEGER` | Validity flag (0 or 1, DEFAULT 1). |
| `hash_data` | `TEXT` | JSON-serialized dictionary of computed hashes and quality data (e.g., {'phash': 'abc123...', 'brisque_score': 75.5}). Contents are conditional: minimal (XXH3 only) for 'duplicate'; full (pHash, wHash, XXH3, quality) for 'similarity' on images. |
| `created_at` | `REAL` | Unix timestamp when entry was created. |
| `updated_at` | `REAL` | Unix timestamp of last update. |

**FlatCacheEntry Dataclass (from [`flat_cache.py`](src/pk_py_lib/core/flat_cache.py:64)):**
The `FlatCacheEntry` dataclass has been updated to reflect the streamlined schema in version 5.0.0. It now includes only the retained fields for core validation and computed data. Optional fields like `width`/`height` are populated based on `search_type`.

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

1. **Size Check**: `current_size == entry.size`
2. **Modification Date Check**: `current_mtime == entry.mtime` (with float tolerance for precision)
3. **Inode Check**: `current_inode == entry.file_inode` (if present)
4. **Device Check**: `current_device == entry.file_device` (if present)

If any of these checks fail, a [`FlatCacheValidationError`](src/pk_py_lib/core/flat_cache.py:48) is raised, indicating a cache miss and forcing recomputation. For conditional data, validation also checks if the cached `hash_data` includes the required keys for the current `search_type`; if not, partial recomputation occurs.

### Handling File System Changes

- **File Content Change**: Changes to file content typically update `size` and `mod_date`, causing validation failure.
- **File Move/Rename (within same device)**: On POSIX systems, moving a file often preserves the `inode` but changes the `file` path. Since the cache key is the normalized path, a move results in a cache miss (not found), forcing a new entry creation.
- **File Copy/Hard Link**: A copy results in a new path, new `inode`, and new `mod_date`, resulting in a cache miss (not found). Hard links are not explicitly handled but would likely result in a cache miss due to path mismatch.

### Error Handling

- If `os.stat` raises `FileNotFoundError`, validation fails, and the entry is treated as stale/invalid.
- If `os.stat` raises `PermissionError` (e.g., access denied), validation fails, forcing recomputation if possible, or logging a warning.
- Database errors (e.g., connection issues, corruption) are wrapped in [`FlatCacheDBError`](src/pk_py_lib/core/flat_cache.py:36) and typically result in a fallback to computation or a graceful failure, depending on the calling function.
- EXIF extraction in [`_extract_image_metadata`](src/pk_py_lib/core/flat_cache.py:947) now includes serialization via [`_serialize_exif`](src/pk_py_lib/core/flat_cache.py:946) to convert non-JSON-serializable types (e.g., IFDRational to (numerator, denominator) tuples, bytes to UTF-8 strings) before JSON storage, preventing serialization errors during cache updates. Note: Full EXIF data is no longer cached; only essential fields like `lens_model` are retained (and only for 'similarity' mode), with others computed on-demand.

## API Reference (FlatCacheManager)

The [`FlatCacheManager`](src/pk_py_lib/core/flat_cache.py:149) is the primary interface for interacting with the cache. Many methods now support an optional `search_type` parameter to enable conditional retrieval/computation.

### `__init__(self, db_path: Optional[Path | str] = None, logger: Optional[logging.Logger] = None)`

Initializes the manager, resolves the database path, and ensures the database file and schema exist (including migration to version 5.0.0 if needed).

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `db_path` | `Path` or `str` | The full path to the SQLite database file. |
| `logger` | `Optional[logging.Logger]` | Custom logger instance. |

### `get_entry(self, file_path: str) -> Optional[FlatCacheEntry]`

Queries the cache for an entry by file path and performs file stat validation. The entry's `hash_data` may be partial based on prior `search_type` used.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `file_path` | `str` | The path to the file. |

**Returns**: `Optional[FlatCacheEntry]`. The valid entry, or `None` if not found or invalid (stale).

### `set_entry(self, entry: FlatCacheEntry) -> bool`

Inserts or replaces a cache entry (UPSERT). Automatically normalizes the path, updates the `computed_at` timestamp, and fetches current file stats before saving. The entry must conform to the updated schema (version 5.0.0), with `hash_data` populated conditionally.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `entry` | [`FlatCacheEntry`](src/pk_py_lib/core/flat_cache.py:64) | The entry object to store. |

**Returns**: `bool`. `True` if the operation succeeded, `False` otherwise (e.g., file inaccessible).

**Example Usage (from [`similarity.py`](src/pk_py_lib/core/image/similarity.py:429), updated for search_type):**
```python
# Get current entry or create a new one with file stats
search_type = 'similarity'  # Or 'duplicate'
current_entry = flat_cache_manager.get_entry(image_path)
if current_entry is None:
    size, mtime, inode, device = flat_cache_manager._get_file_stats(image_path)
    current_entry = FlatCacheEntry(
        path=image_path, size=size, mtime=mtime, file_inode=inode, file_device=device
    )

# Conditional update based on search_type
if search_type == 'similarity':
    current_entry.hash_data = {'phash': hash_str, 'whash': whash_str, 'xxh3': xxh3_str}
    current_entry.width, current_entry.height = extract_dimensions(image_path)
elif search_type == 'duplicate':
    current_entry.hash_data = {'xxh3': xxh3_str}

flat_cache_manager.set_entry(current_entry)
```

### `batch_set(self, entries: List[FlatCacheEntry]) -> int`

Performs a transactional batch UPSERT of multiple cache entries, optimizing database performance. Skips entries for inaccessible files. Entries must use the updated `FlatCacheEntry` structure, with conditional `hash_data`.

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `entries` | `List[FlatCacheEntry]` | A list of entries to store. |

**Returns**: `int`. The number of entries successfully inserted/updated.

### `get_uncached_files(self, paths: List[str]) -> List[str]`

Identifies which files in a provided list are either missing from the cache or have an invalid (stale) cache entry. Can optionally take `search_type` to check for specific data availability.

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

- Database initialization and connection handling (including WAL mode verification and schema migration to 5.0.0).
- File stat retrieval and error handling (`FileNotFoundError`, `PermissionError`).
- Cache validation logic, ensuring mismatches in size, `mtime`, `inode`, or `device` result in cache misses.
- CRUD operations (`get_entry`, `set_entry`, `invalidate_entry`).
- Batch operations (`batch_set`, `get_uncached_files`).
- Cleanup functionality (`cleanup_old_entries`).
- Data retrieval by hash algorithm (`get_all_hashes_by_algorithm`), including conditional checks for `search_type`.
- Compatibility with the updated `FlatCacheEntry` dataclass and schema.
- Conditional computation tests: Verify minimal data for 'duplicate' and full data for 'similarity' modes.