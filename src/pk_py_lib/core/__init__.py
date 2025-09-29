"""
PK-Py-Lib Core Module

Core functionality for image processing, file operations, and system utilities.
This module provides the foundation for both GUI and CLI interfaces.
"""

__version__ = "0.1.0"
__author__ = "Paul Kirkaas"

# Core submodules
from . import filesystem
from . import logging
from . import image
from . import io
from . import utils

from .utils import get_data_dir # Import the unified path function

__all__ = [
    "get_data_dir",
    "filesystem",
    "logging",
    "image",
    "io",
    "utils"
]