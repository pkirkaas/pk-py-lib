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

### 2.2 Common Patterns [ID: API-001]
```python
# Standard response pattern
@dataclass
class ApiResponse(Generic[T]):
    """
    Standard API response wrapper.

    Fields:
        success: Indicates operation success (True/False).
        data: Optional payload of type T when success is True.
        error: Human-readable error message when success is False.
        code: Machine-readable error code (see ErrorCodes enum).
        metadata: Optional dictionary with extra contextual data.
    """
    success: bool
    data: Optional[T]
    error: Optional[str]
    code: Optional[str]
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
    """API for application settings.

    Notes:
        - The application supports a single AppSettings row (application-scoped)
          for UI and performance fields, plus multiple named Profile entries for
          algorithm/file-handling defaults and history.
        - Methods below expose both profile-scoped and app-scoped access where
          appropriate. Use `scope='app'` to target AppSettings.
    """
    
    def get_setting(
        self,
        key: str,
        default: Any = None,
        scope: Optional[str] = "profile",
        profile: Optional[str] = None
    ) -> Any:
        """
        Get configuration setting.

        Args:
            key: Dot-separated setting key (e.g., "performance.max_threads" or "algorithms.default")
            default: Default value if not found
            scope: "app" to read from AppSettings, "profile" to read from a named Profile (default)
            profile: Profile name when scope='profile'; if omitted uses current profile

        Returns:
            Setting value or default
        """
        
    def set_setting(
        self,
        key: str,
        value: Any,
        scope: Optional[str] = "profile",
        profile: Optional[str] = None,
        persist: bool = True
    ) -> ApiResponse[bool]:
        """
        Set configuration value.

        Args:
            key: Setting key
            value: New value
            scope: "app" or "profile"
            profile: Profile name when scope='profile'
            persist: Persist change to storage when True
        """
        
    def get_app_settings(self) -> ApiResponse[AppSettings]:
        """
        Retrieve the application-scoped AppSettings object containing strongly-typed
        global fields such as theme, language, ui_scale, max_threads, max_memory_mb,
        and cache_size_mb.
        """
        
    def update_app_settings(
        self,
        updates: Dict[str, Any]
    ) -> ApiResponse[AppSettings]:
        """
        Apply a partial update to AppSettings, validate, persist, and return the
        updated AppSettings instance.

        Args:
            updates: Mapping of AppSettings field names to new values.
        """
        
    def export_settings(
        self,
        path: Path,
        profile: Optional[str] = None,
        scope: Optional[str] = "profile"
    ) -> ApiResponse[bool]:
        """
        Export settings to file.

        Args:
            path: Destination path for exported settings
            profile: When exporting profile-scoped settings, the profile name
            scope: "app" to export AppSettings, "profile" to export profile settings
        """
```

### 7.2 Profile Management API
```python
class ProfileAPI:
    """API for settings profile management.
    
    Settings profiles represent different scanning workflows and configurations.
    Each profile contains pool settings, path configurations, and algorithm preferences.
    """
    
    def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        base_profile: Optional[str] = None
    ) -> ApiResponse[Profile]:
        """
        Create new settings profile.
        
        Args:
            name: Unique profile name (required)
            description: Optional profile description
            base_profile: Clone settings from existing profile
            
        Returns:
            ApiResponse with created Profile
        """
        
    def get_profile(
        self,
        name: Optional[str] = None
    ) -> ApiResponse[Profile]:
        """
        Get profile by name.
        
        Args:
            name: Profile name, or None for current/default profile
            
        Returns:
            ApiResponse with Profile object
        """
        
    def update_profile(
        self,
        name: str,
        updates: Dict[str, Any]
    ) -> ApiResponse[Profile]:
        """
        Update existing profile.
        
        Args:
            name: Profile name to update
            updates: Dictionary of field updates
            
        Returns:
            ApiResponse with updated Profile
        """
        
    def delete_profile(
        self,
        name: str,
        confirm: bool = True
    ) -> ApiResponse[bool]:
        """
        Delete profile with confirmation.
        
        Args:
            name: Profile name to delete
            confirm: Require user confirmation
            
        Returns:
            ApiResponse with success status
        """
        
    def clone_profile(
        self,
        source_name: str,
        new_name: str,
        description: Optional[str] = None
    ) -> ApiResponse[Profile]:
        """
        Clone existing profile to new name.
        
        Args:
            source_name: Source profile to copy
            new_name: Name for new profile
            description: Optional new description
            
        Returns:
            ApiResponse with cloned Profile
        """
        
    def set_default_profile(
        self,
        name: str
    ) -> ApiResponse[bool]:
        """
        Set profile as default (auto-load on startup).
        
        Args:
            name: Profile name to set as default
            
        Returns:
            ApiResponse with success status
        """
        
    def list_profiles(self) -> ApiResponse[List[ProfileInfo]]:
        """
        List all available profiles.
        
        Returns:
            ApiResponse with list of ProfileInfo objects
        """
        
    def export_profile(
        self,
        name: str,
        path: Path
    ) -> ApiResponse[bool]:
        """
        Export profile to JSON file.
        
        Args:
            name: Profile name to export
            path: Destination file path
            
        Returns:
            ApiResponse with success status
        """
        
    def import_profile(
        self,
        path: Path,
        name: Optional[str] = None
    ) -> ApiResponse[Profile]:
        """
        Import profile from JSON file.
        
        Args:
            path: Source file path
            name: Optional new name (uses file's name if not provided)
            
        Returns:
            ApiResponse with imported Profile
        """
```

### 7.3 Pool Configuration API
```python
class PoolConfigAPI:
    """API for pool configuration in profiles."""
    
    def configure_pool_mode(
        self,
        profile: str,
        mode: str,
        inverse: bool = False
    ) -> ApiResponse[bool]:
        """
        Configure pool mode for profile.
        
        Args:
            profile: Profile name
            mode: 'single' or 'dual'
            inverse: For dual mode, show non-matches
            
        Returns:
            ApiResponse with success status
        """
        
    def set_pool_paths(
        self,
        profile: str,
        pool_number: int,
        include_dirs: List[Path],
        exclude_dirs: Optional[List[Path]] = None,
        include_globs: Optional[List[str]] = None,
        exclude_globs: Optional[List[str]] = None
    ) -> ApiResponse[bool]:
        """
        Set path configuration for a pool.
        
        Args:
            profile: Profile name
            pool_number: 1 or 2 (pool 2 only for dual mode)
            include_dirs: Directories to scan
            exclude_dirs: Directories to skip
            include_globs: File patterns to include
            exclude_globs: File patterns to exclude
            
        Returns:
            ApiResponse with success status
        """
        
    def get_pool_paths(
        self,
        profile: str,
        pool_number: int
    ) -> ApiResponse[PathConfig]:
        """
        Get path configuration for a pool.
        
        Args:
            profile: Profile name
            pool_number: 1 or 2
            
        Returns:
            ApiResponse with PathConfig object
        """
        
    def validate_paths(
        self,
        paths: List[Path]
    ) -> ApiResponse[PathValidation]:
        """
        Validate paths exist and are accessible.
        
        Args:
            paths: List of paths to validate
            
        Returns:
            ApiResponse with validation results
        """
        
    def preview_effective_paths(
        self,
        profile: str,
        pool_number: int,
        limit: int = 100
    ) -> ApiResponse[List[Path]]:
        """
        Preview effective file list after includes/excludes.
        
        Args:
            profile: Profile name
            pool_number: Pool number
            limit: Maximum files to return
            
        Returns:
            ApiResponse with sample file paths
        """
```

### 7.4 File Identity Detection API
```python
class FileIdentityAPI:
    """API for file identity and hashing configuration."""
    
    def configure_hashing(
        self,
        profile: str,
        hash_algo: str = "sha256",
        staged_hashing: bool = True,
        partial_hash_size_kb: int = 256
    ) -> ApiResponse[bool]:
        """
        Configure file hashing settings.
        
        Args:
            profile: Profile name
            hash_algo: Hashing algorithm ('sha256', 'md5', 'blake3')
            staged_hashing: Enable staged pre-filtering
            partial_hash_size_kb: Size for partial hash (KB)
            
        Returns:
            ApiResponse with success status
        """
        
    def test_hash_settings(
        self,
        profile: str,
        sample_files: List[Path],
        measure_performance: bool = True
    ) -> ApiResponse[HashTestResult]:
        """
        Test hash settings on sample files.
        
        Args:
            profile: Profile name
            sample_files: Files to test on
            measure_performance: Include timing metrics
            
        Returns:
            ApiResponse with test results including:
            - Hash computation times
            - Memory usage
            - Collision detection
            - Recommended settings
        """
        
    def compute_file_hash(
        self,
        file_path: Path,
        algorithm: str = "sha256",
        staged: bool = True
    ) -> ApiResponse[FileHashResult]:
        """
        Compute hash for a single file.
        
        Args:
            file_path: File to hash
            algorithm: Hash algorithm
            staged: Use staged hashing if applicable
            
        Returns:
            ApiResponse with FileHashResult containing:
            - full_hash: Complete file hash
            - partial_hash: Partial hash (if staged)
            - computation_time: Time taken
            - file_size: File size in bytes
        """
        
    def find_identical_files(
        self,
        paths: List[Path],
        use_cache: bool = True,
        progress_callback: Optional[Callable] = None
    ) -> ApiResponse[List[IdenticalGroup]]:
        """
        Find byte-for-byte identical files using SHA-256.
        
        Args:
            paths: Files to check
            use_cache: Use cached hashes where valid
            progress_callback: Progress updates
            
        Returns:
            ApiResponse with groups of identical files
        """
```

### 7.5 Settings Validation API
```python
class SettingsValidationAPI:
    """API for settings validation and testing."""
    
    def validate_profile(
        self,
        profile: Union[str, Profile]
    ) -> ApiResponse[ValidationResult]:
        """
        Validate all profile settings.
        
        Args:
            profile: Profile name or object
            
        Returns:
            ApiResponse with validation results:
            - is_valid: Overall validity
            - errors: List of validation errors
            - warnings: List of warnings
            - suggestions: Optimization suggestions
        """
        
    def validate_app_settings(
        self,
        settings: Optional[AppSettings] = None
    ) -> ApiResponse[ValidationResult]:
        """
        Validate application settings.
        
        Args:
            settings: Settings to validate (current if None)
            
        Returns:
            ApiResponse with validation results
        """
        
    def check_disk_space(
        self,
        required_mb: Optional[int] = None
    ) -> ApiResponse[DiskSpaceInfo]:
        """
        Check available disk space for cache.
        
        Args:
            required_mb: Required space in MB (uses cache_size_mb if None)
            
        Returns:
            ApiResponse with disk space information
        """
        
    def optimize_settings(
        self,
        profile: str,
        target: str = "performance"
    ) -> ApiResponse[Dict[str, Any]]:
        """
        Suggest optimized settings.
        
        Args:
            profile: Profile to optimize
            target: Optimization target ('performance', 'accuracy', 'balanced')
            
        Returns:
            ApiResponse with suggested settings
        """
```

### 7.6 Plugin API
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
### 10.0 Error Codes

```python
from enum import Enum

class ErrorCodes(Enum):
    """Canonical machine-readable error codes for API responses."""

    LOCKED_DB = "LOCKED_DB"               # Database locked / concurrent access
    FILE_MISSING = "FILE_MISSING"         # File not found on disk
    OUT_OF_MEMORY = "OUT_OF_MEMORY"       # Memory allocation failure
    PERMISSION_DENIED = "PERMISSION_DENIED"  # Read/write permission denied
    CORRUPTED_IMAGE = "CORRUPTED_IMAGE"   # Image file corrupted or unreadable
    INVALID_CONFIG = "INVALID_CONFIG"     # Configuration validation failed
    NETWORK_ERROR = "NETWORK_ERROR"       # Network or mount error for remote paths
    TIMEOUT = "TIMEOUT"                   # Operation timed out
    UNKNOWN_ERROR = "UNKNOWN_ERROR"       # Fallback/unspecified error
```
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
## 13. Settings Profiles API (Library)

Status: Planned

Scope
- High-level library API for managing settings profiles with full CRUD + copy and explicit Active vs Default semantics.
- Intended consumer: application bootstrap and settings UI. Implementation provided by [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1), delegating to core logic in [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) and configuration in [src/pk_py_lib/core/configuration.py](src/pk_py_lib/core/configuration.py:1).

Dependencies and Data
- Persistence: SQLite settings.db via [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:405).
- Tables: profiles, settings, meta.
- Canonical meta key: meta.active_profile_id (INTEGER) stores the current Active profile id.
- Uniqueness: profiles.name UNIQUE (case-insensitive rule enforced by core).

API Surface (methods are conceptual contracts; names/documentation-first)
- Listing and retrieval
  - [SettingsProfilesAPI.list_profiles()](src/pk_py_lib/api/settings_profiles.py:1)
    - Returns list of ProfileInfo: id, name, is_default, is_active, created_at, modified_at.
  - [SettingsProfilesAPI.get_active_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Returns the currently Active profile (by meta.active_profile_id). If missing, see Initialization behavior below.
  - [SettingsProfilesAPI.get_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Get by name or id. If omitted, returns Active.

- Creation, update, deletion
  - [SettingsProfilesAPI.create_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name (required), description (optional), base_profile (optional name/id to copy from), set_default (bool), set_active (bool).
    - Behavior: validates name; creates profile; optionally clones settings from base; optionally sets default/active with exclusivity.
  - [SettingsProfilesAPI.update_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name or id (target), updates (mapping of allowed fields: name, description, algorithm defaults, paths config, hashing config).
    - Behavior: Partial update with validation; name change preserves uniqueness.
  - [SettingsProfilesAPI.delete_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name or id; confirm (bool).
    - Rules: cannot delete Active; cannot delete last remaining profile; if Default, require selecting a replacement Default first.
  - [SettingsProfilesAPI.copy_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: source_name or id, new_name, description (optional), set_active (bool).
    - Behavior: deep copy of profile-scoped settings rows.

- Active and Default management
  - [SettingsProfilesAPI.set_active_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name or id.
    - Behavior: updates meta.active_profile_id; ensures [ConfigurationManager.switch_profile()](src/pk_py_lib/core/configuration.py:399) aligns in-process.
  - [SettingsProfilesAPI.set_default_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name or id.
    - Behavior: sets profiles.is_default=1 and clears all others; does not implicitly change Active.

- Validation helpers
  - [SettingsProfilesAPI.validate_profile_name()](src/pk_py_lib/api/settings_profiles.py:1)
    - Rules: required; 1–64 characters; allowed: letters, digits, space, underscore, hyphen; uniqueness case-insensitive.
  - [SettingsProfilesAPI.validate_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Validates field ranges and referential constraints; returns issues and suggestions suitable for UI display.

- Import/Export
  - [SettingsProfilesAPI.export_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: name or id, path. Exports profile metadata and profile-scoped settings to JSON.
  - [SettingsProfilesAPI.import_profile()](src/pk_py_lib/api/settings_profiles.py:1)
    - Params: path, name (optional override), set_active (optional). Creates a new profile from JSON, validating name.

Return Shapes and Errors
- All methods return ApiResponse per canonical pattern; see [ApiResponse](docs/roo/img-app-api-specifications.md:16) and ErrorCodes in [ErrorCodes](docs/roo/img-app-api-specifications.md:1167).
- Common error codes:
  - INVALID_CONFIG: validation failed (e.g., duplicate name, invalid characters, out-of-range thresholds).
  - LOCKED_DB: database locked; advise retry.
  - UNKNOWN_ERROR: unexpected failures; include diagnostics.
- Non-destructive behaviors:
  - Update/Apply uses transactions; failures rollback completely.
  - Delete requires confirmation and respects protection rules (not Active, not last).

Initialization Behavior (First Launch)
- On first use, when profiles table is empty:
  - The GUI manager prompts creation of a first profile. See UI spec in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1).
  - meta.active_profile_id is set to the newly created profile upon successful save.
- When profiles exist but meta.active_profile_id is missing:
  - The Default profile (if any) is set Active; otherwise the lexicographically first profile is set Active.

Active vs Default Semantics
- Active:
  - The profile in effect for the current session.
  - Stored in meta.active_profile_id; switching Active is explicit and does not modify is_default.
- Default:
  - Preferred profile to select on next launch; at most one profile has is_default=1.
  - Changing Default does not change Active until the next session (or unless user chooses Set Active).

Validation Rules (canonical)
- Name:
  - Required, 1–64 chars; allowed: [A–Z a–z 0–9 space _ -]; uniqueness case-insensitive.
- Thresholds:
  - UI percent 0–100 maps to internal 0.0–1.0; see helpers in [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1).
- Paths:
  - Validation warns on inaccessible paths; Save is allowed with warnings (non-strict mode).
- Hashing options:
  - Algorithm values per canonical list; staged hashing boolean; partial size in KB range [64, 2048] (advisory).

Usage Notes
- The application’s startup flow must call [SettingsProfilesAPI.set_active_profile()](src/pk_py_lib/api/settings_profiles.py:1) based on user selection in the modal before creating the main window.
- The settings UI should use [SettingsProfilesAPI.validate_profile_name()](src/pk_py_lib/api/settings_profiles.py:1) for immediate feedback while typing names.

Next Steps
- Implement [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1) aligning with this contract.
- Implement core manager [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) to enforce invariants.
- Integrate modal at startup (see implementation guide section).