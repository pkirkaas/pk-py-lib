# KDC Image Organizer - API Specifications

## 1. Overview

This document defines the API interfaces between the img-app application and the pk-py-lib component library. All APIs follow consistent patterns for error handling, data validation, and async operations.

## 2. Core API Principles

### 2.1 Design Principles
- **Consistency**: Uniform naming conventions and patterns
- **Type Safety**: Full type hints and runtime validation  
- **Error Handling**: Explicit error types with recovery options
- **Async Support**: Async variants for I/O operations
- **Extensibility**: Plugin-friendly interfaces

### 2.2 Common Patterns
```python
# Standard response pattern
@dataclass
class ApiResponse[T]:
    """Standard API response wrapper."""
    success: bool
    data: Optional[T]
    error: Optional[str]
    metadata: Dict[str, Any]

# Standard error pattern
class ApiError(Exception):
    """Base API error class."""
    def __init__(self, message: str, code: str, details: Dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
```

## 3. Image Processing API

### 3.1 Image Loader API
```python
class ImageLoaderAPI:
    """API for loading and validating images."""
    
    def load_image(
        self, 
        path: Path,
        max_size: Optional[Tuple[int, int]] = None,
        validate: bool = True
    ) -> ApiResponse[Image]:
        """
        Load image from file system.
        
        Args:
            path: Path to image file
            max_size: Maximum dimensions (width, height)
            validate: Perform validation checks
            
        Returns:
            ApiResponse containing PIL Image or error
            
        Raises:
            FileNotFoundError: Image file doesn't exist
            InvalidImageError: Image is corrupted or unsupported
            PermissionError: No read access to file
        """
        
    async def load_image_async(
        self,
        path: Path,
        max_size: Optional[Tuple[int, int]] = None
    ) -> ApiResponse[Image]:
        """Async version of load_image."""
        
    def load_images_batch(
        self,
        paths: List[Path],
        parallel: bool = True,
        progress_callback: Optional[Callable] = None
    ) -> List[ApiResponse[Image]]:
        """
        Load multiple images in batch.
        
        Args:
            paths: List of image paths
            parallel: Use parallel processing
            progress_callback: Progress update function
            
        Returns:
            List of ApiResponse objects
        """
```

### 3.2 Thumbnail Generator API
```python
class ThumbnailAPI:
    """API for thumbnail generation and management."""
    
    def generate_thumbnail(
        self,
        image: Union[Image, Path],
        size: int = 256,
        quality: int = 85,
        format: str = "JPEG"
    ) -> ApiResponse[bytes]:
        """
        Generate thumbnail from image.
        
        Args:
            image: PIL Image or path to image
            size: Square thumbnail size
            quality: JPEG quality (1-100)
            format: Output format
            
        Returns:
            ApiResponse containing thumbnail bytes
        """
        
    def get_cached_thumbnail(
        self,
        image_path: Path,
        size: int = 256
    ) -> Optional[bytes]:
        """
        Retrieve cached thumbnail if available.
        
        Args:
            image_path: Original image path
            size: Thumbnail size
            
        Returns:
            Thumbnail bytes or None if not cached
        """
        
    def generate_thumbnails_batch(
        self,
        images: List[Path],
        sizes: List[int] = [256, 512, 1024],
        progress_callback: Optional[Callable] = None
    ) -> Dict[Path, Dict[int, bytes]]:
        """Generate multiple thumbnails for multiple images."""
```

### 3.3 Similarity Detection API
```python
class SimilarityAPI:
    """API for image similarity detection."""
    
    def compute_similarity(
        self,
        image1: Union[Image, Path],
        image2: Union[Image, Path],
        algorithm: str = "phash",
        **kwargs
    ) -> ApiResponse[float]:
        """
        Compute similarity between two images.
        
        Args:
            image1: First image
            image2: Second image
            algorithm: Algorithm name
            **kwargs: Algorithm-specific parameters
            
        Returns:
            ApiResponse with similarity score (0.0-1.0)
        """
        
    def find_similar_images(
        self,
        images: List[Path],
        threshold: float = 0.85,
        algorithms: List[str] = ["phash"],
        reference_set: Optional[List[Path]] = None,
        progress_callback: Optional[Callable] = None
    ) -> ApiResponse[List[SimilarityGroup]]:
        """
        Find similar images in collection.
        
        Args:
            images: Images to analyze
            threshold: Similarity threshold
            algorithms: Algorithms to use
            reference_set: Optional reference image set
            progress_callback: Progress updates
            
        Returns:
            ApiResponse with similarity groups
        """
        
    def register_algorithm(
        self,
        name: str,
        algorithm: BaseAlgorithm
    ) -> None:
        """Register custom similarity algorithm."""
```

## 4. File System API

### 4.1 File Selection API
```python
class FileSelectionAPI:
    """API for file and folder selection."""
    
    def select_files(
        self,
        initial_dir: Optional[Path] = None,
        filters: List[str] = None,
        multiple: bool = True
    ) -> ApiResponse[List[Path]]:
        """
        Open file selection dialog.
        
        Args:
            initial_dir: Starting directory
            filters: File extension filters
            multiple: Allow multiple selection
            
        Returns:
            ApiResponse with selected file paths
        """
        
    def select_folder(
        self,
        initial_dir: Optional[Path] = None,
        multiple: bool = False
    ) -> ApiResponse[List[Path]]:
        """Open folder selection dialog."""
        
    def get_images_from_folder(
        self,
        folder: Path,
        recursive: bool = True,
        filters: List[str] = None,
        follow_symlinks: bool = False
    ) -> ApiResponse[List[Path]]:
        """
        Get all image files from folder.
        
        Args:
            folder: Folder path
            recursive: Include subfolders
            filters: Extension filters
            follow_symlinks: Follow symbolic links
            
        Returns:
            ApiResponse with image file paths
        """
```

### 4.2 File Operations API
```python
class FileOperationsAPI:
    """API for file system operations."""
    
    def move_file(
        self,
        source: Path,
        destination: Path,
        overwrite: bool = False,
        create_backup: bool = True
    ) -> ApiResponse[Path]:
        """
        Move file with safety checks.
        
        Args:
            source: Source file path
            destination: Destination path
            overwrite: Allow overwriting
            create_backup: Create backup before overwrite
            
        Returns:
            ApiResponse with final destination path
        """
        
    def delete_file(
        self,
        path: Path,
        use_trash: bool = True,
        confirm: bool = True
    ) -> ApiResponse[bool]:
        """
        Delete file safely.
        
        Args:
            path: File to delete
            use_trash: Move to trash instead of permanent delete
            confirm: Require confirmation
            
        Returns:
            ApiResponse with success status
        """
        
    def batch_operation(
        self,
        operations: List[Dict],
        atomic: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> ApiResponse[List[Any]]:
        """Execute batch file operations."""
```

### 4.3 File Monitoring API
```python
class FileMonitoringAPI:
    """API for file system monitoring."""
    
    def watch_directory(
        self,
        path: Path,
        recursive: bool = True,
        events: List[str] = ["created", "modified", "deleted"],
        callback: Callable[[FileEvent], None] = None
    ) -> ApiResponse[WatchHandle]:
        """
        Start watching directory for changes.
        
        Args:
            path: Directory to watch
            recursive: Watch subdirectories
            events: Event types to monitor
            callback: Event handler function
            
        Returns:
            ApiResponse with watch handle
        """
        
    def stop_watching(self, handle: WatchHandle) -> ApiResponse[bool]:
        """Stop directory watching."""
        
    def get_file_changes(
        self,
        path: Path,
        since: datetime
    ) -> ApiResponse[List[FileEvent]]:
        """Get file changes since timestamp."""
```

## 5. GUI Widget API

### 5.1 Image Viewer API
```python
class ImageViewerAPI:
    """API for image viewer widget."""
    
    def create_viewer(
        self,
        parent: Optional[QWidget] = None,
        config: Optional[ViewerConfig] = None
    ) -> ImageViewerWidget:
        """
        Create image viewer widget.
        
        Args:
            parent: Parent widget
            config: Viewer configuration
            
        Returns:
            Configured ImageViewerWidget
        """
        
    def display_image(
        self,
        viewer: ImageViewerWidget,
        image: Union[Image, Path, bytes],
        fit_mode: str = "fit_window"
    ) -> ApiResponse[bool]:
        """Display image in viewer."""
        
    def set_comparison_mode(
        self,
        viewer: ImageViewerWidget,
        images: List[Union[Image, Path]],
        sync_controls: bool = True
    ) -> ApiResponse[bool]:
        """Enable comparison mode."""
```

### 5.2 File Selector Widget API
```python
class FileSelectorAPI:
    """API for file selector widget."""
    
    def create_selector(
        self,
        parent: Optional[QWidget] = None,
        mode: str = "files",
        filters: List[str] = None
    ) -> FileSelectorWidget:
        """
        Create file selector widget.
        
        Args:
            parent: Parent widget
            mode: Selection mode ('files', 'folders', 'both')
            filters: File filters
            
        Returns:
            Configured FileSelectorWidget
        """
        
    def get_selected_items(
        self,
        selector: FileSelectorWidget
    ) -> List[Path]:
        """Get currently selected items."""
        
    def set_selected_items(
        self,
        selector: FileSelectorWidget,
        items: List[Path]
    ) -> ApiResponse[bool]:
        """Set selected items programmatically."""
```

### 5.3 Progress Widget API
```python
class ProgressAPI:
    """API for progress indication."""
    
    def create_progress_dialog(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Processing",
        cancelable: bool = True
    ) -> ProgressDialog:
        """Create progress dialog."""
        
    def update_progress(
        self,
        dialog: ProgressDialog,
        current: int,
        total: int,
        message: str = ""
    ) -> None:
        """Update progress status."""
        
    def create_progress_bar(
        self,
        parent: Optional[QWidget] = None,
        style: str = "default"
    ) -> ProgressBar:
        """Create embedded progress bar."""
```

## 6. Database API

### 6.1 Database Connection API
```python
class DatabaseAPI:
    """API for database operations."""
    
    def connect(
        self,
        db_path: Path,
        mode: str = "read_write",
        timeout: float = 5.0
    ) -> ApiResponse[DatabaseConnection]:
        """
        Connect to database.
        
        Args:
            db_path: Database file path
            mode: Access mode ('read_only', 'read_write')
            timeout: Connection timeout
            
        Returns:
            ApiResponse with connection object
        """
        
    def execute_query(
        self,
        connection: DatabaseConnection,
        query: str,
        params: Tuple = None
    ) -> ApiResponse[List[Dict]]:
        """Execute SQL query."""
        
    def execute_transaction(
        self,
        connection: DatabaseConnection,
        operations: List[Tuple[str, Tuple]]
    ) -> ApiResponse[bool]:
        """Execute multiple operations in transaction."""
```

### 6.2 Cache Management API
```python
class CacheAPI:
    """API for cache management."""
    
    def get_cache_info(self) -> CacheInfo:
        """Get cache statistics and information."""
        
    def clear_cache(
        self,
        category: Optional[str] = None,
        older_than: Optional[datetime] = None
    ) -> ApiResponse[int]:
        """
        Clear cache entries.
        
        Args:
            category: Specific category to clear
            older_than: Clear entries older than date
            
        Returns:
            ApiResponse with number of entries cleared
        """
        
    def optimize_cache(self) -> ApiResponse[bool]:
        """Optimize cache database."""
        
    def export_cache_stats(
        self,
        format: str = "json"
    ) -> ApiResponse[str]:
        """Export cache statistics."""
```

## 7. Configuration API

### 7.1 Settings API
```python
class SettingsAPI:
    """API for application settings."""
    
    def get_setting(
        self,
        key: str,
        default: Any = None,
        profile: Optional[str] = None
    ) -> Any:
        """
        Get configuration setting.
        
        Args:
            key: Setting key
            default: Default value if not found
            profile: Specific profile name
            
        Returns:
            Setting value or default
        """
        
    def set_setting(
        self,
        key: str,
        value: Any,
        profile: Optional[str] = None,
        persist: bool = True
    ) -> ApiResponse[bool]:
        """Set configuration value."""
        
    def get_profile(
        self,
        name: Optional[str] = None
    ) -> ApiResponse[UserProfile]:
        """Get user profile."""
        
    def export_settings(
        self,
        path: Path,
        profile: Optional[str] = None
    ) -> ApiResponse[bool]:
        """Export settings to file."""
```

### 7.2 Plugin API
```python
class PluginAPI:
    """API for plugin management."""
    
    def discover_plugins(
        self,
        directory: Path
    ) -> ApiResponse[List[PluginInfo]]:
        """Discover available plugins."""
        
    def load_plugin(
        self,
        plugin_path: Path
    ) -> ApiResponse[Plugin]:
        """Load and initialize plugin."""
        
    def register_plugin(
        self,
        plugin: Plugin
    ) -> ApiResponse[bool]:
        """Register plugin with application."""
        
    def get_plugin_api(
        self,
        plugin_name: str
    ) -> Optional[Any]:
        """Get plugin's exposed API."""
```

## 8. Logging API

### 8.1 Logger API
```python
class LoggerAPI:
    """API for application logging."""
    
    def get_logger(
        self,
        name: str,
        level: str = "INFO"
    ) -> Logger:
        """
        Get configured logger instance.
        
        Args:
            name: Logger name
            level: Logging level
            
        Returns:
            Configured logger
        """
        
    def log_operation(
        self,
        operation: str,
        status: str,
        details: Dict = None,
        duration: Optional[float] = None
    ) -> None:
        """Log operation with structured data."""
        
    def log_error(
        self,
        error: Exception,
        context: Dict = None,
        user_message: Optional[str] = None
    ) -> None:
        """Log error with context."""
        
    def get_log_entries(
        self,
        since: Optional[datetime] = None,
        level: Optional[str] = None,
        limit: int = 100
    ) -> List[LogEntry]:
        """Retrieve log entries."""
```

## 9. Event System API

### 9.1 Event Bus API
```python
class EventBusAPI:
    """API for application event system."""
    
    def subscribe(
        self,
        event_type: str,
        handler: Callable,
        priority: int = 0
    ) -> SubscriptionHandle:
        """
        Subscribe to event type.
        
        Args:
            event_type: Event type name
            handler: Event handler function
            priority: Handler priority (higher = earlier)
            
        Returns:
            Subscription handle
        """
        
    def unsubscribe(
        self,
        handle: SubscriptionHandle
    ) -> bool:
        """Unsubscribe from events."""
        
    def emit(
        self,
        event_type: str,
        data: Any,
        async_mode: bool = False
    ) -> None:
        """Emit event to subscribers."""
        
    def emit_and_wait(
        self,
        event_type: str,
        data: Any,
        timeout: float = 5.0
    ) -> List[Any]:
        """Emit event and wait for responses."""
```

### 9.2 Standard Events
```python
# Standard event types
class Events:
    # File events
    FILE_SELECTED = "file.selected"
    FILE_DELETED = "file.deleted"
    FILE_MOVED = "file.moved"
    
    # Processing events  
    SCAN_STARTED = "scan.started"
    SCAN_PROGRESS = "scan.progress"
    SCAN_COMPLETED = "scan.completed"
    SCAN_ERROR = "scan.error"
    
    # UI events
    VIEW_CHANGED = "ui.view_changed"
    THEME_CHANGED = "ui.theme_changed"
    PANEL_TOGGLED = "ui.panel_toggled"
    
    # Data events
    CACHE_CLEARED = "data.cache_cleared"
    SETTINGS_CHANGED = "data.settings_changed"
    PROFILE_SWITCHED = "data.profile_switched"
```

## 10. Error Handling

### 10.1 Error Types
```python
class ImageProcessingError(ApiError):
    """Image processing failed."""
    
class FileSystemError(ApiError):
    """File system operation failed."""
    
class DatabaseError(ApiError):
    """Database operation failed."""
    
class ValidationError(ApiError):
    """Data validation failed."""
    
class PermissionError(ApiError):
    """Permission denied."""
    
class NetworkError(ApiError):
    """Network operation failed."""
```

### 10.2 Error Recovery API
```python
class ErrorRecoveryAPI:
    """API for error recovery strategies."""
    
    def register_handler(
        self,
        error_type: Type[Exception],
        handler: Callable[[Exception], RecoveryAction]
    ) -> None:
        """Register error recovery handler."""
        
    def handle_error(
        self,
        error: Exception,
        context: Dict = None
    ) -> RecoveryAction:
        """Handle error with recovery strategy."""
        
    def retry_operation(
        self,
        operation: Callable,
        max_retries: int = 3,
        backoff: float = 1.0
    ) -> ApiResponse[Any]:
        """Retry operation with exponential backoff."""
```

## 11. Testing Support API

### 11.1 Mock API
```python
class MockAPI:
    """API for testing support."""
    
    def create_mock_image(
        self,
        size: Tuple[int, int] = (100, 100),
        format: str = "RGB"
    ) -> Image:
        """Create mock image for testing."""
        
    def create_mock_files(
        self,
        count: int,
        directory: Path,
        pattern: str = "test_*.jpg"
    ) -> List[Path]:
        """Create mock image files."""
        
    def create_mock_database(
        self,
        schema: str = "default"
    ) -> DatabaseConnection:
        """Create in-memory test database."""
```

## 12. Usage Examples

### 12.1 Basic Image Scanning
```python
# Initialize APIs
file_api = FileSelectionAPI()
similarity_api = SimilarityAPI()
progress_api = ProgressAPI()

# Select images
result = file_api.get_images_from_folder(
    Path("/photos"),
    recursive=True,
    filters=[".jpg", ".png"]
)

if result.success:
    images = result.data
    
    # Create progress dialog
    progress = progress_api.create_progress_dialog(
        title="Scanning for Duplicates"
    )
    
    # Find similar images
    def on_progress(current, total):
        progress_api.update_progress(
            progress, current, total,
            f"Processing image {current} of {total}"
        )
    
    similar = similarity_api.find_similar_images(
        images,
        threshold=0.90,
        algorithms=["phash", "histogram"],
        progress_callback=on_progress
    )
    
    if similar.success:
        print(f"Found {len(similar.data)} groups")
```

### 12.2 Custom Algorithm Registration
```python
# Define custom algorithm
class CustomAlgorithm(BaseAlgorithm):
    def compute_hash(self, image: Image) -> Any:
        # Custom hash computation
        return custom_hash
    
    def compare(self, hash1: Any, hash2: Any) -> float:
        # Custom comparison
        return similarity_score

# Register with API
similarity_api = SimilarityAPI()
similarity_api.register_algorithm(
    "custom_algorithm",
    CustomAlgorithm()
)

# Use in scanning
result = similarity_api.find_similar_images(
    images,
    algorithms=["custom_algorithm"]
)