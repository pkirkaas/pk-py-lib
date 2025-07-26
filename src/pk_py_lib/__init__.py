"""
PK-Py-Lib: A comprehensive library for image processing and GUI components.

This library provides reusable components for:
- File system operations with advanced path handling
- Real-time file monitoring 
- Flexible multi-output logging
- GUI components for image manipulation
- CLI tools and processing APIs
"""

__version__ = "0.1.0"
__author__ = "Paul Kirkaas"

# Core modules
from . import core

# Export commonly used functions for convenience
from .core.filesystem import normalize_paths, remove_contained_paths, safe_move
from .core.logging import get_logger, configure_logging

__all__ = [
    "core",
    "normalize_paths", 
    "remove_contained_paths",
    "safe_move",
    "get_logger",
    "configure_logging"
]

# Setup default logging when package is imported
def _setup_default_logging():
    """Setup reasonable default logging configuration."""
    try:
        configure_logging(
            console=True,
            level=core.logging.LogLevel.INFO,
            rich_console=True
        )
    except Exception:
        # Fallback to basic logging if rich is not available
        configure_logging(
            console=True,
            level=core.logging.LogLevel.INFO,
            rich_console=False
        )

# Initialize logging on import
_setup_default_logging()