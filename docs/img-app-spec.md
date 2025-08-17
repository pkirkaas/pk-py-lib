# KDC Image Organizer (img-app) Project Specification

This specification is synchronized with the detailed specifications under docs/roo and follows all canonical decisions. For full details and exact values/algorithms, see [canonical-decisions.md](docs/roo/canonical-decisions.md).

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
