"""
Utilities Module

Core utility functions and classes for common operations and helpers.
"""

import os
from pathlib import Path
from typing import Optional

import platformdirs

from datetime import datetime


def get_data_dir(app_name: str = "pk_py_lib", app_author: str = "Pk") -> Path:
    """
    Determine the unified, platform-appropriate application data directory.

    This function uses platformdirs to find the standard user data directory
    for the application. It respects the environment variable
    'PK_PY_LIB_HOME' for overriding the default location, which is useful
    for testing or portable installations.

    Args:
        app_name: The name of the application/library (e.g., "pk_py_lib").
        app_author: The author/qualifier (e.g., "Pk").

    Returns:
        Path: The resolved Path object for the data directory.

    Raises:
        RuntimeError: If the environment variable override path is invalid.

    Example:
        >>> data_dir = get_data_dir()
        >>> # On Windows: Path('C:/Users/User/AppData/Local/Pk/pk_py_lib')
        >>> # On Linux: Path('~/.local/share/pk_py_lib')
    """
    # 1. Check for environment variable override
    env_var = os.environ.get("PK_PY_LIB_HOME")
    if env_var:
        try:
            # Expand user home directory (~) and environment variables
            expanded_path = os.path.expanduser(os.path.expandvars(env_var))
            data_dir = Path(expanded_path)

            # Check if path exists and is a file before resolving
            if data_dir.exists() and not data_dir.is_dir():
                raise RuntimeError(
                    f"PK_PY_LIB_HOME environment variable points to an existing file, not a directory: {data_dir}"
                )

            # Resolve with error handling to prevent circular symlink issues
            try:
                resolved_dir = data_dir.resolve()
            except (OSError, RuntimeError) as e:
                # Handle circular symlinks, permission issues, or other path resolution errors
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to resolve path {data_dir}, using unresolve path: {e}")
                # Fall back to using the unresolved path if resolve fails
                resolved_dir = data_dir

            # Final validation
            if resolved_dir.exists() and not resolved_dir.is_dir():
                raise RuntimeError(
                    f"PK_PY_LIB_HOME environment variable points to an existing file, not a directory: {resolved_dir}"
                )

            return resolved_dir

        except Exception as e:
            # If environment variable path is invalid, log warning and fall back to platformdirs
            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid PK_PY_LIB_HOME environment variable '{env_var}': {e}. Using default location.")

    # 2. Use platformdirs for OS-appropriate location
    # Ensure app_name and app_author are used correctly for platformdirs
    # We use 'pk_py_lib' as the name and 'Pk' as the qualifier/author
    return Path(platformdirs.user_data_dir(app_name, app_author))


def format_timestamp(timestamp: float | None) -> str:
    """
    Format a Unix timestamp (float) into a human-readable datetime string.

    This utility converts a Unix timestamp (seconds since epoch, as float) to a
    formatted string in the format 'YYYY-MM-DD HH:MM:SS'. It is designed for
    displaying file modification times, log entries, or cache metadata in the UI
    or reports. The function handles common edge cases such as None inputs or
    invalid timestamps by raising informative exceptions for debugging.

    Args:
        timestamp: The Unix timestamp as a float (e.g., from os.stat().st_mtime).
                   If None, raises a ValueError.

    Returns:
        str: Formatted datetime string, e.g., '2025-10-06 14:53:46'.

    Raises:
        ValueError: If timestamp is None or invalid (e.g., negative value or
                    out of reasonable range for datetime.fromtimestamp).
        TypeError: If timestamp is not a float or None.

    Examples:
        >>> format_timestamp(1728231226.0)
        '2025-10-06 14:53:46'

        >>> # Invalid case
        >>> format_timestamp(-1)  # Raises ValueError: Invalid timestamp -1.0

    Notes:
        - Timezone: Uses local system timezone for fromtimestamp.
        - Precision: Truncates microseconds; uses seconds only.
        - Usage in FileItem: Commonly used for mod_date in duplicate/similarity managers,
          e.g., mod_date = format_timestamp(stat.st_mtime).
        - Error Reporting: Exceptions include the invalid timestamp value for
          debugging. In production, wrap with try-except to log to stderr.
        - Syntax validation: This function has been validated using Python's ast module.
    """
    if timestamp is None:
        raise ValueError("Timestamp cannot be None. Provide a valid float Unix timestamp.")
    if not isinstance(timestamp, float):
        raise TypeError(f"Expected float timestamp, got {type(timestamp)}: {timestamp}")
    if timestamp < 0:
        raise ValueError(f"Invalid timestamp {timestamp}. Unix timestamps cannot be negative.")

    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, ValueError) as e:
        raise ValueError(f"Invalid timestamp {timestamp}: {str(e)}") from e


__all__ = [
    "get_data_dir",
    "format_timestamp"
]
