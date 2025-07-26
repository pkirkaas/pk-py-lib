"""
Event Aggregation and Smart Handling

Advanced event processing with pattern recognition and intelligent aggregation.
"""

from typing import Dict, List, Any, Callable
from collections import defaultdict
import time

from .watcher import FileEvent, EventType


class EventAggregator:
    """
    Aggregates rapid file events for efficient processing.
    
    Useful for scenarios like:
    - Bulk file copies
    - Image saves from editing software  
    - Directory synchronization
    """
    
    def __init__(self, window_seconds: float = 1.0):
        """
        Initialize event aggregator.
        
        Args:
            window_seconds: Time window for aggregating events
        """
        self.window_seconds = window_seconds
        self.events: Dict[str, List[FileEvent]] = defaultdict(list)
        self.last_event_time = 0
        
    def add_event(self, event: FileEvent) -> List[FileEvent]:
        """
        Add event and return aggregated events if window expired.
        
        Args:
            event: File event to add
            
        Returns:
            List of aggregated events if window expired, empty list otherwise
        """
        now = time.time()
        path_key = str(event.path)
        
        # Add event to aggregation
        self.events[path_key].append(event)
        self.last_event_time = now
        
        # Check if window has expired
        if now - self.last_event_time >= self.window_seconds:
            # Return all aggregated events and clear
            all_events = []
            for events_list in self.events.values():
                all_events.extend(events_list)
            
            self.events.clear()
            return all_events
        
        return []
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of pending events.
        
        Returns:
            Dictionary with counts by event type, affected directories, etc.
        """
        summary = {
            "total_events": 0,
            "by_type": defaultdict(int),
            "affected_paths": set(),
            "affected_directories": set()
        }
        
        for events_list in self.events.values():
            for event in events_list:
                summary["total_events"] += 1
                summary["by_type"][event.event_type.value] += 1
                summary["affected_paths"].add(str(event.path))
                summary["affected_directories"].add(str(event.path.parent))
        
        # Convert sets to lists for JSON serialization
        summary["affected_paths"] = list(summary["affected_paths"])
        summary["affected_directories"] = list(summary["affected_directories"])
        summary["by_type"] = dict(summary["by_type"])
        
        return summary


class SmartEventHandler:
    """
    Intelligent event handling with pattern recognition.
    
    Detects patterns like:
    - Image sequence saves (e.g., burst mode photos)
    - Software-specific save patterns (Photoshop, Lightroom)
    - Sync operations
    """
    
    def __init__(self):
        """Initialize smart event handler."""
        self.patterns = []
        
    def register_pattern(self,
                        name: str,
                        detector: Callable[[List[FileEvent]], bool],
                        handler: Callable[[List[FileEvent]], None]):
        """
        Register a custom event pattern detector and handler.
        
        Args:
            name: Pattern name for identification
            detector: Function that returns True if pattern is detected
            handler: Function to handle the detected pattern
        """
        self.patterns.append({
            'name': name,
            'detector': detector,
            'handler': handler
        })
    
    def process_events(self, events: List[FileEvent]) -> None:
        """
        Process events and apply pattern detection.
        
        Args:
            events: List of events to process
        """
        # Try each pattern detector
        for pattern in self.patterns:
            try:
                if pattern['detector'](events):
                    pattern['handler'](events)
                    return  # First match wins
            except Exception as e:
                # Log error but continue with other patterns
                print(f"Error in pattern '{pattern['name']}': {e}")
        
        # No pattern matched, handle as individual events
        for event in events:
            self._handle_individual_event(event)
    
    def _handle_individual_event(self, event: FileEvent) -> None:
        """Default handler for individual events."""
        pass  # Override in subclasses


def create_photo_burst_detector() -> Callable[[List[FileEvent]], bool]:
    """Create detector for photo burst sequences."""
    
    def detector(events: List[FileEvent]) -> bool:
        # Look for multiple image files created in quick succession
        image_extensions = {'.jpg', '.jpeg', '.png', '.raw', '.cr2', '.nef'}
        
        image_events = [
            e for e in events 
            if e.event_type == EventType.CREATED 
            and e.path.suffix.lower() in image_extensions
        ]
        
        # Consider it a burst if 3+ images in 2 seconds
        if len(image_events) >= 3:
            time_span = max(e.timestamp for e in image_events) - min(e.timestamp for e in image_events)
            return time_span <= 2.0
        
        return False
    
    return detector


def create_software_save_detector(software_patterns: List[str]) -> Callable[[List[FileEvent]], bool]:
    """
    Create detector for software-specific save patterns.
    
    Args:
        software_patterns: List of filename patterns indicating software saves
    """
    
    def detector(events: List[FileEvent]) -> bool:
        # Look for temporary files followed by final saves
        temp_events = []
        final_events = []
        
        for event in events:
            filename = event.path.name.lower()
            
            # Check for software patterns
            for pattern in software_patterns:
                if pattern in filename:
                    if any(temp_marker in filename for temp_marker in ['~tmp', '.tmp', '~']):
                        temp_events.append(event)
                    else:
                        final_events.append(event)
        
        # Pattern detected if we have both temp and final events
        return len(temp_events) > 0 and len(final_events) > 0
    
    return detector