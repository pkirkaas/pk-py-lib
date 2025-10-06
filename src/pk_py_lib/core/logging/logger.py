"""
Core Logger Implementation

Advanced logger with multiple outputs, variable watching, performance tracking,
and rich context management for debugging and monitoring.
"""

from typing import Any, Dict, List, Optional, Union, Callable
from .. import get_data_dir
from dataclasses import dataclass, field
from enum import Enum
import inspect
import time
import threading
from pathlib import Path
from contextlib import contextmanager
import sys


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

        # Handle known LogEntry fields from kwargs and route extras to variables
        known_fields = {}
        variables = kwargs.pop('variables', {}) if 'variables' in kwargs else {}
        if not isinstance(variables, dict):
            variables = {}

        # Extract known fields
        if 'exception' in kwargs:
            known_fields['exception'] = kwargs.pop('exception')
        if 'context' in kwargs:
            # Merge with current context if provided
            extra_context = kwargs.pop('context', {})
            if isinstance(extra_context, dict):
                current_ctx = self._get_current_context()
                current_ctx.update(extra_context)
                known_fields['context'] = current_ctx
            else:
                known_fields['context'] = self._get_current_context()
        if 'line_number' in kwargs:
            known_fields['line_number'] = kwargs.pop('line_number')
        if 'source' in kwargs:
            known_fields['source'] = kwargs.pop('source')
        if 'tags' in kwargs:
            known_fields['tags'] = kwargs.pop('tags')

        # Route remaining kwargs to variables
        variables.update(kwargs)

        # Ensure variables is not None
        known_fields['variables'] = variables if variables else None

        # Create log entry
        entry = LogEntry(
            level=level,
            message=message,
            context=self._get_current_context(),
            **known_fields
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

    def trace(self, message: str, *args, **kwargs) -> None:
        """Log trace message with *args and **kwargs support."""
        self._log(LogLevel.TRACE, message, *args, **kwargs)

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

    def error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        exc_info: bool = False,
        **kwargs
    ) -> None:
        """
        Log error message with support for both explicit exceptions and exc_info.

        This method allows logging errors in two ways:
        - Provide an explicit 'exception' parameter for a specific exception instance.
        - Use 'exc_info=True' to automatically capture the current exception from the call stack
          using sys.exc_info()[1] if no explicit exception is provided.

        If both 'exception' and 'exc_info=True' are provided, the explicit 'exception' takes precedence.
        This follows a similar pattern to Python's standard logging module but adapted for our LogEntry structure.

        Args:
            message: The primary error message to log.
            exception: An optional explicit Exception instance to include in the log entry.
            exc_info: If True and no exception is provided, captures the current exception.
            **kwargs: Additional keyword arguments passed to the underlying _log method and LogEntry.

        Note: When exc_info=True, sys.exc_info()[1] retrieves the active exception instance.
              This is useful for logging exceptions from try-except blocks without explicitly passing the exception.
        """
        # Handle exc_info=True by capturing current exception if none provided
        if exc_info and exception is None:
            # sys.exc_info()[1] gets the current exception instance (index 1 is the exception object)
            exception = sys.exc_info()[1]

        self._log(LogLevel.ERROR, message, exception=exception, **kwargs)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, exception=exception, **kwargs)

    def log(
        self,
        level: Union[str, LogLevel],
        message: str,
        *args,
        exception: Optional[Exception] = None,
        exc_info: bool = False,
        **kwargs
    ) -> None:
        """
        Generic log method that accepts string levels or LogLevel enum, with *args and full **kwargs support.

        Compatible with standard logging.log(level, msg, *args, exc_info=None, **kwargs) signature.
        Unknown kwargs routed to LogEntry.variables.

        This method provides a flexible way to log messages at any level, mapping
        string levels to the corresponding LogLevel enum values. It handles exceptions
        similarly to the error method, supporting both explicit exceptions and
        automatic capture via exc_info.

        Args:
            level: Log level as string ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
                   "TRACE", "WATCH", "SUCCESS") or LogLevel enum instance.
            message: The log message to record (supports % formatting with *args).
            *args: Positional arguments for message formatting.
            exception: An optional explicit Exception instance to include in the log entry.
            exc_info: If True and no exception is provided, captures the current exception
                      from sys.exc_info()[1]. Useful for logging active exceptions without
                      passing them explicitly.
            **kwargs: Additional keyword arguments passed to _log; unknowns routed to variables dict.

        Note:
            - String levels are case-insensitive and mapped to LogLevel enum values.
            - Unknown string levels default to LogLevel.INFO.
            - If both 'exception' and 'exc_info=True' are provided, the explicit 'exception'
              takes precedence.
            - This method ensures compatibility with standard logging patterns while
              leveraging PKLogger's structured logging features. Extra kwargs (e.g., file_path,
              parameters, stack_trace) are preserved in LogEntry.variables for GUI error handling.

        Example:
            >>> log.log("INFO", "Processing file %s", "/path/to/file.jpg", file_path="/path/to/file.jpg")
            >>> log.log("ERROR", "Failed to read file", exception=IOError("Access denied"), stack_trace="trace")
            >>> try:
            ...     risky_operation()
            ... except:
            ...     log.log("ERROR", "Operation failed", exc_info=True, function_name="risky_operation")
        """
        if isinstance(level, str):
            level_map = {
                "TRACE": LogLevel.TRACE,
                "DEBUG": LogLevel.DEBUG,
                "INFO": LogLevel.INFO,
                "WATCH": LogLevel.WATCH,
                "SUCCESS": LogLevel.SUCCESS,
                "WARNING": LogLevel.WARNING,
                "ERROR": LogLevel.ERROR,
                "CRITICAL": LogLevel.CRITICAL,
            }
            level = level_map.get(level.upper(), LogLevel.INFO)

        # Handle exc_info similar to the error method
        if exc_info and exception is None:
            try:
                exception = sys.exc_info()[1]
            except (RuntimeError, ValueError):
                exception = None

        self._log(level, message, *args, exception=exception, **kwargs)

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


def get_cache_logger(name: str = "cache", log_dir: Optional[Path] = None) -> PKLogger:
    """
    Get or create the dedicated cache logger instance.

    This function creates a specialized logger for cache-related operations,
    configured to output exclusively to the project's logs/cache_process.log file.
    The logger is set to DEBUG level to capture detailed cache events such as
    gets, sets, misses, validations, etc.

    Configuration details:
    - Logger name: "cache" (or provided name)
    - Log level: DEBUG (captures all cache operations)
    - Output: Single FileOutput to logs/cache_process.log
      - rotate_existing: False (rotation handled externally in app.py)
      - max_size_mb: None (no size-based rotation for cache logs)
      - json_format: False (uses detailed text format)
    - Format: Uses the detailed text format from FileOutput, which includes:
        - Timestamp: YYYY-MM-DD HH:MM:SS.mmm
        - Level: DEBUG (right-aligned)
        - Message: Structured by caller, e.g., "Cache get for /path/to/file.jpg field=hash: found=True, size_valid=True, date_valid=False"
        - Source: Module.function (e.g., flat_cache.get_cache_entry)
        - Line number: If available
        - Thread ID: If not MainThread
        - Variables/Context: If provided via log.watch() or context()
        - Exceptions: Full traceback for errors

    The rotation and header writing for cache_process.log is handled separately
    in img_app/img_app/app.py before calling this function, ensuring a fresh
    log file per application session without interference from this logger's init.

    Usage example:
        >>> from src.pk_py_lib.core.logging.logger import get_cache_logger
        >>> cache_log = get_cache_logger()
        >>>
        >>> # Log a cache get operation
        >>> cache_log.debug(
        ...     "Cache get for /images/photo.jpg field=hash: found=True, size_valid=True, date_valid=False"
        ... )
        >>>
        >>> # With variables for more details
        >>> cache_log.watch(
        ...     filepath="/images/photo.jpg",
        ...     field="hash",
        ...     action="get",
        ...     found=True,
        ...     size_bytes=2048,
        ...     cache_age_days=1.5
        ... )
        >>>
        >>> # In context for session tracking
        >>> with cache_log.context(session_id="scan_123", cache_type="flat"):
        ...     cache_log.info("Cache miss for /images/missing.jpg field=dimensions")

    Args:
        name: Logger name (defaults to "cache" for consistency)
        log_dir: Optional directory for logs. If None, uses get_data_dir() / "logs".

    Returns:
        PKLogger: The configured cache logger instance

    Raises:
        RuntimeError: If the logs directory cannot be created or accessed
        OSError: If file operations fail during output initialization
        ValueError: If log_dir is invalid or get_data_dir() returns an invalid path

    Note:
        This logger does not add global outputs or console output to avoid
        polluting the main application logs with cache details. It is dedicated
        solely to cache_process.log for focused debugging and analysis of
        cache performance, hits/misses, validation failures, etc.

        Callers should structure messages to include key details:
        - filepath: Full path to the cached file
        - field: Cache field name (e.g., 'hash', 'dimensions', 'quality_score')
        - action: Operation type (e.g., 'get', 'set', 'miss', 'hit', 'validate', 'evict')
        - result_details: Key-value pairs like 'found: True, size_valid: True, date_valid: False'

        This enables easy parsing and analysis of cache behavior.
    """
    global _loggers

    if name not in _loggers:
        # Determine log directory
        if log_dir is None:
            data_dir = get_data_dir()
            if not isinstance(data_dir, Path) or not data_dir.exists():
                raise ValueError(
                    f"Invalid data directory from get_data_dir(): {data_dir}. "
                    f"Expected a valid Path object pointing to an existing directory."
                )
            logs_dir = data_dir / "logs"
        else:
            logs_dir = log_dir

        cache_log_path = logs_dir / "cache_process.log"

        # Ensure logs directory exists (creates parents if needed)
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Failed to create logs directory '{logs_dir}': {e}\n"
                f"Details: {e.strerror if hasattr(e, 'strerror') else 'Unknown OSError details'}\n"
                f"Error number: {e.errno if hasattr(e, 'errno') else 'Unknown'}\n"
                f"This may be due to insufficient permissions, disk space, or path issues. "
                f"Please check directory access rights and available storage."
            ) from e

        # Create the dedicated cache logger
        logger = PKLogger(name)
        logger.set_level(LogLevel.DEBUG)

        # Add dedicated file output (no rotation here, handled in app.py)
        # Use detailed text format for readability
        try:
            from .outputs.file import FileOutput
            cache_output = FileOutput(
                file_path=cache_log_path,
                max_size_mb=None,  # No size rotation for cache logs (focus on session)
                backup_count=0,    # No backups; rotation is timestamp-based externally
                json_format=False, # Use human-readable text format
                rotate_existing=False  # Rotation already handled in app.py
            )
            logger.add_output(cache_output)
        except Exception as e:
            raise RuntimeError(
                f"Failed to configure cache file output for '{cache_log_path}': {e}\n"
                f"Details: Cache logger initialization failed. This prevents cache "
                f"debugging logs from being written. Check file permissions and disk space."
            ) from e

        # Cache the logger instance
        _loggers[name] = logger

    return _loggers[name]


# Module-level convenience logger instance
# This allows direct usage like: from .logger import logger; logger.error("message")
# It uses the module's own name for logging, ensuring consistency with per-module loggers.
# All global outputs and level configurations from configure_logging() will apply automatically.
logger = get_logger(__name__)
