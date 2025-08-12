# KDC Image Organizer - Error Handling & Edge Cases

## 1. Overview

This document provides comprehensive error handling strategies and edge case scenarios for the KDC Image Organizer application. Each scenario includes detection methods, recovery strategies, and user communication approaches.

## 2. File System Error Scenarios

### 2.1 File Access Errors

#### 2.1.1 Permission Denied
```python
class PermissionErrorHandler:
    """Handle file permission errors."""
    
    def handle_permission_denied(self, file_path: Path, operation: str):
        """
        Scenario: User lacks read/write permissions for file/folder
        
        Recovery Strategy:
        1. Check if running with admin privileges
        2. Offer to skip file
        3. Request elevation if possible
        4. Log detailed error with path
        """
        
        # Detection
        try:
            file_path.stat()
        except PermissionError as e:
            # Recovery options
            recovery_options = [
                "Skip this file and continue",
                "Retry with different credentials",
                "Run application as administrator",
                "Select different folder"
            ]
            
            # User notification
            self.notify_user(
                title="Permission Denied",
                message=f"Cannot access {file_path}",
                details=str(e),
                options=recovery_options
            )
            
            # Log for debugging
            self.logger.warning(
                "Permission denied",
                path=str(file_path),
                operation=operation,
                user=os.getenv('USERNAME')
            )
```

#### 2.1.2 File Locked by Another Process
```python
def handle_file_locked(self, file_path: Path):
    """
    Scenario: File is locked by another application
    
    Edge Cases:
    - File opened in image editor
    - Antivirus scanning file
    - Cloud sync in progress
    - System indexing service
    
    Recovery:
    1. Wait and retry (exponential backoff)
    2. Create read-only copy for analysis
    3. Skip and mark for later retry
    4. Identify locking process if possible
    """
    
    max_retries = 3
    wait_time = 1.0
    
    for attempt in range(max_retries):
        try:
            # Attempt to open file
            with open(file_path, 'rb') as f:
                return f.read()
        except OSError as e:
            if e.errno == 32:  # File locked
                time.sleep(wait_time)
                wait_time *= 2
            else:
                raise
    
    # Fallback: Try read-only shadow copy
    return self.create_shadow_copy(file_path)
```

#### 2.1.3 File Moved/Deleted During Processing
```python
def handle_file_disappeared(self, file_path: Path, cached_hash: str):
    """
    Scenario: File deleted/moved after initial scan
    
    Recovery:
    1. Search for file by hash in common locations
    2. Check recycle bin
    3. Update cache to mark as missing
    4. Offer to remove from results
    """
    
    # Search for relocated file
    possible_locations = [
        file_path.parent,  # Same directory
        Path.home() / "Pictures",  # Common picture folders
        Path.home() / "Downloads",
        Path.home() / "Desktop"
    ]
    
    for location in possible_locations:
        found = self.find_file_by_hash(location, cached_hash)
        if found:
            self.update_file_location(file_path, found)
            return found
    
    # Mark as missing in cache
    self.mark_file_missing(file_path)
```

### 2.2 Network Drive Issues

#### 2.2.1 Network Drive Disconnection
```python
class NetworkDriveHandler:
    """Handle network drive issues."""
    
    def handle_network_disconnection(self, path: Path):
        """
        Scenario: Network drive becomes unavailable during operation
        
        Edge Cases:
        - WiFi disconnection
        - VPN timeout
        - NAS going to sleep
        - SMB/CIFS timeout
        
        Recovery:
        1. Detect network vs local drive
        2. Pause operation and wait for reconnection
        3. Cache partial results
        4. Offer to continue with local files only
        """
        
        if self.is_network_path(path):
            # Monitor network status
            reconnect_timeout = 30  # seconds
            
            if self.wait_for_network(reconnect_timeout):
                # Network restored
                self.resume_operation()
            else:
                # Offer alternatives
                self.offer_offline_mode()
                self.save_partial_results()
```

#### 2.2.2 Slow Network Performance
```python
def handle_slow_network(self, transfer_rate: float):
    """
    Scenario: Network too slow for efficient operation
    
    Detection: Transfer rate < 1MB/s for image operations
    
    Recovery:
    1. Switch to metadata-only mode
    2. Queue files for background processing
    3. Reduce thumbnail quality
    4. Implement adaptive timeout
    """
    
    if transfer_rate < 1_000_000:  # bytes/second
        self.enable_low_bandwidth_mode()
        self.reduce_concurrent_operations()
        self.increase_cache_aggressiveness()
```

### 2.3 Storage Issues

#### 2.3.1 Insufficient Disk Space
```python
class StorageHandler:
    """Handle storage-related errors."""
    
    def handle_disk_full(self, required_space: int, available_space: int):
        """
        Scenario: Not enough space for cache/thumbnails
        
        Edge Cases:
        - Cache directory on different drive
        - System temp directory full
        - User quota exceeded
        
        Recovery:
        1. Automatic cache cleanup
        2. Use alternative temp location
        3. Reduce cache size limit
        4. Stream processing without cache
        """
        
        # Try to free space
        freed = self.cleanup_old_cache_entries()
        
        if freed >= required_space:
            return True
        
        # Offer alternatives
        alternatives = [
            self.get_alternative_cache_locations(),
            self.suggest_cleanup_targets(),
            self.calculate_minimum_cache_size()
        ]
        
        return self.prompt_user_action(alternatives)
```

#### 2.3.2 Cache Corruption
```python
def handle_cache_corruption(self, cache_db: Path):
    """
    Scenario: Cache database corrupted
    
    Detection: SQLite integrity check fails
    
    Recovery:
    1. Attempt automatic repair
    2. Rebuild from backup
    3. Clear and regenerate
    4. Continue without cache
    """
    
    try:
        # Attempt repair
        self.repair_sqlite_db(cache_db)
    except:
        # Try backup
        backup = cache_db.with_suffix('.backup')
        if backup.exists():
            shutil.copy2(backup, cache_db)
        else:
            # Full rebuild
            self.rebuild_cache_from_scratch()
```

## 3. Image Processing Errors

### 3.1 Corrupted Images

#### 3.1.1 Partial Image Corruption
```python
class CorruptedImageHandler:
    """Handle corrupted image files."""
    
    def handle_partial_corruption(self, image_path: Path):
        """
        Scenario: Image partially corrupted but partially readable
        
        Edge Cases:
        - Truncated JPEG
        - Bad EXIF data
        - Color profile corruption
        - Progressive JPEG with missing scans
        
        Recovery:
        1. Try alternative decoders
        2. Extract readable portions
        3. Use file recovery tools
        4. Mark as corrupted but include in results
        """
        
        strategies = [
            self.try_pillow_decoder,
            self.try_opencv_decoder,
            self.try_imagemagick,
            self.extract_thumbnail_from_exif,
            self.create_placeholder_thumbnail
        ]
        
        for strategy in strategies:
            try:
                return strategy(image_path)
            except Exception as e:
                self.log_recovery_attempt(strategy.__name__, e)
                
        return self.create_error_placeholder()
```

#### 3.1.2 Unsupported Format Variations
```python
def handle_format_variation(self, image_path: Path, claimed_format: str):
    """
    Scenario: File extension doesn't match actual format
    
    Edge Cases:
    - JPEG saved as .png
    - WebP with .jpg extension
    - HEIC on system without support
    - Rare formats (JPEG-XR, AVIF)
    
    Recovery:
    1. Detect actual format from headers
    2. Try multiple decoders
    3. Convert using external tools
    4. Install missing codecs
    """
    
    actual_format = self.detect_format_from_header(image_path)
    
    if actual_format != claimed_format:
        self.log_format_mismatch(image_path, claimed_format, actual_format)
        
    # Try format-specific handlers
    return self.get_format_handler(actual_format).decode(image_path)
```

### 3.2 Memory Issues

#### 3.2.1 Out of Memory for Large Images
```python
class MemoryErrorHandler:
    """Handle memory-related errors."""
    
    def handle_large_image_oom(self, image_path: Path, dimensions: tuple):
        """
        Scenario: Image too large to load in memory
        
        Edge Cases:
        - Gigapixel panoramas
        - Uncompressed TIFF files
        - Multi-page TIFF
        - 16/32-bit per channel images
        
        Recovery:
        1. Use memory-mapped loading
        2. Process in tiles
        3. Downsample before processing
        4. Use streaming decoder
        """
        
        width, height = dimensions
        pixel_count = width * height
        
        if pixel_count > 100_000_000:  # 100 megapixels
            # Use tiled processing
            return self.process_image_in_tiles(image_path, tile_size=1024)
        else:
            # Try downsampling
            return self.process_downsampled(image_path, max_size=4096)
```

#### 3.2.2 Memory Fragmentation
```python
def handle_memory_fragmentation(self):
    """
    Scenario: Memory fragmented, unable to allocate large blocks
    
    Recovery:
    1. Force garbage collection
    2. Restart worker processes
    3. Reduce concurrent operations
    4. Implement memory pooling
    """
    
    gc.collect()
    
    if self.get_memory_fragmentation_ratio() > 0.5:
        self.restart_worker_pool()
        self.reduce_batch_size()
```

## 4. Database Errors

### 4.1 Database Lock Issues

#### 4.1.1 Database Locked
```python
class DatabaseErrorHandler:
    """Handle database-related errors."""
    
    def handle_database_locked(self, db_path: Path, operation: str):
        """
        Scenario: SQLite database locked by another process
        
        Edge Cases:
        - Multiple app instances
        - Backup software accessing DB
        - Antivirus scanning
        - Incomplete transaction
        
        Recovery:
        1. Wait with exponential backoff
        2. Use WAL mode
        3. Create temporary copy
        4. Force unlock (risky)
        """
        
        # Enable WAL mode for better concurrency
        self.enable_wal_mode(db_path)
        
        # Retry with backoff
        for attempt in range(5):
            try:
                return self.execute_with_timeout(operation, timeout=5.0)
            except sqlite3.OperationalError as e:
                if "locked" in str(e):
                    time.sleep(2 ** attempt)
                else:
                    raise
                    
        # Last resort: work with copy
        return self.work_with_db_copy(db_path, operation)
```

#### 4.1.2 Database Corruption During Write
```python
def handle_write_corruption(self, db_path: Path, transaction: dict):
    """
    Scenario: Database corrupted during write operation
    
    Recovery:
    1. Rollback transaction
    2. Restore from journal
    3. Replay from operation log
    4. Restore from backup
    """
    
    # Check for journal files
    journal = db_path.with_suffix('.db-journal')
    wal = db_path.with_suffix('.db-wal')
    
    if journal.exists() or wal.exists():
        self.recover_from_journal(db_path)
    else:
        self.restore_from_last_backup(db_path)
        self.replay_operations_since_backup(transaction)
```

## 5. Algorithm Processing Errors

### 5.1 Algorithm Failures

#### 5.1.1 Hash Computation Failure
```python
class AlgorithmErrorHandler:
    """Handle algorithm-related errors."""
    
    def handle_hash_failure(self, image: Image, algorithm: str):
        """
        Scenario: Hash algorithm fails on specific image
        
        Edge Cases:
        - Grayscale when expecting RGB
        - Unusual bit depth
        - Alpha channel issues
        - Extreme aspect ratios
        
        Recovery:
        1. Convert image format
        2. Use fallback algorithm
        3. Compute partial hash
        4. Skip with warning
        """
        
        # Try format conversion
        conversions = [
            ('RGB', self.convert_to_rgb),
            ('L', self.convert_to_grayscale),
            ('RGBA', self.remove_alpha_channel)
        ]
        
        for target_mode, converter in conversions:
            try:
                converted = converter(image)
                return self.compute_hash(converted, algorithm)
            except:
                continue
                
        # Use simpler algorithm
        return self.compute_basic_hash(image)
```

#### 5.1.2 Comparison Overflow
```python
def handle_comparison_overflow(self, num_images: int):
    """
    Scenario: Too many comparisons (n²/2 complexity)
    
    Edge Cases:
    - 100,000+ images
    - All images very similar
    - Degenerate clustering
    
    Recovery:
    1. Use hierarchical clustering
    2. Implement early termination
    3. Use approximate algorithms
    4. Process in chunks
    """
    
    max_direct_comparisons = 1_000_000
    total_comparisons = (num_images * (num_images - 1)) // 2
    
    if total_comparisons > max_direct_comparisons:
        # Switch to approximate method
        return self.use_lsh_algorithm()  # Locality Sensitive Hashing
```

## 6. User Interface Errors

### 6.1 Display Issues

#### 6.1.1 High DPI Scaling Problems
```python
class UIErrorHandler:
    """Handle UI-related errors."""
    
    def handle_dpi_scaling_issue(self, detected_dpi: float):
        """
        Scenario: UI elements incorrectly scaled
        
        Edge Cases:
        - Multiple monitors with different DPI
        - Dynamic DPI changes
        - Fractional scaling (125%, 175%)
        - Remote desktop sessions
        
        Recovery:
        1. Auto-detect and adjust
        2. Provide manual override
        3. Use DPI-aware rendering
        4. Fall back to 100% scaling
        """
        
        if detected_dpi > 144:  # High DPI display
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        
        # Handle per-monitor DPI
        if self.has_multiple_monitors():
            self.enable_per_monitor_dpi()
```

#### 6.1.2 Widget Rendering Failures
```python
def handle_widget_render_failure(self, widget: QWidget, error: Exception):
    """
    Scenario: Custom widget fails to render
    
    Recovery:
    1. Fall back to basic widget
    2. Disable hardware acceleration
    3. Use software rendering
    4. Reduce visual effects
    """
    
    try:
        # Try software rendering
        widget.setAttribute(Qt.WA_UseSoftwareOpenGL)
        widget.update()
    except:
        # Replace with simpler widget
        return self.create_fallback_widget()
```

## 7. Configuration Errors

### 7.1 Settings Corruption

#### 7.1.1 Invalid Configuration Values
```python
class ConfigErrorHandler:
    """Handle configuration-related errors."""
    
    def handle_invalid_config(self, config: dict, schema: dict):
        """
        Scenario: Configuration contains invalid values
        
        Edge Cases:
        - Type mismatches
        - Out of range values
        - Missing required keys
        - Circular references
        
        Recovery:
        1. Validate and sanitize
        2. Use defaults for invalid values
        3. Prompt user for critical settings
        4. Restore from backup
        """
        
        validated = {}
        errors = []
        
        for key, schema_def in schema.items():
            value = config.get(key, schema_def.get('default'))
            
            try:
                validated[key] = self.validate_value(value, schema_def)
            except ValidationError as e:
                errors.append((key, e))
                validated[key] = schema_def['default']
        
        if errors:
            self.notify_config_fixes(errors)
            
        return validated
```

### 7.2 Profile Issues

#### 7.2.1 Profile Migration Failure
```python
def handle_profile_migration_failure(self, old_version: str, new_version: str):
    """
    Scenario: Profile incompatible with new version
    
    Recovery:
    1. Create backup of old profile
    2. Attempt partial migration
    3. Create new profile with defaults
    4. Offer manual migration tool
    """
    
    backup_path = self.backup_profile(old_version)
    
    try:
        # Try partial migration
        migrated = self.partial_migrate_profile(backup_path, new_version)
        missing = self.get_missing_settings(migrated)
        
        if missing:
            self.prompt_for_missing_settings(missing)
            
    except:
        # Create fresh profile
        self.create_default_profile()
        self.import_favorites_from_backup(backup_path)
```

## 8. Concurrency Issues

### 8.1 Thread Safety

#### 8.1.1 Race Conditions
```python
class ConcurrencyHandler:
    """Handle concurrency-related issues."""
    
    def handle_race_condition(self, resource: str):
        """
        Scenario: Multiple threads accessing shared resource
        
        Edge Cases:
        - Cache updates during read
        - Simultaneous file modifications
        - GUI updates from worker threads
        
        Recovery:
        1. Implement proper locking
        2. Use thread-safe data structures
        3. Queue operations
        4. Retry with backoff
        """
        
        with self.get_lock(resource):
            # Ensure exclusive access
            return self.perform_operation(resource)
```

#### 8.1.2 Deadlock Detection
```python
def handle_deadlock(self, timeout: float = 30.0):
    """
    Scenario: Circular wait causing deadlock
    
    Recovery:
    1. Implement timeout on all locks
    2. Detect and break circular dependencies
    3. Use lock ordering
    4. Restart affected operations
    """
    
    if self.detect_circular_wait():
        # Break deadlock
        self.release_lowest_priority_lock()
        self.restart_operation()
```

## 9. Edge Case Scenarios

### 9.1 Extreme Data Sizes

#### 9.1.1 Single Folder with 1M+ Files
```python
def handle_extreme_file_count(self, folder: Path, count: int):
    """
    Scenario: Folder contains millions of files
    
    Recovery:
    1. Use generator-based iteration
    2. Process in batches
    3. Implement pagination
    4. Use database for file list
    """
    
    if count > 100_000:
        # Stream process
        return self.process_files_streaming(folder)
```

#### 9.1.2 Deeply Nested Folders
```python
def handle_deep_nesting(self, path: Path, depth: int):
    """
    Scenario: Folder structure nested 100+ levels
    
    Recovery:
    1. Limit recursion depth
    2. Use iterative traversal
    3. Implement path length checks
    4. Flatten structure in cache
    """
    
    if depth > 50:
        self.use_iterative_traversal()
        self.warn_user_about_depth(depth)
```

### 9.2 Unusual File Systems

#### 9.2.1 Case-Sensitive File Systems
```python
def handle_case_sensitivity(self, path: Path):
    """
    Scenario: Mixed case-sensitive/insensitive systems
    
    Recovery:
    1. Normalize all paths
    2. Use case-insensitive comparison
    3. Detect file system type
    4. Maintain case mapping
    """
    
    fs_type = self.detect_filesystem_type(path)
    
    if fs_type.case_sensitive:
        self.enable_case_sensitive_mode()
```

### 9.3 System Resource Limits

#### 9.3.1 File Handle Exhaustion
```python
def handle_file_handle_limit(self):
    """
    Scenario: Too many open files
    
    Recovery:
    1. Implement file handle pooling
    2. Close unused handles
    3. Increase system limits
    4. Process in smaller batches
    """
    
    # Monitor open handles
    if self.get_open_handle_count() > self.max_handles * 0.8:
        self.close_idle_handles()
        self.reduce_concurrent_operations()
```

## 10. Recovery Strategies Summary

### 10.1 General Recovery Principles
1. **Fail Gracefully**: Never crash, always provide feedback
2. **Preserve Data**: Never lose user data or work
3. **Continue Operation**: Skip problems when possible
4. **Inform User**: Clear, actionable error messages
5. **Log Everything**: Detailed logs for debugging
6. **Learn from Errors**: Adapt behavior based on errors

### 10.2 Error Priority Levels
```python
class ErrorPriority(Enum):
    CRITICAL = 1    # Stop operation, require user action
    HIGH = 2        # Warn user, attempt recovery
    MEDIUM = 3      # Log warning, auto-recover
    LOW = 4         # Log info, continue silently
```

### 10.3 User Communication Strategy
```python
def communicate_error(self, error: Exception, priority: ErrorPriority):
    """
    Standardized error communication.
    
    - CRITICAL: Modal dialog with options
    - HIGH: Toast notification with action
    - MEDIUM: Status bar warning
    - LOW: Log entry only
    """
    
    if priority == ErrorPriority.CRITICAL:
        self.show_error_dialog(error)
    elif priority == ErrorPriority.HIGH:
        self.show_warning_notification(error)
    elif priority == ErrorPriority.MEDIUM:
        self.update_status_bar(error)
    else:
        self.log_error(error)
```

## 11. Testing Error Scenarios

### 11.1 Error Injection Testing
```python
class ErrorInjector:
    """Inject errors for testing recovery."""
    
    def inject_random_errors(self, probability: float = 0.1):
        """Randomly inject errors during testing."""
        
        if random.random() < probability:
            error_type = random.choice([
                PermissionError,
                FileNotFoundError,
                MemoryError,
                sqlite3.OperationalError
            ])
            raise error_type("Injected for testing")
```

### 11.2 Stress Testing Scenarios
1. Process 1M+ images
2. Fill disk during operation
3. Disconnect network drives
4. Corrupt cache database
5. Mix file formats randomly
6. Exceed memory limits
7. Create circular symlinks
8. Use Unicode filenames
9. Simulate slow network
10. Kill processes randomly

## 12. Implementation Guidelines

### 12.1 Error Handler Registration
```python
class ErrorHandlerRegistry:
    """Central registry for error handlers."""
    
    handlers = {
        PermissionError: PermissionErrorHandler,
        MemoryError: MemoryErrorHandler,
        sqlite3.DatabaseError: DatabaseErrorHandler,
        OSError: FileSystemErrorHandler,
    }
    
    def handle(self, error: Exception) -> RecoveryAction:
        """Route error to appropriate handler."""
        
        handler_class = self.handlers.get(type(error), DefaultErrorHandler)
        handler = handler_class()
        return handler.handle(error)
```

### 12.2 Monitoring and Metrics
```python
class ErrorMetrics:
    """Track error patterns for improvement."""
    
    def record_error(self, error: Exception, recovery: RecoveryAction):
        """Record error occurrence and recovery success."""
        
        self.error_counts[type(error)] += 1
        self.recovery_success[recovery] += 1
        
        # Identify patterns
        if self.error_counts[type(error)] > 10:
            self.suggest_preventive_action(error)
```

This comprehensive error handling ensures robust operation even under adverse conditions, maintaining data integrity and providing clear user feedback throughout.