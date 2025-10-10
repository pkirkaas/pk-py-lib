"""
src/pk_py_lib/api/settings/__init__.py

Unified Settings API package providing consolidated access to application and profile settings.

This package consolidates functionality from both legacy SettingsAPI and SettingsProfilesAPI
into a single, coherent interface.

Exports
-------
UnifiedSettingsAPI : Main unified API class
    Single interface for all settings operations

Examples
--------
>>> from pk_py_lib.api.settings import UnifiedSettingsAPI
>>> api = UnifiedSettingsAPI()
>>> settings = api.get_app_settings()
>>> profiles = api.list_profiles()
"""

from .unified_api import UnifiedSettingsAPI

__all__ = ["UnifiedSettingsAPI"]
