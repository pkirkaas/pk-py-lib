# pk-py-lib

A comprehensive library of reusable Python components for image processing, file operations, and GUI development.

## Features

- **Advanced File Operations**: Path manipulation, safe operations, real-time monitoring
- **Flexible Logging**: Multi-output logging with variable watching and rich formatting
- **GUI Components**: Reusable widgets and dialogs for image manipulation
- **Component Showcase**: Interactive GUI test framework for component development

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
- Core dependencies: pillow, numpy, watchdog, rich

### Optional Dependencies
```bash
# For GUI components
pip install PySide6

# For advanced image processing
pip install opencv-python scikit-image imagehash

# For CLI tools
pip install click tqdm
```

### Development Installation
```bash
git clone <repository>
cd pk-py-lib
pip install -e .[gui,image_processing,dev]
```

## Project Structure

```
pk-py-lib/
├── src/pk_py_lib/           # Main library
│   ├── core/                # Core utilities
│   │   ├── filesystem/      # File operations & monitoring
│   │   └── logging/         # Advanced logging system
│   ├── gui/                 # GUI components (future)
│   ├── processing/          # High-level APIs (future)
│   └── cli/                 # CLI tools (future)
├── showcase/                # Component test framework
├── run_showcase.py          # Quick launcher for GUI testing
└── example_usage.py         # Usage demonstrations
```

## Key Features

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

