"""
Core File Watcher Implementation

Cross-platform file system watcher with advanced filtering and event handling.
Uses watchdog library for cross-platform support.
"""

from pathlib import Path
from typing import List, Callable, Optional, Set, Dict, Any
from dataclasses import dataclass
from enum import Enum
import threading
import time
import fnmatch
from collections import defaultdict, deque

from ...logging import get_logger

log = get_logger(__name__)


class EventType(Enum):
    """File system event types."""
    CREATED = "created"
    MODIFIED = "modified" 
    DELETED = "deleted"
    MOVED = "moved"
    BATCH_START = "batch_start"  # For bulk operations
    BATCH_END = "batch_end"


@dataclass
class FileEvent:
    """
    Represents a file system event.
    
    Contains all relevant information about a file system change
    including metadata and context.
    """
    event_type: EventType
    path: Path
    old_path: Optional[Path] = None  # For move events
    is_directory: bool = False
    size: Optional[int] = None
    timestamp: float = None
    
    def __post_init__(self):
        """Auto-fill timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()


class FileWatcher:
    """
    Cross-platform file system watcher with advanced filtering.
    
    Uses watchdog library for cross-platform support and provides
    intelligent event handling with debouncing and pattern matching.
    
    Example:
        >>> watcher = FileWatcher()
        >>> watch_id = watcher.watch(
        ...     Path("/photos"),
        ...     patterns=["*.jpg", "*.png"],
        ...     ignore_patterns=["*thumbnail*"]
        ... )
        >>> 
        >>> @watcher.on_event([EventType.CREATED])
        >>> def handle_new_file(event):
        ...     print(f"New file: {event.path}")
    """
    
    def __init__(self, 
                 debounce_seconds: float = 0.5,
                 batch_threshold: int = 10):
        """
        Initialize file watcher.
        
        Args:
            debounce_seconds: Delay before processing rapid changes
            batch_threshold: Number of events to trigger batch mode
        """
        self.watchers: Dict[str, Any] = {}
        self.handlers: List[Dict[str, Any]] = []
        self.filters: List[Any] = []
        self.debounce_seconds = debounce_seconds
        self.batch_threshold = batch_threshold
        
        # Event aggregation for debouncing
        self.pending_events: Dict[str, FileEvent] = {}
        self.event_timer: Optional[threading.Timer] = None
        self.lock = threading.RLock()
        
        # Check if watchdog is available
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            self.watchdog_available = True
            self.Observer = Observer
            self.FileSystemEventHandler = FileSystemEventHandler
            log.debug("Watchdog library available for file monitoring")
        except ImportError:
            self.watchdog_available = False
            log.warning("Watchdog library not available - file monitoring disabled")
    
    def watch(self,
              path: Path,
              recursive: bool = True,
              patterns: Optional[List[str]] = None,  # ["*.jpg", "*.png"]
              ignore_patterns: Optional[List[str]] = None,  # ["*.tmp", ".*"]
              ignore_directories: bool = False) -> str:
        """
        Start watching a directory.
        
        Args:
            path: Path to watch
            recursive: Whether to watch subdirectories
            patterns: Include patterns (glob-style)
            ignore_patterns: Exclude patterns (glob-style)
            ignore_directories: Whether to ignore directory events
            
        Returns:
            Watch ID for later removal
            
        Raises:
            RuntimeError: If watchdog is not available
            FileNotFoundError: If path doesn't exist
        """
        if not self.watchdog_available:
            raise RuntimeError("File watching requires watchdog library: pip install watchdog")
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Watch path does not exist: {path}")
        
        if not path.is_dir():
            raise ValueError(f"Watch path must be a directory: {path}")
        
        # Create unique watch ID
        watch_id = f"watch_{id(path)}_{time.time()}"
        
        # Create event handler
        handler = self._create_event_handler(
            patterns=patterns,
            ignore_patterns=ignore_patterns,
            ignore_directories=ignore_directories
        )
        
        # Start observer
        observer = self.Observer()
        observer.schedule(handler, str(path), recursive=recursive)
        observer.start()
        
        # Store watcher info
        with self.lock:
            self.watchers[watch_id] = {
                'observer': observer,
                'handler': handler,
                'path': path,
                'patterns': patterns,
                'ignore_patterns': ignore_patterns,
                'recursive': recursive
            }
        
        log.info(f"Started watching {path} (ID: {watch_id})")
        return watch_id
    
    def unwatch(self, watch_id: str) -> bool:
        """
        Stop watching a directory.
        
        Args:
            watch_id: Watch ID returned by watch()
            
        Returns:
            True if successfully removed, False if not found
        """
        with self.lock:
            if watch_id not in self.watchers:
                return False
            
            watcher_info = self.watchers[watch_id]
            observer = watcher_info['observer']
            
            try:
                observer.stop()
                observer.join(timeout=1.0)  # Wait up to 1 second
                log.info(f"Stopped watching {watcher_info['path']} (ID: {watch_id})")
            except Exception as e:
                log.error(f"Error stopping watcher {watch_id}: {e}")
            
            del self.watchers[watch_id]
            return True
    
    def stop_all(self) -> None:
        """Stop all watchers."""
        with self.lock:
            watch_ids = list(self.watchers.keys())
            for watch_id in watch_ids:
                self.unwatch(watch_id)
    
    def _create_event_handler(self, patterns=None, ignore_patterns=None, ignore_directories=False):
        """Create watchdog event handler."""
        
        class PKEventHandler(self.FileSystemEventHandler):
            def __init__(handler_self):
                super().__init__()
                self.outer = self  # Reference to FileWatcher instance
            
            def on_created(handler_self, event):
                if ignore_directories and event.is_directory:
                    return
                self._handle_watchdog_event(EventType.CREATED, event, patterns, ignore_patterns)
            
            def on_modified(handler_self, event):
                if ignore_directories and event.is_directory:
                    return
                self._handle_watchdog_event(EventType.MODIFIED, event, patterns, ignore_patterns)
            
            def on_deleted(handler_self, event):
                if ignore_directories and event.is_directory:
                    return
                self._handle_watchdog_event(EventType.DELETED, event, patterns, ignore_patterns)
            
            def on_moved(handler_self, event):
                if ignore_directories and event.is_directory:
                    return
                self._handle_watchdog_event(EventType.MOVED, event, patterns, ignore_patterns)
        
        return PKEventHandler()
    
    def _handle_watchdog_event(self, event_type: EventType, watchdog_event, patterns, ignore_patterns):
        """Convert watchdog event to our event format and process."""
        path = Path(watchdog_event.src_path)
        
        # Apply pattern filtering
        if not self._matches_patterns(path, patterns, ignore_patterns):
            return
        
        # Create our event
        event = FileEvent(
            event_type=event_type,
            path=path,
            old_path=Path(watchdog_event.dest_path) if hasattr(watchdog_event, 'dest_path') else None,
            is_directory=watchdog_event.is_directory
        )
        
        # Try to get file size
        try:
            if not event.is_directory and path.exists():
                event.size = path.stat().st_size
        except OSError:
            pass
        
        # Process the event
        self._process_event(event)
    
    def _matches_patterns(self, path: Path, patterns: Optional[List[str]], ignore_patterns: Optional[List[str]]) -> bool:
        """Check if path matches include/exclude patterns."""
        filename = path.name
        
        # Check ignore patterns first
        if ignore_patterns:
            for pattern in ignore_patterns:
                if fnmatch.fnmatch(filename, pattern):
                    return False
        
        # Check include patterns
        if patterns:
            for pattern in patterns:
                if fnmatch.fnmatch(filename, pattern):
                    return True
            return False  # Didn't match any include pattern
        
        return True  # No patterns specified, include everything
    
    def _process_event(self, event: FileEvent) -> None:
        """Process a file event with debouncing."""
        event_key = f"{event.event_type.value}:{event.path}"
        
        with self.lock:
            # Store/update pending event
            self.pending_events[event_key] = event
            
            # Reset debounce timer
            if self.event_timer:
                self.event_timer.cancel()
            
            self.event_timer = threading.Timer(
                self.debounce_seconds,
                self._flush_pending_events
            )
            self.event_timer.start()
    
    def _flush_pending_events(self) -> None:
        """Flush all pending events to handlers."""
        with self.lock:
            if not self.pending_events:
                return
            
            events = list(self.pending_events.values())
            self.pending_events.clear()
            
            # Check if this looks like a batch operation
            if len(events) >= self.batch_threshold:
                self._emit_event(FileEvent(EventType.BATCH_START, Path(".")))
            
            # Emit all events
            for event in events:
                self._emit_event(event)
            
            # End batch if it was a batch
            if len(events) >= self.batch_threshold:
                self._emit_event(FileEvent(EventType.BATCH_END, Path(".")))
            
            log.debug(f"Flushed {len(events)} pending events")
    
    def _emit_event(self, event: FileEvent) -> None:
        """Emit event to all registered handlers."""
        for handler_info in self.handlers:
            try:
                # Check if handler wants this event type
                if handler_info['event_types'] is None or event.event_type in handler_info['event_types']:
                    handler_info['handler'](event)
            except Exception as e:
                log.error(f"Error in event handler: {e}", exception=e)
    
    def on_event(self, 
                 event_types: Optional[List[EventType]] = None,
                 handler: Optional[Callable[[FileEvent], None]] = None):
        """
        Register an event handler.
        
        Args:
            event_types: List of event types to handle (None for all)
            handler: Handler function
            
        Can be used as decorator:
            >>> @watcher.on_event([EventType.CREATED])
            >>> def handle_creation(event):
            ...     print(f"Created: {event.path}")
        """
        def decorator(func):
            self.handlers.append({
                'event_types': event_types,
                'handler': func
            })
            return func
        
        if handler:
            return decorator(handler)
        else:
            return decorator
    
    def on_image_added(self, handler: Callable[[Path], None]):
        """
        Convenience method for image addition events.
        
        Args:
            handler: Function that takes a Path argument
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
        
        @self.on_event([EventType.CREATED])
        def image_handler(event: FileEvent):
            if not event.is_directory and event.path.suffix.lower() in image_extensions:
                handler(event.path)
        
        return image_handler
    
    def on_batch_operation(self,
                          start_handler: Callable[[], None],
                          end_handler: Callable[[List[FileEvent]], None]):
        """
        Handle batch operations like bulk file copies.
        
        Args:
            start_handler: Called when batch starts
            end_handler: Called when batch ends with list of events
        """
        batch_events = []
        
        @self.on_event([EventType.BATCH_START])
        def batch_start(event: FileEvent):
            batch_events.clear()
            start_handler()
        
        @self.on_event([EventType.BATCH_END]) 
        def batch_end(event: FileEvent):
            end_handler(batch_events.copy())
            batch_events.clear()
        
        @self.on_event([EventType.CREATED, EventType.MODIFIED, EventType.DELETED, EventType.MOVED])
        def collect_events(event: FileEvent):
            batch_events.append(event)
    
    def get_watch_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all active watches.
        
        Returns:
            Dictionary mapping watch IDs to watch information
        """
        with self.lock:
            info = {}
            for watch_id, watcher_info in self.watchers.items():
                info[watch_id] = {
                    'path': str(watcher_info['path']),
                    'recursive': watcher_info['recursive'],
                    'patterns': watcher_info['patterns'],
                    'ignore_patterns': watcher_info['ignore_patterns'],
                    'active': watcher_info['observer'].is_alive()
                }
            return info
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - stop all watchers."""
        self.stop_all()