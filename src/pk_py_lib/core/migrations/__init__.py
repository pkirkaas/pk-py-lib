"""
Database migration utilities for pk-py-lib.

This package provides tools for migrating the database schema and data
as the application evolves, particularly for the settings consolidation.
"""

from .settings_migration import SettingsMigration

__all__ = [
    'SettingsMigration',
]
