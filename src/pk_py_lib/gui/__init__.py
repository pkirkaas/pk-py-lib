"""
GUI components for pk-py-lib.

This module contains reusable GUI components and utilities for building
desktop applications with PySide6.
"""

from __future__ import annotations

# Import only what's available to avoid circular imports
try:
    from . import models
    _models_available = True
except ImportError:
    _models_available = False

__all__ = [
    "models",
]
