"""
Core Logger Implementation

Advanced logger with multiple outputs, variable watching, performance tracking,
and rich context management for debugging and monitoring.
"""

from typing import Any, Dict, List, Optional, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import inspect
import time
import threading
from pathlib import Path
from contextlib import contextmanager


class LogLevel(Enum):
    """Log levels for different types of messages."""
    TRACE = 5      # Finest details - function entry/exit
    DEBUG = 10     # Debug information
    INFO = 20      # General information
    WATCH = 25     # Variable watching/monitoring
    SUCCESS = 30   # Success messages
    WARNING = 40   # Warning messages
    ERROR = 50     # Error messages
    CRITICAL = 60  # Critical errors

    def __lt__(self, other):
        return self.value < other.value

    def __le__(self, other):
        return self.value <= other.value

    def __gt__(self, other):
        return self.value > other.value

    def __ge__(self, other):
        return self.value >= other.value


@dataclass
class LogEntry:
    """
    Structured log entry with rich metadata.
    
    This contains all the information about a single log event,
    including context, variables, and source information.
    """
    level: LogLevel
    message: str
    timestamp: float = field(default_factory=time.time)
    source: str = ""  # Module/function name
    line_number: int = 0
    variables: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    exception: Optional[Exception] = None
    thread_id: Optional[str] = None
    
    def __post_init__(self):
        """Auto-fill some fields if not provided."""
        if self.thread_id is None:
            self.thread_id = threading.current_thread().name
        
        if not self.source:
            # Try to get caller information
            frame = inspect.currentframe()
            try:
                # Go up the stack to find the actual caller
                caller_frame = frame.f_back.f_back.f_back  # Skip dataclass, logger internals
                if caller_frame:
                    self.source = f"{caller_frame.f_globals.get('__name__', 'unknown')}.{caller_frame.f_code.co_name}"
                    self.line_number = caller_frame.f_lineno
            finally:
                del frame  # Prevent reference cycles


class LogOutput:
    """Base class for log output handlers."""
    
    def write(self, entry: LogEntry) -> None:
        """Write a log entry to the output destination."""
        raise NotImplementedError
    
    def should_write(self, entry: LogEntry) -> bool:
        """Determine if this output should handle the given entry."""
        return True
    
    def close(self) -> None:
        """Close the output handler and clean up resources."""
        pass


class PKLogger:
    """
    Advanced logger with multiple outputs and rich features.
    
    Features:
    - Multiple output destinations (console, file, GUI, DB)
    - Variable watching for debugging
    - Performance timing
    - Context management
    - Rich formatting
    - Thread-safe operation
    
    Example:
        >>> log = get_logger(__name__)
        >>> 
        >>> # Simple logging
        >>> log.info("Processing started")
        >>> 
        >>> # Variable watching
        >>> log.watch(image_count=150, processing_time=2.5)
        >>> 
        >>> # Context logging
        >>> with log.context(operation="duplicate_detection"):
        ...     log.debug("Analyzing images")
        ...     log.watch(similarity_threshold=0.95)
        >>> 
        >>> # Performance tracking
        >>> with log.timer("image_processing"):
        ...     process_images()
    """
    
    def __init__(self, name: str):
        """
        Initialize logger.
        
        Args:
            name: Logger name (typically module name)
        """
        self.name = name
        self.outputs: List[LogOutput] = []
        self.level = LogLevel.DEBUG
        self.context_stack: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
    
    def add_output(self, output: LogOutput) -> None:
        """
        Add a new output destination.
        
        Args:
            output: Output handler to add
        """
        with self._lock:
            self.outputs.append(output)
    
    def remove_output(self, output: LogOutput) -> None:
        """
        Remove an output destination.
        
        Args:
            output: Output handler to remove
        """
        with self._lock:
            if output in self.outputs:
                self.outputs.remove(output)
                output.close()
    
    def set_level(self, level: LogLevel) -> None:
        """
        Set minimum log level.
        
        Args:
            level: Minimum level to log
        """
        self.level = level
    
    def _should_log(self, level: LogLevel) -> bool:
        """Check if message should be logged based on level."""
        return level >= self.level
    
    def _get_current_context(self) -> Dict[str, Any]:
        """Get merged context from context stack."""
        context = {}
        for ctx in self.context_stack:
            context.update(ctx)
        return context
    
    def _log(self, level: LogLevel, message: str, **kwargs) -> None:
        """
        Internal logging method.
        
        Args:
            level: Log level
            message: Log message
            **kwargs: Additional fields for LogEntry
        """
        if not self._should_log(level):
            return
        
        # Create log entry
        entry = LogEntry(
            level=level,
            message=message,
            context=self._get_current_context(),
            **kwargs
        )
        
        # Send to all outputs
        with self._lock:
            for output in self.outputs:
                try:
                    if output.should_write(entry):
                        output.write(entry)
                except Exception as e:
                    # Avoid infinite recursion if logging itself fails
                    print(f"Error in log output {output}: {e}")
    
    def trace(self, message: str, **kwargs) -> None:
        """Log trace message."""
        self._log(LogLevel.TRACE, message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._log(LogLevel.INFO, message, **kwargs)
    
    def success(self, message: str, **kwargs) -> None:
        """Log success message."""
        self._log(LogLevel.SUCCESS, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **kwargs)
    
    def error(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """Log error message."""
        self._log(LogLevel.ERROR, message, exception=exception, **kwargs)
    
    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, exception=exception, **kwargs)
    
    def watch(self, **variables) -> None:
        """
        Log variable values for debugging.
        
        Args:
            **variables: Variables to watch as key=value pairs
            
        Example:
            >>> log.watch(
            ...     image_path="/photos/img.jpg",
            ...     dimensions=(1920, 1080),
            ...     file_size=2048576
            ... )
        """
        if not variables:
            return
            
        # Format variables nicely
        var_strings = []
        for name, value in variables.items():
            var_strings.append(f"{name}={repr(value)}")
        
        message = f"Variables: {', '.join(var_strings)}"
        self._log(LogLevel.WATCH, message, variables=variables)
    
    @contextmanager
    def context(self, **context_vars):
        """
        Add context that will be included in all logs within the block.
        
        Args:
            **context_vars: Context variables to add
            
        Example:
            >>> with log.context(operation="duplicate_detection", user_id=123):
            ...     log.info("Starting operation")  # Will include context
        """
        self.context_stack.append(context_vars)
        try:
            yield
        finally:
            self.context_stack.pop()
    
    @contextmanager
    def timer(self, operation_name: str, log_level: LogLevel = LogLevel.INFO):
        """
        Context manager for timing operations.
        
        Args:
            operation_name: Name of the operation being timed
            log_level: Level to log timing results at
            
        Example:
            >>> with log.timer("image_processing"):
            ...     process_images()  # Will log execution time
        """
        start_time = time.time()
        self._log(log_level, f"Started: {operation_name}")
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            self._log(log_level, f"Completed: {operation_name} ({elapsed:.3f}s)")
    
    def function_trace(self, func: Callable) -> Callable:
        """
        Decorator to trace function calls.
        
        Args:
            func: Function to trace
            
        Returns:
            Wrapped function that logs entry/exit
            
        Example:
            >>> @log.function_trace
            >>> def process_image(path: Path) -> Image:
            ...     return Image.open(path)
        """
        def wrapper(*args, **kwargs):
            func_name = f"{func.__module__}.{func.__name__}"
            
            # Log function entry
            arg_strs = [repr(arg) for arg in args[:3]]  # Limit args shown
            if len(args) > 3:
                arg_strs.append("...")
            if kwargs:
                kwarg_strs = [f"{k}={repr(v)}" for k, v in list(kwargs.items())[:2]]
                if len(kwargs) > 2:
                    kwarg_strs.append("...")
                arg_strs.extend(kwarg_strs)
            
            args_str = ", ".join(arg_strs) if arg_strs else ""
            self.trace(f"→ {func_name}({args_str})")
            
            try:
                with self.timer(func_name, LogLevel.TRACE):
                    result = func(*args, **kwargs)
                
                # Log successful exit
                self.trace(f"← {func_name} -> {type(result).__name__}")
                return result
                
            except Exception as e:
                # Log exception exit
                self.error(f"✗ {func_name} failed", exception=e)
                raise
        
        return wrapper


# Global logger registry
_loggers: Dict[str, PKLogger] = {}
_global_outputs: List[LogOutput] = []
_default_level = LogLevel.INFO


def get_logger(name: str) -> PKLogger:
    """
    Get or create a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
        
    Example:
        >>> log = get_logger(__name__)
        >>> log.info("Hello world")
    """
    if name not in _loggers:
        logger = PKLogger(name)
        logger.set_level(_default_level)
        
        # Add any global outputs that were configured before this logger was created
        for output in _global_outputs:
            logger.add_output(output)
        
        _loggers[name] = logger
    
    return _loggers[name]


def configure_logging(
    console: bool = True,
    file_path: Optional[Path] = None,
    gui_panel: Optional[Any] = None,  # Avoid circular import
    level: LogLevel = LogLevel.INFO,
    rich_console: bool = True
) -> None:
    """
    Global logging configuration.
    
    Args:
        console: Enable console output
        file_path: Path for file output (None to disable)
        gui_panel: GUI panel for log display (None to disable)
        level: Default log level
        rich_console: Use rich formatting for console
        
    Example:
        >>> configure_logging(
        ...     console=True,
        ...     file_path=Path("logs/app.log"),
        ...     level=LogLevel.DEBUG
        ... )
    """
    global _default_level, _global_outputs
    
    _default_level = level
    
    # Clear existing global outputs
    for output in _global_outputs:
        output.close()
    _global_outputs.clear()
    
    # Add console output
    if console:
        if rich_console:
            try:
                from .outputs.console import RichConsoleOutput
                _global_outputs.append(RichConsoleOutput())
            except ImportError:
                from .outputs.console import SimpleConsoleOutput
                _global_outputs.append(SimpleConsoleOutput())
        else:
            from .outputs.console import SimpleConsoleOutput
            _global_outputs.append(SimpleConsoleOutput())
    
    # Add file output
    if file_path:
        from .outputs.file import FileOutput
        _global_outputs.append(FileOutput(file_path))
    
    # Add GUI output
    if gui_panel:
        from .outputs.gui import GuiLogOutput
        gui_output = GuiLogOutput()
        gui_output.register_panel(gui_panel)
        _global_outputs.append(gui_output)
    
    # Apply to all existing loggers
    for logger in _loggers.values():
        logger.set_level(level)
        for output in _global_outputs:
            logger.add_output(output)