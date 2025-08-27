# KDC Image Organizer (img-app) Project Specification

## Conventions

- Cache size is configured via app_settings.cache_size_mb (units: MB). Do not use max_size_gb, MAX_CACHE_SIZE_GB, or ambiguous "GB" phrasing.
- Thresholds:
  - UI displays values on a 0–100 scale.
  - Internal logic uses 0.0–1.0.
  - Conversions: internal = ui / 100; ui = round(internal * 100).
- File extension tokens must be dot-prefixed (e.g., .png, .jpg, .jpeg, .tiff, .webp).

> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
> This specification acknowledges the new profile-based configuration model for Option A: two pools (A/B), Modes (duplicates vs similarity), Directions (A→B, B→A, A without matches in B, B without matches in A), UI Degree 0–100 normalized to [0.0..1.0], and report-only execution for v1. See data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), API [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md), and decision §18 in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

## 5A. Settings Profiles v1 (Option A) — Profile-based configuration and acceptance

Scope
- Profiles define:
  - Pools: A (required) and B (required only for two-pool scope), each with paths array (directories or files), include/exclude patterns, recurse, max_depth, type filters, optional size/date constraints.
  - Mode: "duplicates" (exact) or "similarity".
  - Criteria:
    - Duplicates: fixed algorithm "blake3" (no degree/threshold).
    - Similarity: "phash" with Degree UI 0–100; internal normalized degree ∈ [0.0..1.0].
  - Scope/Direction:
    - Single-pool: clustering within A.
    - Two-pool: A→B, B→A, A_without_in_B, B_without_in_A.
  - Output: "report_only" in v1 (no file actions).
- Centralized validator (single source of truth) returns ValidationReport with is_valid, errors, warnings, and normalized profile (degree_normalized computed for similarity). The GUI progressively enables/disables controls based on validator outcomes.

Compatibility note (identity hashing)
- For Option A "duplicates" runs, the identity algorithm is BLAKE3 (fixed). Prior mentions of SHA‑256 for identical files in this specification remain applicable to cache identity strategies and non‑Option‑A flows; Option A duplicates explicitly uses BLAKE3 for report generation. See [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md) §18.

Acceptance criteria (Option A overlay)
- Data model: JSON Schema and examples in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md) define profile shape and invariants; UI Degree 0–100 maps to internal [0.0..1.0].
- UI: Progressive states and Resolved configuration preview as specified in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md) 13B; Direction radios shown only when two pools validate; Degree visible only in similarity mode.
- API: Validate endpoint returns normalized view; Run endpoints for duplicates/similarity are report‑only with response shapes as in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md) 13B.
- Architecture: Centralized validator and normalization utilities shared by GUI and core as in [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md) 11B.
- Errors/UX: Validation failures, conflicts, large-scale edge cases, and user guidance are cataloged in [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md) 13B.

Notes
- The legacy sections referencing per‑feature configuration remain historically accurate; Option A introduces the profile‑centric overlay for v1 with report‑only execution.

This specification is synchronized with the detailed specifications under docs/roo and follows all canonical decisions. For full details and exact values/algorithms, see [canonical-decisions.md](docs/roo/canonical-decisions.md).
### 5A.0 Overview and goals

Settings Profiles v1 (Option A) establishes a profile-centric capability for scanning and comparing images with safety-first defaults and centralized validation.

- Two pools (A/B) with single-pool and two-pool scopes
- Modes: duplicates uses fixed BLAKE3 (no degree); similarity uses pHash with Degree UI 0–100 normalized to [0.0..1.0]
- Report-only execution in v1 (no mutations); actions are explicitly out of scope
- Centralized validator is the single source of truth: applies Balanced defaults, enforces invariants, normalizes fields, and emits capability flags for the GUI
- Progressive GUI enable/disable (Set A): initial mode=duplicates, Pool A enabled (empty), Direction disabled until both pools validate; Save/Run gated by validator outcomes; Degree controls enabled only for similarity

Canonical decision (authoritative): see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md)

### 5A.1 Functional scope and user stories

User story: Single-pool duplicates (within A)
- Preconditions
  - Pool A has at least one valid path (directory or file) that exists and is readable
  - Scope.kind = single_pool
  - Mode = duplicates (algorithm fixed BLAKE3)
- Trigger
  - User sets Pool A paths and clicks Run
- Main flow
  - Validator normalizes profile with Balanced defaults and confirms is_valid=true; capability flags allow can_run=true
  - Engine clusters files within Pool A by BLAKE3 equality; returns report-only results
- Acceptance criteria
  - Save enabled when Pool A valid; Run enabled when report.is_valid=true
  - Report includes groups of identical files; no degree fields present
  - Response includes the normalized profile snapshot used (provenance)

User story: Single-pool similarity (within A, degree threshold)
- Preconditions
  - Pool A has at least one valid path (directory or file) that exists and is readable
  - Scope.kind = single_pool
  - Mode = similarity; Degree UI in [0..100] (default 90)
- Trigger
  - User sets Pool A paths and degree threshold and clicks Run
- Main flow
  - Validator applies defaults, computes degree_normalized=degree_ui/100, and confirms is_valid=true; can_run=true
  - Engine groups similar images within Pool A where similarity ≥ degree_normalized
- Acceptance criteria
  - Degree controls visible and enabled; Save/Run gating follows capability flags
  - Report contains groups with similarity values; normalized profile snapshot included

User story: Two-pool duplicates (A→B matches)
- Preconditions
  - Pools A and B have at least one valid path (directory or file) that exists and is readable
  - Scope.kind = two_pool; Direction A_TO_B (default when enabled)
  - Mode = duplicates (algorithm fixed BLAKE3)
- Trigger
  - User sets A and B paths; Direction controls become enabled; user clicks Run
- Main flow
  - Validator enables direction (both pools valid), confirms is_valid=true; can_run=true
  - Engine reports, for each reference item in A, the duplicates found in B (BLAKE3 equality)
- Acceptance criteria
  - Direction defaults to A→B when first enabled; Save/Run enabled only after both pools validate
  - Report lists matches_by_reference; normalized profile snapshot included

User story: Two-pool similarity (A→B matches; “A without matches in B”)
- Preconditions
  - Pools A and B have at least one valid path (directory or file) that exists and is readable
  - Scope.kind = two_pool; Direction either A_TO_B (matches) or A_WITHOUT_IN_B (non-matches)
  - Mode = similarity; Degree UI in [0..100] (default 90)
- Trigger
  - User sets A and B paths; Direction controls enable; user selects A_TO_B or A_WITHOUT_IN_B and clicks Run
- Main flow
  - Validator applies defaults, computes degree_normalized, and confirms is_valid=true; can_run=true
  - Engine either:
    - A→B: returns matches per A reference where similarity ≥ degree_normalized, or
    - A without in B: returns A items with zero matches in B at the threshold
- Acceptance criteria
  - Degree and Direction controls enabled; Save/Run gating follows capability flags
  - Report structure reflects chosen direction; normalized profile snapshot included

### 5A.2 Acceptance criteria (product-level)

Product expression of technical criteria
- Defaults and initial states
  - Balanced defaults + Package A specifics are applied whenever fields are omitted (validator-filled)
  - Set A GUI initial-state overlay: initial mode=duplicates; Pool A enabled; Direction disabled until both pools validate; single_pool_clustering unchecked
- Gating and capability flags
  - Save and Run buttons reflect validator capability flags (can_save, can_run)
  - Direction controls are disabled until both pools validate (can_enable_direction_controls=false); when enabled, default selection is A_TO_B
  - Degree controls enabled only in similarity mode (can_enable_degree_controls=true)
- Provenance
  - All Run responses include the normalized profile snapshot used for execution

Checklist (cross-referenced)
- Data model schema and defaults: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- UI behavior and flows: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API contracts and examples: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Architecture rules and gating: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Tests and migration: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)
- Error taxonomy and UX guidance: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

### 5A.3 Feature details

Pools
- A and B pools each require at least one valid path (directory or file)
- Include/Exclude semantics: gitignore-like glob patterns evaluated relative to each path in the pool; multiline input maps to string arrays
- Traversal defaults: recurse=true; max_depth=0 means unlimited; include_hidden=false; follow_symlinks=false
- File-type defaults: images only — jpg, jpeg, png, webp, tiff, bmp, gif, heic, heif (case-insensitive matching)

Modes & criteria
- Duplicates mode: algorithm fixed to BLAKE3; no degree field allowed
- Similarity mode: algorithm default pHash; degree_ui default=90 (UI scale 0–100); normalization mapping degree_normalized=degree_ui/100 as defined in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- Package A specifics: degree_ui = round(100 * (1 - d/64)) for 64‑bit pHash Hamming distance d; match requires degree_ui ≥ threshold

Direction & scope
- Scope.kind supports single_pool and two_pool
- single_pool_clustering: default false (unchecked)
- Two-pool direction default A_TO_B; direction remains inactive until both pools validate

### 5A.4 Non-functional requirements (v1)

- Execution is report-only; no file mutations
- Safety and gating: Save/Run blocked when required pool paths are missing or unreadable; direction gated until both pools have valid paths
- OS-aware matching: pattern case is OS-aware (Windows insensitive; POSIX sensitive); extension filter matching is case-insensitive on all OS
- Correctness over performance; performance optimizations are out of scope for v1
- Logging and diagnostics (namespace and expectations) follow [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)

### 5A.5 Out of scope (v1)

- N‑pool workflows (beyond two pools)
- Additional similarity algorithms beyond pHash
- Action endpoints (move/delete/copy); v1 is report-only
- Pagination of results
- RAW formats enabled by default

### 5A.6 Glossary and references

Glossary (canonical terms)
- Pool A: primary/reference pool; always requires at least one valid path
- Pool B: secondary/target pool; requires at least one valid path for two-pool scope
- Mode: duplicates (BLAKE3 identity) or similarity (pHash threshold)
- Degree (UI vs normalized): Degree UI is 0–100; normalized degree is degree_ui/100 ∈ [0.0..1.0]
- Direction: A_TO_B, B_TO_A, A_WITHOUT_IN_B, B_WITHOUT_IN_A (two-pool only)
- single_pool_clustering: cluster within Pool A when Scope.kind=single_pool
- Defaults: Balanced defaults + Package A specifics applied by the centralized validator
- Capability flags: validator outputs used by GUI and API (e.g., can_run, can_save, can_enable_direction_controls, can_enable_degree_controls, required_pools)

References
- Canonical decisions: [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md)
- Data model and schema: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- UI design and gating: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API contracts and examples: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Technical architecture and logging: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Implementation plan and tests: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)
- Errors and edge cases: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

## 1. Overview

The KDC Image Organizer (img-app) is a desktop GUI application for organizing very large local photo collections. It focuses on duplicate and near-duplicate detection, safe operations, and reusable library components provided by pk-py-lib.

- Primary goals
  - Detect exact and near-duplicate images
  - Provide single or dual pool comparison modes, including inverse queries
  - Offer safe, non-destructive operations with undo and backups
  - Maintain robust, cache-backed performance for large datasets

## 2. Canonical conventions and references

- Internal similarity values are floats in the range 0.0–1.0; UI shows 0–100%.
- UI brand: “KDC Image Organizer”; platform path identity uses Vendor "Pk" and App "Img App".
- Authoritative ledger of decisions: [canonical-decisions.md](docs/roo/canonical-decisions.md:1)
- Detailed specs: [img-app-specification.md](docs/roo/img-app-specification.md:1), [img-app-data-model.md](docs/roo/img-app-data-model.md:1), [img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1), [img-app-ui-design.md](docs/roo/img-app-ui-design.md:1), [img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1)

## 3. Application startup: database validation and migration

On application start:

1) Ensure databases exist
- settings.db and sessions.db located in platformdirs user_data_dir
- cache.db located in platformdirs user_cache_dir
- PK_IMG_APP_HOME environment variable may override base directories

2) Validate integrity per database
- Run PRAGMA quick_check
- If it fails, run PRAGMA integrity_check
- If integrity_check fails:
  - settings.db: offer to export/preserve settings if possible, then rebuild
  - sessions.db: offer repair or rebuild
  - cache.db: safe to rebuild automatically

3) Check schema version and migrate
- Each DB has meta.schema_version
- If mismatch: create timestamped backup under data/backups, run Alembic migrations, update schema_version
- Backup retention: keep 10 most recent per DB; purge older than 30 days
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:38)

## 4. Application data locations

- Platform directories via platformdirs with Vendor "Pk", App "Img App"
- Override with PK_IMG_APP_HOME; structure:
  - data/: settings.db, sessions.db, backups/
  - cache/: cache.db, thumbnails/ (file-backed thumbnails in size subfolders)
- Per-OS examples (derived via platformdirs):
  - Windows: %LOCALAPPDATA%\Pk\Img App
  - macOS: ~/Library/Caches/Pk/Img App (cache) and ~/Library/Application Support/Pk/Img App (data)
  - Linux: ~/.cache/Pk/Img App (cache) and ~/.local/share/Pk/Img App (data)
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:14)

## 5. Settings profiles and pools

Each settings profile includes:
- id (UUID), name (unique), description, created_at, updated_at, profile_version
- pool_mode: single or dual
- inverse_mode: applies only when pool_mode = dual; shows Pool 1 items with zero matches in Pool 2
- Path configuration per pool: include_dirs, exclude_dirs, include_globs, exclude_globs, follow_symlinks
- Hashing options: hash_algo = sha256; staged_hashing = true; partial_hash_size_kb = 256
- Cache invalidation keys: absolute_path, file_size, mtime_ns, inode (where available)
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:61)

## 6. Identical file detection (exact duplicates)

- Algorithm: SHA-256 content hash
- Staged hashing pipeline (when enabled):
  - Stage 1: Group by exact file size
  - Stage 2: Partial hash for files ≥ 512 KiB
    - Hash first 256 KiB and last 256 KiB; combine as partial signature
  - Stage 3: Full-file SHA-256 only for candidates whose partial signatures match
- Cache strategy:
  - Store both partial and full SHA-256 in cache.db
  - Invalidate when file signature changes (size, mtime_ns, inode)
  - Files < 512 KiB skip partial hashing and go directly to full SHA-256
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:93)

## 7. Results semantics

- Single pool
  - Find and group duplicate/similar sets (clusters) within the pool
  - UI shows cluster header with representative thumbnail, member count, total size, etc., plus all member files

- Dual pools (default)
  - Pool 1 is the reference
  - Results show only Pool 2 files that match Pool 1 (Pool 1 files in headers, not listed standalone)

- Dual inverse
  - Show only Pool 1 items with zero matches in Pool 2; no Pool 2 files listed
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:111)

## 8. Settings GUI behaviors

- CRUD: create, select/activate, edit, delete (with confirmation), copy/clone
- Manage default profile (auto-load on startup)
- Validate paths on save, with warnings for inaccessible paths
- Preview effective include/exclude sets
- Test hash settings on a small sample (show timings, memory, collisions)
- Import/export profiles (JSON); templates/presets supported
- Reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:128), [img-app-ui-design.md](docs/roo/img-app-ui-design.md:183)

## 9. Database technology and schema versioning

- Technology: SQLite (settings.db, sessions.db, cache.db)
- Meta schema_version table in each DB
- Alembic-based migrations with pre-migration backups and retention policy (10 most recent and 30-day purge)
- Reference: [img-app-data-model.md](docs/roo/img-app-data-model.md:287), [img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:442)

## 10. Error handling and recovery highlights

- Startup DB validation and guided recovery flows
- Safe rebuilds for cache; export/preserve attempts for settings
- Centralized error categories and recovery strategies
- Reference: [img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:378)

## 11. Dependencies

- Python 3.13+, PySide6, Pillow, NumPy, OpenCV, scikit-image, imagehash, SQLite3, platformdirs, Alembic
- Reference: [img-app-specification.md](docs/roo/img-app-specification.md:561)

## 12. Acceptance and testing

- Unit tests for algorithms, integration tests for workflows, GUI tests (pytest-qt), performance benchmarking
- Reference: [img-app-specification.md](docs/roo/img-app-specification.md:544)

End of synchronized specification for legacy docs branch.

### 5A.SA Set A — Initial-state defaults overlay (Option A)

Authoritative initial UI defaults (encode verbatim)
- Initial mode: "duplicates"
- Pool A inputs enabled (empty by default)
- Pool B inputs enabled from the start; Direction radios remain disabled until both Pool A and Pool B have valid paths
- single_pool_clustering: unchecked by default
- Save/Run disabled until Pool A has valid paths and the profile passes validation
- When both pools have valid paths and scope.kind="two_pool", Direction radios enable with A_TO_B preselected

Capabilities consumed (validator → GUI)
- capabilities.can_run
- capabilities.can_enable_direction_controls
- capabilities.can_enable_degree_controls
- capabilities.required_pools (array: ["A"] or ["A","B"])
- capabilities.can_save

Token and label normalization (canonical)
- Direction tokens: A_TO_B, B_TO_A, A_WITHOUT_IN_B, B_WITHOUT_IN_A
- Similarity algorithm label: "pHash" (UI/documentation); parameter object key remains "phash" in JSON (e.g., criteria.phash.hash_size)

Cross-references
- UI initial states and capability consumption: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:989)
- API ValidationReport.capabilities (examples for A-only and A+B valid): [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1666)
- Capability derivation and controller mapping: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1459)
- Error cases tied to capabilities (direction gated; run blocked without both pools valid): [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:1564)

Acceptance overlay (verifiable)
- Direction radios disabled until both pools have valid paths; when enabled the default selection is A_TO_B
- Degree controls disabled in duplicates; enabled in similarity (UI 0–100 → internal [0.0..1.0])
- Save enabled when Pool A has valid paths and profile structurally valid; Run enabled only when all required_pools have valid paths
- Normalized preview shows algorithm "pHash", degree_ui (with degree_normalized), and scope.direction as per capability state
