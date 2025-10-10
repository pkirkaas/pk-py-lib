"""
src/pk_py_lib/core/configuration.py

DEPRECATED: This module has been moved and consolidated.

This file exists only for backward compatibility. Please use the new location:
- src.pk_py_lib.core.settings.manager for unified settings management

All imports from this module will continue to work but will show deprecation warnings.
"""

import warnings

# Issue deprecation warning
warnings.warn(
    "Importing from 'src.pk_py_lib.core.configuration' is deprecated. "
    "Use 'src.pk_py_lib.core.settings.manager' for unified settings management.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything from the new location
from .settings.manager import *

# For backward compatibility, also provide legacy names
from .settings.manager import SettingsManager as ConfigurationManager
