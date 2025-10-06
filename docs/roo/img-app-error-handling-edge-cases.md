# KDC Image Organizer - Error Handling & Edge Cases

## Conventions

- Cache size is configured via app_settings.cache_size_mb (units: MB). Do not use max_size_gb, MAX_CACHE_SIZE_GB, or ambiguous "GB" phrasing.
- Thresholds:
  - UI displays values on a 0–100 scale.
  - Internal logic uses 0.0–1.0.
  - Conversions: internal = ui / 100; ui = round(internal * 100).
- File extension tokens must be dot-prefixed (e.g., .png, .jpg, .jpeg, .tiff, .webp).
> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
> This document now catalogs Option A–specific validation failures, conflicts, edge cases at scale, and UX guidance tied to the centralized validator and progressive enable/disable UI. Cross-references: data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), API [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), decision §18 [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).
## Settings Profiles v1 (Option A) — Error Handling Canonical
Option A + Balanced Defaults + Package A + Set A. Terminology, invariants, and defaults align with the canonical decision in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md) and the contracts in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), and [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md).

1) Philosophy and scope
- v1 prioritizes correctness and rich diagnostics over permissiveness. All validation failures surface structured, machine-readable errors with JSON Pointers.
- Save and Run are gated by centralized validator capability flags; buttons remain disabled until required conditions are satisfied (Set A policy).
- Execution is report-only in v1. Run endpoints never alter files; actions are deferred (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)).
- Consistency: GUI, API, and engine consume the same centralized validator. Defaults and normalization always flow through the validator.

2) Canonical structured error format
- Detail object (per issue) returned by validator and APIs:
```json
{
  "code": "PATH_MISSING",
  "message": "Pool A root_path is required",
  "details": { "pool": "A" },
  "path": "/pools/A/root_path",
  "hint": "Select an existing, readable directory"
}
```
- Where it appears
  - Validation (200 OK): { success:true, data:{ is_valid:false, errors:[…], warnings:[…], normalized:null, capabilities:{…} }, code:null, error:null } (see §13B.2 in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)).
  - Fail-fast errors (e.g., malformed JSON): top-level ApiResponse.fail with code and metadata.details (see “Structured error payload” in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:2101)).
- Fields
  - code: machine-readable string (see taxonomy below)
  - message: concise, human-readable description
  - details: optional map with context (e.g., pool="A", index=2, algorithm="pHash")
  - path: JSON Pointer to offending field in the profile payload
  - hint: optional suggestion to resolve the issue

3) Error taxonomy (detail-level codes and when they occur)
Note: These are validator-level detail codes. API top-level codes (e.g., INVALID_CONFIG, FILE_MISSING, PERMISSION_DENIED) wrap or accompany these details as appropriate (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1172)).

- PATH_MISSING
  - Occurs when a required path field is empty or omitted (e.g., /pools/A/root_path is missing/blank).
  - Example triggers: No Pool A root_path; Pool B required by two_pool scope but omitted.
- PATH_UNREADABLE
  - Occurs when a provided path does not exist or is unreadable (permissions, offline network path, unmounted volume, or Windows path length issues).
  - Mapping: often paired with top-level FILE_MISSING or PERMISSION_DENIED depending on OS error.
- DEGREE_OUT_OF_RANGE
  - Occurs when criteria.degree_ui is provided but not in [0..100] inclusive.
- INVALID_COMBINATION
  - Occurs on incompatible field combinations, including:
    - degree_ui present with mode="duplicates"
    - duplicates algorithm not "blake3"
    - similarity algorithm not "pHash"
    - scope.single_pool but a direction is provided
    - single_pool_clustering used when scope.kind != "single_pool"
- POOL_B_REQUIRED_FOR_DIRECTION
  - Occurs when a direction is requested but Pool B is invalid or missing, or when direction is set while scope.kind="single_pool".
- PATTERN_COMPILE_ERROR
  - Occurs when include/exclude patterns cannot be parsed (invalid glob syntax). details typically include pattern and index.
- SCHEMA_VALIDATION_ERROR
  - Occurs when the payload violates JSON Schema (types, enums, required fields). Often reported for malformed JSON with HTTP 400 in REST variants.
- UNSUPPORTED_FILE_TYPE (warning)
  - Occurs when files outside the default image set are referenced while type_filters constrain to defaults. Hint to add extensions explicitly.
- NORMALIZATION_CONFLICT (warning)
  - Occurs when inputs require normalization adjustments (e.g., degree_ui rounding, coercing negative max_depth to 0). The normalized profile reflects the resolved values.

4) Edge-case catalogue — scenarios, behavior, UX
- Paths
  - Pool A missing/invalid
    - Behavior: Save/Run disabled; inline error and banner show PATH_MISSING or PATH_UNREADABLE for /pools/A/root_path.
    - OS/FS hints: For Windows long paths or network shares, suggest enabling long path support or verifying mount/credentials.
  - Pool B invalid while a direction is selected
    - Behavior: Direction controls are gated off by capabilities; attempting to run returns POOL_B_REQUIRED_FOR_DIRECTION detail and top-level INVALID_CONFIG in run APIs.
  - Network/unmounted drives, offline shares, permission denied
    - Behavior: PATH_UNREADABLE; top-level may be FILE_MISSING or PERMISSION_DENIED with OS-specific hint text.
- Patterns and filters
  - Invalid glob pattern
    - Behavior: PATTERN_COMPILE_ERROR with offending pattern and index (e.g., /pools/A/include/2).
  - Empty include with exclude=[]
    - Behavior: Balanced defaults applied (include=["**/*"]); info note in warnings as applicable.
  - Hidden handling
    - Default include_hidden=false; hidden files are excluded even if matched by patterns. Toggle include_hidden to include them explicitly.
  - Symlinks
    - Default follow_symlinks=false; avoids traversal loops. Broken links are skipped without errors.
  - File type mismatches and RAW formats
    - Defaults restrict to common image types; RAW is off by default. Provide a hint to add specific RAW extensions into type_filters.
- Mode/criteria
  - Duplicates with degree provided
    - Behavior: INVALID_COMBINATION at /criteria/degree_ui.
  - Similarity with algorithm != "pHash"
    - Behavior: INVALID_COMBINATION at /criteria/algorithm.
  - Degree out of range
    - Behavior: DEGREE_OUT_OF_RANGE at /criteria/degree_ui.
  - Direction requested in single-pool contexts
    - Behavior: POOL_B_REQUIRED_FOR_DIRECTION (direction incompatible without Pool B or when scope.kind="single_pool").
- Large trees and recursion
  - max_depth=0 (unlimited) on massive trees
    - Behavior: allowed; add a performance warning. Suggest setting a positive max_depth. Save/Run allowed if otherwise valid.
- Result/data issues
  - Empty result sets (no duplicates/matches)
    - Behavior: valid; return an empty report with a summary that indicates zero matches.
  - Per-file metadata read failures
    - Behavior: captured as warnings in the report with file path and reason; do not fail the entire run.

5) UX guidance (GUI behaviors)
- Inline, non-blocking hints directly beneath offending widgets with concise messages and tooltips for details.
- Capability-gated controls and buttons:
  - Save and Run remain disabled until capability flags allow (can_save/can_run). Direction radios are disabled until both pools validate. See [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md) and [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md).
- Error banner with a “Copy JSON” action that copies the structured error list (details[]) for support/debugging.
- Focus management: highlight the first actionable error; pressing Enter in a field re-validates and re-focuses the next error.
- Tooltips for controls summarize constraints (e.g., “Degree 0–100; normalized internally to [0.0..1.0]”).

6) Logging and diagnostics
- Logger namespace: pk_py_lib.settings_profiles (INFO: validate/normalize/run; WARNING: validation failures/default fallbacks; ERROR: IO/DB/algorithm).
- Validator logging includes:
  - counts of errors/warnings by code,
  - list of JSON Pointers for first-N issues,
  - applied-defaults counters per section (pools, criteria, scope, output),
  - capability flags snapshot (can_run, can_save, can_enable_*).
- Provenance: every Run response includes the normalized profile snapshot used for execution (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)).

7) Cross-references to rules and defaults
- Data model defaults and normalization (authoritative)
  - Balanced defaults pack and JSON Schema: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md).
  - Degree UI normalization and Package A formula: degree_ui = round(100 * (1 - d/64)) for 64‑bit pHash; match if degree_ui ≥ threshold_ui (see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:508)).
- UI progressive enable/disable and state flows
  - Panels, widgets, gating, and preview: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md).
- Capability flags and gating rules
  - Derivation and consumption: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md).
- Implementation tests and acceptance strategy
  - Validation, normalization, and capability test matrix: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md).

8) Error message templates and examples
Templates (message strings; variables in braces):
- PATH_MISSING: "Pool {pool} root_path is required"
- PATH_UNREADABLE: "Path not found or not readable: {path}"
- DEGREE_OUT_OF_RANGE: "Degree out of range: {value} (expected 0–100)"
- INVALID_COMBINATION: "Invalid combination: {reason}"
  - Examples: "degree_ui is not allowed in duplicates mode", "algorithm must be 'blake3' for duplicates", "algorithm must be 'pHash' for similarity", "direction not allowed in single_pool scope"
- POOL_B_REQUIRED_FOR_DIRECTION: "Direction {direction} requires a valid Pool B root_path"
- PATTERN_COMPILE_ERROR: "Invalid pattern at index {index}: {pattern}"
- SCHEMA_VALIDATION_ERROR: "Schema validation failed at {path}: {why}"
- UNSUPPORTED_FILE_TYPE (warning): "File type {ext} is not enabled by default; add it to type_filters to include"
- NORMALIZATION_CONFLICT (warning): "Normalized {field} from {original} to {normalized}"

Example payloads (validator 200 OK with is_valid=false):
```json
{
  "success": true,
  "data": {
    "is_valid": false,
    "errors": [
      {
        "code": "PATH_MISSING",
        "message": "Pool A root_path is required",
        "details": { "pool": "A" },
        "path": "/pools/A/root_path",
        "hint": "Select an existing, readable directory"
      }
    ],
    "warnings": [],
    "normalized": null,
    "capabilities": {
      "can_run": false,
      "can_save": false,
      "can_enable_direction_controls": false,
      "can_enable_degree_controls": false,
      "required_pools": ["A"]
    }
  },
  "code": null,
  "error": null
}
```

```json
{
  "success": true,
  "data": {
    "is_valid": false,
    "errors": [
      {
        "code": "DEGREE_OUT_OF_RANGE",
        "message": "Degree out of range: 110 (expected 0–100)",
        "details": { "value": 110 },
        "path": "/criteria/degree_ui",
        "hint": "Enter an integer between 0 and 100"
      },
      {
        "code": "INVALID_COMBINATION",
        "message": "degree_ui is not allowed in duplicates mode",
        "details": { "mode": "duplicates" },
        "path": "/criteria/degree_ui"
      }
    ],
    "warnings": [
      {
        "code": "NORMALIZATION_CONFLICT",
        "message": "Normalized max_depth from -1 to 0 (unlimited)",
        "details": { "original": -1, "normalized": 0 },
        "path": "/pools/A/max_depth"
      }
    ],
    "normalized": null,
    "capabilities": {
      "can_run": false,
      "can_save": false,
      "can_enable_direction_controls": false,
      "can_enable_degree_controls": false,
      "required_pools": ["A"]
    }
  },
  "code": null,
  "error": null
}
```

Pattern and direction examples:
```json
{
  "success": true,
  "data": {
    "is_valid": false,
    "errors": [
      {
        "code": "PATTERN_COMPILE_ERROR",
        "message": "Invalid pattern at index 2: **/*.[jpg",
        "details": { "index": 2, "pattern": "**/*.[jpg" },
        "path": "/pools/B/include/2"
      },
      {
        "code": "POOL_B_REQUIRED_FOR_DIRECTION",
        "message": "Direction A_TO_B requires a valid Pool B root_path",
        "details": { "direction": "A_TO_B" },
        "path": "/scope/direction",
        "hint": "Provide pools.B.root_path or switch to single_pool"
      }
    ],
    "warnings": [],
    "normalized": null,
    "capabilities": {
      "can_run": false,
      "can_save": true,
      "can_enable_direction_controls": false,
      "can_enable_degree_controls": true,
      "required_pools": ["A","B"]
    }
  }
}
```

Schema example (malformed JSON; REST variant may respond with 400):
```json
{
  "success": false,
  "error": "Malformed JSON payload",
  "code": "INVALID_CONFIG",
  "metadata": {
    "details": [
      {
        "code": "SCHEMA_VALIDATION_ERROR",
        "message": "Expected object at /criteria, got string",
        "path": "/criteria"
      }
    ]
  }
}
```

## 13B. Settings Profiles v1 (Option A) — Validation Failures, Conflicts, and UX

Scope
- Applies to Option A’s strongly typed Settings Profile schema with two Pools (A/B), Modes (duplicates vs similarity), Directions for two-pool scope, UI Degree 0–100 (normalized to [0..1]), and report-only execution.
- Centralized validator is the source of truth; GUI progressive enable/disable derives from validator outcome.

13B.1 Canonical validation failures (with suggested resolutions)
- Degree present in duplicates mode
  - Symptom: criteria.degree_ui provided while mode="duplicates".
  - Error: INVALID_CONFIG.
  - Resolution: Remove degree_ui; duplicates uses fixed algorithm BLAKE3 and no threshold.
- Missing degree in similarity mode
  - Symptom: mode="similarity" without criteria.degree_ui, or out of [0..100].
  - Error: INVALID_CONFIG.
  - Resolution: Provide degree_ui in range 0–100 (UI); validator normalizes to [0..1].
- Two-pool direction constraints
  - Symptom: scope.kind="two_pool" but missing direction; or direction set without valid Pools A and B.
  - Error: INVALID_CONFIG.
  - Resolution: Ensure Pools A and B validate; set one of A_TO_B, B_TO_A, A_WITHOUT_IN_B, B_WITHOUT_IN_A.
- Pool path existence / access
  - Symptom: pools.A.root_path or pools.B.root_path does not exist or is inaccessible.
  - Error: FILE_MISSING or PERMISSION_DENIED (depending on failure).
  - Resolution: Correct the path, mount the drive, or adjust permissions. GUI preserves input and shows inline hints.
- Pattern compilability / syntax
  - Symptom: invalid glob in include/exclude.
  - Error: INVALID_CONFIG.
  - Resolution: Fix offending patterns; validator identifies the specific index (e.g., /pools/A/include/2).
- Numeric/date bounds
  - Symptom: max_depth < 0; min_bytes > max_bytes; min_date > max_date.
  - Error: INVALID_CONFIG.
  - Resolution: Adjust values to satisfy ordering and bounds.
- Unsupported file-type tokens
  - Symptom: type_filters contains empty/invalid strings.
  - Error: INVALID_CONFIG.
  - Resolution: Remove empties; use “.jpg”, “.png”, etc.

13B.1a Balanced Defaults — additional cases and messages
- Hidden files excluded by default
  - Symptom: expected files (dotfiles or hidden attributes) not appearing.
  - Root cause: include_hidden=false by default.
  - Resolution: enable Include hidden on the Pools panel or add explicit patterns that surface them; message: "Hidden files are excluded by default. Enable 'Include hidden' to include them."
- Symlink traversal disabled by default
  - Symptom: files reachable only via symlinks are missing; potential "no files matched" in folders using junctions/links.
  - Root cause: follow_symlinks=false by default (prevents loops and surprises).
  - Resolution: enable Follow symlinks explicitly; message: "Following symlinks is disabled by default. Enable 'Follow symlinks' to traverse linked folders (use with caution to avoid cycles)."
- RAW formats off by default
  - Symptom: RAW files (e.g., .CR2, .NEF, .ARW) not included in scans.
  - Root cause: default type_filters include common image formats only.
  - Resolution: add RAW extensions to type_filters; message: "RAW formats are not included by default. Add desired RAW extensions to File types to include them."
- Unlimited recursion risks (depth)
  - Symptom: very slow traversal or huge result sets in deep trees.
  - Root cause: max_depth=0 means unlimited recursion by default.
  - Resolution: set a positive max_depth to limit traversal; message: "Unlimited recursion may be slow on deep trees. Consider setting a positive Max depth."
- OS-aware case behavior in patterns
  - Symptom: pattern matches differ across OS (e.g., '*.JPG' matches on Windows but not on Linux/macOS).
  - Root cause: patterns are case-insensitive on Windows, case-sensitive on POSIX.
  - Resolution: adjust pattern case or use multiple patterns; message: "Pattern case is OS-aware: case-insensitive on Windows, case-sensitive on POSIX."

13B.2 Large-scale and extreme scenarios (performance-safe behaviors)
- Empty pools or zero-effective files
  - Behavior: Validator may return is_valid=true with warnings; GUI allows Save/Run, but run will produce empty reports. UX: show “No files matched your criteria.”
- Massive directory trees (deep recursion)
  - Risk: Long-running previews and validations.
  - Guidance: Provide max_depth; limit “Preview Effective Paths” to 100 items with progress/cancel. Inline warning on extreme depth.
- Huge file counts (n^2 comparisons)
  - Run engines should rely on hashing prefilters and degree thresholds; validator unaffected. UX: show progress; allow cancel; report-only ensures no destructive operations.
- Network/unavailable drives
  - Behavior: FILE_MISSING/PERMISSION_DENIED; present retry hints; keep Save disabled until fixed (unless UI allows warnings-only saves per policy).
- Permission issues (locked folders/files)
  - Behavior: PERMISSION_DENIED; keep dialog open; allow Export of current draft profile to JSON for later recovery.

13B.3 Error mapping and API shapes
- Validator response (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)):
  - is_valid: bool
  - errors: [{ path, code, message }]
  - warnings: [{ path, code, message }]
  - normalized: profile (degree_normalized present when similarity)
- Error codes used: INVALID_CONFIG, FILE_MISSING, PERMISSION_DENIED, LOCKED_DB, UNKNOWN_ERROR.

13B.4 Progressive enable/disable UX (examples)
- Single-pool duplicates
  - Degree controls hidden; Run enabled only when Pool A valid.
- Single-pool similarity
  - Degree controls enabled; Run enabled when Pool A valid and Degree valid.
- Two-pool modes
  - Direction radios disabled until both Pools validate.
  - “Without matches” options enabled only for two-pool.

13B.5 Preservation of user input
- On any validation failure, user input remains intact; inline hints and summary list indicate offending fields.
- Save/Run disabled only for errors; warnings are non-blocking.

13B.6 Conflict and recovery examples
- Example: user switches from similarity (degree_ui=85) to duplicates
  - Validator error surfaces “Degree is not allowed in duplicates mode”.
  - GUI auto-disables Degree controls; user removes Degree or switches mode back to similarity.
- Example: direction set to A_TO_B but Pool B missing
  - Validator flags missing pools.B; Direction radios remain visible but disabled until B is valid.

References
- Central validator and normalization utilities: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Data model rules and JSON Schema: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- UI progressive logic and preview: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API validation/run contracts: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)

## 1. Overview

This document provides comprehensive error handling strategies and edge case scenarios for the KDC Image Organizer application. Each scenario includes detection methods, recovery strategies, and user communication approaches.

## 2. File System Error Scenarios

### 2.1 File Access Errors

#### 2.1.1 Permission Denied
```python
class PermissionErrorHandler:
    """Handle file permission errors."""

    def handle_permission_denied(self, file_path: Path, operation: str):
        """
        Scenario: User lacks read/write permissions for file/folder

        Recovery Strategy:
        1. Check if running with admin privileges
        2. Offer to skip file
        3. Request elevation if possible
        4. Log detailed error with path
        """

        # Detection
        try:
            file_path.stat()
        except PermissionError as e:
            # Recovery options
            recovery_options = [
                "Skip this file and continue",
                "Retry with different credentials",
                "Run application as administrator",
                "Select different folder"
            ]

            # User notification
            self.notify_user(
                title="Permission Denied",
                message=f"Cannot access {file_path}",
                details=str(e),
                options=recovery_options
            )

            # Log for debugging
            self.logger.warning(
                "Permission denied",
                path=str(file_path),
                operation=operation,
                user=os.getenv('USERNAME')
            )
```

#### 2.1.2 File Locked by Another Process
```python
def handle_file_locked(self, file_path: Path):
    """
    Scenario: File is locked by another application

    Edge Cases:
    - File opened in image editor
    - Antivirus scanning file
    - Cloud sync in progress
    - System indexing service

    Recovery:
    1. Wait and retry (exponential backoff)
    2. Create read-only copy for analysis
    3. Skip and mark for later retry
    4. Identify locking process if possible
    """

    max_retries = 3
    wait_time = 1.0

    for attempt in range(max_retries):
        try:
            # Attempt to open file
            with open(file_path, 'rb') as f:
                return f.read()
        except OSError as e:
            if e.errno == 32:  # File locked
                time.sleep(wait_time)
                wait_time *= 2
            else:
                raise

    # Fallback: Try read-only shadow copy
    return self.create_shadow_copy(file_path)
```

#### 2.1.3 File Moved/Deleted During Processing
```python
def handle_file_disappeared(self, file_path: Path, cached_hash: str):
    """
    Scenario: File deleted/moved after initial scan

    Recovery:
    1. Search for file by hash in common locations
    2. Check recycle bin
    3. Update cache to mark as missing
    4. Offer to remove from results
    """

    # Search for relocated file
    possible_locations = [
        file_path.parent,  # Same directory
        Path.home() / "Pictures",  # Common picture folders
        Path.home() / "Downloads",
        Path.home() / "Desktop"
    ]

    for location in possible_locations:
        found = self.find_file_by_hash(location, cached_hash)
        if found:
            self.update_file_location(file_path, found)
            return found

    # Mark as missing in cache
    self.mark_file_missing(file_path)
```

### 2.2 Network Drive Issues

#### 2.2.1 Network Drive Disconnection
```python
class NetworkDriveHandler:
    """Handle network drive issues."""

    def handle_network_disconnection(self, path: Path):
        """
        Scenario: Network drive becomes unavailable during operation

        Edge Cases:
        - WiFi disconnection
        - VPN timeout
        - NAS going to sleep
        - SMB/CIFS timeout

        Recovery:
        1. Detect network vs local drive
        2. Pause operation and wait for reconnection
        3. Cache partial results
        4. Offer to continue with local files only
        """

        if self.is_network_path(path):
            # Monitor network status
            reconnect_timeout = 30  # seconds

            if self.wait_for_network(reconnect_timeout):
                # Network restored
                self.resume_operation()
            else:
                # Offer alternatives
                self.offer_offline_mode()
                self.save_partial_results()
```

#### 2.2.2 Slow Network Performance
```python
def handle_slow_network(self, transfer_rate: float):
    """
    Scenario: Network too slow for efficient operation

    Detection: Transfer rate < 1MB/s for image operations

    Recovery:
    1. Switch to metadata-only mode
    2. Queue files for background processing
    3. Reduce thumbnail quality
    4. Implement adaptive timeout
    """

    if transfer_rate < 1_000_000:  # bytes/second
        self.enable_low_bandwidth_mode()
        self.reduce_concurrent_operations()
        self.increase_cache_aggressiveness()
```

### 2.3 Storage Issues

#### 2.3.1 Insufficient Disk Space
```python
class StorageHandler:
    """Handle storage-related errors."""

    def handle_disk_full(self, required_space: int, available_space: int):
        """
        Scenario: Not enough space for cache/thumbnails

        Edge Cases:
        - Cache directory on different drive
        - System temp directory full
        - User quota exceeded

        Recovery:
        1. Automatic cache cleanup
        2. Use alternative temp location
        3. Reduce cache size limit
        4. Stream processing without cache
        """

        # Try to free space
        freed = self.cleanup_old_cache_entries()

        if freed >= required_space:
            return True

        # Offer alternatives
        alternatives = [
            self.get_alternative_cache_locations(),
            self.suggest_cleanup_targets(),
            self.calculate_minimum_cache_size()
        ]

        return self.prompt_user_action(alternatives)
```

#### 2.3.2 Cache Corruption
```python
def handle_cache_corruption(self, cache_db: Path):
    """
    Scenario: Cache database corrupted

    Detection: SQLite integrity check fails

    Recovery:
    1. Attempt automatic repair
    2. Rebuild from backup
    3. Clear and regenerate
    4. Continue without cache
    """

    try:
        # Attempt repair
        self.repair_sqlite_db(cache_db)
    except:
        # Try backup
        backup = cache_db.with_suffix('.backup')
        if backup.exists():
            shutil.copy2(backup, cache_db)
        else:
            # Full rebuild
            self.rebuild_cache_from_scratch()
```

## 3. Image Processing Errors

### 3.1 Corrupted Images

#### 3.1.1 Partial Image Corruption
```python
class CorruptedImageHandler:
    """Handle corrupted image files."""

    def handle_partial_corruption(self, image_path: Path):
        """
        Scenario: Image partially corrupted but partially readable

        Edge Cases:
        - Truncated JPEG
        - Bad EXIF data
        - Color profile corruption
        - Progressive JPEG with missing scans

        Recovery:
        1. Try alternative decoders
        2. Extract readable portions
        3. Use file recovery tools
        4. Mark as corrupted but include in results
        """

        strategies = [
            self.try_pillow_decoder,
            self.try_opencv_decoder,
            self.try_imagemagick,
            self.extract_thumbnail_from_exif,
            self.create_placeholder_thumbnail
        ]

        for strategy in strategies:
            try:
                return strategy(image_path)
            except Exception as e:
                self.log_recovery_attempt(strategy.__name__, e)

        return self.create_error_placeholder()
```

#### 3.1.2 Unsupported Format Variations
```python
def handle_format_variation(self, image_path: Path, claimed_format: str):
    """
    Scenario: File extension doesn't match actual format

    Edge Cases:
    - JPEG saved as .png
    - WebP with .jpg extension
    - HEIC on system without support
    - Rare formats (JPEG-XR, AVIF)

    Recovery:
    1. Detect actual format from headers
    2. Try multiple decoders
    3. Convert using external tools
    4. Install missing codecs
    """

    actual_format = self.detect_format_from_header(image_path)

    if actual_format != claimed_format:
        self.log_format_mismatch(image_path, claimed_format, actual_format)

    # Try format-specific handlers
    return self.get_format_handler(actual_format).decode(image_path)
```

### 3.2 Memory Issues

#### 3.2.1 Out of Memory for Large Images
```python
class MemoryErrorHandler:
    """Handle memory-related errors."""

    def handle_large_image_oom(self, image_path: Path, dimensions: tuple):
        """
        Scenario: Image too large to load in memory

        Edge Cases:
        - Gigapixel panoramas
        - Uncompressed TIFF files
        - Multi-page TIFF
        - 16/32-bit per channel images

        Recovery:
        1. Use memory-mapped loading
        2. Process in tiles
        3. Downsample before processing
        4. Use streaming decoder
        """

        width, height = dimensions
        pixel_count = width * height

        if pixel_count > 100_000_000:  # 100 megapixels
            # Use tiled processing
            return self.process_image_in_tiles(image_path, tile_size=1024)
        else:
            # Try downsampling
            return self.process_downsampled(image_path, max_size=4096)
```

#### 3.2.2 Memory Fragmentation
```python
def handle_memory_fragmentation(self):
    """
    Scenario: Memory fragmented, unable to allocate large blocks

    Recovery:
    1. Force garbage collection
    2. Restart worker processes
    3. Reduce concurrent operations
    4. Implement memory pooling
    """

    gc.collect()

    if self.get_memory_fragmentation_ratio() > 0.5:
        self.restart_worker_pool()
        self.reduce_batch_size()
```

## 4. Database Errors

### 4.0 Database Startup Validation

#### 4.0.1 Database Integrity Check on Startup
```python
class DatabaseStartupValidator:
    """Handle database validation and recovery on application startup."""

    def validate_databases_on_startup(self):
        """
        Scenario: Application startup database validation

        Validation Sequence:
        1. Check existence of all required databases
        2. Run PRAGMA quick_check on each database
        3. If quick_check fails, run PRAGMA integrity_check
        4. Handle corruption based on database type

        Databases:
        - settings.db (user_data_dir)
        - sessions.db (user_data_dir)
        - cache.db (user_cache_dir)
        """

        databases = [
            ('settings.db', self.data_dir, 'critical'),
            ('sessions.db', self.data_dir, 'important'),
            ('cache.db', self.cache_dir, 'recoverable')
        ]

        for db_name, location, importance in databases:
            db_path = location / db_name

            # Check existence
            if not db_path.exists():
                self.create_database_with_schema(db_path, db_name)
                continue

            # Validate integrity
            if not self.validate_database_integrity(db_path):
                self.handle_corrupt_database(db_path, importance)

    def validate_database_integrity(self, db_path: Path) -> bool:
        """
        Run PRAGMA checks on database.

        Returns True if healthy, False if corrupt.
        """
        conn = sqlite3.connect(db_path)
        try:
            # Quick check first (faster)
            cursor = conn.execute("PRAGMA quick_check")
            result = cursor.fetchone()

            if result[0] != "ok":
                # Full integrity check if quick check fails
                cursor = conn.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                return result[0] == "ok"

            return True

        except Exception as e:
            self.logger.error(f"Database validation failed: {e}")
            return False
        finally:
            conn.close()

    def handle_corrupt_database(self, db_path: Path, importance: str):
        """
        Handle corrupt database based on importance level.

        Recovery strategies:
        - critical (settings.db): Try to export/preserve settings
        - important (sessions.db): Offer to rebuild
        - recoverable (cache.db): Auto-rebuild
        """

        if importance == 'critical':
            # settings.db - try to preserve data
            self.handle_corrupt_settings_db(db_path)
        elif importance == 'important':
            # sessions.db - prompt user
            self.handle_corrupt_sessions_db(db_path)
        else:
            # cache.db - safe to rebuild
            self.rebuild_cache_database(db_path)

    def handle_corrupt_settings_db(self, db_path: Path):
        """
        Handle corrupted settings database.

        Recovery:
        1. Attempt to export readable settings
        2. Create backup of corrupt database
        3. Rebuild with preserved settings if possible
        4. Use defaults if export fails
        """

        backup_path = db_path.with_suffix('.corrupt.backup')

        try:
            # Try to export settings
            exported_settings = self.export_readable_settings(db_path)

            # Backup corrupt database
            shutil.copy2(db_path, backup_path)

            # Rebuild database
            self.create_database_with_schema(db_path, 'settings.db')

            # Restore exported settings
            if exported_settings:
                self.import_settings(db_path, exported_settings)
                self.notify_user(
                    "Settings Database Recovered",
                    "Your settings have been preserved and restored.",
                    level="info"
                )
            else:
                self.notify_user(
                    "Settings Database Rebuilt",
                    "Settings could not be recovered. Using defaults.",
                    level="warning"
                )

        except Exception as e:
            self.logger.error(f"Failed to recover settings.db: {e}")
            self.prompt_critical_error(
                "Settings database is corrupt and cannot be recovered.",
                options=["Use defaults", "Exit application"]
            )

    def handle_corrupt_sessions_db(self, db_path: Path):
        """
        Handle corrupted sessions database.

        Recovery:
        1. Inform user about session loss
        2. Offer to rebuild from scratch
        3. Create backup of corrupt database
        """

        response = self.prompt_user(
            title="Sessions Database Corrupted",
            message="Your scan sessions history is corrupted. Rebuild?",
            options=["Rebuild (lose history)", "Try repair", "Exit"]
        )

        if response == "Rebuild (lose history)":
            backup_path = db_path.with_suffix('.corrupt.backup')
            shutil.copy2(db_path, backup_path)
            self.create_database_with_schema(db_path, 'sessions.db')

        elif response == "Try repair":
            self.attempt_database_repair(db_path)
        else:
            sys.exit(1)

    def rebuild_cache_database(self, db_path: Path):
        """
        Rebuild cache database (safe to lose).

        Cache will be regenerated as needed during operation.
        """

        self.logger.info("Rebuilding cache database")

        # Remove corrupt database
        if db_path.exists():
            db_path.unlink()

        # Create fresh database
        self.create_database_with_schema(db_path, 'cache.db')

        self.notify_user(
            "Cache Rebuilt",
            "Image cache has been cleared and will rebuild automatically.",
            level="info"
        )
```

#### 4.0.2 Schema Migration Error Handling
```python
class SchemaMigrationHandler:
    """Handle database schema migration errors."""

    def handle_migration_with_safety(self, db_path: Path, target_version: str):
        """
        Scenario: Database needs schema migration

        Safety measures:
        1. Create timestamped backup before migration
        2. Run Alembic migrations
        3. Rollback on failure
        4. Maintain backup retention policy
        """

        # Create backup before migration
        backup_path = self.create_migration_backup(db_path)

        try:
            # Run Alembic migration
            self.run_alembic_migration(db_path, target_version)

            # Verify migration success
            if self.verify_migration(db_path, target_version):
                # Clean up old backups per retention policy
                self.cleanup_old_backups(db_path)
                return True
            else:
                raise Exception("Migration verification failed")

        except Exception as e:
            self.logger.error(f"Migration failed: {e}")

            # Rollback from backup
            self.restore_from_backup(backup_path, db_path)

            # Notify user
            self.notify_user(
                "Database Migration Failed",
                f"Could not update database to version {target_version}. "
                "The database has been restored to its previous state.",
                level="error"
            )

            return False

    def create_migration_backup(self, db_path: Path) -> Path:
        """
        Create timestamped backup before migration.

        Format: {db_name}.{ISO_timestamp}.v{schema_version}
        """
        from datetime import datetime

        # Get current schema version
        version = self.get_schema_version(db_path)

        # Create backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{db_path.stem}.{timestamp}.v{version}"
        backup_path = self.backups_dir / backup_name

        # Copy database
        shutil.copy2(db_path, backup_path)

        self.logger.info(f"Created migration backup: {backup_path}")
        return backup_path

    def cleanup_old_backups(self, db_path: Path):
        """
        Apply backup retention policy.

        Policy:
        - Keep 10 most recent backups per database
        - Purge backups older than 30 days
        """
        from datetime import datetime, timedelta

        db_name = db_path.stem
        cutoff_date = datetime.now() - timedelta(days=30)

        # Find all backups for this database
        backups = list(self.backups_dir.glob(f"{db_name}.*"))

        # Sort by modification time (newest first)
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Keep 10 most recent
        for backup in backups[10:]:
            backup.unlink()
            self.logger.info(f"Removed old backup: {backup}")

        # Remove backups older than 30 days
        for backup in backups[:10]:
            if datetime.fromtimestamp(backup.stat().st_mtime) < cutoff_date:
                backup.unlink()
                self.logger.info(f"Removed expired backup: {backup}")

    def restore_from_backup(self, backup_path: Path, db_path: Path):
        """
        Restore database from backup after failed migration.
        """

        self.logger.info(f"Restoring database from {backup_path}")

        # Remove failed migration database
        if db_path.exists():
            db_path.unlink()

        # Restore from backup
        shutil.copy2(backup_path, db_path)

        self.logger.info("Database restored successfully")
```

#### 4.0.3 Meta Table Management
```python
class MetaTableHandler:
    """Handle meta table creation and management."""

    def ensure_meta_table(self, db_path: Path):
        """
        Ensure meta table exists with schema version.

        Required for all databases to track schema version.
        """

        conn = sqlite3.connect(db_path)
        try:
            # Create meta table if not exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    notes TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Insert schema version if not present
            conn.execute("""
                INSERT OR IGNORE INTO meta (key, value, notes)
                VALUES ('schema_version', '1.0.0', 'Initial schema version')
            """)

            conn.commit()

        except Exception as e:
            self.logger.error(f"Failed to create meta table: {e}")
            raise
        finally:
            conn.close()

    def get_schema_version(self, db_path: Path) -> str:
        """Get current schema version from meta table."""

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            )
            result = cursor.fetchone()
            return result[0] if result else '0.0.0'

        except:
            return '0.0.0'
        finally:
            conn.close()
```

### 4.1 Database Lock Issues

#### 4.1.1 Database Locked
```python
class DatabaseErrorHandler:
    """Handle database-related errors."""

    def handle_database_locked(self, db_path: Path, operation: str):
        """
        Scenario: SQLite database locked by another process

        Edge Cases:
        - Multiple app instances
        - Backup software accessing DB
        - Antivirus scanning
        - Incomplete transaction

        Recovery:
        1. Wait with exponential backoff
        2. Use WAL mode
        3. Create temporary copy
        4. Force unlock (risky)
        """

        # Enable WAL mode for better concurrency
        self.enable_wal_mode(db_path)

        # Retry with backoff
        for attempt in range(5):
            try:
                return self.execute_with_timeout(operation, timeout=5.0)
            except sqlite3.OperationalError as e:
                if "locked" in str(e):
                    time.sleep(2 ** attempt)
                else:
                    raise

        # Last resort: work with copy
        return self.work_with_db_copy(db_path, operation)
```

#### 4.1.2 Database Corruption During Write
```python
def handle_write_corruption(self, db_path: Path, transaction: dict):
    """
    Scenario: Database corrupted during write operation

    Recovery:
    1. Rollback transaction
    2. Restore from journal
    3. Replay from operation log
    4. Restore from backup
    """

    # Check for journal files
    journal = db_path.with_suffix('.db-journal')
    wal = db_path.with_suffix('.db-wal')

    if journal.exists() or wal.exists():
        self.recover_from_journal(db_path)
    else:
        self.restore_from_last_backup(db_path)
        self.replay_operations_since_backup(transaction)
```

## 5. Algorithm Processing Errors

### 5.1 Algorithm Failures

#### 5.1.1 Hash Computation Failure
```python
class AlgorithmErrorHandler:
    """Handle algorithm-related errors."""

    def handle_hash_failure(self, image: Image, algorithm: str):
        """
        Scenario: Hash algorithm fails on specific image

        Edge Cases:
        - Grayscale when expecting RGB
        - Unusual bit depth
        - Alpha channel issues
        - Extreme aspect ratios

        Recovery:
        1. Convert image format
        2. Use fallback algorithm
        3. Compute partial hash
        4. Skip with warning
        """

        # Try format conversion
        conversions = [
            ('RGB', self.convert_to_rgb),
            ('L', self.convert_to_grayscale),
            ('RGBA', self.remove_alpha_channel)
        ]

        for target_mode, converter in conversions:
            try:
                converted = converter(image)
                return self.compute_hash(converted, algorithm)
            except:
                continue

        # Use simpler algorithm
        return self.compute_basic_hash(image)
```

#### 5.1.2 Comparison Overflow
```python
def handle_comparison_overflow(self, num_images: int):
    """
    Scenario: Too many comparisons (n²/2 complexity)

    Edge Cases:
    - 100,000+ images
    - All images very similar
    - Degenerate clustering

    Recovery:
    1. Use hierarchical clustering
    2. Implement early termination
    3. Use approximate algorithms
    4. Process in chunks
    """

    max_direct_comparisons = 1_000_000
    total_comparisons = (num_images * (num_images - 1)) // 2

    if total_comparisons > max_direct_comparisons:
        # Switch to approximate method
        return self.use_lsh_algorithm()  # Locality Sensitive Hashing
```

## 6. User Interface Errors

### 6.1 Display Issues

#### 6.1.1 High DPI Scaling Problems
```python
class UIErrorHandler:
    """Handle UI-related errors."""

    def handle_dpi_scaling_issue(self, detected_dpi: float):
        """
        Scenario: UI elements incorrectly scaled

        Edge Cases:
        - Multiple monitors with different DPI
        - Dynamic DPI changes
        - Fractional scaling (125%, 175%)
        - Remote desktop sessions

        Recovery:
        1. Auto-detect and adjust
        2. Provide manual override
        3. Use DPI-aware rendering
        4. Fall back to 100% scaling
        """

        if detected_dpi > 144:  # High DPI display
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

        # Handle per-monitor DPI
        if self.has_multiple_monitors():
            self.enable_per_monitor_dpi()
```

#### 6.1.2 Widget Rendering Failures
```python
def handle_widget_render_failure(self, widget: QWidget, error: Exception):
    """
    Scenario: Custom widget fails to render

    Recovery:
    1. Fall back to basic widget
    2. Disable hardware acceleration
    3. Use software rendering
    4. Reduce visual effects
    """

    try:
        # Try software rendering
        widget.setAttribute(Qt.WA_UseSoftwareOpenGL)
        widget.update()
    except:
        # Replace with simpler widget
        return self.create_fallback_widget()
```

## 7. Configuration Errors

### 7.1 Settings Corruption

#### 7.1.1 Invalid Configuration Values
```python
class ConfigErrorHandler:
    """Handle configuration-related errors."""

    def handle_invalid_config(self, config: dict, schema: dict):
        """
        Scenario: Configuration contains invalid values

        Edge Cases:
        - Type mismatches
        - Out of range values
        - Missing required keys
        - Circular references

        Recovery:
        1. Validate and sanitize
        2. Use defaults for invalid values
        3. Prompt user for critical settings
        4. Restore from backup
        """

        validated = {}
        errors = []

        for key, schema_def in schema.items():
            value = config.get(key, schema_def.get('default'))

            try:
                validated[key] = self.validate_value(value, schema_def)
            except ValidationError as e:
                errors.append((key, e))
                validated[key] = schema_def['default']

        if errors:
            self.notify_config_fixes(errors)

        return validated
```

### 7.2 Profile Issues

#### 7.2.1 Profile Migration Failure
```python
def handle_profile_migration_failure(self, old_version: str, new_version: str):
    """
    Scenario: Profile incompatible with new version

    Recovery:
    1. Create backup of old profile
    2. Attempt partial migration
    3. Create new profile with defaults
    4. Offer manual migration tool
    """

    backup_path = self.backup_profile(old_version)

    try:
        # Try partial migration
        migrated = self.partial_migrate_profile(backup_path, new_version)
        missing = self.get_missing_settings(migrated)

        if missing:
            self.prompt_for_missing_settings(missing)

    except:
        # Create fresh profile
        self.create_default_profile()
        self.import_favorites_from_backup(backup_path)
```

## 8. Concurrency Issues

### 8.1 Thread Safety

#### 8.1.1 Race Conditions
```python
class ConcurrencyHandler:
    """Handle concurrency-related issues."""

    def handle_race_condition(self, resource: str):
        """
        Scenario: Multiple threads accessing shared resource

        Edge Cases:
        - Cache updates during read
        - Simultaneous file modifications
        - GUI updates from worker threads

        Recovery:
        1. Implement proper locking
        2. Use thread-safe data structures
        3. Queue operations
        4. Retry with backoff
        """

        with self.get_lock(resource):
            # Ensure exclusive access
            return self.perform_operation(resource)
```

#### 8.1.2 Deadlock Detection
```python
def handle_deadlock(self, timeout: float = 30.0):
    """
    Scenario: Circular wait causing deadlock

    Recovery:
    1. Implement timeout on all locks
    2. Detect and break circular dependencies
    3. Use lock ordering
    4. Restart affected operations
    """

    if self.detect_circular_wait():
        # Break deadlock
        self.release_lowest_priority_lock()
        self.restart_operation()
```

## 9. Edge Case Scenarios

### 9.1 Extreme Data Sizes

#### 9.1.1 Single Folder with 1M+ Files
```python
def handle_extreme_file_count(self, folder: Path, count: int):
    """
    Scenario: Folder contains millions of files

    Recovery:
    1. Use generator-based iteration
    2. Process in batches
    3. Implement pagination
    4. Use database for file list
    """

    if count > 100_000:
        # Stream process
        return self.process_files_streaming(folder)
```

#### 9.1.2 Deeply Nested Folders
```python
def handle_deep_nesting(self, path: Path, depth: int):
    """
    Scenario: Folder structure nested 100+ levels

    Recovery:
    1. Limit recursion depth
    2. Use iterative traversal
    3. Implement path length checks
    4. Flatten structure in cache
    """

    if depth > 50:
        self.use_iterative_traversal()
        self.warn_user_about_depth(depth)
```

### 9.2 Unusual File Systems

#### 9.2.1 Case-Sensitive File Systems
```python
def handle_case_sensitivity(self, path: Path):
    """
    Scenario: Mixed case-sensitive/insensitive systems

    Recovery:
    1. Normalize all paths
    2. Use case-insensitive comparison
    3. Detect file system type
    4. Maintain case mapping
    """

    fs_type = self.detect_filesystem_type(path)

    if fs_type.case_sensitive:
        self.enable_case_sensitive_mode()
```

### 9.3 System Resource Limits

#### 9.3.1 File Handle Exhaustion
```python
def handle_file_handle_limit(self):
    """
    Scenario: Too many open files

    Recovery:
    1. Implement file handle pooling
    2. Close unused handles
    3. Increase system limits
    4. Process in smaller batches
    """

    # Monitor open handles
    if self.get_open_handle_count() > self.max_handles * 0.8:
        self.close_idle_handles()
        self.reduce_concurrent_operations()
```

## 10. Recovery Strategies Summary

### 10.1 General Recovery Principles
1. **Fail Gracefully**: Never crash, always provide feedback
2. **Preserve Data**: Never lose user data or work
3. **Continue Operation**: Skip problems when possible
4. **Inform User**: Clear, actionable error messages
5. **Log Everything**: Detailed logs for debugging
6. **Learn from Errors**: Adapt behavior based on errors

### 10.2 Error Priority Levels
```python
class ErrorPriority(Enum):
    CRITICAL = 1    # Stop operation, require user action
    HIGH = 2        # Warn user, attempt recovery
    MEDIUM = 3      # Log warning, auto-recover
    LOW = 4         # Log info, continue silently
```

### 10.3 User Communication Strategy
```python
def communicate_error(self, error: Exception, priority: ErrorPriority):
    """
    Standardized error communication.

    - CRITICAL: Modal dialog with options
    - HIGH: Toast notification with action
    - MEDIUM: Status bar warning
    - LOW: Log entry only
    """

    if priority == ErrorPriority.CRITICAL:
        self.show_error_dialog(error)
    elif priority == ErrorPriority.HIGH:
        self.show_warning_notification(error)
    elif priority == ErrorPriority.MEDIUM:
        self.update_status_bar(error)
    else:
        self.log_error(error)
```

## 11. Testing Error Scenarios

### 11.1 Error Injection Testing
```python
class ErrorInjector:
    """Inject errors for testing recovery."""

    def inject_random_errors(self, probability: float = 0.1):
        """Randomly inject errors during testing."""

        if random.random() < probability:
            error_type = random.choice([
                PermissionError,
                FileNotFoundError,
                MemoryError,
                sqlite3.OperationalError
            ])
            raise error_type("Injected for testing")
```

### 11.2 Stress Testing Scenarios
1. Process 1M+ images
2. Fill disk during operation
3. Disconnect network drives
4. Corrupt cache database
5. Mix file formats randomly
6. Exceed memory limits
7. Create circular symlinks
8. Use Unicode filenames
9. Simulate slow network
10. Kill processes randomly

## 12. Implementation Guidelines

### 12.1 Error Handler Registration
```python
class ErrorHandlerRegistry:
    """Central registry for error handlers."""

    handlers = {
        PermissionError: PermissionErrorHandler,
        MemoryError: MemoryErrorHandler,
        sqlite3.DatabaseError: DatabaseErrorHandler,
        OSError: FileSystemErrorHandler,
    }

    def handle(self, error: Exception) -> RecoveryAction:
        """Route error to appropriate handler."""

        handler_class = self.handlers.get(type(error), DefaultErrorHandler)
        handler = handler_class()
        return handler.handle(error)
```

### 12.2 Monitoring and Metrics
```python
class ErrorMetrics:
    """Track error patterns for improvement."""

    def record_error(self, error: Exception, recovery: RecoveryAction):
        """Record error occurrence and recovery success."""

        self.error_counts[type(error)] += 1
        self.recovery_success[recovery] += 1

        # Identify patterns
        if self.error_counts[type(error)] > 10:
            self.suggest_preventive_action(error)
```

This comprehensive error handling ensures robust operation even under adverse conditions, maintaining data integrity and providing clear user feedback throughout.
## 13. Settings/Profile Manager Errors and Edge Cases

Status: Planned

Scope
- Enumerates profile-management specific errors, validation failures, database/persistence issues, and user-visible messages.
- Applies to first-launch/startup modal, ongoing settings management, and import/export of profiles.

13.1 Validation and Naming Errors
- Duplicate profile name
  - Detection: create/update/copy attempts where proposed name matches existing (case-insensitive).
  - User message: "A profile with that name already exists. Choose a different name."
  - Recovery: keep focus in Name; highlight field; disable Continue/Apply; suggest available variant (e.g., "<name> (copy)").
  - Error code: INVALID_CONFIG
- Invalid characters or length
  - Rules: required; 1–64 chars; allowed [A–Z a–z 0–9 space _ -].
  - User message: "Name must be 1–64 characters using letters, numbers, spaces, _ or -."
  - Recovery: inline tooltip; prevent save.
  - Error code: INVALID_CONFIG
- Invalid thresholds or fields
  - Threshold out of range (UI 0–100)
  - User message: "Threshold must be between 0 and 100."
  - Error code: INVALID_CONFIG
  - Reference: [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1)

13.2 Active/Default Invariants
- Delete Active profile
  - Rule: disallowed.
  - User message: "Cannot delete the active profile. Please switch to another profile first."
  - Recovery: keep Delete disabled; offer Switch Active action.
- Delete last remaining profile
  - Rule: disallowed.
  - User message: "At least one profile is required. Create a new profile before deleting this one."
  - Recovery: disable Delete until another profile exists.
- Multiple Defaults
  - Rule: not allowed; enforce exclusivity.
  - Behavior: when setting one as Default, clear is_default on all others.
  - Logging: INFO with affected profile ids.

13.3 Startup Modal Outcomes
- Cancel with no Active profile
  - Behavior: exit application immediately.
  - User message (toast/log only, not modal): "Startup canceled without selecting a profile. Exiting."
  - Rationale: canonical policy to enforce explicit Active selection on launch.
- Cancel with existing Active profile
  - Policy: exit to enforce confirmation each run (canonical); see decisions.
  - Alternative policy (future): allow continue with last Active; currently not adopted.

13.4 Persistence and Database Errors
- Database locked (concurrent access)
  - Symptom: sqlite3.OperationalError: database is locked
  - User message: "Settings database is currently in use. Please close other instances and try again."
  - Recovery: retry with backoff; offer Retry/Exit; suggest closing other instances.
  - Error code: LOCKED_DB
- Integrity/migration failure during startup
  - Symptom: PRAGMA checks fail or migration fails
  - User message:
    - settings.db: "Settings database appears corrupted. We can try to preserve readable settings and rebuild."
    - Offer: "Rebuild" or "Exit" (see general DB section 4.0).
  - Error code: INVALID_CONFIG or UNKNOWN_ERROR
- Write failure (disk full, permissions)
  - User message: "Could not save profile changes. Check disk space and permissions."
  - Recovery: do not lose edits; keep dialog open; allow Save As (export).
  - Error code: PERMISSION_DENIED or UNKNOWN_ERROR
- Fallback persistence (rare)
  - Trigger: unrecoverable SQLite initialization failures.
  - Behavior: write minimal JSON fallback (profiles.json) under data_dir; warn user and proceed.
  - User message: "Using temporary settings storage due to a database issue. Your changes will be migrated when the database becomes available."
  - Logging: WARNING; attempt auto-import on next successful DB init.

13.5 Import/Export Errors
- Import invalid JSON or incompatible schema
  - User message: "The selected file is not a valid profile export."
  - Recovery: show details; do not modify existing profiles.
  - Error code: INVALID_CONFIG
- Import name collision
  - User message: "A profile named '<name>' already exists." Offer to rename.
  - Recovery: pre-fill with "<name> (imported)".
- Export write failure
  - User message: "Could not export profile. Check path permissions."
  - Error code: PERMISSION_DENIED

13.6 Path Validation and Long-Running Checks
- Missing/inaccessible paths
  - User message: inline warnings per path; block Save/Run until corrected (strict for Option A — Package A).
  - Recovery: "Fix Issues" dialog; list inaccessible paths; allow Ignore Warnings.
- Slow or huge path previews
  - Behavior: limit preview to 100 items; show progress; allow cancel.

13.7 Non-Destructive Behavior Summary
- All modifications are transactional; failed operations leave prior state intact.
- Deletions require confirmation and are blocked by invariants (Active/last profile).
- Copy never overwrites an existing profile.
- Cancel from modal never writes changes.

13.8 Logging and Telemetry (local only)
- Logger: "pk_py_lib.settings_profiles"
- INFO: create/update/delete/copy/set-active/set-default
- WARNING: validation failures, fallback storage usage
- ERROR: DB errors, persistence failures, migration failures

13.9 Next Steps
- Map errors to ApiResponse with ErrorCodes; see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:164).
- Add pytest-qt tests covering dialog error flows (duplicate name, delete active, cancel on startup).
- Implement fallback JSON writer/reader hooks in [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) guarded by explicit error cases.
<!-- Settings Manager errors finalization -->

## 13A. Settings/Profile Manager — Finalized Errors, Concurrency, and Scalability

Status: Approved

Path and scope updates
- Supersedes prior references to `src/pk_py_lib/gui/settings/profile_manager.py`.
- Canonical GUI module path for the reusable dialog is [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1).
- All profile operations go through the API [SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69); GUI must not touch the DB directly.

13A.1 Data integrity and recovery
- Dangling or missing meta.active_profile_id
  - Detection: Active retrieval returns None or resolves to a non-existent id.
  - Core behavior: [SettingsProfilesManager.get_active_profile()](src/pk_py_lib/core/settings_profiles.py:273) repairs by setting Default (if present) else first-by-name and persists meta.active_profile_id.
  - GUI: show a non-blocking info banner “Active profile repaired to <name>” on dialog open.
- Corrupted JSON in settings_profiles.data
  - Detection: Core loads data via `json.loads` and wraps non-dict into dict or {} on exception; see [SettingsProfilesManager._row_to_profile()](src/pk_py_lib/core/settings_profiles.py:175).
  - Behavior: GUI should allow opening and saving; save will write a normalized dictionary and repair the payload.
  - Logging: WARNING with context; surface INVALID_CONFIG if user attempts to save invalid structures.

13A.2 Validation and naming (reaffirmed)
- Name rules: [SettingsProfilesManager.validate_name()](src/pk_py_lib/core/settings_profiles.py:144) — ^[A–Z a–z 0–9 _ - and space]{1,64}$ (case-insensitive unique)
- Duplicate name collisions
  - Create/Update/Copy: API returns INVALID_CONFIG with message; GUI keeps focus in Name and suggests “(copy)” strategy.
  - Import: strategy “rename” auto-synthesizes unique candidate; see [SettingsProfilesManager.import_profile()](src/pk_py_lib/core/settings_profiles.py:625)

13A.3 Invariants (delete/copy/default/active)
- Cannot delete Active profile: enforced in [SettingsProfilesManager.delete_profile()](src/pk_py_lib/core/settings_profiles.py:439) with INVALID_CONFIG surface
- Cannot delete last remaining profile: enforced in delete_profile
- Single Default invariant: [SettingsProfilesManager.set_default_profile()](src/pk_py_lib/core/settings_profiles.py:574) clears others
- Copy collisions: handled via name validation; GUI should pre-fill “<name> (copy)” and iterate “(copy N)”

13A.4 Concurrency and multi-instance
- Database locked
  - Symptom: sqlite3.OperationalError “database is locked”; API maps to LOCKED_DB (see [_map_exception](src/pk_py_lib/api/settings_profiles.py:48))
  - GUI: show modal “Database in use” with actions: Retry (exponential backoff), Exit. Provide tip to close other instances.
- Lost-update avoidance
  - Design: All writes transactional; GUI fetches fresh item before Apply; consider warning if timestamps changed (optional future enhancement via updated_at comparison).
- Two app instances performing conflicting operations
  - Disposition: last successful transaction wins; invariants still enforced; user-facing errors guided by ApiResponse.

13A.5 I/O and persistence failures
- Disk full / permissions
  - Create/Update/Delete/Copy: return PERMISSION_DENIED or UNKNOWN_ERROR; GUI must not lose edits; keep dialog open; allow Export to JSON as backup.
- Fallback persistence (rare)
  - Trigger: catastrophic SQLite init failure during startup (outside normal operations)
  - Behavior: core may write `profiles.json` fallback (see decisions); GUI shows warning banner; changes migrate on next successful DB init; logging at WARNING.

13A.6 Scalability: large number of profiles
- UI responsiveness
  - Use in-memory filtering over the list returned by [SettingsProfilesAPI.list_profiles()](src/pk_py_lib/api/settings_profiles.py:109).
  - For N > 2,000, enable incremental filtering (debounce 150ms) and consider virtualized list rendering.
- Sorting
  - Default: case-insensitive by name; maintain stable order while editing.
- Search
  - Case-insensitive substring on name (and optional description if present in data payload).

13A.7 Startup modal outcomes (policy)
- Cancel without any Active profile: exit application immediately
- Cancel with existing Active profile: exit application to enforce explicit confirmation each run (canonical policy)
- Continue: only enabled when a valid Active profile exists; after accept, app invokes [ConfigurationManager.switch_profile()](src/pk_py_lib/core/configuration.py:399)

13A.8 Import/Export errors (reaffirmed)
- Import invalid JSON: INVALID_CONFIG; do not mutate DB; show details and allow retry
- Import name collision: offer rename; auto-fill “(imported)”
- Export write failure: PERMISSION_DENIED; offer alternate path

13A.9 Test matrix (minimum)
- Name validation: invalid chars, too long, duplicate case-insensitive
- CRUD invariants: delete Active; delete last; set Default exclusivity
- Concurrency: simulate LOCKED_DB on write → Retry/Exit flow
- Scalability: seed 5,000 profiles; verify search debounce and UI responsiveness
- Repair path: dangling meta.active_profile_id auto-repair behavior surfaced to UI

Error codes used
- INVALID_CONFIG, LOCKED_DB, PERMISSION_DENIED, UNKNOWN_ERROR — see [ErrorCodes](docs/roo/img-app-api-specifications.md:1167)

## 13B.SA Set A capability-gated cases (Option A)

The following UX and API behaviors are explicitly tied to the validator’s capability flags in ValidationReport.capabilities. These rules ensure deterministic, centralized gating of controls.

Direction toggle when Pool B invalid (UI prevented)
- Condition:
  - capabilities.can_enable_direction_controls = false
  - Typical cause: scope.kind = "two_pool" with pools.B missing/invalid
- UI behavior:
  - Direction radio group is disabled; user cannot change selection
  - Tooltip/help text: "Direction is available only after both Pool A and Pool B validate."
- Logging:
  - INFO gate event with context { a_valid, b_valid, scope_kind: "two_pool" }
- Reference:
  - API: ValidationReport.capabilities.can_enable_direction_controls (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1666))

Two-pool Run without both pools valid (blocked)
- Condition:
  - capabilities.can_run = false because required_pools = ["A","B"] and pools.B is missing/invalid
- UI behavior:
  - Run button disabled; inline summary shows what’s missing (e.g., “Pool B path is required for two-pool runs”)
- API behavior (server-side re-validation on POST /runs/*):
  - Return ApiResponse.fail with code = "INVALID_CONFIG"
  - Message example: "Two-pool run requires valid Pool A and Pool B root_path values."
- User guidance:
  - "Provide a valid path for Pool B or switch Scope to Single Pool."
- Reference:
  - API: Run endpoints and ErrorCodes (see [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1726), [ErrorCodes](docs/roo/img-app-api-specifications.md:1169))

Save gating for Set A (A-only valid)
- Condition:
  - capabilities.can_save = true when report.is_valid = true and Pool A is valid
  - capabilities.can_run = false until all required_pools validate
- UI behavior:
  - Save enabled; Run disabled
  - Degree controls enabled only in Similarity mode (capabilities.can_enable_degree_controls = true when mode = "similarity")
- Reference:
  - Capabilities derivation rules (see [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1459))

## 14. Comprehensive GUI Error Handling System

The project now includes a comprehensive GUI error handling system implemented in [`src/pk_py_lib/gui/utils/messages.py`](src/pk_py_lib/gui/utils/messages.py). This system provides centralized error handling for all GUI operations with consistent user-facing dialogs and detailed logging.

### 14.1 Overview of the Error Handling System

The GUI error handling system consists of three main components:

#### 14.1.1 `handle_gui_error` Function
Centralized error handler that:
- Shows user-friendly error dialogs with selectable text
- Logs detailed error information to STDERR with full context
- Captures call stack, parameters, and component information
- Supports both string messages and exception objects

**Key Features:**
- **Selectable Text Dialogs**: All error dialogs use [`show_selectable_error`](src/pk_py_lib/gui/utils/messages.py:118) which enables text selection for easy copying
- **Comprehensive Logging**: Detailed error information including component name, file path, line number, parameters, and full stack traces
- **Dual Output**: User-friendly dialogs + detailed technical logging for debugging

#### 14.1.2 `gui_error_handler` Decorator
Automatic error handling decorator for GUI functions that:
- Automatically wraps functions to catch exceptions
- Extracts context from function arguments
- Determines parent widget automatically (for QWidget methods)
- Provides configurable component naming and default context

#### 14.1.3 `gui_error_context` Context Manager
Context manager for GUI operations that:
- Catches exceptions within the context
- Handles them using the centralized error system
- Re-raises exceptions after handling (allows calling code to handle cleanup)
- Provides configurable context variables

### 14.2 Compliance with Project Requirements

The system fully complies with the project's GUI error handling requirements:

#### 14.2.1 Selectable Text in Dialogs
- Uses [`show_selectable_error`](src/pk_py_lib/gui/utils/messages.py:118) which internally calls [`_enable_label_selection`](src/pk_py_lib/gui/utils/messages.py:31) to enable text selection on all QMessageBox labels
- Users can copy/paste error messages for debugging

#### 14.2.2 Detailed STDERR Logging
The system logs comprehensive error details including:
- **Full error text/description**: Complete error message
- **File path of component**: Full path to source file where error occurred
- **Line number**: Exact line number where error was handled
- **Parameters/values**: All context variables that caused the error
- **Call stack**: Complete stack trace for exceptions

**Logging Examples:**
- With logging infrastructure available: Uses structured logging with [`get_logger("gui.error")`](src/pk_py_lib/gui/utils/messages.py:236)
- Without logging: Falls back to detailed STDERR output with all context ([lines 258-277](src/pk_py_lib/gui/utils/messages.py:258))

### 14.3 Usage Examples

#### 14.3.1 Basic Usage with `handle_gui_error`
```python
from src.pk_py_lib.gui.utils.messages import handle_gui_error

# Handle exception with context
try:
    risky_operation()
except Exception as e:
    handle_gui_error(
        parent=self,  # QWidget parent for dialog
        error=e,
        title="Operation Failed",
        component_name="MyComponent",
        file_path="/path/to/file.jpg",
        operation_type="image_processing"
    )
```

#### 14.3.2 Automatic Handling with `gui_error_handler` Decorator
```python
from src.pk_py_lib.gui.utils.messages import gui_error_handler

@gui_error_handler(component_name="FileProcessor", operation="file_processing")
def process_file(self, file_path: str, quality: int):
    """Automatically handles errors in this method"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    # Processing logic here
```

#### 14.3.3 Context-Based Handling with `gui_error_context`
```python
from src.pk_py_lib.gui.utils.messages import gui_error_context

with gui_error_context(
    parent=self,
    component_name="BatchProcessing",
    batch_id=123,
    file_count=len(files)
):
    for file in files:
        process_file(file)  # Errors automatically handled
```

### 14.4 Integration with Existing Components

#### 14.4.1 Settings Manager Integration
The Settings Manager components already integrate with the error handling system:

**Settings Manager Dialog** ([`src/pk_py_lib/gui/settings_manager/dialog.py`](src/pk_py_lib/gui/settings_manager/dialog.py:502)):
```python
def _show_error(self, title: str, message: Optional[str], code: Optional[str]) -> None:
    """Show error using centralized error handler with detailed logging."""
    msg = str(message) if message is not None else "An unexpected error occurred."
    if code:
        msg += f"\n\nCode: {code}"

    handle_gui_error(
        parent=self,
        error=msg,
        title=title,
        component_name="SettingsManagerDialog",
        error_code=code
    )
```

**Structured Settings Dialog** ([`src/pk_py_lib/gui/settings_manager/structured_dialog.py`](src/pk_py_lib/gui/settings_manager/structured_dialog.py:533)):
```python
def _show_error(self, title: str, message: Optional[str], code: Optional[str]) -> None:
    """Show error using centralized error handler with detailed logging."""
    msg = str(message) if message is not None else "An unexpected error occurred."
    if code:
        msg += f"\n\nCode: {code}"

    handle_gui_error(
        parent=self,
        error=msg,
        title=title,
        component_name="StructuredSettingsManagerDialog",
        error_code=code
    )
```

#### 14.4.2 File Selector Integration
File selector components can be easily enhanced with error handling:

```python
from src.pk_py_lib.gui.utils.messages import gui_error_handler

@gui_error_handler(component_name="FileSelector", operation="directory_selection")
def on_directory_selected(self, directory_path: str):
    """Handle directory selection with automatic error handling"""
    if not os.path.isdir(directory_path):
        raise ValueError(f"Invalid directory: {directory_path}")
    # Process directory
```

### 14.5 Error Handling Patterns

#### 14.5.1 Centralized Error Handling
All GUI errors should be routed through [`handle_gui_error`](src/pk_py_lib/gui/utils/messages.py:175) for consistent behavior:
- User-friendly dialogs with selectable text
- Detailed technical logging
- Context capture for debugging

#### 14.5.2 Decorator Pattern for Methods
Use [`gui_error_handler`](src/pk_py_lib/gui/utils/messages.py:280) for automatic error handling in GUI methods:
- Automatically captures method arguments as context
- Determines parent widget from `self` parameter
- Provides clean error handling without try/except blocks

#### 14.5.3 Context Manager Pattern for Operations
Use [`gui_error_context`](src/pk_py_lib/gui/utils/messages.py:352) for error handling in operation blocks:
- Handles errors within specific contexts
- Allows re-raising for cleanup operations
- Provides operation-specific context variables

### 14.6 Testing and Validation

The error handling system includes comprehensive tests in [`test_gui_error_handling.py`](test_gui_error_handling.py) covering:
- String and exception error handling
- Decorator functionality with and without parameters
- Context manager successful and error cases
- Integration with existing components

### 14.7 Best Practices

1. **Use Centralized Handling**: Always use [`handle_gui_error`](src/pk_py_lib/gui/utils/messages.py:175) instead of direct QMessageBox calls
2. **Provide Context**: Include relevant context variables for better debugging
3. **Component Naming**: Use descriptive component names for better error identification
4. **Decorator for Methods**: Use [`gui_error_handler`](src/pk_py_lib/gui/utils/messages.py:280) for GUI method error handling
5. **Context for Operations**: Use [`gui_error_context`](src/pk_py_lib/gui/utils/messages.py:352) for operation blocks

### 14.8 Error Recovery Strategy

The GUI error handling system follows these recovery principles:
1. **User Communication**: Show clear, actionable error messages
2. **Technical Logging**: Record detailed error information for debugging
3. **Context Preservation**: Capture all relevant context for issue resolution
4. **Graceful Degradation**: Allow application to continue when possible

This comprehensive error handling system ensures robust GUI operation with excellent user experience and detailed debugging capabilities.

### 14.9 View Cache Dialog Specific Error Handling Enhancements

To address a specific "Unexpected error: name 'QColor' is not defined" issue in the View Cache dialog (following the FlatCacheValidationError fix), the following enhancements were implemented in [`src/pk_py_lib/gui/dialogs/view_cache_dialog.py`](src/pk_py_lib/gui/dialogs/view_cache_dialog.py):

#### 14.9.1 Missing Import Fix
- **Issue**: The dialog used `QColor` for table cell coloring (valid/invalid entries) without importing it from `PySide6.QtGui`.
- **Fix**: Added `from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor` in the imports section (line 26).
- **Impact**: Ensures proper coloring of valid (green) and invalid (red) cache entries in the table view, improving visual feedback without runtime errors.

#### 14.9.2 Enhanced Exception Logging in `__init__`
- **Previous Behavior**: Basic error messages shown in dialogs and labels, but insufficient logging to terminal/STDERR.
- **Enhancements**: Updated both `except` blocks (FlatCacheDBError and general Exception) to use `logger.error` with comprehensive details:
  - **Error Message**: Includes context like "Failed to load cache data from {db_path}" or "Unexpected error in ViewCacheDialog __init__ from {db_path}".
  - **Traceback**: `exc_info=True` captures full stack trace.
  - **File Path**: Logs the database path (`db_path`) from the cache manager.
  - **Relevant Parameters**: For general exceptions, includes `metadata_keys` if available (list of metadata keys from partial load).
  - **Logger**: Uses `get_logger(__name__)` initialized in `__init__` (line 55), ensuring output via console handler to STDERR/terminal.
- **Compliance**: Aligns with project rules in `.roo/rules/15-PythonGUI.md` for detailed STDERR reporting (error text, file path, parameters, call stack).
- **Example Log Output** (simulated error):
  ```
  [23:35:47] ERROR   Unexpected error in ViewCacheDialog __init__ from C:\Users\pkirk\AppData\Local\Pk\pk_py_lib\flat_cache.db: name 'QColor' is not defined
  db_path: C:\Users\pkirk\AppData\Local\Pk\pk_py_lib\flat_cache.db
  metadata_keys: []
  Traceback (most recent call last):
    File "src\pk_py_lib\gui\dialogs\view_cache_dialog.py", line 107, in __init__
      item.setForeground(QColor("green"))
  NameError: name 'QColor' is not defined
  ```
- **Testing Confirmation**:
  - Ran `pdm run imgapp` and triggered "View Cache": No GUI error; proper table display with colored validity column.
  - Simulated exception (e.g., force NameError): Error dialog shown; full details logged to terminal/STDERR and `logs/img-app-terminal.log`.
  - Verified console output uses RichConsoleOutput/SimpleConsoleOutput, routing ERROR to sys.stderr as required.

#### 14.9.3 Global Exception Handler Assessment
- **Evaluation**: The specific uncaught error was resolved by catching in `__init__` and enhancing logging. No additional global handler needed for this dialog, as errors are now fully caught and logged. For broader app coverage, existing `gui_error_handler` decorator and `handle_gui_error` function provide sufficient uncaught error handling in other GUI components.
- **Recommendation**: Monitor for similar issues; if uncaught GUI errors appear elsewhere, integrate `sys.excepthook` override in `img_app/app.py` main() to route to `handle_gui_error`.

## 15. Recent Fixes: Logging, Decorator Invocation, and GUI Attribute Initialization (Session-Specific Resolutions)

This section documents targeted fixes implemented to resolve startup crashes, runtime TypeErrors, and AttributeErrors in the imgapp GUI. These changes enhance logging robustness, ensure proper decorator factory invocation, and prevent dialog closure issues. All fixes align with project guidelines for detailed STDERR logging, selectable error dialogs, and graceful error recovery. They were verified through `pdm run imgapp` execution, confirming clean startup, functional path editing in the GUI, and stable dialog handling without exceptions.

### 15.1 Decorator Invocation Fixes in Structured Editor and Widgets
- **Issue**: The `@log_errors` and `@log_warnings` decorators in [`src/pk_py_lib/gui/settings_manager/structured_editor.py`](src/pk_py_lib/gui/settings_manager/structured_editor.py) and [`src/pk_py_lib/gui/file_selector/widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py) were applied without parentheses, treating them as classes rather than factory functions. This caused TypeErrors during method decoration (e.g., "TypeError: 'function' object is not callable" or unbound method issues), preventing proper error/warning logging and leading to unhandled exceptions in GUI event handlers.
- **Resolution**: Added parentheses to invoke the factories correctly, e.g., `@log_errors()` and `@log_warnings()`. This ensures the decorators return callable wrappers that intercept exceptions and route them through the centralized GUI error handling system ([`src/pk_py_lib/gui/utils/messages.py`](src/pk_py_lib/gui/utils/messages.py)).
  - **Affected Lines** (approximate; post-fix):
    - In `structured_editor.py`: Lines ~45-60 for method decorators like `_validate_field` and `save_profile`.
    - In `widgets.py`: Lines ~30-50 for file selector event handlers like `on_path_changed`.
- **Impact on GUI Workflows**: Path editing in the file selector and settings editor now logs warnings/errors without crashing. For example, invalid path inputs trigger selectable dialogs with details (e.g., "Invalid path format") and comprehensive STDERR output (file path, parameters like `path_str='invalid/path'`, full stack trace), enabling clean user interactions and debugging.
- **Best Practices Reflected**: Ensures decorator factories are invoked as intended, aligning with Python decorator patterns. Integrates with the GUI error system for selectable text dialogs and detailed logging per `.roo/rules/15-PythonGUI.md`.

### 15.2 Module-Level Logger and PKLogger Method Enhancements
- **Issue**: The PKLogger class in [`src/pk_py_lib/core/logging/logger.py`](src/pk_py_lib/core/logging/logger.py) lacked a module-level logger instance, causing AttributeErrors when accessing `logger` in imported modules. Additionally, methods like `_log`, `error`, `warning` did not handle `*args` and `**kwargs` properly, leading to TypeErrors (e.g., "TypeError: _log() takes 2 positional arguments but 3 were given") during formatted logging calls from GUI components.
- **Resolution**:
  - Added a module-level `logger = PKLogger(__name__)` instance at the top of the file (line ~10) for direct access without instantiation.
  - Updated PKLogger methods (`_log`, `error`, `warning`, etc.) to unpack `*args` and `**kwargs` correctly, forwarding them to the underlying handler (e.g., `self._handler.log(level, msg, *args, **kwargs)`). This supports formatted messages like `logger.error("Failed to load %s", path, exc_info=True)`.
  - Ensured integration with console and file outputs via existing handlers in [`src/pk_py_lib/core/logging/outputs`](src/pk_py_lib/core/logging/outputs).
- **Impact on GUI Workflows**: App startup now initializes logging without errors, and runtime events (e.g., path validation in settings editor) produce structured logs. For instance, a failed path load logs: "ERROR: Path load failed for /invalid/path | file: structured_editor.py:45 | params: {'path': '/invalid/path'} | traceback: ...", routed to STDERR and `logs/img-app-terminal.log`. This prevents silent failures and supports debugging of GUI path editing flows.
- **Best Practices Reflected**: Promotes reusable logging with flexible argument handling, adhering to Python logging standards. Enhances diagnostics for GUI errors, ensuring full context (file, line, params, stack) as required by project rules.

### 15.3 PathSelectorDialog Attribute Initialization Fix
- **Issue**: In the PathSelectorDialog (part of file selector widgets), the `_original_msg_handler` attribute was not initialized in `__init__`, causing an AttributeError ("'PathSelectorDialog' object has no attribute '_original_msg_handler'") during `closeEvent` when attempting to restore the original message handler. This led to crashes when closing the dialog after path selection, disrupting GUI workflows like editing paths in the settings manager.
- **Resolution**: Initialized `self._original_msg_handler = None` in `PathSelectorDialog.__init__` (line ~25 in [`src/pk_py_lib/gui/file_selector/widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py)). Updated `closeEvent` to check `if self._original_msg_handler is not None:` before restoration, preventing the error. The handler is set during dialog open and restored on close to manage custom message handling.
- **Impact on GUI Workflows**: Dialogs for path selection (e.g., browsing directories in Pool A/B configuration) now close cleanly without AttributeErrors. Users can edit paths in the structured editor, select via dialog, and dismiss without crashes. Errors, if any, are caught by the GUI error system, showing selectable dialogs (e.g., "Dialog closed unexpectedly") with STDERR details (component: "PathSelectorDialog", file: widgets.py:120, params: {'selected_paths': []}, stack trace).
- **Best Practices Reflected**: Ensures attribute initialization to avoid runtime errors in event handlers. Aligns with Qt best practices for dialog lifecycle management and integrates with the centralized error handler for robust recovery.

### 15.4 Overall Verification and Testing
- **Testing Approach**: Fixes were validated by running `pdm run imgapp`, simulating startup, path editing in settings (e.g., invalid inputs), and dialog interactions (open/close PathSelector). No crashes observed; logs confirm detailed STDERR output and selectable dialogs.
- **Session Outcome**: These resolutions enable successful imgapp execution with clean startup and stable GUI operations. Logging now captures all edge cases comprehensively, supporting future maintenance and user debugging.
- **Cross-References**: Integrates with the GUI error system in section 14; UI impacts noted in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md) for path editing flows; spec updates in [docs/img-app-spec.md](docs/img-app-spec.md) for error recovery behaviors.
