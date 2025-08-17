# PK-Py-Lib Architecture Implementation Plan

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
│   │   ├── traversal.py  # Directory walking & filtering
│   │   ├── safety.py     # Safe operations with rollback
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
│   │   │   ├── gui.py        # GUI panel integration
│   │   │   └── database.py   # DB logging (future)
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
  - Platform paths: Vendor "Pk", App "Img App" (internal identity for platformdirs)
  - Environment override: PK_IMG_APP_HOME to relocate both data and cache trees
  - Canonical reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:14)

- Directory structure and databases
  - settings.db and sessions.db in user_data_dir
  - cache.db in user_cache_dir
  - backups subfolder under data dir for DB snapshots
  - Thumbnails stored on disk under cache/thumbnails/{size}/; database stores metadata
  - Canonical reference: [img-app-specification.md](docs/roo/img-app-specification.md:54), [img-app-data-model.md](docs/roo/img-app-data-model.md:287)

- Startup validation and migration
  - On app start: ensure DBs exist; run PRAGMA quick_check, then integrity_check on failure
  - If corrupt: settings.db attempts export/preserve, sessions.db prompt to rebuild or repair, cache.db safe to rebuild
  - Schema versioning via meta.schema_version; run Alembic migrations on mismatch
  - Pre-migration backup; retention: keep 10 most recent per DB, purge backups older than 30 days
  - Canonical reference: [canonical-decisions.md](docs/roo/canonical-decisions.md:38)

- Identical-file hashing strategy
  - Algorithm: SHA-256 (canonical)
  - Staged prefilters: size grouping → partial SHA-256 (first/last 256 KiB) for files ≥ 512 KiB → full-file SHA-256 for candidates
  - Cache both partial and full hashes; invalidate on absolute_path, file_size, mtime_ns, inode changes
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
- Provide standard menus: File, View, Help (initially no-op actions)
- Central widget displays a centered text: "The KDC Image Organizer will go here"

### Development Approach

- Incremental vertical slices, keeping img_app thin and delegating functionality to pk-py-lib
- Maintain clear module boundaries and avoid cross-imports from img_app into pk-py-lib
- Ensure all new reusable logic lands in pk-py-lib and is consumed by img_app

## Next Steps

1. Review and adjust this plan based on your priorities
2. Set up the basic structure
3. Implement the first vertical slice
4. Iterate based on what you learn
5. Add img_app plan and scaffolding per sections above
## Settings/Profile Manager (References)

Status: Planned

Brief
- The application must present a startup modal to manage and select a Settings Profile before the main window is created. Active profile semantics and validation rules are canonicalized. This section cross-references the full design and does not duplicate content.

Cross-References
- UI design and flows: [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1) (Section "Settings/Profile Manager")
- Technical architecture: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1) (Section "Settings Profiles Architecture")
- API contract: [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md:1) (Section "Settings Profiles API")
- Error handling: [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md:1) (Section "Settings/Profile Manager Errors and Edge Cases")
- Implementation steps: [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md:1) (Section "Integrating the Settings Manager at Startup")
- Canonical decisions: [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:1) (Section "Settings Profiles and Startup Modal")

Next Steps
- Implement core manager [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) and API adapter [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1)
- Implement reusable GUI dialog [src/pk_py_lib/gui/settings/profile_manager.py](src/pk_py_lib/gui/settings/profile_manager.py:1)
- Add app integration helper [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1) and wire in [img_app/img_app/app.py](img_app/img_app/app.py:60)
- Add tests: core/API unit tests and pytest-qt GUI/startup flows