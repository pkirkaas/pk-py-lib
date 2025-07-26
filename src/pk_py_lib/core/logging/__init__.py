"""
Advanced Logging System

Flexible logging with multiple outputs including terminal, file, GUI, and future DB support.
Supports variable watching, performance tracking, and rich formatting.
"""

from .logger import PKLogger, LogLevel, LogEntry, get_logger, configure_logging
from .decorators import log_calls, log_performance, watch_variables
from .context import LogTimer, LogContext

# Import output handlers
from . import outputs
from . import formatters

__all__ = [
    "PKLogger",
    "LogLevel", 
    "LogEntry",
    "get_logger",
    "configure_logging",
    "log_calls",
    "log_performance", 
    "watch_variables",
    "LogTimer",
    "LogContext",
    "outputs",
    "formatters"
]

# Convenience functions for quick setup
def setup_console_logging(level=LogLevel.INFO, rich_output=True):
    """Quick setup for console-only logging."""
    configure_logging(console=True, level=level, rich_console=rich_output)

def setup_file_logging(file_path, level=LogLevel.DEBUG):
    """Quick setup for file-only logging."""
    configure_logging(console=False, file_path=file_path, level=level)

def setup_full_logging(log_dir="logs", level=LogLevel.INFO):
    """Setup comprehensive logging with both console and file output."""
    from pathlib import Path
    log_file = Path(log_dir) / "pk_py_lib.log"
    configure_logging(console=True, file_path=log_file, level=level, rich_console=True)