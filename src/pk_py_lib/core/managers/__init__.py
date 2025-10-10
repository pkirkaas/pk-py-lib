"""
Unified settings managers.

This module provides the unified managers for application settings
and settings profiles, replacing the old fragmented managers.
"""

from .app_settings import AppSettingsManager
from .profiles import ProfilesManager

__all__ = ['AppSettingsManager', 'ProfilesManager']
