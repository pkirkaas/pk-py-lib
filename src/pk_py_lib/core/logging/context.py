"""
Logging Context Managers

Context managers for structured logging, timing, and contextual information.
"""

import time
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional, Generator
from .logger import get_logger, PKLogger

# Get module logger
logger = get_logger(__name__)


class LogTimer:
    """
    Context manager for timing operations and logging the results.
    
    Example:
        with LogTimer("Processing data"):
            # Some operation
            process_data()
            
        # Logs: "Processing data took 0.1234s"
    """
    
    def __init__(self, operation: str, level: str = "INFO", logger: Optional[PKLogger] = None):
        """
        Initialize the LogTimer.
        
        Args:
            operation: Description of the operation being timed
            level: Log level for the timing message
            logger: Optional specific logger to use (defaults to module logger)
        """
        self.operation = operation
        self.level = level
        self.logger = logger or get_logger(__name__)
        self.start_time = 0.0
        
    def __enter__(self) -> "LogTimer":
        """Start timing the operation."""
        self.start_time = time.perf_counter()
        self.logger.debug(f"Starting {self.operation}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Log the execution time when exiting the context."""
        end_time = time.perf_counter()
        duration = end_time - self.start_time
        
        if exc_type is None:
            # Normal exit
            self.logger.log(self.level, f"{self.operation} took {duration:.4f}s")
        else:
            # Exception occurred
            self.logger.error(f"{self.operation} failed after {duration:.4f}s with {exc_type.__name__}: {exc_val}")


class LogContext:
    """
    Context manager for adding contextual information to log messages.
    
    Example:
        with LogContext(user="john_doe", session="abc123"):
            # All log messages in this context will include the user and session info
            logger.info("User performed action")
            
        # Logs: "[user=john_doe, session=abc123] User performed action"
    """
    
    # Thread-local storage for context stack
    _local = threading.local()
    
    def __init__(self, **context: Any):
        """
        Initialize the LogContext with contextual information.
        
        Args:
            **context: Key-value pairs to include in log messages
        """
        self.context = context
        
    def __enter__(self) -> "LogContext":
        """Add this context to the context stack."""
        # Initialize context stack if needed
        if not hasattr(self._local, 'context_stack'):
            self._local.context_stack = []
            
        # Push this context onto the stack
        self._local.context_stack.append(self.context)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Remove this context from the context stack."""
        # Pop this context from the stack
        if hasattr(self._local, 'context_stack') and self._local.context_stack:
            self._local.context_stack.pop()
            
    @classmethod
    def get_current_context(cls) -> Dict[str, Any]:
        """
        Get the current merged context from all active contexts.
        
        Returns:
            Dictionary of merged context information
        """
        if not hasattr(cls._local, 'context_stack'):
            return {}
            
        # Merge all contexts in the stack
        merged_context = {}
        for context in cls._local.context_stack:
            merged_context.update(context)
        return merged_context


@contextmanager
def log_context(**context: Any) -> Generator[None, None, None]:
    """
    Context manager function for adding contextual information to log messages.
    
    This is a convenience function that creates a LogContext.
    
    Args:
        **context: Key-value pairs to include in log messages
        
    Example:
        with log_context(user="jane", request_id="req-789"):
            logger.info("Processing request")
    """
    with LogContext(**context):
        yield