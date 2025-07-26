"""
Event Filters

Filters for file system events to reduce noise and focus on relevant changes.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from collections import defaultdict, deque
import time

from .watcher import FileEvent


class EventFilter(ABC):
    """Base class for event filters."""
    
    @abstractmethod
    def should_process(self, event: FileEvent) -> bool:
        """Return True if event should be processed."""
        pass


class SizeFilter(EventFilter):
    """Filter events by file size."""
    
    def __init__(self, min_size: int = 0, max_size: Optional[int] = None):
        """
        Initialize size filter.
        
        Args:
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes (None for unlimited)
        """
        self.min_size = min_size
        self.max_size = max_size
        
    def should_process(self, event: FileEvent) -> bool:
        """Check if event passes size filter."""
        if event.size is None:
            return True  # Can't filter without size info
            
        if event.size < self.min_size:
            return False
            
        if self.max_size is not None and event.size > self.max_size:
            return False
            
        return True


class RateLimitFilter(EventFilter):
    """Limit events per path to prevent flooding."""
    
    def __init__(self, max_events_per_second: float = 10):
        """
        Initialize rate limit filter.
        
        Args:
            max_events_per_second: Maximum events per second per path
        """
        self.max_events_per_second = max_events_per_second
        self.event_times = defaultdict(deque)
        
    def should_process(self, event: FileEvent) -> bool:
        """Check if event passes rate limit."""
        now = time.time()
        path_key = str(event.path)
        
        # Clean old events (older than 1 second)
        times = self.event_times[path_key]
        while times and times[0] < now - 1.0:
            times.popleft()
        
        # Check rate limit
        if len(times) >= self.max_events_per_second:
            return False
        
        # Add current event time
        times.append(now)
        return True


class CompositeFilter(EventFilter):
    """Combine multiple filters with AND/OR logic."""
    
    def __init__(self, filters: List[EventFilter], mode: str = "AND"):
        """
        Initialize composite filter.
        
        Args:
            filters: List of filters to combine
            mode: "AND" (all must pass) or "OR" (any must pass)
        """
        self.filters = filters
        self.mode = mode.upper()
        
        if self.mode not in ("AND", "OR"):
            raise ValueError("Mode must be 'AND' or 'OR'")
    
    def should_process(self, event: FileEvent) -> bool:
        """Apply composite filter logic."""
        if not self.filters:
            return True
        
        if self.mode == "AND":
            return all(f.should_process(event) for f in self.filters)
        else:  # OR
            return any(f.should_process(event) for f in self.filters)