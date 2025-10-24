"""
Advanced logger implementation for pk-py-lib.

This module provides the core logging functionality with support for
multiple outputs, structured logging, and variable watching.
"""

from __future__ import annotations

import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional
import structlog


class PKLogger:
    """
    Advanced logger with multiple output support and variable watching.

    This logger provides structured logging with support for:
    - Multiple output formats (console, file, GUI)
    - Variable watching for debugging complex state
    - Performance timing and metrics
    - Rich formatting with colors and structure
    """

    def __init__(self, name: str, level: str = "INFO"):
        """
        Initialize PKLogger.

        Args:
            name: Logger name (typically __name__)
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.name = name
        self.level = getattr(logging, level.upper(), logging.INFO)

        # Setup structured logging
        self._setup_structlog()

        # Variable watching
        self._watched_vars: Dict[str, Any] = {}

        # Performance tracking
        self._timers: Dict[str, float] = {}

    def _setup_structlog(self) -> None:
        """Setup structured logging configuration."""
        # Configure structlog processors
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ]

        structlog.configure(
            processors=processors,
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Get the structured logger
        self._logger = structlog.get_logger(self.name)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self._logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self._logger.critical(message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback."""
        self._logger.exception(message, **kwargs)

    def watch(self, **variables) -> None:
        """
        Watch variables for debugging.

        Args:
            **variables: Variables to watch (name=value)
        """
        for name, value in variables.items():
            self._watched_vars[name] = value
            self.debug(f"Watching {name}", **{name: value})

    def unwatch(self, *var_names) -> None:
        """
        Stop watching variables.

        Args:
            *var_names: Variable names to stop watching
        """
        for name in var_names:
            if name in self._watched_vars:
                del self._watched_vars[name]
                self.debug(f"Stopped watching {name}")

    def get_watched_vars(self) -> Dict[str, Any]:
        """Get currently watched variables."""
        return self._watched_vars.copy()

    def start_timer(self, name: str) -> None:
        """
        Start a performance timer.

        Args:
            name: Timer name
        """
        import time
        self._timers[name] = time.time()
        self.debug(f"Started timer: {name}")

    def end_timer(self, name: str) -> float:
        """
        End a performance timer and return elapsed time.

        Args:
            name: Timer name

        Returns:
            Elapsed time in seconds
        """
        import time
        if name not in self._timers:
            raise ValueError(f"Timer '{name}' not started")

        elapsed = time.time() - self._timers[name]
        del self._timers[name]

        self.debug(f"Timer {name} completed", elapsed=elapsed)
        return elapsed

    def log_performance(self, operation: str, duration: float, **metadata) -> None:
        """
        Log performance metrics.

        Args:
            operation: Operation name
            duration: Duration in seconds
            **metadata: Additional performance metadata
        """
        self.info(f"Performance: {operation}", duration=duration, **metadata)


# Global logger factory
_loggers: Dict[str, PKLogger] = {}


def get_logger(name: str, level: str = "INFO") -> PKLogger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (typically __name__)
        level: Logging level

    Returns:
        PKLogger instance
    """
    if name not in _loggers:
        _loggers[name] = PKLogger(name, level)
    return _loggers[name]


def configure_logging(
    level: str = "INFO",
    console: bool = True,
    file_path: Optional[str] = None,
    json_format: bool = False
) -> None:
    """
    Configure global logging settings.

    Args:
        level: Global logging level
        console: Enable console output
        file_path: Optional file path for log output
        json_format: Use JSON format instead of human-readable
    """
    # Configure standard Python logging
    logging_level = getattr(logging, level.upper(), logging.INFO)

    # Configure structlog
    if json_format:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ]
    else:
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer(colors=True)
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging_level)

        if json_format:
            formatter = structlog.stdlib.ProcessorFormatter(
                processors=[structlog.processors.JSONRenderer()]
            )
        else:
            formatter = structlog.stdlib.ProcessorFormatter(
                processors=[structlog.dev.ConsoleRenderer(colors=True)]
            )

        console_handler.setFormatter(formatter)

        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging_level)

    # Configure file handler
    if file_path:
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(logging_level)

        if json_format:
            formatter = structlog.stdlib.ProcessorFormatter(
                processors=[structlog.processors.JSONRenderer()]
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
            )

        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


# Convenience functions for backward compatibility
def debug(message: str, **kwargs) -> None:
    """Log debug message (convenience function)."""
    logger = get_logger("pk_py_lib")
    logger.debug(message, **kwargs)


def info(message: str, **kwargs) -> None:
    """Log info message (convenience function)."""
    logger = get_logger("pk_py_lib")
    logger.info(message, **kwargs)


def warning(message: str, **kwargs) -> None:
    """Log warning message (convenience function)."""
    logger = get_logger("pk_py_lib")
    logger.warning(message, **kwargs)


def error(message: str, **kwargs) -> None:
    """Log error message (convenience function)."""
    logger = get_logger("pk_py_lib")
    logger.error(message, **kwargs)


def critical(message: str, **kwargs) -> None:
    """Log critical message (convenience function)."""
    logger = get_logger("pk_py_lib")
    logger.critical(message, **kwargs)
