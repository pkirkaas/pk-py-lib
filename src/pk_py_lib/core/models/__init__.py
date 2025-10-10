"""
Core data models for pk-py-lib.

This package contains the canonical data models for the application,
consolidating previously fragmented models into a unified architecture.
"""

from .settings import AppSettings, SettingsProfile, DEFAULT_PROFILES

__all__ = [
    'AppSettings',
    'SettingsProfile',
    'DEFAULT_PROFILES',
]
