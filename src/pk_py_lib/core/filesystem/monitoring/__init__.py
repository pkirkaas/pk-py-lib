"""
File System Monitoring Module

Real-time file system monitoring with intelligent event handling,
debouncing, and cross-platform support.
"""

from .watcher import FileWatcher, EventType, FileEvent
from .events import EventAggregator, SmartEventHandler
from .filters import EventFilter, SizeFilter, RateLimitFilter, CompositeFilter

__all__ = [
    "FileWatcher",
    "EventType",
    "FileEvent", 
    "EventAggregator",
    "SmartEventHandler",
    "EventFilter",
    "SizeFilter",
    "RateLimitFilter",
    "CompositeFilter"
]

# Convenience function for quick file watching
def watch_directory(
    path,
    on_created=None,
    on_modified=None,
    on_deleted=None,
    on_moved=None,
    patterns=None,
    recursive=True
):
    """
    Quick setup for directory watching.
    
    Args:
        path: Directory to watch
        on_created: Callback for file creation
        on_modified: Callback for file modification
        on_deleted: Callback for file deletion
        on_moved: Callback for file moves
        patterns: File patterns to watch (e.g., ["*.jpg", "*.png"])
        recursive: Whether to watch subdirectories
        
    Returns:
        FileWatcher instance
        
    Example:
        >>> def on_new_image(event):
        ...     print(f"New image: {event.path}")
        >>> 
        >>> watcher = watch_directory(
        ...     "/photos",
        ...     on_created=on_new_image,
        ...     patterns=["*.jpg", "*.png"]
        ... )
    """
    watcher = FileWatcher()
    
    watch_id = watcher.watch(
        path,
        recursive=recursive,
        patterns=patterns
    )
    
    # Register callbacks
    if on_created:
        watcher.on_event([EventType.CREATED], on_created)
    if on_modified:
        watcher.on_event([EventType.MODIFIED], on_modified)
    if on_deleted:
        watcher.on_event([EventType.DELETED], on_deleted)
    if on_moved:
        watcher.on_event([EventType.MOVED], on_moved)
    
    return watcher