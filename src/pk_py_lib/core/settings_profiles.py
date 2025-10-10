"""
src/pk_py_lib/core/settings_profiles.py

DEPRECATED: This module has been consolidated into the unified settings manager.

This file exists only for backward compatibility. Please use:
- src.pk_py_lib.core.settings.manager for all settings management functionality

All imports from this module will continue to work but will show deprecation warnings.
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "Importing from 'src.pk_py_lib.core.settings_profiles' is deprecated. "
    "Use 'src.pk_py_lib.core.settings.manager' for all settings management functionality.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything from the unified settings manager
from .settings.manager import *
