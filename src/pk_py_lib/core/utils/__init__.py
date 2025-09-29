"""
Utilities Module

Core utility functions and classes for common operations and helpers.
"""

import os
from pathlib import Path
from typing import Optional

import platformdirs


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
        data_dir = Path(env_var).resolve()
        if not data_dir.is_dir() and data_dir.exists():
            raise RuntimeError(
                f"PK_PY_LIB_HOME environment variable points to an existing file, not a directory: {data_dir}"
            )
        return data_dir

    # 2. Use platformdirs for OS-appropriate location
    # Ensure app_name and app_author are used correctly for platformdirs
    # We use 'pk_py_lib' as the name and 'Pk' as the qualifier/author
    return Path(platformdirs.user_data_dir(app_name, app_author))


__all__ = [
    "get_data_dir"
]