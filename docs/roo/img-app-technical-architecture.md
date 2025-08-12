# KDC Image Organizer - Technical Architecture

## 1. System Architecture Overview

### 1.1 High-Level Architecture
```
┌─────────────────────────────────────────────────────┐
│                  GUI Layer (PySide6)                 │
│  ┌────────────────────────────────────────────────┐ │
│  │ Main Window │ Panels │ Dialogs │ Widgets      │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│              Application Core Layer                  │
│  ┌────────────────────────────────────────────────┐ │
│  │ Controllers │ Services │ Managers │ Models    │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│             Processing Engine Layer                  │
│  ┌────────────────────────────────────────────────┐ │
│  │ Algorithms │ Processors │ Analyzers │ Queue   │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│               Data Access Layer                      │
│  ┌────────────────────────────────────────────────┐ │
│  │ Database │ Cache │ File System │ Serializers  │ │
│  └────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────┤
│            pk-py-lib Components Layer                │
│  ┌────────────────────────────────────────────────┐ │
│  │ GUI Widgets │ File Utils │ Image Utils │ Log  │ │
│  └────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 1.2 Component Interaction Flow
```python
# Example similarity detection flow
User Input → GUI Event → Controller → Service → Processing Engine
                                           ↓
Database ← Cache Manager ← Result ← Algorithm Implementation
     ↓
GUI Update ← Model Update ← Controller ← Service
```

## 2. Core Components

### 2.1 Application Core (`img_app/core/`)

#### 2.1.1 Application Manager
```python
class ApplicationManager:
    """
    Central application controller managing lifecycle and coordination.
    
    Responsibilities:
    - Application initialization and shutdown
    - Component registration and dependency injection
    - Global event bus management
    - Cross-component communication
    """
    
    def __init__(self):
        self.config_manager: ConfigurationManager
        self.database_manager: DatabaseManager
        self.cache_manager: CacheManager
        self.processing_engine: ProcessingEngine
        self.profile_manager: ProfileManager
        self.event_bus: EventBus
        
    def initialize(self) -> None:
        """Initialize all application components in correct order."""
        
    def shutdown(self) -> None:
        """Graceful shutdown with resource cleanup."""
```

#### 2.1.2 Configuration Manager
```python
class ConfigurationManager:
    """
    Manages all application configuration and settings.
    
    Storage: SQLite database (settings.db)
    
    Configuration Categories:
    - Application settings (window state, theme, language)
    - Algorithm configurations (thresholds, parameters)
    - Performance settings (thread count, memory limits)
    - User preferences (shortcuts, defaults)
    """
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Retrieve configuration value with fallback."""
        
    def set_setting(self, key: str, value: Any) -> None:
        """Update configuration value with validation."""
        
    def load_profile(self, profile_name: str) -> None:
        """Load complete configuration profile."""
        
    def export_profile(self, path: Path) -> None:
        """Export current configuration to file."""
```

### 2.2 Processing Engine (`img_app/processing/`)

#### 2.2.1 Similarity Detection Engine
```python
class SimilarityEngine:
    """
    Orchestrates similarity detection across multiple algorithms.
    
    Features:
    - Algorithm plugin system
    - Parallel processing with thread pool
    - Progress tracking and cancellation
    - Result aggregation and scoring
    """
    
    def __init__(self, config: AlgorithmConfig):
        self.algorithms: Dict[str, BaseAlgorithm] = {}
        self.thread_pool: ThreadPoolExecutor
        self.progress_tracker: ProgressTracker
        
    def register_algorithm(self, name: str, algorithm: BaseAlgorithm):
        """Register similarity algorithm implementation."""
        
    async def find_similar(
        self, 
        images: List[Path],
        reference_images: Optional[List[Path]] = None,
        algorithms: List[str] = None,
        threshold: float = 0.85
    ) -> SimilarityResults:
        """Execute similarity detection with specified algorithms."""
```

#### 2.2.2 Algorithm Implementations
```python
class BaseAlgorithm(ABC):
    """Abstract base for similarity algorithms."""
    
    @abstractmethod
    def compute_hash(self, image: Image) -> Any:
        """Compute image hash/signature."""
        
    @abstractmethod
    def compare(self, hash1: Any, hash2: Any) -> float:
        """Compare two hashes, return similarity 0.0-1.0."""

class PerceptualHashAlgorithm(BaseAlgorithm):
    """pHash implementation using imagehash library."""
    
    def __init__(self, hash_size: int = 8):
        self.hash_size = hash_size
        
    def compute_hash(self, image: Image) -> imagehash.ImageHash:
        return imagehash.phash(image, hash_size=self.hash_size)
        
    def compare(self, hash1: imagehash.ImageHash, hash2: imagehash.ImageHash) -> float:
        distance = hash1 - hash2
        max_distance = self.hash_size * self.hash_size
        return 1.0 - (distance / max_distance)

class HistogramAlgorithm(BaseAlgorithm):
    """Color histogram comparison using OpenCV."""
    
    def compute_hash(self, image: Image) -> np.ndarray:
        # Convert to CV2 format and compute histogram
        pass
        
    def compare(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        # Use cv2.compareHist with correlation method
        pass
```

### 2.3 Data Management (`img_app/data/`)

#### 2.3.1 Database Schema
```sql
-- settings.db schema

CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'string', 'int', 'float', 'bool', 'json'
    UNIQUE(profile_id, key)
);

CREATE TABLE operation_history (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id),
    operation_type TEXT NOT NULL,
    operation_data JSON NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_undone BOOLEAN DEFAULT FALSE
);

-- cache.db schema

CREATE TABLE image_metadata (
    id INTEGER PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_size INTEGER NOT NULL,
    file_modified TIMESTAMP NOT NULL,
    width INTEGER,
    height INTEGER,
    format TEXT,
    exif_data JSON,
    file_hash TEXT,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE thumbnails (
    id INTEGER PRIMARY KEY,
    image_id INTEGER REFERENCES image_metadata(id),
    size INTEGER NOT NULL,  -- 256, 512, 1024
    thumbnail_data BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(image_id, size)
);

CREATE TABLE similarity_cache (
    id INTEGER PRIMARY KEY,
    image1_id INTEGER REFERENCES image_metadata(id),
    image2_id INTEGER REFERENCES image_metadata(id),
    algorithm TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(image1_id, image2_id, algorithm)
);

CREATE TABLE scan_sessions (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER,
    scan_type TEXT NOT NULL,  -- 'single_set', 'dual_set'
    configuration JSON NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL  -- 'running', 'completed', 'cancelled', 'error'
);

CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES scan_sessions(id),
    group_id INTEGER NOT NULL,
    image_id INTEGER REFERENCES image_metadata(id),
    similarity_score REAL,
    is_reference BOOLEAN DEFAULT FALSE
);
```

#### 2.3.2 Cache Manager
```python
class CacheManager:
    """
    Manages thumbnail and result caching with size limits.
    
    Features:
    - LRU eviction policy
    - Configurable size limits
    - Automatic cleanup
    - Cache warming strategies
    """
    
    def __init__(self, cache_dir: Path, max_size_gb: float = 20.0):
        self.cache_dir = cache_dir
        self.max_size_bytes = max_size_gb * 1024 * 1024 * 1024
        self.db_path = cache_dir / "cache.db"
        
    def get_thumbnail(self, image_path: Path, size: int) -> Optional[QPixmap]:
        """Retrieve cached thumbnail or None."""
        
    def cache_thumbnail(self, image_path: Path, size: int, pixmap: QPixmap):
        """Store thumbnail in cache with LRU management."""
        
    def get_similarity(self, path1: Path, path2: Path, algorithm: str) -> Optional[float]:
        """Retrieve cached similarity score."""
        
    def invalidate_file(self, image_path: Path):
        """Invalidate all cache entries for modified file."""
```

### 2.4 GUI Components (`img_app/gui/`)

#### 2.4.1 Main Window Structure
```python
class MainWindow(QMainWindow):
    """
    Application main window with dockable panels.
    
    Components:
    - Menu bar with standard menus
    - Tool bars for common actions
    - Central widget (results view)
    - Dockable panels (file browser, preview, properties)
    - Status bar with progress
    """
    
    def __init__(self, app_manager: ApplicationManager):
        super().__init__()
        self.app_manager = app_manager
        self.setup_ui()
        self.setup_panels()
        self.setup_connections()
        
    def setup_panels(self):
        """Create and configure dockable panels."""
        self.file_panel = FileExplorerPanel()
        self.results_panel = ResultsPanel()
        self.preview_panel = PreviewPanel()
        self.properties_panel = PropertiesPanel()
```

#### 2.4.2 Custom Widgets
```python
class ImageComparisonWidget(QWidget):
    """
    Side-by-side image comparison with synchronized controls.
    
    Features:
    - Synchronized zoom/pan
    - Difference highlighting
    - Swipe comparison mode
    - Metadata overlay
    """
    
    def __init__(self):
        self.left_viewer: ImageViewer
        self.right_viewer: ImageViewer
        self.sync_controls = True
        
class ResultsTreeWidget(QTreeWidget):
    """
    Displays similarity results in grouped hierarchy.
    
    Features:
    - Custom item delegates for rich display
    - Lazy loading for large result sets
    - Context menus for operations
    - Keyboard navigation
    """
    
    def __init__(self):
        self.result_model: SimilarityResultModel
        self.selection_manager: SelectionManager
```

## 3. Threading and Concurrency

### 3.1 Thread Architecture
```python
class ThreadManager:
    """
    Manages application threading with proper Qt integration.
    
    Thread Types:
    1. Main GUI Thread - Qt event loop
    2. Worker Pool - CPU-bound image processing
    3. I/O Thread Pool - File operations
    4. Database Thread - Async DB operations
    """
    
    def __init__(self):
        self.worker_pool = QThreadPool()
        self.worker_pool.setMaxThreadCount(QThread.idealThreadCount())
        self.io_pool = ThreadPoolExecutor(max_workers=4)
        self.db_thread = DatabaseThread()

class ImageProcessingWorker(QRunnable):
    """
    Worker for image processing tasks.
    
    Features:
    - Progress reporting via signals
    - Cancellation support
    - Error handling with recovery
    - Memory-efficient processing
    """
    
    def __init__(self, task: ProcessingTask):
        self.task = task
        self.signals = WorkerSignals()
        self._is_cancelled = False
        
    def run(self):
        """Execute processing with progress updates."""
        try:
            for i, image in enumerate(self.task.images):
                if self._is_cancelled:
                    break
                result = self.process_image(image)
                progress = (i + 1) / len(self.task.images) * 100
                self.signals.progress.emit(progress)
        except Exception as e:
            self.signals.error.emit(str(e))
```

## 4. Performance Optimization

### 4.1 Memory Management
```python
class MemoryManager:
    """
    Monitors and manages application memory usage.
    
    Strategies:
    - Lazy loading with generators
    - Image pyramid for multi-resolution
    - Aggressive garbage collection
    - Memory-mapped file access
    """
    
    def __init__(self, limit_mb: int = 2048):
        self.limit_bytes = limit_mb * 1024 * 1024
        self.current_usage = 0
        
    def load_image_lazy(self, path: Path) -> Generator[Image, None, None]:
        """Load image with minimal memory footprint."""
        
    def create_image_pyramid(self, image: Image) -> Dict[int, Image]:
        """Create multi-resolution pyramid for efficient display."""
```

### 4.2 Batch Processing Optimization
```python
class BatchProcessor:
    """
    Optimizes batch operations for maximum throughput.
    
    Techniques:
    - Vectorized operations with NumPy
    - Batch I/O operations
    - Pipeline parallelism
    - Adaptive batch sizing
    """
    
    def process_batch(self, images: List[Path], operation: Operation) -> Results:
        """Process image batch with optimization."""
        batch_size = self.calculate_optimal_batch_size(len(images))
        with ThreadPoolExecutor() as executor:
            futures = []
            for batch in chunks(images, batch_size):
                future = executor.submit(self.process_chunk, batch, operation)
                futures.append(future)
            return self.aggregate_results(futures)
```

## 5. Plugin Architecture

### 5.1 Plugin System Design
```python
class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.
    
    Plugin Types:
    - Algorithm plugins (new similarity methods)
    - Processor plugins (new batch operations)
    - Export plugins (new output formats)
    - UI plugins (custom panels/widgets)
    """
    
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Plugin] = {}
        
    def discover_plugins(self):
        """Scan plugin directory for valid plugins."""
        
    def load_plugin(self, plugin_path: Path) -> Plugin:
        """Dynamically load and validate plugin."""

class Plugin(ABC):
    """Base class for all plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin display name."""
        
    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""
        
    @abstractmethod
    def initialize(self, app_context: ApplicationContext) -> None:
        """Initialize plugin with application context."""
        
    @abstractmethod
    def shutdown(self) -> None:
        """Clean shutdown of plugin."""
```

## 6. Error Handling and Recovery

### 6.1 Error Management Strategy
```python
class ErrorManager:
    """
    Centralized error handling with recovery strategies.
    
    Error Categories:
    - File System Errors (permissions, missing files)
    - Image Processing Errors (corruption, unsupported)
    - Database Errors (lock, corruption)
    - Memory Errors (out of memory)
    """
    
    def handle_error(self, error: Exception, context: ErrorContext) -> RecoveryAction:
        """Determine and execute recovery strategy."""
        
        if isinstance(error, FileNotFoundError):
            return self.handle_missing_file(error, context)
        elif isinstance(error, PermissionError):
            return self.handle_permission_error(error, context)
        elif isinstance(error, MemoryError):
            return self.handle_memory_error(error, context)
        else:
            return self.handle_generic_error(error, context)
            
class RecoveryAction(Enum):
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    FALLBACK = "fallback"
```

## 7. Testing Architecture

### 7.1 Test Structure
```python
# tests/test_algorithms.py
class TestSimilarityAlgorithms:
    """Test suite for similarity algorithms."""
    
    def test_phash_identical_images(self):
        """Test pHash with identical images returns 1.0."""
        
    def test_phash_different_images(self):
        """Test pHash with different images returns < threshold."""
        
    def test_algorithm_performance(self):
        """Benchmark algorithm performance."""

# tests/test_gui.py
class TestGUIComponents:
    """Test suite for GUI components using pytest-qt."""
    
    def test_main_window_initialization(self, qtbot):
        """Test main window creates correctly."""
        
    def test_file_selection(self, qtbot):
        """Test file selection workflow."""
```

## 8. Logging and Monitoring

### 8.1 Logging Architecture
```python
class ApplicationLogger:
    """
    Multi-level logging with structured output.
    
    Features:
    - Multiple outputs (console, file, GUI)
    - Structured logging with context
    - Performance metrics collection
    - Rotating file logs
    """
    
    def __init__(self):
        self.logger = structlog.get_logger()
        self.setup_outputs()
        
    def log_operation(self, operation: str, **context):
        """Log operation with structured context."""
        self.logger.info(operation, **context)
        
    def log_performance(self, metric: str, value: float, unit: str):
        """Log performance metric."""
        self.logger.info("performance", metric=metric, value=value, unit=unit)
```

## 9. Build and Deployment

### 9.1 Build Configuration
```python
# pyinstaller.spec
a = Analysis(
    ['img_app/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('img_app/assets', 'assets'),
        ('img_app/plugins', 'plugins'),
    ],
    hiddenimports=['PySide6', 'PIL', 'cv2', 'sklearn'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KDC Image Organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico'
)
```

## 10. Integration with pk-py-lib

### 10.1 Component Usage
```python
# Using pk-py-lib components

from pk_py_lib.gui.file_selector import FileSelector
from pk_py_lib.core.filesystem import FileWatcher, PathUtils
from pk_py_lib.core.logging import AdvancedLogger
from pk_py_lib.core.image import ImageProcessor

class ImageOrganizerApp:
    """Main application using pk-py-lib components."""
    
    def __init__(self):
        # Use pk-py-lib file selector
        self.file_selector = FileSelector(
            mode='multi',
            filters=['*.jpg', '*.png', '*.heic']
        )
        
        # Use pk-py-lib file watcher
        self.file_watcher = FileWatcher()
        self.file_watcher.file_changed.connect(self.on_file_changed)
        
        # Use pk-py-lib logger
        self.logger = AdvancedLogger("img_app")
        
        # Use pk-py-lib image processor
        self.image_processor = ImageProcessor()
```

### 10.2 Extension Points
```python
# Define interfaces for pk-py-lib integration

class IPkPyLibImageAlgorithm(Protocol):
    """Interface for pk-py-lib image algorithms."""
    
    def process(self, image: Image) -> Any:
        """Process image with algorithm."""
        
class PkPyLibAdapter:
    """Adapter for pk-py-lib components."""
    
    def adapt_widget(self, widget: QWidget) -> QWidget:
        """Adapt pk-py-lib widget for application."""
        return widget  # Add app-specific styling/behavior