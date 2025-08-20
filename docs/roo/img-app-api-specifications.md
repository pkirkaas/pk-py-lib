# KDC Image Organizer - API Specifications
> Updated for Settings Profiles v1 (Option A) — Balanced Defaults — Package A — Set A
>
>
> This document adds canonical Option A profile I/O (create/update/get/validate), normalized views, and run specifications for duplicates (BLAKE3) and similarity (pHash with Degree 0–100 UI → [0.0..1.0]). Cross-references: data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), technical architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md), decision §18 in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).

## 1. Overview

This document defines the API interfaces between the img-app application and the pk-py-lib component library. All APIs follow consistent patterns for error handling, data validation, and async operations.

Note — v1 scope and sources of truth
- Report-only in v1: All Run endpoints produce reports only; no file-altering actions (move/delete/copy) are exposed in v1. Action endpoints are deferred (see [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)).
- Centralized validator and schema: Default-filling and validation rules are enforced by the centralized validator and the canonical JSON Schema. The normalized view returned by the API includes defaults applied and degree normalization. References: [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), and decision DEC-SettingsProfilesV1-OptionA-Balanced-PackageA-SetA in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).
- Direction gating (Set A): Direction defaults to A_TO_B but remains disabled until both pools validate; Save/Run buttons are gated by the validator’s capability flags (see [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md) and [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md)).
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
        algorithm: str = "pHash",
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
        algorithms: List[str] = ["pHash"],
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
    PANEL_TOGGLED = "ui.panel_toggled"
    
    # Data events
    CACHE_CLEARED = "data.cache_cleared"
    SETTINGS_CHANGED = "data.settings_changed"
    PROFILE_SWITCHED = "data.profile_switched"
```
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
        algorithms=["pHash", "histogram"],
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
  - Balanced defaults policy (Option A v1): required pool root paths MUST exist and be readable; Save and Run are blocked until fixed. Errors: FILE_MISSING or PERMISSION_DENIED.
- Hashing options:
  - Algorithm values per canonical list; staged hashing boolean; partial size in KB range [64, 2048] (advisory).

Usage Notes
- The application’s startup flow must call [SettingsProfilesAPI.set_active_profile()](src/pk_py_lib/api/settings_profiles.py:1) based on user selection in the modal before creating the main window.
- The settings UI should use [SettingsProfilesAPI.validate_profile_name()](src/pk_py_lib/api/settings_profiles.py:1) for immediate feedback while typing names.

Next Steps
- Implement [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:1) aligning with this contract.
- Implement core manager [src/pk_py_lib/core/settings_profiles.py](src/pk_py_lib/core/settings_profiles.py:1) to enforce invariants.
- Integrate modal at startup (see implementation guide section).
<!-- Finalized Settings Profiles API aligning with implemented code -->

## 13A. Settings Profiles API — Finalized Contract (Library)

Status: Approved

Purpose
- Finalize the profile-management API contract to match the implemented library code and canonical decisions. Supersedes earlier placeholders referencing `get_profile(name)` or name-based operations; the canonical API is id-centric.

Scope and Data
- Persistence: SQLite settings.db via [DatabaseManager.initialize()](src/pk_py_lib/core/database.py:415)
- Tables used: `settings_profiles`, `meta`
- Canonical meta key: `meta.active_profile_id` stores the current Active profile id (INTEGER as text)
- Core logic: [SettingsProfilesManager](src/pk_py_lib/core/settings_profiles.py:95)
- API adapter (this contract): [SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69)
- GUI consumers must not access the DB directly; always use the API

Data Shapes
- SettingsProfile (dictionary returned by API):
  - id: int
  - name: str
  - data: dict (JSON-serializable payload)
  - is_default: bool
  - created_at: Optional[str] (ISO8601 Z)
  - updated_at: Optional[str] (ISO8601 Z)
  - is_active: bool (added by list_profiles when enriched)

API Surface (implemented)
- Listing and retrieval
  - [SettingsProfilesAPI.list_profiles()](src/pk_py_lib/api/settings_profiles.py:109)
    - Returns List[SettingsProfile] with is_active boolean computed from meta.active_profile_id
  - [SettingsProfilesAPI.get_profile()](src/pk_py_lib/api/settings_profiles.py:131)
    - Get by id (int). Returns 404-like ApiResponse.fail when not found (INVALID_CONFIG)
  - [SettingsProfilesAPI.get_active()](src/pk_py_lib/api/settings_profiles.py:153)
    - Returns the active profile dict or None when no profiles exist

- Create / Update / Delete / Copy
  - [SettingsProfilesAPI.create()](src/pk_py_lib/api/settings_profiles.py:172)
    - Params: name: str, data: Optional[dict] = None, make_active: bool = False, make_default: bool = False
    - Behavior: validates name; persists; optional default exclusivity; optional set active
  - [SettingsProfilesAPI.update()](src/pk_py_lib/api/settings_profiles.py:191)
    - Params: profile_id: int, name?: str, data?: dict, make_default?: bool
    - Behavior: partial update; name uniqueness preserved; default exclusivity when requested
  - [SettingsProfilesAPI.delete()](src/pk_py_lib/api/settings_profiles.py:214)
    - Params: profile_id: int
    - Invariants: cannot delete Active; cannot delete last remaining
  - [SettingsProfilesAPI.copy()](src/pk_py_lib/api/settings_profiles.py:230)
    - Params: source_profile_id: int, new_name: str, make_active: bool = False, make_default: bool = False
    - Behavior: deep copy (data cloned); optional default/active

- Active / Default management
  - [SettingsProfilesAPI.set_active()](src/pk_py_lib/api/settings_profiles.py:260)
    - Params: profile_id: int
    - Updates meta.active_profile_id; GUI/app must call [ConfigurationManager.switch_profile()](src/pk_py_lib/core/configuration.py:399) afterward to align in-process state
  - [SettingsProfilesAPI.set_default()](src/pk_py_lib/api/settings_profiles.py:276)
    - Params: profile_id: int
    - Sets is_default=1 and clears others

- Validation
  - [SettingsProfilesAPI.validate_name()](src/pk_py_lib/api/settings_profiles.py:295)
    - Syntax/length validation; uniqueness enforced on write

- Import / Export
  - [SettingsProfilesAPI.export_profile()](src/pk_py_lib/api/settings_profiles.py:314)
    - Params: profile_id: int; returns portable dictionary payload
  - [SettingsProfilesAPI.import_profile()](src/pk_py_lib/api/settings_profiles.py:329)
    - Params: payload: dict, strategy: str = "fail_on_conflict" | "rename" | "overwrite"
    - Behavior: creates/renames/overwrites per strategy; optional is_default honored with exclusivity

Validation Rules (canonical)
- Name: required; 1–64 chars; charset [A–Z a–z 0–9 space _ -]; case-insensitive uniqueness (enforced by core)
- Data: JSON-serializable dictionary
- Default vs Active semantics: setting Default does not change Active; setting Active does not change Default; see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:261)

Errors and Mappings
- The API adapter maps exceptions to ErrorCodes:
  - ValueError → INVALID_CONFIG
  - sqlite3.OperationalError with "locked" → LOCKED_DB
  - PermissionError → PERMISSION_DENIED
  - Otherwise → UNKNOWN_ERROR
- Reference implementation: [_map_exception](src/pk_py_lib/api/settings_profiles.py:48)

Acceptance Criteria (verifiable)
- list_profiles returns all profiles sorted by name with is_active flags set correctly
- create enforces name rules and uniqueness; optional default exclusivity; optional active sets meta.active_profile_id
- update preserves invariants; default exclusivity when True; timestamps updated
- delete prevents deleting Active and last remaining; returns success True when deleted
- copy duplicates data with new unique name; optional default/active behave correctly
- set_active writes meta.active_profile_id; returned profile matches selected id
- set_default enforces single default flag across rows
- export_profile returns full payload dict including data, timestamps
- import_profile honors strategy semantics and default exclusivity
- All mutating operations are transactional; on failure, state is unchanged and ApiResponse.fail contains error and ErrorCodes
- GUI dialog uses id-centric operations exclusively and follows the startup gate contract

Notes on GUI and Module Path
- Reusable dialog path: [src/pk_py_lib/gui/settings_manager/dialog.py](src/pk_py_lib/gui/settings_manager/dialog.py:1) (supersedes older `gui/settings/profile_manager.py` reference)
- App integration helper: [img_app/img_app/widgets/settings_manager.py](img_app/img_app/widgets/settings_manager.py:1) blocks startup until a valid Active profile is set

## 13B. Settings Profiles v1 (Option A) — API I/O, Validation, and Run (report-only)

Scope
- Canonicalize the API contracts specific to Option A:
  - Strongly-typed Settings Profile payload (Pools A/B; Mode: duplicates vs similarity; Scope/Direction; Output=report_only).
  - Centralized validation returning normalized view and UI enablement signals.
  - Run specifications for duplicates (BLAKE3) and similarity (pHash; Degree UI 0–100 → internal [0.0..1.0]).
- Cross-references: data model [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md), UI [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md), architecture [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md), errors [docs/roo/img-app-error-handling-edge-cases.md](docs/roo/img-app-error-handling-edge-cases.md), decision §18 in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md).
- Validation utilities (design reference): [src/pk_py_lib/gui/settings_manager/validators.py](src/pk_py_lib/gui/settings_manager/validators.py:1), degree helpers: [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1).
- Profiles API adapter (design reference): [src/pk_py_lib/api/settings_profiles.py](src/pk_py_lib/api/settings_profiles.py:69).

13B.0 Balanced Defaults — Defaulting and Normalization (Option A v1)
- Absent fields are filled by the centralized validator using the Balanced defaults pack and returned explicitly in the normalized view.
- Defaults (authoritative; see [data model](docs/roo/img-app-data-model.md:864)):
  - Pools: recurse=true; max_depth=0 (unlimited); follow_symlinks=false; include_hidden=false; include=["**/*"]; exclude=[]; type_filters images only [.jpg .jpeg .png .webp .tiff .bmp .gif .heic .heif].
  - Similarity: algorithm="pHash"; degree_ui=90; phash.hash_size=8.
  - Duplicates: algorithm fixed "blake3" (no degree).
  - Scope/Direction: kind defaults to "two_pool"; direction defaults to "A_TO_B" (enabled only when both pools validate).
  - Output: mode="report_only".
  - Patterns: glob (gitignore-style), relative to pool root; case handling is OS-aware (Windows case-insensitive; POSIX case-sensitive).
- Normalized responses:
  - POST /profiles/validate and all Run endpoints return a normalized profile with defaults applied.

Example — validate with omitted fields (defaults applied)
Request:
```json
POST /profiles/validate
{
  "profile": {
    "id": "11111111-2222-3333-4444-555555555555",
    "name": "A→B similar (defaults)",
    "pools": {
      "A": { "root_path": "D:/Reference" },
      "B": { "root_path": "F:/Target" }
    },
    "mode": "similarity",
    "criteria": {},
    "scope": { "kind": "two_pool" },
    "output": {}
  }
}
```
Response (excerpt):
```json
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "normalized": {
      "mode": "similarity",
      "criteria": { "algorithm": "pHash", "degree_ui": 90, "degree_normalized": 0.9, "phash": { "hash_size": 8 } },
      "scope": { "kind": "two_pool", "direction": "A_TO_B" },
      "output": { "mode": "report_only" },
      "pools": {
        "A": { "root_path": "D:/Reference", "recurse": true, "max_depth": 0, "include": ["**/*"], "exclude": [], "follow_symlinks": false, "include_hidden": false,
               "type_filters": [".jpg",".jpeg",".png",".webp",".tiff",".bmp",".gif",".heic",".heif"] },
        "B": { "root_path": "F:/Target",   "recurse": true, "max_depth": 0, "include": ["**/*"], "exclude": [], "follow_symlinks": false, "include_hidden": false,
               "type_filters": [".jpg",".jpeg",".png",".webp",".tiff",".bmp",".gif",".heic",".heif"] }
      }
    }
  }
}
```

13B.1 Profile I/O shapes (create, update, get)
- Input/Output payloads use the Option A profile schema defined in the data model (see JSON Schema in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md)).
- Minimal canonical shapes:

Create
- Request body (JSON):
```
{
  "name": "A→B similar (90%)",
  "data": { /* full SettingsProfileOptionA object (see schema) */ },
  "make_active": false,
  "make_default": false
}
```
- Response body:
```
{
  "success": true,
  "data": {
    "id": 42,
    "name": "A→B similar (90%)",
    "is_default": false,
    "is_active": false,
    "created_at": "2025-08-19T00:00:00Z",
    "updated_at": "2025-08-19T00:00:00Z",
    "data": { /* stored profile object */ }
  },
  "error": null,
  "code": null,
  "metadata": {}
}
```

Update
- Request body (JSON):
```
{
  "profile_id": 42,
  "name": "A uniques vs B (90%)",
  "data": { /* partial or full profile object; server applies merge-with-validate */ },
  "make_default": false
}
```
- Response body mirrors Create.

Get
- Request: by id (preferred) or list.
- Response: ApiResponse with SettingsProfile entries; list responses include computed is_active.

13B.2 Validation API (centralized; GUI and core use the same source of truth)
- Endpoint: POST /profiles/validate
- Purpose: Validate a draft Settings Profile (Option A) and return:
  - is_valid boolean (block Save/Run when false),
  - errors and warnings with JSON Pointers to offending fields,
  - normalized view for UI preview and for engine consumption (degree normalized, defaults applied).

Request
```
{
  "profile": { /* full or partial profile per Option A schema */ }
}
```

Response
```
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": [
      { "path": "/pools/A/exclude/0", "code": "PATTERN_WARN", "message": "Pattern excludes hidden files broadly" }
    ],
    "capabilities": {
      "can_run": true,
      "can_enable_direction_controls": true,
      "can_enable_degree_controls": true,
      "required_pools": ["A","B"],
      "can_save": true
    },
    "normalized": {
      "mode": "similarity",
      "criteria": {
        "algorithm": "pHash",
        "degree_ui": 90,
        "degree_normalized": 0.90,
        "phash": { "hash_size": 8 }
      },
      "scope": { "kind": "two_pool", "direction": "A_TO_B" },
      "output": { "mode": "report_only" },
      "pools": {
        "A": { "root_path": "D:/Reference", "recurse": true, "include": ["**/*.jpg"], "exclude": [] },
        "B": { "root_path": "F:/Target", "recurse": true, "include": ["**/*.jpg"], "exclude": [] }
      }
    }
  },
  "error": null,
  "code": null,
  "metadata": {}
}
```

Capabilities (validator response)
- can_run: boolean — current draft can be executed (no blocking errors)
- can_enable_direction_controls: boolean — scope.kind="two_pool" and both pools validate
- can_enable_degree_controls: boolean — mode="similarity" with degree_ui in range
- required_pools: array — ["A"] or ["A","B"] depending on scope
- can_save: boolean — profile structure valid to persist

Validation rules (excerpt; full list in data model)
- Mode duplicates: criteria.algorithm = blake3; degree_ui MUST be absent.
- Mode similarity: criteria.algorithm = pHash; degree_ui ∈ [0..100].
- Single-pool: direction omitted; Two-pool: B required and direction required.
- Paths exist; patterns compile; numeric ranges (depth, size, dates) coherent.

Error codes
- INVALID_CONFIG (syntax, bounds, incompatible options),
- FILE_MISSING (nonexistent root_path),
- PERMISSION_DENIED (inaccessible path),
- LOCKED_DB (rare, for persistence-backed validation),
- UNKNOWN_ERROR.

13B.3 Run API (report-only) — Duplicates and Similarity

Contract
- The Run endpoints accept either:
  - profile_id (server loads and validates the stored profile, then normalizes), or
  - inline profile payload (validate + normalize; nothing is persisted).
- Execution is report-only in v1: no file mutations.

Endpoints
- POST /runs/duplicates
- POST /runs/similarity

Common request shape
```
{
  "profile_id": 42,
  "override": { /* optional partial profile to override before validate+normalize */ },
  "limit": { "max_groups": 1000, "max_items_per_group": 100 },
  "progress": { "subscribe": false }
}
```
- Alternatively: replace profile_id with "profile": { /* full profile */ }.

13B.3.1 Duplicates (BLAKE3)

Behavior
- Single-pool: cluster duplicate files within Pool A; groups consist of files sharing the same blake3 hash.
- Two-pool A→B or B→A: report only matches found in the target pool; reference pool items show as group headers; no degree.
- Two-pool "without" directions: list items in reference pool with zero matches in the opposite pool.

Response (single-pool)
```
{
  "success": true,
  "data": {
    "mode": "duplicates",
    "scope": { "kind": "single_pool" },
    "summary": { "groups": 23, "files": 124, "reference_pool": "A" },
    "groups": [
      {
        "group_id": "g-0001",
        "hash_blake3": "a1b2c3...",
        "files": [
          { "path": "C:/Photos/x.jpg", "size": 5242880, "pool": "A" },
          { "path": "C:/Photos/y.jpg", "size": 5242880, "pool": "A" }
        ]
      }
    ]
  },
  "error": null,
  "code": null,
  "metadata": {}
}
```

Response (two-pool A→B)
```
{
  "success": true,
  "data": {
    "mode": "duplicates",
    "scope": { "kind": "two_pool", "direction": "A_TO_B" },
    "summary": { "references": 300, "matches": 512, "reference_pool": "A", "target_pool": "B" },
    "matches_by_reference": [
      {
        "reference": { "path": "D:/Masters/a.jpg", "size": 7331 },
        "matches": [
          { "path": "E:/Working/a_copy.jpg", "size": 7331, "hash_blake3": "f00d..." }
        ]
      }
    ]
  }
}
```

Response (A without matches in B)
```
{
  "success": true,
  "data": {
    "mode": "duplicates",
    "scope": { "kind": "two_pool", "direction": "A_WITHOUT_IN_B" },
    "summary": { "non_matches": 127, "reference_pool": "A", "target_pool": "B" },
    "non_matches": [
      { "path": "D:/Masters/unique.jpg", "size": 12345 }
    ]
  }
}
```

13B.3.2 Similarity (pHash, Degree)

Behavior
- Similarity uses normalized degree t = degree_ui / 100.
- For 64-bit pHash with Hamming distance d: degree_ui = round(100 * (1 - d/64)); a match requires degree_ui ≥ threshold_ui.
- Single-pool: cluster similar images within A (s ≥ t).
- Two-pool directions: produce matches per reference in the target pool; "without" lists reference items with zero matches above threshold.

Response (single-pool)
```
{
  "success": true,
  "data": {
    "mode": "similarity",
    "criteria": { "algorithm": "pHash", "degree_ui": 90, "degree_normalized": 0.90 },
    "scope": { "kind": "single_pool" },
    "summary": { "groups": 18, "files": 96, "reference_pool": "A" },
    "groups": [
      {
        "group_id": "s-0001",
        "representative": { "path": "C:/Photos/ref.jpg", "size": 4123 },
        "members": [
          { "path": "C:/Photos/ref.jpg", "similarity": 1.00 },
          { "path": "C:/Photos/var.jpg", "similarity": 0.93 }
        ],
        "stats": { "avg_similarity": 0.94, "min_similarity": 0.90, "max_similarity": 1.00 }
      }
    ]
  }
}
```

Response (two-pool A→B)
```
{
  "success": true,
  "data": {
    "mode": "similarity",
    "criteria": { "algorithm": "pHash", "degree_ui": 85, "degree_normalized": 0.85 },
    "scope": { "kind": "two_pool", "direction": "A_TO_B" },
    "summary": { "references": 300, "matches": 842, "reference_pool": "A", "target_pool": "B" },
    "matches_by_reference": [
      {
        "reference": { "path": "D:/Reference/a.jpg" },
        "matches": [
          { "path": "F:/Target/a1.jpg", "similarity": 0.92 },
          { "path": "F:/Target/a2.jpg", "similarity": 0.87 }
        ]
      }
    ]
  }
}
```

Response (A without matches in B)
```
{
  "success": true,
  "data": {
    "mode": "similarity",
    "criteria": { "algorithm": "pHash", "degree_ui": 90, "degree_normalized": 0.90 },
    "scope": { "kind": "two_pool", "direction": "A_WITHOUT_IN_B" },
    "summary": { "non_matches": 54, "reference_pool": "A", "target_pool": "B" },
    "non_matches": [
      { "path": "D:/Reference/r001.jpg" },
      { "path": "D:/Reference/r002.jpg" }
    ]
  }
}
```

13B.4 Error conditions and messages (Option A)
- INVALID_CONFIG
  - degree_ui present with mode=duplicates
  - mode=similarity with missing/out-of-range degree_ui
  - scope.two_pool without Pool B or without direction
  - pattern compilation error; max_depth < 0; inverted min/max size or date
  - Message examples:
    - "Degree is not allowed in duplicates mode"
    - "Degree must be between 0 and 100"
    - "Two-pool direction requires both pools A and B"
- FILE_MISSING
  - "Root path does not exist or is inaccessible: C:/Missing"
- PERMISSION_DENIED
  - "Insufficient permissions to read: D:/Locked"
- LOCKED_DB
  - "Settings database is in use; retry later"
- UNKNOWN_ERROR
  - Generic fallback (include diagnostics)

13B.5 Example end-to-end payloads (aligned with schema)

A) Validate + Run (two-pool similarity; A→B)
- Validate request:
```
POST /profiles/validate
{
  "profile": {
    "id": "9b0d3f12-0d0a-4a3b-8e0f-4c1d2e3f4a5b",
    "name": "A→B similar (90%)",
    "pools": {
      "A": { "root_path": "D:/Reference", "recurse": true, "include": ["**/*.jpg"] },
      "B": { "root_path": "F:/Target", "recurse": true, "include": ["**/*.jpg"] }
    },
    "mode": "similarity",
    "criteria": { "algorithm": "pHash", "degree_ui": 90 },
    "scope": { "kind": "two_pool", "direction": "A_TO_B" },
    "output": { "mode": "report_only" },
    "created_at": "2025-08-19T00:00:00Z",
    "updated_at": "2025-08-19T00:00:00Z"
  }
}
```
- Run request:
```
POST /runs/similarity
{
  "profile_id": 42
}
```
- Run response: see "Response (two-pool A→B)" above.

B) Validate failure (duplicates with degree)
- Request has: "mode": "duplicates", "criteria": { "algorithm": "blake3", "degree_ui": 80 }
- Response:
```
{
  "success": true,
  "data": {
    "is_valid": false,
    "errors": [
      { "path": "/criteria/degree_ui", "code": "INVALID_CONFIG", "message": "Degree is not allowed in duplicates mode" }
    ],
    "warnings": [],
    "normalized": null
  },
  "error": null,
  "code": "INVALID_CONFIG"
}
```

Implementation notes
- The validator applies normalization and supplies "normalized" to GUI preview and to execution.
- Degree normalization uses helpers in [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1).
- The API adapter maps exceptions to ErrorCodes (see §10.0 and [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md)).

### 13B.SA Set A validation examples (capabilities)

Example — Only Pool A valid (Set A initial state; single-pool duplicates)
Request:
```json
POST /profiles/validate
{
  "profile": {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "name": "A only — duplicates",
    "pools": {
      "A": { "root_path": "D:/Reference" }
    },
    "mode": "duplicates",
    "criteria": { "algorithm": "blake3" },
    "scope": { "kind": "single_pool" },
    "output": { "mode": "report_only" }
  }
}
```
Response (excerpt):
```json
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "capabilities": {
      "can_run": true,
      "can_enable_direction_controls": false,
      "can_enable_degree_controls": false,
      "required_pools": ["A"],
      "can_save": true
    },
    "normalized": {
      "mode": "duplicates",
      "criteria": { "algorithm": "blake3" },
      "scope": { "kind": "single_pool" },
      "output": { "mode": "report_only" },
      "pools": {
        "A": {
          "root_path": "D:/Reference",
          "recurse": true,
          "max_depth": 0,
          "include": ["**/*"],
          "exclude": [],
          "follow_symlinks": false,
          "include_hidden": false,
          "type_filters": [".jpg",".jpeg",".png",".webp",".tiff",".bmp",".gif",".heic",".heif"]
        }
      }
    }
  }
}
```

Example — Both Pools valid (two-pool similarity; direction enabled with default A_TO_B)
Request:
```json
POST /profiles/validate
{
  "profile": {
    "id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
    "name": "A↔B similarity (90%)",
    "pools": {
      "A": { "root_path": "D:/Reference" },
      "B": { "root_path": "F:/Target" }
    },
    "mode": "similarity",
    "criteria": { "algorithm": "pHash", "degree_ui": 90 },
    "scope": { "kind": "two_pool" },
    "output": { "mode": "report_only" }
  }
}
```
Response (excerpt):
```json
{
  "success": true,
  "data": {
    "is_valid": true,
    "errors": [],
    "warnings": [],
    "capabilities": {
      "can_run": true,
      "can_enable_direction_controls": true,
      "can_enable_degree_controls": true,
      "required_pools": ["A","B"],
      "can_save": true
    },
    "normalized": {
      "mode": "similarity",
      "criteria": {
        "algorithm": "pHash",
        "degree_ui": 90,
        "degree_normalized": 0.90,
        "phash": { "hash_size": 8 }
      },
      "scope": { "kind": "two_pool", "direction": "A_TO_B" },
      "output": { "mode": "report_only" },
      "pools": {
        "A": { "root_path": "D:/Reference", "recurse": true, "max_depth": 0, "include": ["**/*"], "exclude": [], "follow_symlinks": false, "include_hidden": false,
               "type_filters": [".jpg",".jpeg",".png",".webp",".tiff",".bmp",".gif",".heic",".heif"] },
        "B": { "root_path": "F:/Target",   "recurse": true, "max_depth": 0, "include": ["**/*"], "exclude": [], "follow_symlinks": false, "include_hidden": false,
               "type_filters": [".jpg",".jpeg",".png",".webp",".tiff",".bmp",".gif",".heic",".heif"] }
      }
    }
  }
}
```

Notes
- Direction radios are enabled only in the second example because capabilities.can_enable_direction_controls = true when both pools validate.
- Degree controls are enabled only in similarity mode (can_enable_degree_controls = true).
- required_pools is an array (["A"] or ["A","B"]) and should be used verbatim by the UI to render concise gating messages.
- See capabilities derivation rules in [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1459) and UI consumption in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:999).

## 13B.0a Normalization mapping and Package A addenda (Option A v1)
- Degree normalization
  - UI degree 0–100 maps to internal degree_normalized ∈ [0.0..1.0] as degree_normalized = degree_ui / 100 (see helpers in [src/pk_py_lib/core/utils/thresholds.py](src/pk_py_lib/core/utils/thresholds.py:1)).
- Package A degree formula (64‑bit pHash)
  - degree_ui = round(100 * (1 - d/64)) where d is the Hamming distance between 64‑bit hashes.
  - Match rule (similarity): a match requires degree_ui ≥ threshold_ui (see decision in [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:508)).
- Addendum to defaults (explicit)
  - scope.single_pool_clustering default=false (see schema in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1288)).
  - Direction defaults to A_TO_B but is inert until both pools validate (Set A); see gating notes and capabilities below and [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:993).

## 13B.1R Profile management endpoints (REST, Option A v1)
These HTTP contracts complement the library API ([SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69)) and use the Option A schema and normalization rules documented in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1023) and the centralized validator described in [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1348).

Common behaviors
- Request bodies reference the Option A profile schema. Omitted fields are default-filled in the normalized view by the centralized validator (Balanced defaults).
- Responses are wrapped in the canonical ApiResponse (see [ApiResponse](docs/roo/img-app-api-specifications.md:22), [ErrorCodes](docs/roo/img-app-api-specifications.md:1169)).
- Error payloads include a top-level code plus a structured details list with per-field issues (JSON Pointer path).

Structured error payload (embedded within ApiResponse on failure)
```json
{
  "success": false,
  "error": "Human-readable summary",
  "code": "INVALID_CONFIG",
  "metadata": {
    "details": [
      { "code": "PATH_MISSING", "message": "Pool A root_path not found", "path": "/pools/A/root_path" }
    ]
  }
}
```

1) POST /profiles/validate
- Purpose: Validate a transient (draft) profile payload and return defaults-applied normalized_profile, validation report, and capability flags.
- Request body:
  - { "profile": SettingsProfileOptionA (partial allowed) }
- Response body (success 200):
  - { success, data: { normalized, errors, warnings, capabilities, is_valid }, code:null, error:null }
  - normalized includes degree_normalized when mode="similarity"
- Status codes:
  - 200 OK on successful validation (even when is_valid=false; error details are returned inside data.errors)
  - 400 Bad Request on malformed JSON (SCHEMA_VALIDATION_ERROR)
- See full shape and examples in §13B.2 and examples below.

2) POST /profiles
- Purpose: Create a profile; persist metadata and data; optionally set as active/default.
- Request body:
```json
{
  "name": "My Profile",
  "data": { /* SettingsProfileOptionA per schema; partial allowed, defaults applied on read */ },
  "make_active": false,
  "make_default": false
}
```
- Response body (201 Created):
```json
{
  "success": true,
  "data": {
    "id": 42,
    "name": "My Profile",
    "is_default": false,
    "is_active": false,
    "created_at": "2025-08-19T00:00:00Z",
    "updated_at": "2025-08-19T00:00:00Z",
    "data": { /* persisted profile object as saved (not normalized view) */ }
  }
}
```
- Status codes and errors:
  - 201 Created on success
  - 400 INVALID_CONFIG (name pattern invalid; payload fails schema/invariants)
  - 409 INVALID_CONFIG (duplicate name)
  - 423 LOCKED_DB (database locked)
  - Error payload includes details[] entries (see common format)

3) PUT /profiles/{profile_id}
- Purpose: Update profile metadata and/or data; returns updated normalized view and validation report.
- Request body:
```json
{
  "name": "Renamed Profile (optional)",
  "data": { /* partial update; server merges then validate+normalize */ },
  "make_default": false
}
```
- Response body (200 OK):
```json
{
  "success": true,
  "data": {
    "profile": { "id": 42, "name": "Renamed Profile (optional)", "is_default": false, "updated_at": "..." },
    "normalized": { /* normalized profile with defaults applied (includes degree_normalized when applicable) */ },
    "validation": { "is_valid": true, "errors": [], "warnings": [] },
    "capabilities": { "can_run": true, "can_enable_direction_controls": true, "required_pools": ["A","B"], "can_save": true }
  }
}
```
- Status codes and errors:
  - 200 OK on success
  - 400 INVALID_CONFIG (invalid fields, e.g., degree in duplicates mode)
  - 404 INVALID_CONFIG (not found)
  - 423 LOCKED_DB

4) GET /profiles/{profile_id}
- Purpose: Fetch a persisted profile (as saved). Optional normalized view.
- Query:
  - ?normalized=true to additionally return normalized (defaults applied) beside persisted data
- Response body (200 OK):
```json
{
  "success": true,
  "data": {
    "profile": { "id": 42, "name": "My Profile", "is_default": false, "created_at": "...", "updated_at": "...", "data": { /* as saved */ } },
    "normalized": { /* present only when normalized=true; defaults applied */ }
  }
}
```
- Status codes and errors:
  - 200 OK
  - 404 INVALID_CONFIG (not found)

5) GET /profiles
- Purpose: List profiles with basic metadata; optional filters (by name substring, is_default, is_active).
- Response body (200 OK):
```json
{
  "success": true,
  "data": [
    { "id": 12, "name": "Default", "is_default": true,  "is_active": false, "created_at": "...", "updated_at": "..." },
    { "id": 42, "name": "My Profile", "is_default": false, "is_active": true, "created_at": "...", "updated_at": "..." }
  ]
}
```

6) DELETE /profiles/{profile_id}
- Purpose: Delete a profile. Optional in v1; if deferred, server should return 405 Method Not Allowed. When implemented, invariants apply (cannot delete Active; cannot delete last remaining).
- Response (200 OK):
```json
{ "success": true, "data": { "deleted": true } }
```
- Status codes and errors:
  - 200 OK on success
  - 400 INVALID_CONFIG (attempt to delete Active or last remaining)
  - 404 INVALID_CONFIG (not found)
  - 405 when deferred in this deployment
  - 423 LOCKED_DB

Notes
- Name validation rules: ^[A-Za-z0-9 _-]{1,64}$; uniqueness case-insensitive (see [SettingsProfilesAPI.validate_name()](src/pk_py_lib/api/settings_profiles.py:295)).
- Active/Default invariants: setting Default does not change Active; setting Active does not change Default (see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:317) and [SettingsProfilesAPI.set_active()](src/pk_py_lib/api/settings_profiles.py:260), [SettingsProfilesAPI.set_default()](src/pk_py_lib/api/settings_profiles.py:276)).

## 13B.3R Run endpoints (report-only) — quick reference
This summarizes §13B.3. Full examples remain below.

- POST /runs/duplicates
  - Input: profile_id or inline "profile". mode must be "duplicates".
  - Output: single-pool clusters OR two-pool matches/non-matches. No degree. Algorithm fixed to BLAKE3.
  - Direction defaults to A_TO_B but remains inactive until both pools validate (Set A).
- POST /runs/similarity
  - Input: profile_id or inline "profile". mode must be "similarity".
  - Output: groups or matches with similarity values; non_matches arrays when using WITHOUT directions.
  - Degree threshold uses degree_normalized = degree_ui / 100; Package A formula defines degree_ui from pHash distances.

## 13B.4a Error formats and canonical codes (Option A v1)
Structured error format (per-item details) used inside ApiResponse.metadata.details:
- Fields: code, message, details (optional map), path (JSON Pointer)

Canonical validator-level codes (non-exhaustive)
- PATH_MISSING — pools.*.root_path does not exist
- PATH_UNREADABLE — pools.*.root_path exists but is not accessible
- DEGREE_OUT_OF_RANGE — criteria.degree_ui not in [0..100]
- INVALID_COMBINATION — incompatible fields (e.g., degree present in duplicates mode)
- POOL_B_REQUIRED_FOR_DIRECTION — scope.kind="two_pool" requires Pool B and direction
- PATTERN_COMPILE_ERROR — include/exclude pattern failed to compile
- SCHEMA_VALIDATION_ERROR — payload shape invalid (JSON Schema)
- Notes and mappings:
  - OS-aware pattern case: Windows case-insensitive; POSIX case-sensitive (see [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1111), [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1371)).
  - Extension filter matching is case-insensitive on all OS.
  - Hidden excluded via attribute by default (include_hidden=false).
  - These detail codes are typically surfaced under a top-level ApiResponse.code of INVALID_CONFIG, FILE_MISSING, or PERMISSION_DENIED (see [ErrorCodes](docs/roo/img-app-api-specifications.md:1169)).

## 13B.7 Capability flags and gating (summary, Set A)
Validator emits capability flags consumed by GUI and clients (see derivation rules in [docs/roo/img-app-technical-architecture.md](docs/roo/img-app-technical-architecture.md:1459) and UI consumption in [docs/roo/img-app-ui-design.md](docs/roo/img-app-ui-design.md:1003)):
- can_run: boolean — true only when required pools for the current normalized scope are valid and no blocking errors exist
- can_save: boolean — true when report.is_valid and Pool A is valid (Set A policy)
- can_enable_direction_controls: boolean — true when scope.kind = "two_pool" AND both pools validate (synonym: can_enable_direction)
- can_enable_degree_controls: boolean — true when mode = "similarity"
- required_pools: array — ["A"] or ["A","B"]
- Save/Run gating:
  - Save/Run blocked if any required pool path is missing or unreadable (see [docs/roo/canonical-decisions.md](docs/roo/canonical-decisions.md:15))
  - Direction controls are disabled until both pools validate; when they become enabled, default selection is A_TO_B

## 13B.8 Versioning and extensibility notes
- Versioning
  - profile_version defaults to "1.0.0" (see schema in [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1252)).
  - API is report-only in v1; action endpoints (move/delete/copy) are explicitly deferred.
- Extensibility
  - Future N-pool support (generalizing A/B), additional similarity algorithms (e.g., histogram, feature-based), and pagination for large reports are planned evolutions.
  - Direction set expands naturally with N pools; current tokens are canonical: A_TO_B, B_TO_A, A_WITHOUT_IN_B, B_WITHOUT_IN_A (see [docs/roo/img-app-data-model.md](docs/roo/img-app-data-model.md:1290)).
  - Library API surface will remain the integration point ([SettingsProfilesAPI](src/pk_py_lib/api/settings_profiles.py:69)); REST endpoints mirror that surface for remote or process-separated consumers.
