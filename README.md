# pk-py-lib

A comprehensive library of reusable Python components for image processing, file operations, and GUI development.

## Features

- **Image Similarity Detection**: Modular package for perceptual hashing (pHash, wHash) and similarity grouping
- **Advanced File Operations**: Path manipulation, safe operations, real-time monitoring
- **Flexible Logging**: Multi-output logging with variable watching and rich formatting
- **GUI Components**: Reusable widgets and dialogs for image manipulation
- **Persistent Caching**: FlatCacheManager provides file-stat validated cache for computed hashes and quality scores (always enabled)
- **Unified Settings Architecture**: Consolidated settings system with AppSettings and SettingsProfile models
- **Component Showcase**: Interactive GUI test framework for component development

## Recent Updates

**Phase 3 Refactoring Complete (2025-10-10)**
- ✅ Hash computation utilities extracted - eliminated ~40% code duplication
- ✅ find_similar_images simplified from 235 lines to ~50 lines using phase-based architecture
- ✅ 76 new tests added (54 utilities + 22 phases) - comprehensive coverage
- ✅ All LSH references removed and test files organized
- ✅ 100% backward compatibility maintained
- See [`docs/roo/phase3-completion-summary.md`](docs/roo/phase3-completion-summary.md:1) for complete details

**Phase 1-2 Refactoring Complete + Settings Consolidation (2025-10-10)**
- ✅ Similarity module split into 6 focused modules for better maintainability
- ✅ GUI models consolidated to eliminate duplication
- ✅ Cache architecture unified (FlatCacheManager is sole solution)
- ✅ Settings architecture consolidated into unified system
- ✅ 433 lines of obsolete code removed
- ✅ 100% backward compatibility maintained
- See [`docs/refactoring-summary.md`](docs/refactoring-summary.md:1) for complete details

## Quick Start

### Launch the GUI Component Showcase

From the project root directory:

```bash
python run_showcase.py
```

This launches an interactive GUI where you can:
- Browse and test all available components
- Live preview with property editing
- Interactive code playground
- Integrated logging panel

## Launch the img_app development application

To run the development application (img_app) which exercises components from this repository, use the PDM script defined in [`pyproject.toml`](pyproject.toml:49):

```bash
pdm run imgapp
```

This launches the KDC Image Organizer window. As of 2025-08-15 the app attempts to open with the MultiPathSelector widget as the central view (implemented in [`src/pk_py_lib/gui/file_selector/widgets.py`](src/pk_py_lib/gui/file_selector/widgets.py:693)). If the library widget is unavailable, the app will fall back to a minimal placeholder.
## Design Docs and Decisions

Primary design/spec references:
- [architecture-plan.md](architecture-plan.md)
- [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md)
- [docs/img-app-spec.md](docs/img-app-spec.md)
- [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)
- [docs/roo/img-app-api-specifications.md](docs/roo/img-app-api-specifications.md)
- [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)
- [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md)
- [docs/roo/img-app-implementation-guide.md](docs/roo/img-app-implementation-guide.md)
- [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md)
- [docs/roo/acceptance-review-checklist.md](docs/roo/acceptance-review-checklist.md)

These are the sources of truth for terminology, defaults, gating, and API/DB shapes. Keep cross-document consistency when updating any of them.

### Core Functionality Examples

```python
# Path operations - remove nested/contained paths
from src.pk_py_lib.core.filesystem import PathOperations
paths = [Path("/photos"), Path("/photos/vacation"), Path("/documents")]
minimal = PathOperations.remove_contained_paths(paths)
# Result: [Path("/photos"), Path("/documents")]

# Advanced logging with variable watching
from src.pk_py_lib import get_logger
log = get_logger(__name__)
log.watch(image_count=150, threshold=0.95)

# Real-time file monitoring
from src.pk_py_lib.core.filesystem.monitoring import FileWatcher
watcher = FileWatcher()
watcher.watch("/photos", patterns=["*.jpg", "*.png"])
```

## Installation

### Requirements
- Python >= 3.13

### Recommended: PDM-managed development environment
```bash
pipx install pdm   # or: python -m pip install -U pdm
pdm install        # install all deps from pyproject
```

- Launch the img_app:
```bash
pdm run imgapp
```

- Launch the component showcase:
```bash
python run_showcase.py
```

### Optional Dependencies
```bash
# For GUI components
pip install PySide6

# For advanced image processing
pip install opencv-python scikit-image imagehash

# For CLI tools
pip install click tqdm
```

### Optional: pip development installation
```bash
git clone <repository>
cd pk-py-lib
pip install -e .[gui,image_processing,dev]
```
Note: PDM is the primary workflow for this repository. The pip editable install is provided for convenience only.

## Project Structure

```
pk-py-lib/
├── src/pk_py_lib/           # Main library
│   ├── core/                # Core utilities
│   │   ├── filesystem/      # File operations & monitoring
│   │   ├── logging/         # Advanced logging system
│   │   ├── image/           # Image processing
│   │   │   └── similarity/  # Modular similarity detection (9 modules)
│   │   │       ├── types.py           # Shared types and exceptions
│   │   │       ├── validation.py      # Parameter validation
│   │   │       ├── metadata.py        # Metadata extraction
│   │   │       ├── hashing.py         # Hash computation
│   │   │       ├── hash_utils.py      # Common hash utilities (NEW)
│   │   │       ├── algorithm_utils.py # Algorithm management (NEW)
│   │   │       ├── clustering.py      # Similarity detection
│   │   │       ├── phases.py          # Phase-based processing (NEW)
│   │   │       └── __init__.py        # Public API
│   │   ├── models/          # Unified data models (NEW)
│   │   │   └── settings.py  # AppSettings & SettingsProfile models
│   │   ├── settings/        # Unified settings management (NEW)
│   │   │   ├── manager.py   # Settings manager
│   │   │   ├── profiles.py  # Profile CRUD operations
│   │   │   └── schema.py    # Schema validation & defaults
│   │   └── migrations/      # Database migration utilities (NEW)
│   │       └── settings_migration.py # Settings migration framework
│   ├── gui/                 # GUI components
│   │   ├── models.py        # Shared GUI models (consolidated)
│   │   ├── widgets.py       # Reusable widgets
│   │   └── dialogs/         # Dialog components
│   ├── api/                 # High-level APIs
│   │   ├── settings/        # Unified settings API (NEW)
│   │   │   └── unified_api.py # Clean, consistent settings API
│   │   └── settings_profiles.py # Legacy API (deprecated, with warnings)
│   ├── processing/          # High-level APIs (future)
│   └── cli/                 # CLI tools (future)
├── img_app/                 # Development application
├── showcase/                # Component test framework
├── tests/                   # Test suite (150+ tests)
│   ├── test_hash_utils.py   # Hash utilities tests (NEW)
│   ├── test_algorithm_utils.py # Algorithm utils tests (NEW)
│   ├── test_phases.py       # Phase-based tests (NEW)
│   ├── test_unified_settings.py # Unified settings tests (NEW)
│   └── ...
├── docs/                    # Project documentation
│   ├── refactoring-summary.md  # Complete refactoring details
│   ├── roo/                 # Detailed specifications
│   │   ├── phase3-completion-summary.md # Phase 3 details (NEW)
│   │   ├── settings-migration-guide.md  # Settings migration guide (NEW)
│   │   └── ...
├── run_showcase.py          # Quick launcher for GUI testing
└── example_usage.py         # Usage demonstrations
```

## Key Features

### Image Similarity Detection
- **Modular architecture**: 9 focused modules for clarity and maintainability
- **Multiple algorithms**: pHash (DCT-based), wHash (wavelet-based), XXH3 (exact duplicates)
- **Phase-based processing**: 4 distinct phases for improved testability and maintainability
- **Utility extraction**: Common hash computation utilities eliminate code duplication
- **Flexible grouping**: Transitive clustering with configurable thresholds
- **Comprehensive**: Handles metadata extraction, validation, and batch processing
- **High test coverage**: 150+ tests including 76 new tests for utilities and phases
- See [`src/pk_py_lib/core/image/similarity/`](src/pk_py_lib/core/image/similarity/__init__.py:1)

### File System Operations
- **Path normalization**: Handle mixed file/directory collections
- **Safe operations**: Transaction support with rollback
- **Real-time monitoring**: Cross-platform file watching
- **Organization**: Intelligent file sorting and duplicate handling

### Advanced Logging
- **Multi-output**: Terminal, file, GUI panel, future DB support
- **Variable watching**: Debug complex state with `log.watch()`
- **Performance tracking**: Built-in timing and profiling
- **Rich formatting**: Beautiful console output

### Component Development
- **Interactive showcase**: Test GUI components in real-time
- **Property inspection**: Live configuration editing
- **Code playground**: Execute custom test code
- **Auto-discovery**: Automatically find and display components

## License

MIT License

