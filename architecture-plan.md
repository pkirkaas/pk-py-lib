# PK-Py-Lib Architecture Implementation Plan
> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
> This plan reflects the adoption of a strongly typed Settings Profile model with a centralized validator (single source of truth), Option A algorithms (BLAKE3 for duplicates; pHash for similarity with Degree UI 0–100 normalized to [0.0..1.0]), two-pool directions, and report-only execution in v1. Cross-references: data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), API [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), technical architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md), canonical decision §18 [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

## Executive summary — Settings Profiles v1 (Option A)

Settings Profiles v1 standardizes two pools (Pool A, Pool B) with two Modes: duplicates (fixed BLAKE3) and similarity (pHash). The Degree is entered in the UI as 0–100 and normalized to [0.0..1.0] for processing. v1 runs are report-only. A centralized validator is the single source of truth for schema/defaults/compatibility and emits capability flags that drive progressive GUI enable/disable per Set A initial states (initial Mode=duplicates, Pool A enabled, Direction disabled until both pools validate). **GUI text selectability**: All text elements must be selectable and copyable by mouse to enhance user interaction. Canonical decision: DEC‑SettingsProfilesV1‑OptionA‑Balanced‑PackageA‑SetA in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

## System components and responsibilities

- Data model and JSON Schema (source of truth): [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- Centralized validator and rule engine (defaults + compatibility + capability flags): [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Normalization utilities (degree_ui → degree_norm; Package A degree formula): [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- GUI (Settings Manager) and progressive enable/disable: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API façade (validate → normalize → run → report): [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Error handling and UX patterns: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

Intended implementation locations (design pointers only; no code edits):
- Core schema/validator: [src/pk_py_lib/core/settings/](src/pk_py_lib/core/settings/:1) (manager.py, profiles.py, schema.py)
- API façade: [src/pk_py_lib/api/settings/unified_api.py](src/pk_py_lib/api/settings/unified_api.py:1)
- Legacy API (deprecated): [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1)
- GUI controller: [src/pk_py_lib/gui/settings_manager/controller.py](src/pk_py_lib/gui/settings_manager/controller.py:1)

## End-to-end flows (high-level, non-code)

- Profile authoring
  - Edit in GUI → Validate (centralized) → Normalize (defaults applied; degree_ui→degree_norm) + Capability flags → Save or Run
  - Refs: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Duplicates run (report-only)
  - profile_id or inline JSON → Validate/Normalize → Execute (BLAKE3 exact-identity) → Return groups report
  - Refs: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Similarity run (report-only)
  - profile_id or inline JSON → Validate/Normalize → Direction gating (A→B default when both pools valid) → Return matches (and non-matches when requested)
  - Refs: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md), [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)

## Defaults and gating overview (Balanced + Package A + Set A)

Balanced defaults (v1):
- include = ["**/*"], exclude = [], recurse = true, max_depth = 0 (0 = unlimited)
- include_hidden = false, follow_symlinks = false
- type_filters default image list: [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]

Modes and algorithms:
- mode default "duplicates"
- duplicates algorithm = BLAKE3 (fixed); no degree
- similarity algorithm default "pHash"; degree_ui default = 90
- direction default A→B (inactive until both pools validate)
- single_pool_clustering = false

Package A degree mapping (64-bit pHash):
- degree_ui = round(100 * (1 - d/64)), where d is Hamming distance
- Match rule: a match requires degree_ui ≥ threshold_ui

Set A initial states (GUI):
- mode = "duplicates"
- Pool A enabled (empty)
- Pool B disabled until valid
- Save/Run disabled until Pool A valid
- Direction disabled until both pools validate

## Acceptance criteria alignment

- JSON Schema with defaults present and self‑consistent: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- UI initial states and progressive logic: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API request/response contracts and default‑filling examples: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Technical architecture gating/capabilities and OS/FS semantics: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Tests and migration plan: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)
- Error taxonomy and UX: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

## Out of scope (v1)

- N‑pool comparisons
- Additional similarity algorithms beyond pHash
- Action endpoints (non‑reporting)
- Performance optimizations
- Pagination in API responses
- RAW formats enabled by default

## Roadmap notes

- Next iterations: N‑pool support, extended similarity algorithms, action endpoints, pagination for large results
- Evolve schema versioning alongside changes (profile_version baseline; see [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md))

## Option A Overview — Data Model, Validator, and GUI Enablement (v1)

Scope
- Profiles define Pools A and B with root_path, include/exclude patterns (glob; gitignore-style), recurse and max_depth, type filters, optional size/date constraints. Patterns are evaluated relative to each pool root.
- Modes:
  - Duplicates: fixed algorithm BLAKE3, no degree/threshold.
  - Similarity: pHash, Degree UI 0–100 normalized to [0.0..1.0].
- Two-pool directions: A→B, B→A, A without matches in B, B without matches in A; single-pool clustering supported.
- Output: report-only in v1.

Balanced Defaults — v1 (authoritative)
- Recursion: recurse=true; max_depth=0 means unlimited.
- Symlinks: follow_symlinks=false.
- Hidden files: include_hidden=false (excluded by default).
- File types: images only [.jpg .jpeg .png .webp .tiff .bmp .gif .heic .heif]; RAW off by default.
- Similarity defaults: algorithm="pHash" (64-bit grayscale DCT; hash_size=8), degree_ui=90.
- Duplicates: algorithm="blake3" fixed; no degree.
- Scope/Direction: default kind="two_pool"; direction default "A_TO_B" (selected only when both pools validate).
- Pattern matching case: OS-aware (Windows case-insensitive; POSIX case-sensitive).

Centralized validator
- Single source of truth shared by GUI and core; produces ValidationReport with is_valid, errors, warnings, and a normalized profile view (includes degree_normalized for similarity).
- Applies Balanced defaults to omitted fields; GUI progressive enable/disable states derive exclusively from validator outcomes.

Normalization
- Degree mapping: degree = degree_ui / 100.
- pHash mapping: for hash_size h, max distance D_max = h*h; similarity s = 1 − (d/D_max); match if s ≥ degree.

Implementation notes
- For Option A "duplicates", BLAKE3 supersedes earlier generic identical-file notes in this document. Existing SHA-256 guidance remains relevant for general cache/identity concerns outside Option A runs.
- See detailed JSON Schema, defaults, and examples in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:864).

Acceptance snapshots
- Centralized validator present and invoked by both GUI and API; absent fields normalized with Balanced defaults.
- GUI initial states reflect Balanced defaults (Recurse checked; Max depth=0; Follow symlinks OFF; Hidden OFF; File types preselected; Degree=90 in Similarity).
- single_pool_clustering: unchecked by default.
- Path validation is strict: invalid/missing pool paths block Save/Run until fixed.
- Direction radios: default A→B preselected only when both pools validate; other directions off initially.
- Run endpoints perform report-only execution with response shapes documented in [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1536).
- Pattern engine respects OS-aware case rules (Windows case-insensitive; POSIX case-sensitive).

## Phase 1: Core Structure Setup (Week 1)

### 1.1 Create Base Directory Structure
```bash
src/pk_py_lib/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── filesystem/       # File system operations
│   │   ├── __init__.py
│   │   ├── paths.py      # Path manipulation & validation
│   │   ├── operations.py # File/directory operations
│   │   ├── organization.py # File organization utilities
│   │   └── traversal.py  # Directory walking & filtering
│   │   └── monitoring/   # Real-time file system monitoring
│   │       ├── __init__.py
│   │       ├── watcher.py    # Core file watcher
│   │       ├── events.py     # Event types and handlers
│   │       ├── filters.py    # Event filtering
│   │       └── debounce.py   # Debouncing for rapid changes
│   ├── logging/          # Advanced logging system
│   │   ├── __init__.py
│   │   ├── logger.py     # Core logger with multiple outputs
│   │   ├── outputs/      # Output handlers
│   │   │   ├── __init__.py
│   │   │   ├── console.py    # Terminal output with colors
│   │   │   ├── file.py       # File rotation and management
│   │   │   └── gui.py        # GUI panel integration
│   │   ├── formatters/   # Log formatting
│   │   │   ├── __init__.py
│   │   │   └── rich.py       # Rich formatting
│   │   ├── decorators.py # Function decorators
│   │   └── context.py    # Context managers
│   ├── image/
│   │   └── __init__.py
│   ├── io/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
├── gui/
│   ├── __init__.py
│   ├── widgets/
│   │   └── __init__.py
│   ├── dialogs/
│   │   └── __init__.py
│   └── models/
│       └── __init__.py
├── processing/
│   └── __init__.py
└── cli/
    ├── __init__.py
    └── commands/
        └── __init__.py

showcase/                  # Component showcase application
├── __init__.py
├── app.py                # Main showcase application
├── gallery/              # Component gallery
│   ├── __init__.py
│   ├── browser.py        # Component browser
│   ├── preview.py        # Live preview panel
│   └── inspector.py      # Property inspector
├── examples/             # Example implementations
│   ├── __init__.py
│   ├── widgets/          # Widget examples
│   └── dialogs/          # Dialog examples
└── playground/           # Interactive testing
    ├── __init__.py
    ├── sandbox.py        # Live code editor
    └── recorder.py       # Interaction recorder
```

### 1.2 Update pyproject.toml
- Add PySide6 dependency
- Add core image processing libraries (Pillow, OpenCV, scikit-image)
- Add CLI framework (Click or Typer)
- Configure package discovery

### 1.3 Create Base Classes
- `core/base.py`: Abstract base classes for processors
- `gui/base_widget.py`: Base widget with common functionality
- `processing/base_processor.py`: Base for high-level processors

## Phase 2: Core Functionality (Week 2)

### 2.1 Implement Core File System Operations
- `core/filesystem/paths.py`: Path normalization and deduplication
- `core/filesystem/operations.py`: Safe file operations
- `core/filesystem/traversal.py`: Directory walking utilities
- `core/filesystem/monitoring/watcher.py`: Real-time file monitoring
- `core/logging/logger.py`: Flexible logging system

### 2.2 Implement Core Image Operations
- `core/image/similarity.py`: Basic similarity algorithms
- `core/image/transforms.py`: Image transformations
- `core/io/formats.py`: Format handling

### 2.3 Create First GUI Widgets

- `gui/widgets/image_viewer.py`: Basic image viewer widget
- Include zoom, pan, basic info display

### 2.4 First Processing API
- `processing/duplicate_detection.py`: High-level duplicate finder
- Uses core similarity algorithms

### 2.5 Component Showcase
- `showcase/app.py`: Main showcase application
- `showcase/gallery/browser.py`: Component browser
- Create initial widget examples

## Phase 3: CLI and Examples (Week 3)

### 3.1 CLI Command Structure
- `cli/commands/find_duplicates.py`: First CLI command
- Integrate with processing API

### 3.2 Create Examples
- `examples/gui_examples/simple_viewer.py`
- `examples/processing_examples/find_duplicates.py`

### 3.3 Documentation
- API documentation structure
- First tutorial: "Finding Duplicate Images"

## Phase 4: Testing Infrastructure (Week 4)

### 4.1 Test Structure
```
tests/
├── conftest.py          # Pytest configuration
├── fixtures/            # Test images and data
├── unit/
│   ├── core/
│   ├── processing/
│   └── gui/
└── integration/
```

### 4.2 Core Tests
- Image similarity algorithms
- File I/O operations
- Basic widget functionality

## Implementation Tips

1. **Start Small**: Begin with one complete vertical slice (e.g., duplicate detection from core → processing → CLI)

2. **Consistent Patterns**: Establish patterns early:
   - Error handling strategy
   - Logging approach
   - Configuration management

3. **Documentation First**: Write docstrings as you code
   - Use Google-style docstrings for consistency
   - Include usage examples in docstrings

4. **Type Hints**: Use type hints throughout
   ```python
   from pathlib import Path
   from typing import List, Optional

   def find_duplicates(
       directory: Path,
       threshold: float = 0.95,
       recursive: bool = True
   ) -> List[List[Path]]:
       """Find duplicate images in a directory."""
   ```

## Dependency Recommendations

### Core Dependencies
```toml
[project]
dependencies = [
    "pillow>=10.0.0",           # Image loading/saving
    "numpy>=1.24.0",            # Array operations
    "opencv-python>=4.8.0",     # Advanced image processing
    "scikit-image>=0.22.0",     # Image algorithms
    "imagehash>=4.3.0",         # Perceptual hashing
    "watchdog>=3.0.0",          # Cross-platform file monitoring
    "structlog>=23.0.0",        # Structured logging
    "rich>=13.0.0",             # Rich terminal output
]
```

### GUI Dependencies
```toml
[project.optional-dependencies]
gui = [
    "PySide6>=6.6.0",           # Qt bindings
    "pyqtgraph>=0.13.0",        # Fast image display
]
```

### CLI Dependencies
```toml
[project.optional-dependencies]
cli = [
    "click>=8.1.0",             # CLI framework
    "tqdm>=4.66.0",             # Progress bars
]

dev = [
    "pytest>=7.4.0",            # Testing framework
    "pytest-qt>=4.2.0",         # Qt testing
    "black>=23.0.0",            # Code formatting
    "mypy>=1.5.0",              # Type checking
]
```

## Application: img_app (KDC Image Organizer)

The repository will host a development-only, extractable desktop GUI application named img_app that consumes pk-py-lib components. This colocated app accelerates prototyping and validation of reusable library features while maintaining clean boundaries to enable future extraction to a separate repository with minimal changes.

### Data locations and startup validation (canonical)

- Branding vs internal ID
  - UI brand: KDC Image Organizer
  - Platform paths: Vendor "Pk", App "pk_py_lib" (internal identity for platformdirs)
  - Environment override: PK_PY_LIB_HOME to relocate the unified data directory
  - Canonical reference: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:175) (Data Directory Structure)

- Directory structure and databases
  - settings.db and sessions.db in user_data_dir
  - All runtime data (settings.db, sessions.db, flat_cache.db, logs/, backups/) is located under the unified data directory determined by `platformdirs.user_data_dir("pk_py_lib", "Pk")` or the `PK_PY_LIB_HOME` override.
  - **flat_cache.db** (persistent metadata cache) in user_data_dir - **sole caching solution**
  - backups subfolder under data dir for DB snapshots
  - Thumbnails generated on-demand by Qt (no persistent thumbnail cache)
  - Canonical reference: [img-app-specification.md](docs/roo/img-app-specification.md:54), [img-app-data-model.md](docs/roo/img-app-data-model.md:287)

- Startup validation and migration
  - On app start: ensure DBs exist; run PRAGMA quick_check, then integrity_check on failure
  - If corrupt: settings.db attempts export/preserve, sessions.db prompt to rebuild or repair, cache.db safe to rebuild
  - Schema versioning via meta.schema_version; run Alembic migrations on mismatch
  - Pre-migration backup; retention: keep 10 most recent per DB, purge backups older than 30 days
  - Canonical reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:38)

- Caching Architecture
  - **Sole Cache Solution**: [`FlatCacheManager`](docs/roo/flat-cache-implementation.md:1) provides file-stat validated persistence for all computed hashes (BLAKE3, XXH3, pHash, wHash) and image quality scores
  - **Always Enabled**: FlatCacheManager is the default and only caching mechanism
  - **Validation**: Cache entries validated via file size, mtime, inode, and device ID
  - **Performance**: SQLite with WAL mode for concurrent access
  - **Caching and Computation Optimizations**: To minimize unnecessary calculations in searches, the FlatCacheManager supports a `search_type` parameter ('duplicate' or 'similarity') that controls conditional computations. For 'duplicate' mode, only lightweight XXH3 hashing is performed on all files, skipping perceptual hashes, image dimensions, and quality scores (e.g., BRISQUE) even for images. For 'similarity' mode, full computations (pHash, wHash, XXH3, dimensions, and BRISQUE if enabled) are applied only to image files. This optimization reduces CPU usage by avoiding image decoding and analysis in duplicate workflows, while ensuring comprehensive data for perceptual similarity. The `search_type` is derived from the profile mode and propagated through traversal and similarity functions, with cache entries storing only the required data in the `hash_data` JSON field.
    - **Example Pseudocode for Conditional Caching**:
      ```python
      def compute_and_cache(file_path: str, search_type: str, cache_mgr: FlatCacheManager):
          if search_type == 'duplicate':
              # Minimal: only XXH3 for all files
              xxh3 = compute_xxh3(file_path)
              cache_mgr.set_entry(FlatCacheEntry(path=file_path, hash_data={'xxh3': xxh3}))
          elif search_type == 'similarity':
              if is_image(file_path):
                  # Full: perceptual hashes, dimensions, quality for images
                  phash = compute_phash(file_path)
                  whash = compute_whash(file_path)
                  width, height = get_dimensions(file_path)
                  brisque = compute_brisque(file_path) if quality_enabled else None
                  cache_mgr.set_entry(FlatCacheEntry(
                      path=file_path,
                      width=width, height=height,
                      hash_data={'phash': phash, 'whash': whash, 'xxh3': compute_xxh3(file_path)}
                  ))
              else:
                  # Non-images: only XXH3
                  cache_mgr.set_entry(FlatCacheEntry(path=file_path, hash_data={'xxh3': compute_xxh3(file_path)}))
      ```
    - This approach ensures cache efficiency, with validation checks ensuring stale entries are recomputed only as needed for the current `search_type`.
  - Canonical reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:93)

- Pools and results semantics
  - Single pool: cluster duplicates within the pool
  - Dual pools: show only Pool 2 matches for Pool 1 references
  - Dual inverse: show only Pool 1 items with zero matches in Pool 2
  - Canonical reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:111)

Implementation guidance diagrams
- Startup + migration: see [img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1)
- Staged hashing: see [img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1)
- Results semantics: see [img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1)

### Purpose

- Provide a thin, user-facing PySide6 application shell to exercise and validate pk-py-lib GUI widgets, file system utilities, and future processing APIs
- Establish patterns for integrating library components into full desktop applications
- Serve as a live testbed alongside the showcase for more realistic end-to-end workflows

### Directory Structure

Top-level sibling of src and showcase:

```
img_app/
  img_app/                  # Python package (extractable as-is)
    __init__.py
    app.py                  # QApplication bootstrap, main()
    main_window.py          # QMainWindow subclass (KDC Image Organizer)
    widgets/
      __init__.py
      central_placeholder.py  # Centered label placeholder content
  assets/
    icons/
  docs/
    README.md
  tests/
    __init__.py
    test_smoke.py
  py.typed
  __main__.py               # Optional entry: python -m img_app
```

Rationale:
- Aligns with best practices for app packaging and future extraction
- Keeps UI code confined to the app package, reusing pk-py-lib for shared functionality
- Adds tests/docs/assets co-located for isolated maintenance and portability

### Integration Points with pk-py-lib

- GUI foundations: reuse pk-py-lib GUI widgets and future base frames where appropriate
- File system utilities: traversal, operations, and monitoring from core/filesystem
- Logging: route app logs through pk-py-lib logging facilities for consistency
- Processing: later steps will incorporate pk-py-lib processing APIs (e.g., duplicate detection)

### Invocation

Add a PDM runnable script:

```
[tool.pdm.scripts]
imgapp = {call = "img_app.img_app.app:main"}
```

This allows launching the app with:

```
pdm run imgapp
```

An alternative module entry is available via __main__.py to support:

```
python -m img_app
```

### First Implementation Step (Milestone M0)

- Implement QMainWindow titled "KDC Image Organizer"
- Provide standard menus: File, Cache, View, Help
- Central widget displays a centered text: "The KDC Image Organizer will go here"

### Development Approach

- Incremental vertical slices, keeping img_app thin and delegating functionality to pk-py-lib
- Maintain clear module boundaries and avoid cross-imports from img_app into pk-py-lib
- Ensure all new reusable logic lands in pk-py-lib and is consumed by img_app

### Recent Refactoring: Phase 3 Complete + Settings Consolidation (2025-10-10)

**Status**: ✅ Complete

The project has undergone major refactoring across multiple phases to improve code organization, maintainability, and quality:

#### Settings Architecture Consolidation ✅
**Status**: ✅ Phase 1 Complete (Preparation)

**Overview**: The project has successfully completed Phase 1 of settings consolidation, establishing a unified architecture foundation.

**New Unified Structure**:
- **Core Models**: [`src/pk_py_lib/core/models/settings.py`](../src/pk_py_lib/core/models/settings.py:1)
  - `AppSettings` - Global application configuration
  - `SettingsProfile` - Named profile configurations
  - `DEFAULT_PROFILES` - System default profiles
- **Core Managers**: [`src/pk_py_lib/core/settings/`](../src/pk_py_lib/core/settings/:1)
  - `manager.py` - Unified settings management
  - `profiles.py` - Profile CRUD operations
  - `schema.py` - Schema validation and defaults
- **Unified API**: [`src/pk_py_lib/api/settings/unified_api.py`](../src/pk_py_lib/api/settings/unified_api.py:1)
  - Clean, consistent API for all settings operations
  - Comprehensive error handling and validation
- **Legacy API**: [`src/pk_py_lib/api/settings_profiles.py`](../src/pk_py_lib/api/settings_profiles.py:1)
  - Deprecated wrapper with deprecation warnings
  - Maintains 100% backward compatibility
- **Migration Framework**: [`src/pk_py_lib/core/migrations/settings_migration.py`](../src/pk_py_lib/core/migrations/settings_migration.py:1)
  - Automated migration utilities for Phase 2
  - Backup and rollback capabilities

**Benefits Achieved**:
- ✅ Single source of truth for all settings
- ✅ Consistent data models and validation
- ✅ Clear separation: AppSettings vs SettingsProfile
- ✅ Comprehensive test coverage (45+ tests)
- ✅ 100% backward compatibility maintained
- ✅ Migration path established for Phase 2

**Documentation**:
- [Settings Migration Guide](../docs/roo/settings-migration-guide.md:1) - Complete migration documentation
- [Settings Consolidation Plan](../docs/roo/settings-consolidation-plan.md:1) - Detailed implementation plan
- [Test Suite](../tests/test_unified_settings.py:1) - Comprehensive test coverage with usage examples

**Next Steps**:
- **Phase 2**: Implement actual migration logic (database schema updates)
- **Phase 3**: Update all consumers to new APIs
- **Phase 4**: Remove deprecated code after migration period

---

#### Phase 3 Refactoring Complete ✅

#### Phase 1: Similarity Module Modularization ✅
- **What Changed**: Split monolithic [`_similarity_deprecated.py`](src/pk_py_lib/core/image/_similarity_deprecated.py:1) (2,150 lines) into focused modules
- **New Structure**: [`similarity/`](src/pk_py_lib/core/image/similarity/__init__.py:1) package with 6 specialized modules:
  - [`types.py`](src/pk_py_lib/core/image/similarity/types.py:1) - Shared types and exceptions (99 lines)
  - [`validation.py`](src/pk_py_lib/core/image/similarity/validation.py:1) - Parameter validation (253 lines)
  - [`metadata.py`](src/pk_py_lib/core/image/similarity/metadata.py:1) - Metadata extraction (329 lines)
  - [`hashing.py`](src/pk_py_lib/core/image/similarity/hashing.py:1) - Hash computation (773 lines)
  - [`clustering.py`](src/pk_py_lib/core/image/similarity/clustering.py:1) - Similarity detection (799 lines)
  - [`__init__.py`](src/pk_py_lib/core/image/similarity/__init__.py:1) - Public API (95 lines)
- **Backward Compatibility**: 100% maintained via public API re-exports
- **Documentation**: See [MIGRATION_GUIDE.md](src/pk_py_lib/core/image/MIGRATION_GUIDE.md:1)

#### Phase 2: Cache Architecture Consolidation ✅
- **What Changed**: Removed legacy CacheManager (433 lines) and unified on FlatCacheManager
- **Benefits**: Single caching solution, eliminated architectural confusion
- **Documentation**: See [`cache-migration-completion.md`](docs/roo/cache-migration-completion.md:1)

#### Phase 3: Code Quality Improvements ✅
- **Hash Computation Utilities**: Created [`hash_utils.py`](src/pk_py_lib/core/image/similarity/hash_utils.py:1) (267 lines) and [`algorithm_utils.py`](src/pk_py_lib/core/image/similarity/algorithm_utils.py:1) (285 lines)
- **Phase-Based Architecture**: Created [`phases.py`](src/pk_py_lib/core/image/similarity/phases.py:1) (580 lines) with 4 distinct processing phases
- **Code Duplication**: Reduced from ~40% to <10%
- **Function Complexity**: find_similar_images simplified from 235 lines to ~50 lines
- **Test Coverage**: Added 76 new tests (54 utilities + 22 phases)
- **Dead Code Cleanup**: Removed all LSH references and organized test files
- **Documentation**: See [`phase3-implementation-plan.md`](docs/roo/phase3-implementation-plan.md:1)

#### Updated Similarity Module Structure
The similarity module now contains 9 focused modules with clear separation of concerns:

**Core Modules**:
- [`types.py`](src/pk_py_lib/core/image/similarity/types.py:1) - Shared types and exceptions (99 lines)
- [`validation.py`](src/pk_py_lib/core/image/similarity/validation.py:1) - Parameter validation (253 lines)
- [`metadata.py`](src/pk_py_lib/core/image/similarity/metadata.py:1) - Metadata extraction (329 lines)

**Computation Modules**:
- [`hashing.py`](src/pk_py_lib/core/image/similarity/hashing.py:1) - Hash computation (773 lines)
- [`hash_utils.py`](src/pk_py_lib/core/image/similarity/hash_utils.py:1) - Common hash utilities (267 lines)
- [`algorithm_utils.py`](src/pk_py_lib/core/image/similarity/algorithm_utils.py:1) - Algorithm management (285 lines)

**Processing Modules**:
- [`clustering.py`](src/pk_py_lib/core/image/similarity/clustering.py:1) - Similarity detection (799 lines)
- [`phases.py`](src/pk_py_lib/core/image/similarity/phases.py:1) - Phase-based processing (580 lines)

**Interface**:
- [`__init__.py`](src/pk_py_lib/core/image/similarity/__init__.py:1) - Public API (95 lines)

**Total**: 3,380 lines across 9 focused modules (vs 2,150 lines monolithic)

#### GUI Models Consolidation ✅
- **What Changed**: Consolidated duplicate classes from `dialog_models.py` and [`models.py`](src/pk_py_lib/gui/models.py:1)
- **Canonical Source**: [`models.py`](src/pk_py_lib/gui/models.py:1) is now the single source of truth for FileItem, GroupStats, DialogView
- **Backward Compatibility**: Maintained via deprecated wrapper with warnings in [`dialog_models.py`](src/pk_py_lib/gui/dialog_models.py:1)
- **Documentation**: See [gui-models-consolidation.md](docs/roo/gui-models-consolidation.md:1)

#### Overall Benefits
- **Code Organization**: Clear separation of concerns across 9 focused modules
- **Maintainability**: Files now 99-799 lines vs 2,150-line monolith
- **Testability**: Individual modules and phases can be tested independently
- **Code Quality**: Eliminated ~40% duplication, improved function complexity
- **Documentation**: Comprehensive test coverage (150+ tests including 76 new tests)
- **Architecture**: Phase-based processing enables better error handling and reusability

#### Testing & Verification
- ✅ Application starts without errors
- ✅ All imports resolve correctly
- ✅ Full functionality preserved
- ✅ Similarity finding works correctly with new phase-based architecture
- ✅ Duplicate detection works correctly
- ✅ All 150+ tests passing (including 76 new tests)

For complete details, see [`docs/refactoring-summary.md`](docs/refactoring-summary.md:1)

---

### Image Processing and Similarity

The image processing pipeline leverages OpenCV, Pillow, and imagehash for perceptual similarity detection, with BLAKE3 for exact duplicates. The similarity functionality is now organized in a modular structure under [`src/pk_py_lib/core/image/similarity/`](src/pk_py_lib/core/image/similarity/__init__.py:1). Key optimizations include conditional computations via `search_type` to ensure efficiency:

- **Efficiency via search_type**: In 'duplicate' mode, no image operations (e.g., decoding, perceptual hashing, or quality assessment) are performed, even on image files—only fast XXH3 hashing is used for content identity. This avoids unnecessary CPU-intensive tasks like DCT transforms for pHash/wHash or BRISQUE scoring. In 'similarity' mode, full caching and computation (pHash, wHash, dimensions, BRISQUE if active) are applied selectively to image files only, enabling accurate visual similarity grouping while skipping non-images. The FlatCacheManager integrates this by storing conditional data, reducing recomputation on subsequent runs and minimizing I/O for large directories.

- **Pipeline Flow**:
  1. Traversal (`scan_directory` in [`traversal.py`](src/pk_py_lib/core/filesystem/traversal.py)) uses `search_type` to compute minimal or full metadata via FlatCacheManager.
  2. Similarity computation (`find_similar_images` in [`similarity.py`](src/pk_py_lib/core/image/similarity.py)) retrieves perceptual hashes from cache, applying Hamming distance thresholds normalized from the profile's degree_ui.
  3. Quality filtering (optional): BRISQUE scores from cache can filter low-quality matches pre-grouping.

- **Example Pseudocode for Similarity Processing**:
  ```python
  def process_similarity(profile: SettingsProfile, cache_mgr: FlatCacheManager):
      search_type = 'similarity' if profile.mode == 'similarity' else 'duplicate'
      files_data = scan_directory(profile.pool_a.root_path, search_type=search_type, cache_mgr=cache_mgr)

      # For similarity: use perceptual hashes
      groups = []
      for file1 in files_data:
          for file2 in files_data:
              if file1.path != file2.path:
                  phash1 = cache_mgr.get_hashes(file1.path, search_type)['phash']
                  phash2 = cache_mgr.get_hashes(file2.path, search_type)['phash']
                  distance = hamming_distance(phash1, phash2)
                  similarity_score = 1 - (distance / 64)  # For 64-bit pHash
                  if similarity_score >= profile.degree_normalized:
                      groups.append([file1.path, file2.path])
                      # Optional: Filter by BRISQUE if quality_enabled
                      if profile.quality_enabled:
                          brisque1 = cache_mgr.get_entry(file1.path).hash_data['brisque_score']
                          if brisque1 < threshold:
                              continue  # Skip low-quality images
      return groups
  ```

This design ensures scalable processing, with cache hits accelerating repeated scans.

### Integration with MainWindow, ScanWorker, and Widgets

The asynchronous workflow in [`MainWindow`](img_app/img_app/main_window.py) integrates the conditional caching seamlessly:

- **ScanWorker**: This QThread (defined in MainWindow) executes `scan_directory` with the profile-derived `search_type`, passing the FlatCacheManager for optimized hashing/metadata extraction. Progress updates reflect conditional computations (e.g., "Hashing files (XXH3 only)" for duplicates vs. "Analyzing images (pHash + quality)" for similarity). Upon completion, it emits scanned files/hashes to the orchestrator.

- **ComparisonWorker**: Builds on ScanWorker results, using `search_type` to perform grouping (exact matches for duplicates via XXH3/BLAKE3; perceptual via pHash). It integrates with the cache for quick lookups, emitting final groups to the MainWindow.

- **Widgets Integration**:
  - **DuplicateManager** ([img_app/img_app/widgets/duplicate_manager.py](img_app/img_app/widgets/duplicate_manager.py)): Receives duplicate groups from ComparisonWorker, displaying them in a tree view with selection states. It queries the cache for additional metadata (e.g., file sizes) but relies on pre-computed XXH3 for grouping.
  - **SimilarityManager** ([img_app/img_app/widgets/similarity_manager.py](img_app/img_app/widgets/similarity_manager.py)): Handles similarity results, showing perceptual scores and optional BRISQUE filters. It uses cache-retrieved dimensions and hashes for previews/sorting, with custom painting for consistent UI across platforms.
  - Both widgets support text selectability in reports and integrate with the collapsible Summary/Report pane in BaseFileManagerDialog for detailed outputs.

This integration ensures the GUI remains responsive during scans, with results flowing directly to specialized managers for user interaction (e.g., selection, deletion, reporting).

## Next Steps

1. Review and adjust this plan based on your priorities
2. Set up the basic structure
3. Implement the first vertical slice
4. Iterate based on what you learn
5. Add img_app plan and scaffolding per sections above

## Settings/Profile Manager (References)

Status: Implemented (Integrated)

Brief
- The application now launches directly with settings management integrated into the main window. Profile selection and management occur within the main application interface instead of a separate modal dialog. Active profile semantics and validation rules remain canonicalized. This section cross-references the updated design and does not duplicate content.

Cross-References
- UI design and flows: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1) (Section "Settings/Profile Manager")
- Technical architecture: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1) (Section "Settings Profiles Architecture")
- API contract: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1) (Section "Settings Profiles API")
- Error handling: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:1) (Section "Settings/Profile Manager Errors and Edge Cases")
- Implementation steps: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) (Section "Integrating Settings Management in Main Window")
- Canonical decisions: [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:1) (Section "Settings Profiles and Integrated Management")

Implementation Status
- Unified settings architecture implemented:
  - Core models: [src/pk_py_lib/core/models/settings.py](src/pk_py_lib/core/models/settings.py:1) (AppSettings, SettingsProfile)
  - Core managers: [src/pk_py_lib/core/settings/](src/pk_py_lib/core/settings/:1) (manager.py, profiles.py, schema.py)
  - Unified API: [src/pk_py_lib/api/settings/unified_api.py](src/pk_py_lib/api/settings/unified_api.py:1)
  - Legacy API (deprecated): [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1)
- Settings management integrated into main window: [img_app/img_app/main_window.py](img_app/img_app/main_window.py:1)
- App bootstrap updated for direct launch: [img_app/img_app/app.py](img_app/img_app/app.py:60)
- Migration framework: [src/pk_py_lib/core/migrations/settings_migration.py](src/pk_py_lib/core/migrations/settings_migration.py:1)
- Tests: comprehensive test suite in [tests/test_unified_settings.py](tests/test_unified_settings.py:1)

## Settings Manager — Integrated Architecture and Cross-References (Updated)

Status: Implemented (Integrated)

Summary
- The application now launches directly with settings management fully integrated into the main window interface. Users can select, create, copy, and manage profiles directly from the main application without a blocking modal dialog.

Library implementation
- Core and API implemented:
  - [UnifiedSettingsAPI](src/pk_py_lib/api/settings/unified_api.py:1) — Clean, consistent settings API
  - [SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69) — Legacy API (deprecated, with warnings)
  - Active persistence via `meta.active_profile_id` managed in [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:415) and core manager logic
- GUI components available for reuse:
  - [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1) — Standalone dialog (optional use)
  - [src/pk_py_lib/gui/settings_manager/controller.py](src/pk_py_lib/gui/settings_manager/controller.py:1)
  - [src/pk_py_lib/gui/settings_manager/models.py](src/pk_py_lib/gui/settings_manager/models.py:1)
  - [src/pk_py_lib/gui/settings_manager/validators.py](src/pk_py_lib/gui/settings_manager/validators.py:1)

App integration
- Main window integration: [img_app/img_app/main_window.py](img_app/img_app/main_window.py:1) — Profile management UI with combobox, create/copy buttons, and progress reporting
- App bootstrap: [img_app/img_app/app.py](img_app/img_app/app.py:60) — Direct launch with active profile loading
  - Supports CLI flag `-d`/`--default` to automatically trigger the active profile's operation (`_on_start`) upon GUI launch.
- Profile operations occur through the API respecting all invariants
- `meta.active_profile_id` is set consistently; list responses include `is_active`

Acceptance criteria (updated architecture-level)
- Application launches directly to main window with integrated settings management
- Profile selection and management available without modal dialogs
- All profile operations occur through the API and respect invariants (no direct DB in GUI)
- Active profile is persisted and restored on launch
- Progress reporting and results display integrated into main interface

Cross-references
- UI design and flows: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1) (Section "Integrated Settings Management")
- Technical architecture details: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1) (Section "Integrated Settings Architecture")
- API contract: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1) (Section "Settings Profiles API")
- Errors and edge cases: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:1) (Section "Integrated Settings Management")
- Implementation steps: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) (Section "Integrating Settings Management in Main Window")
- Canonical decisions: [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:1) (Section "Settings Profiles and Integrated Management")

## Addendum — Package A specifics alignment (Option A, Balanced Defaults v1)

This addendum records the Package A specifics adopted for v1 and serves as acceptance criteria overlays:

- Include/Exclude defaults
  - include = ["**/*"]
  - exclude = []
  - Hidden handled via attribute: include_hidden=false by default (do not use patterns to hide)
- Extension filter: case-insensitive on all operating systems
- Pattern matching case: OS-aware (case-insensitive on Windows; case-sensitive on POSIX)
- Similarity (pHash)
  - Default algorithm: "pHash"; default degree_ui: 90
  - Degree formula (64-bit pHash): degree_ui = round(100 * (1 - d/64)), where d is Hamming distance
  - Match rule: a match requires degree_ui ≥ threshold_ui
- Path validation gating
  - Save/Run is blocked by the validator when any required pool path is missing or unreadable

References
- Data model and JSON Schema defaults: [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- UI initial states and UX rules: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- API validation/normalization semantics: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- Technical architecture (OS-aware matching, defaults SOoT): [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- Errors (blocking behavior): [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)

---
## Image Similarity Manager — Selection State Architecture (Minimal Fix, 2025-09-20)

Summary
- Implemented a targeted fix to resolve:
  - Left pane "Select" column not visibly reflecting selection
  - Cross-group selections appearing to clear unexpectedly
- Retained the existing single-source-of-truth as a global set: self.selected_images
- Deferred a full SelectionStore refactor; documented next-steps below
- **Custom painting now handled by [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159)** for consistent visual rendering

Core Source and Flow
- Source of truth:
  - self.selected_images (Set[str]) maintained by [python.ImageSimilarityManagerDialog](img_app/img_app/widgets/duplicate_manager.py:1)
- Right preview pane → state mutation:
  - [python.ImageSimilarityManagerDialog._on_checkbox_toggled()](img_app/img_app/widgets/duplicate_manager.py:831)
  - Calls [_sync_tree_from_selections](img_app/img_app/widgets/duplicate_manager.py:999) and [_update_preview_checkboxes](img_app/img_app/widgets/duplicate_manager.py:1034)
- Left tree pane → state mutation:
  - [python.ImageSimilarityManagerDialog._on_tree_item_changed()](img_app/img_app/widgets/duplicate_manager.py:1052)
  - Uses [_update_group_checkstate](img_app/img_app/widgets/duplicate_manager.py:966) for tri-state parent; then syncs

UI/UX Adjustments (Minimal Fix)
- Checkbox visibility and clickability in left tree:
  - Enforce header min width and disable stretch:
    - header.setMinimumSectionSize(28), header.resizeSection(0, 28), header.setStretchLastSection(False) in [python.ImageSimilarityManagerDialog.__init__()](img_app/img_app/widgets/duplicate_manager.py:489)
  - **Custom painting by [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159)** for reliable render and toggling:
    - [`GroupTreeDelegate.paint()`](img_app/img_app/widgets/base_group_manager.py:180) handles all visual rendering with custom backgrounds and text
    - [`GroupTreeDelegate.sizeHint()`](img_app/img_app/widgets/base_group_manager.py:374) ensures proper sizing for checkbox column
    - [`GroupTreeDelegate.editorEvent()`](img_app/img_app/widgets/base_group_manager.py:385) manages mouse and keyboard interaction
    - [`GroupTreeDelegate._indicator_rect()`](img_app/img_app/widgets/base_group_manager.py:229) computes checkbox geometry
  - Tri-state and user-checkable flags:
    - Groups: Qt.ItemIsUserCheckable | Qt.ItemIsTristate | Qt.ItemIsEnabled at [python.ImageSimilarityManagerDialog._populate_tree()](img_app/img_app/widgets/duplicate_manager.py:731)
    - Children: Qt.ItemIsUserCheckable | Qt.ItemIsEnabled at [python.ImageSimilarityManagerDialog._populate_tree()](img_app/img_app/widgets/duplicate_manager.py:735)
- Selection persistence and delete semantics:
  - Delete removes only deleted entries from selection: [python.ImageSimilarityManagerDialog._on_delete_clicked()](img_app/img_app/widgets/duplicate_manager.py:864)
  - Optional explicit clear controlled by footer checkbox: [python.ImageSimilarityManagerDialog.__init__()](img_app/img_app/widgets/duplicate_manager.py:595), [python.ImageSimilarityManagerDialog._on_delete_clicked()](img_app/img_app/widgets/duplicate_manager.py:869)
- Recompute/refresh behavior:
  - Post-populate synchronization without clearing: [python.ImageSimilarityManagerDialog._compute_groups()](img_app/img_app/widgets/duplicate_manager.py:676), [python.ImageSimilarityManagerDialog._refresh_groups()](img_app/img_app/widgets/duplicate_manager.py:907)

Acceptance Criteria
- Left "Select" column checkboxes clearly visible and toggle reliably (group tri-state correct)
- Cross-pane synchronization (left/right) remains consistent
- Selections persist across groups and user actions; only deleted items are removed from selection unless explicit clear is requested
- Recompute preserves selection for items still present by path
- **Visual rendering consistent across different system themes and platforms**

Manual Verification
- Launch app (pdm run imgapp), open the dialog
- Select in Group A, then Group B; return to Group A: selections persist
- Delete with the footer checkbox OFF: only deleted items removed from selection
- Delete with the footer checkbox ON: all selections cleared post delete
- Press "Compute Groups": selections still present by path remain selected
- **Verify consistent visual appearance across Windows, macOS, and Linux themes**

Forward Plan — Clean Refactor (Next Step)
- Introduce SelectionStore (QObject) with signals (added/removed/cleared/changed)
- Convert views to model/view (QTreeView/QTableView) exposing Qt.CheckStateRole (tri-state for groups)
- Unidirectional data flow: user action → SelectionStore → models → views
- Identity normalization via Path(path).resolve(); future: content-hash
- See proposed API in [docs/roo/img-similarity-details.md](docs/roo/img-similarity-details.md)

---
## Custom Painting Architecture

### Overview
The custom painting architecture provides theme-independent, consistent visual rendering for group list tables across all platforms. Implemented by [`GroupTreeDelegate`](img_app/img_app/widgets/base_group_manager.py:159), this approach ensures reliable visual feedback for selection, hover, and focus states regardless of system theme settings.

### Design Rationale
- **Theme Independence**: Qt's default item rendering varies significantly across platforms (Windows, macOS, Linux) and themes, leading to inconsistent user experiences
- **Visual Clarity**: Custom painting guarantees clear visibility of selection states and text contrast
- **Performance Optimization**: Eliminates redundant text rendering that caused doubled-text issues
- **Accessibility**: Ensures high contrast and clear visual feedback for all interaction states

### Core Painting Methods

#### [`_paint_text_cell()`](img_app/img_app/widgets/base_group_manager.py:351)
- **Purpose**: Main coordinator for text column painting
- **Responsibilities**:
  - Orchestrates background, text, and focus indicator rendering
  - Eliminates reliance on `super().paint()` for text columns
  - Ensures consistent visual hierarchy across all columns

#### [`_draw_cell_background()`](img_app/img_app/widgets/base_group_manager.py:238)
- **Purpose**: Render cell backgrounds with proper visual states
- **Features**:
  - Uses Qt's style APIs for consistent look across themes
  - Handles group vs child item differentiation
  - Manages selection, hover, focus, and disabled states
  - Provides consistent background colors regardless of system theme

#### [`_draw_cell_text()`](img_app/img_app/widgets/base_group_manager.py:268)
- **Purpose**: Draw text content with proper styling and alignment
- **Capabilities**:
  - Handles text elision for long content
  - Applies appropriate text colors based on selection state
  - Uses custom font styling (bold for group headers)
  - Respects column-specific text alignment
  - Ensures high contrast readability

#### [`_draw_focus_indicator()`](img_app/img_app/widgets/base_group_manager.py:314)
- **Purpose**: Visual feedback for keyboard navigation
- **Implementation**:
  - Draws dotted border around focused items
  - Only activates when `State_HasFocus` is set
  - Uses consistent dotted line style matching Qt defaults

### Visual State Management

#### Background Colors
- **Group Headers**: Light gray (#fafafa) for visual hierarchy
- **Child Items**: White background for content clarity
- **Selection**: Blue (#4a90e2) with white text for high contrast
- **Hover**: Uses Qt's native hover state rendering

#### Text Styling
- **Group Headers**: Bold dark text (#333333) for emphasis
- **Child Items**: Standard dark text (#111111) for readability
- **Selected Items**: White text with bold styling for groups
- **Alignment**: Column-specific alignment (right for numeric, left for text)

### Checkbox Column (Column 0) Specialization
- **Custom Painting**: Direct rendering of checkbox indicators
- **Three States**: Checked (blue with white check), PartiallyChecked (yellow with black dash), Unchecked (white with gray border)
- **Interactive**: Mouse and keyboard toggling via [`editorEvent()`](img_app/img_app/widgets/base_group_manager.py:385)
- **Geometry**: Proper sizing via [`sizeHint()`](img_app/img_app/widgets/base_group_manager.py:374)

### Benefits and Impact

#### Consistency
- Uniform appearance across Windows, macOS, and Linux
- No dependency on system theme settings
- Predictable visual behavior in all environments

#### Accessibility
- Clear visual feedback for all interaction states
- High contrast text and background combinations
- Consistent focus indicators for keyboard navigation

#### Performance
- Eliminated doubled-text rendering issue
- Optimized painting without redundant operations
- Efficient state management and rendering

#### Maintainability
- Centralized painting logic in single delegate class
- Clear separation of concerns between painting methods
- Easy to extend or modify visual appearance

### Integration Points
- Used by both [`DuplicateManager`](img_app/img_app/widgets/duplicate_manager.py) and [`SimilarityManager`](img_app/img_app/widgets/similarity_manager.py)
- Inherited by [`BaseImageGroupManagerDialog`](img_app/img_app/widgets/base_group_manager.py:433)
- Provides consistent visual foundation for all group management dialogs

This custom painting architecture represents a significant improvement in visual consistency and user experience, ensuring that the application maintains a professional appearance across all supported platforms and themes.

---
## BaseFileManagerDialog — Collapsible Summary/Report Pane Architecture (2025-09-29)

Summary
- The shared `BaseFileManagerDialog` (used by `Duplicate File Manager` and `Similar Image Manager`) has been refactored to make the top "Summary Report Pane" collapsible.
- This pane is now structurally separated into a visible header and a collapsible content area, managed by a `QSplitter`.

Architecture Details
- **Main Layout**: The dialog uses a `QSplitter` (vertical) to divide the layout into two main sections:
  1. Top Pane: Contains the Summary/Report header and content. This pane is set to be collapsible (`QSplitter.setCollapsible(0, True)`).
  2. Content Area: Contains subclass-specific controls and the main results view (e.g., image group tree).
- **Header Component**: The header remains visible even when collapsed and contains:
  - A `QTabBar` for switching between "Summary" and "Report" views.
  - A `QToolButton` (`self._collapse_button`) which toggles the visibility of the content area below it.
- **Content Component**: The content area of the Summary/Report pane is a `QStackedWidget` (`self._tab_content_stack`) containing the `QTextEdit` widgets for Summary and Report output.
- **Collapse Mechanism**:
  - The `QToolButton`'s `clicked` signal is connected to `_toggle_collapse()`.
  - `_toggle_collapse()` toggles the visibility of the `QStackedWidget` (`self._tab_content_stack.setVisible()`) and updates the `QToolButton`'s arrow icon (UpArrow for expanded, DownArrow for collapsed).
- **Text Selectability**: Both the Summary and Report `QTextEdit` widgets maintain the project requirement for selectable text (`Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard`).

Implementation Reference
- [src/pk_py_lib/gui/dialogs/base_file_manager_dialog.py](src/pk_py_lib/gui/dialogs/base_file_manager_dialog.py:109) (`_build_ui` and `_build_tabs` methods)

## Asynchronous Scan and Comparison Workflow with Progress Dialog (2025-09-29)

Summary
- The application's core operations (file scanning/hashing and image comparison) are now executed asynchronously using dedicated `QThread` workers to prevent GUI blocking.
- A reusable modal dialog, `ProgressDialog`, provides real-time progress updates and supports cooperative cancellation for long-running tasks.
- The `MainWindow` orchestrates the sequential execution of the two main phases: scanning and comparison, with conditional optimizations via `search_type` integrated into the workers.

### Components and Responsibilities

#### 1. [`ProgressDialog`](src/pk_py_lib/gui/dialogs/progress_dialog.py)
- **Role**: A modal, reusable dialog that displays task progress (percentage, current file/status text) and provides a "Cancel" button.
- **Mechanism**: It manages a `threading.Event` (`stop_event`) which is passed to the worker threads. Clicking "Cancel" sets this event, signaling the worker to stop cooperatively.
- **Signals**: Emits signals to update the progress bar and status text from the worker thread.

#### 2. `ScanWorker` (QThread subclass, defined in [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py))
- **Role**: Executes the file system traversal and hashing phase, with conditional computations based on `search_type`.
- **Core Logic**: Calls the updated [`scan_directory`](src/pk_py_lib/core/filesystem/traversal.py) function, passing a `progress_callback` (to report progress back to the GUI), the `stop_event` (for cancellation), and `search_type` (derived from profile mode) to the FlatCacheManager for optimized metadata extraction (e.g., XXH3 only for duplicates).
- **Output**: Emits a signal upon completion, carrying the list of scanned files/hashes (conditional on `search_type`), or an error/cancellation status.

#### 3. `ComparisonWorker` (QThread subclass, defined in [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py))
- **Role**: Executes the image comparison phase (e.g., pHash similarity or BLAKE3 duplicates) on the results from the `ScanWorker`, using cache-retrieved data tailored to `search_type`.
- **Core Logic**: Performs the comparison logic, respecting the `stop_event` for cooperative cancellation and using a progress callback for updates. For 'similarity', it leverages perceptual hashes and quality scores from the cache; for 'duplicate', it uses exact hash matches.
- **Output**: Emits a signal upon completion, carrying the final results (groups of similar/duplicate images).

#### 4. [`MainWindow`](img_app/img_app/main_window.py)
- **Role**: The central orchestrator of the asynchronous workflow, mapping profile mode to `search_type` and passing it to workers.
- **Orchestration Flow**:
  1. User triggers the operation (e.g., clicks "Run").
  2. `MainWindow` instantiates and shows the `ProgressDialog`.
  3. `MainWindow` instantiates `ScanWorker` with `search_type` (e.g., 'duplicate' for BLAKE3 mode), connects its signals to the `ProgressDialog` for updates, and starts the thread.
  4. Upon `ScanWorker` completion (success or cancellation):
     - If successful, `MainWindow` instantiates `ComparisonWorker` with the same `search_type`, connects its signals, and starts the thread, reusing the `ProgressDialog`.
     - If cancelled or failed, the `ProgressDialog` is closed, and an appropriate message is displayed.
  5. Upon `ComparisonWorker` completion:
     - The `ProgressDialog` is closed.
     - The results (or error) are passed to the appropriate results manager dialog (`Duplicate File Manager` or `Similar Image Manager`), which display groups using cache metadata.

### Workflow Diagram (Simplified)

```mermaid
graph TD
    A[MainWindow: Run Operation] --> B(Instantiate & Show ProgressDialog);
    B --> C(Instantiate ScanWorker with search_type);
    C --> D{ScanWorker: Start Thread};
    D --> E[ScanWorker: Traversal & Conditional Hashing];
    E -- Progress/Status --> B;
    E -- Cancellation Request --> E;
    E -- Success --> F(MainWindow: Scan Complete);
    E -- Failure/Cancel --> K(MainWindow: Handle Error/Cancel);
    F --> G(Instantiate ComparisonWorker with search_type);
    G --> H{ComparisonWorker: Start Thread};
    H --> I[ComparisonWorker: Conditional Image Comparison];
    I -- Progress/Status --> B;
    I -- Cancellation Request --> I;
    I -- Success --> J(MainWindow: Comparison Complete);
    I -- Failure/Cancel --> K;
    J --> L(Close ProgressDialog);
    J --> M(Show Results Manager Dialog: duplicate_manager or similarity_manager);
    K --> L;
```

### Implementation References
- `ProgressDialog` definition: [`src/pk_py_lib/gui/dialogs/progress_dialog.py`](src/pk_py_lib/gui/dialogs/progress_dialog.py)
- `scan_directory` update (progress/cancellation support with search_type): [`src/pk_py_lib/core/filesystem/traversal.py`](src/pk_py_lib/core/filesystem/traversal.py)
- `MainWindow` orchestration and worker definitions (with search_type integration): [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py)
