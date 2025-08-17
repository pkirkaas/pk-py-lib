# Canonical Decisions — KDC Image Organizer

Purpose

This document records the canonical decisions agreed for the KDC Image Organizer project to remove cross-document ambiguity and provide a single source of truth for implementation work by Roo and developers.

Scope

- Applies to threshold units, cache & thumbnail storage, file identity detection (move/rename), API shapes, DB schema versioning, telemetry policy, and benchmark harness.
- Update references: see implementation/action items below.

## Core Decisions

### 1) Application Data Locations (canonical)

- **Vendor Name**: "Pk"
- **Application Name**: "Img App"
- **Platform-specific directories** (via platformdirs library):
  - `settings.db` and `sessions.db`: stored in `user_data_dir()`
  - `cache.db`: stored in `user_cache_dir()`
- **Environment override**: `PK_IMG_APP_HOME` environment variable can override the base directory for all databases and caches
- **Directory structure**:
  ```
  user_data_dir/
    settings.db
    sessions.db
    backups/
      settings.db.YYYYMMDD_HHMMSS.v1.0.0
      sessions.db.YYYYMMDD_HHMMSS.v1.0.0
  user_cache_dir/
    cache.db
    thumbnails/
      256x256/
      512x512/
  ```
- Branding vs internal ID: The UI brand is KDC Image Organizer. Platform path resolution uses Vendor "Pk" and App "Img App" (via platformdirs), with PK_IMG_APP_HOME as an override. This affects on-disk directory names only, not UI naming.
- Implementation target: [`src/pk_py_lib/core/configuration.py`](src/pk_py_lib/core/configuration.py:1)

### 2) Database Technology and Lifecycle (canonical)

- **Technology**: SQLite for all three databases (settings.db, cache.db, sessions.db)
- **Schema versioning**: Each database contains a `meta` table with `schema_version` field
- **Startup validation sequence**:
  1. Run `PRAGMA quick_check` on each database
  2. If quick_check fails, run `PRAGMA integrity_check`
  3. If integrity_check fails, mark database as corrupt and prompt user for auto-rebuild
  4. For corrupt databases:
     - settings.db: attempt to export/preserve settings if possible
     - cache.db and sessions.db: safe to rebuild from scratch
- **Migration management**:
  - Managed by Alembic
  - Auto-run on startup when version mismatch detected
  - Pre-migration safety: create timestamped backup copy of each database before migrating
- **Backup retention policy**:
  - Keep 10 most recent backups per database
  - Purge backups older than 30 days
  - Backup filename format: `{db_name}.{ISO_timestamp}.v{schema_version}`
- Implementation targets: 
  - [`src/pk_py_lib/core/database.py`](src/pk_py_lib/core/database.py:1)
  - [`tests/test_migrations.py`](tests/test_migrations.py:1)

### 3) Settings Profiles Model (canonical)

- **Core fields**:
  - `id`: UUID (primary key)
  - `name`: unique, required string
  - `description`: optional text
  - `created_at`: timestamp
  - `updated_at`: timestamp
  - `profile_version`: string (for profile format versioning)
- **Pool configuration**:
  - `pool_mode`: "single" or "dual"
  - `inverse_mode`: boolean (only applies when pool_mode="dual")
    - false (default): show pool2 files that match pool1
    - true: show pool1 files that have NO matches in pool2
- **Path set definitions** (per pool):
  - `include_dirs`: list of directories to scan
  - `exclude_dirs`: list of directories to skip
  - `include_globs`: list of glob patterns to include
  - `exclude_globs`: list of glob patterns to exclude
- **File identity detection options**:
  - `hash_algo`: "sha256" (default)
  - `staged_hashing`: boolean (default true)
    - When true: size filter → partial hash → full hash
    - When false: always compute full-file SHA-256
- **Cache invalidation keys**:
  - `absolute_path`
  - `file_size`
  - `mtime_ns`
  - `inode` (where available)
  - Full re-hash only when file signature changes
- Implementation target: [`src/pk_py_lib/api/settings_api.py`](src/pk_py_lib/api/settings_api.py:1)

### 4) File Hashing Strategy (canonical)

- **Algorithm**: SHA-256 for identical file detection
- **Staged hashing pipeline** (when enabled):
  1. **Size filter**: Group files by exact size
  2. **Partial hash**: For files ≥ 512 KiB:
     - Hash first 256 KiB of file
     - Hash last 256 KiB of file
     - Combine as partial signature
  3. **Full hash**: Compute full-file SHA-256 only for candidates with matching partial hashes
- **Cache strategy**:
  - Store both partial and full hashes in cache.db
  - Invalidate cache when file signature changes (size, mtime_ns, inode)
- **For files < 512 KiB**: Skip partial hashing, go directly to full-file SHA-256
- Implementation targets:
  - [`src/pk_py_lib/core/filesystem/identity.py`](src/pk_py_lib/core/filesystem/identity.py:1)
  - [`src/pk_py_lib/core/cache.py`](src/pk_py_lib/core/cache.py:1)

### 5) Results Semantics (canonical)

- **Single pool mode**:
  - Find and group duplicate sets (clusters) within the pool
  - UI displays: cluster header + all member files
  - Each cluster shows: representative thumbnail, member count, total size
- **Dual pool mode (default)**:
  - Pool 1: reference pool
  - Pool 2: search pool
  - Results show only pool2 files that match pool1 files
  - No pool1 files displayed in results
- **Dual pool with inverse mode**:
  - Show only pool1 files that have ZERO matches in pool2
  - Results contain only pool1 files (no pool2 files shown)
  - Useful for finding unique files in reference set
- Implementation target: [`img_app/img_app/widgets/results_panel.py`](img_app/img_app/widgets/results_panel.py:1)

### 6) Settings GUI Behaviors (canonical)

- **CRUD operations**:
  - Create new profile (with name validation)
  - Select/activate existing profile
  - Edit profile (in-place or copy-on-write)
  - Delete profile (with confirmation)
  - Copy/clone profile (with new name)
- **Additional features**:
  - Set as default profile (auto-load on startup)
  - Validate paths on save (warn if non-existent)
  - Preview effective include/exclude paths
  - Test hash settings on small sample
- **Profile management**:
  - Export profile to JSON
  - Import profile from JSON
  - Profile templates/presets for common scenarios
- Implementation target: [`img_app/img_app/widgets/settings_panel.py`](img_app/img_app/widgets/settings_panel.py:1)

### 7) Similarity Thresholds (canonical)

- Internal canonical representation: floating-point values in the inclusive range 0.0 — 1.0.
- User interface representation: percentages (0 — 100%). UI components MUST convert at the boundary.
- Conversion helpers (to implement): 
  - `ui_percent_to_internal(pct: float) -> float`
  - `internal_to_ui_percent(value: float) -> float`
- Reference: [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:20)
- Implementation target: [`src/pk_py_lib/core/utils/thresholds.py`](src/pk_py_lib/core/utils/thresholds.py:1)

### 8) Cache & Thumbnails (canonical)

- Default thumbnail/cache size: 5120 MB (config key: `app_settings.cache_size_mb`).
  - Rationale: prefer explicitly-typed, application-scoped integer megabytes for clarity and portability.
  - Implementations should convert MB → bytes (MB * 1024 * 1024) when allocating limits.
- Per-OS recommended default cache directories (derive via platformdirs user_cache_dir("Img App", "Pk")):
  - Windows: Path.home() / "AppData" / "Local" / "Pk" / "Img App"
  - macOS: Path.home() / "Library" / "Caches" / "Pk" / "Img App"
  - Linux: Path.home() / ".cache" / "Pk" / "Img App"
- Thumbnail storage policy (canonical decision): store thumbnails as files on disk (file-backed cache) under:
  `cache/thumbnails/{size}/{cache_key}.jpg` (example path). The database stores metadata and the relative path to the thumbnail.
- Default thumbnail encoding: JPEG, quality=85, configurable.
- Eviction policy: LRU with a cleanup trigger at 90% of max_size.
- Implementation target (example): [`src/pk_py_lib/core/cache.py`](src/pk_py_lib/core/cache.py:1) and examples in [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1).

### 9) File Identity and Move/Rename Detection (canonical)

- Default mode: "robust" (config key `filesystem.identity.mode = "robust"`).
- Robust algorithm (ordered checks):
  1. Where supported, capture (device, inode) pair at initial discovery and store in DB (`file_device`, `file_inode`).
  2. Compute and store SHA-256 content hash (hex string) for every indexed file.
  3. On file disappearance, search the cache DB for matching SHA-256; if found, treat as same file at new path (record path-history).
  4. If hash not found, but inode/device matches an existing entry on the same device, treat as move/rename.
  5. If none match, treat as new file.
- Configurable option "simple": do not compute persistent content hashes automatically; moved/renamed files are treated as new.
- Implementation target: [`src/pk_py_lib/core/filesystem/identity.py`](src/pk_py_lib/core/filesystem/identity.py:1) and integration points in [`src/pk_py_lib/core/filesystem/traversal.py`](src/pk_py_lib/core/filesystem/traversal.py:1).
- Reference: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:40)

### 10) API Canonicalization: ApiResponse & ErrorCodes

- Canonical `ApiResponse` dataclass fields:
  - `success: bool`
  - `data: Optional[T]`
  - `error: Optional[str]` (human message)
  - `code: Optional[str]` (machine-readable error code)
  - `metadata: Dict[str, Any]`
- Canonical `ErrorCodes` enum values:
  - LOCKED_DB, FILE_MISSING, OUT_OF_MEMORY, PERMISSION_DENIED, CORRUPTED_IMAGE, INVALID_CONFIG, NETWORK_ERROR, TIMEOUT, UNKNOWN_ERROR
- Implementation target: [`src/pk_py_lib/api/__init__.py`](src/pk_py_lib/api/__init__.py:1)
- Reference: [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:18)

### 11) DB Schema Versioning and `meta` Table

- The settings DB MUST contain a `meta` table with at least `schema_version` key on creation.
- On DatabaseManager initialization, create the `meta` table if missing and insert `schema_version = '1.0.0'`.
- Provide a `SchemaManager` helper to manage migrations; include `backup_before_migration()` and rollback guidance.
- Implementation touchpoints: DB create scripts and [`img_app/img_app/data/database.py`](img_app/img_app/data/database.py:1) or library DB helper.
- Reference: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:284)

### 12) Thumbnail Format and Quality

- Default thumbnail format: JPEG with quality 85 for performance/size trade-off.
- Allow override per user profile.

### 13) Telemetry and Privacy

- No telemetry or crash-reporting in Phase 1. The application must operate fully offline by default.
- If telemetry/log upload is added later, it MUST be opt-in and documented; prefer plugin extension approach.

### 14) RAW Format Support

- RAW support is deferred to Phase 2 (not required in M0/M1).

### 15) Benchmarks and Performance Harness

- Provide a simple benchmark harness that measures images/sec for a given algorithm and thumbnail size.
- Implementation target: `tools/benchmarks/bench_images.py` and documented in [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)

### 16) Sample JSON Payloads for API Tests

- Create canonical sample payload files:
  - [`docs/roo/samples/scan_session.json`](docs/roo/samples/scan_session.json:1)
  - [`docs/roo/samples/scan_result.json`](docs/roo/samples/scan_result.json:1)
- These are required for contract tests and examples.

## Developer Action Items (short list)

- Implement `ApiResponse` + `ErrorCodes` in [`src/pk_py_lib/api/__init__.py`](src/pk_py_lib/api/__init__.py:1)
- Add threshold helpers [`src/pk_py_lib/core/utils/thresholds.py`](src/pk_py_lib/core/utils/thresholds.py:1)
- Implement file-backed `CacheManager` [`src/pk_py_lib/core/cache.py`](src/pk_py_lib/core/cache.py:1)
- Implement file identity detection module [`src/pk_py_lib/core/filesystem/identity.py`](src/pk_py_lib/core/filesystem/identity.py:1)
- Ensure DB `meta` creation in DB init (integration test)
- Add platformdirs integration for application data locations
- Implement Alembic migrations with backup strategy
- Create settings profile management API
- Implement staged SHA-256 hashing pipeline
- Add sample payloads and benchmark harness; add unit/integration tests

## Change Control and Acceptance

- Update the canonical decisions file and then propagate references into the spec docs and implementation guide. After code changes are implemented, update the progress ledger (`docs/progress.md` and `docs/progress/features.json`) and run `scripts/progress/generate_dashboard.py` to refresh the dashboard.

## References (selected)

- Specification: [`docs/roo/img-app-specification.md`](docs/roo/img-app-specification.md:20)
- Data model: [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1)
- API spec: [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1)
- Implementation guide: [`docs/roo/img-app-implementation-guide.md`](docs/roo/img-app-implementation-guide.md:1)

Author: Roo (AI coding assistant)
Date: 2025-08-17 (Updated with comprehensive specifications)

End of canonical decisions.
### 17) Settings Profiles and Startup Modal (canonical)

Status: Planned

Scope
- Establish canonical behavior for settings profiles, persistence, naming rules, and application startup gating via a modal Settings/Profile Manager.

Decisions
- Persistence and Active Profile
  - Use SQLite settings.db via [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:405).
  - Store the current session’s active profile id in `meta.active_profile_id` (INTEGER).
  - On first-run with zero profiles: the startup modal MUST require creating a profile and setting it Active before proceeding.
  - When profiles exist but `meta.active_profile_id` is missing:
    - If a Default profile exists (`profiles.is_default=1`), set it Active.
    - Otherwise set the lexicographically-first profile Active.
- Default vs Active Semantics
  - Default: preference for future launches (`profiles.is_default=1`, at most one); does not change automatically when Active changes.
  - Active: the profile in effect for the current session (`meta.active_profile_id`); must be explicitly selected by the startup modal.
  - Setting Default does not implicitly change Active; setting Active does not implicitly change Default.
- Startup Modal Policy
  - The Settings/Profile Manager is shown as a blocking modal before the main window is created.
  - Continue only if a valid Active profile exists (either selected or newly created).
  - Cancel results in application exit, regardless of an existing prior Active; this enforces explicit confirmation each run.
  - Implementation entry: [img_app/img_app/app.py](img_app/img_app/app.py:60).
- Validation and Naming
  - Name: required, 1–64 characters, allowed charset: letters, digits, space, underscore, hyphen.
  - Uniqueness: case-insensitive unique across profiles (enforced by core logic).
  - Thresholds: UI percent 0–100 maps to internal 0.0–1.0 (see [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1)).
- CRUD + Copy Invariants
  - Cannot delete the Active profile; user must switch Active first.
  - Cannot delete the last remaining profile.
  - Copy creates a distinct profile; original remains unmodified.
  - Single Default invariant: setting one profile as Default clears `is_default` for all others.
- Fallback Strategy (rare)
  - If SQLite initialization fails catastrophically, the core may write a temporary JSON fallback (e.g., `profiles.json`) under data_dir to allow proceeding with warnings; auto-import on next successful DB init; log at WARNING.
- Migration and Meta
  - Ensure `meta.active_profile_id` exists; initialize per rules above if missing.
  - No schema change required for MVP; behavior governed by core logic.
- Logging
  - Logger: `pk_py_lib.settings_profiles`.
  - INFO: create/update/delete/copy/set-active/set-default operations (include ids and names).
  - WARNING: validation failures, fallback storage usage.
  - ERROR: database/persistence failures and rollbacks.

Implementation Targets
- Core: [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) — CRUD, validation, meta.active_profile_id, default invariants, integration with [ConfigurationManager.switch_profile()](src/pk_py_lib/core/configuration.py:399).
- API: [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1) — list/create/update/delete/copy/set-active/get-active/validate/export/import.
- GUI: [src/pk_py_lib/gui/settings/profile_manager.py](src/pk_py_lib/gui/settings/profile_manager.py:1) — reusable modal, list/detail layout with search, validation, and action buttons.
- App integration: [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1) — launch modal before creating MainWindow.

References
- UI spec: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1) (Section "Settings/Profile Manager")
- Technical architecture: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1) (Section "Settings Profiles Architecture")
- API spec: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1) (Section "Settings Profiles API")
- Error handling: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:1) (Section "Settings/Profile Manager Errors")
- Implementation guide: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) (Section "Integrating the Settings Manager at Startup")

Next Steps
- Implement core, API, GUI, and app integration per targets above.
- Add tests: unit (core/API), pytest-qt (GUI), and integration (startup gate).