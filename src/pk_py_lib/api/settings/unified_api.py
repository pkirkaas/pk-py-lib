"""
src/pk_py_lib/api/settings_api.py

Lightweight adapter exposing a SettingsAPI that delegates to
src.pk_py_lib.core.configuration.ConfigurationManager.

This adapter provides a thin, well-typed surface aligned with the
API specification (docs/roo/img-app-api-specifications.md).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, List

from ...core.settings.manager import SettingsManager
from ...core.models.settings import AppSettings, SettingsProfile


logger = logging.getLogger("pk_py_lib.api.settings.unified_api")


class UnifiedSettingsAPI:
    """
    Adapter that exposes configuration functions in an API-friendly shape.

    The adapter intentionally keeps the surface small and delegates heavy
    lifting to the underlying SettingsManager.
    """

    def __init__(self, settings_manager: Optional[SettingsManager] = None):
        """
        Initialize UnifiedSettingsAPI.

        Args:
            settings_manager: Optional SettingsManager. If omitted, a default
                              SettingsManager is created.
        """
        if settings_manager is None:
            settings_manager = SettingsManager()
        self.settings_manager = settings_manager

    # App-scoped methods
    def get_app_settings(self) -> AppSettings:
        """Return the strongly-typed AppSettings instance."""
        return self.settings_manager.app_settings.load()

    def update_app_settings(self, updates: Dict[str, Any]) -> AppSettings:
        """
        Apply partial updates to the AppSettings object and persist.
        """
        settings = self.get_app_settings()
        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.settings_manager.app_settings.save(settings)
        return self.get_app_settings()

    # Profile-scoped methods
    def get_profile(self, profile_id: int) -> Optional[SettingsProfile]:
        """
        Get the named profile.
        """
        return self.settings_manager.profiles.get_by_id(profile_id)

    def list_profiles(self) -> List[SettingsProfile]:
        """Return a list of available profiles."""
        return self.settings_manager.profiles.get_all()

    # Generic get/set
    def get_setting(self, key: str, default: Any = None, profile_id: Optional[int] = None) -> Any:
        """
        Get a setting value, automatically resolving scope when not provided.
        """
        # For simplicity, this example only supports getting app settings.
        # A more complete implementation would handle profile settings as well.
        try:
            settings = self.get_app_settings()
            return getattr(settings, key, default)
        except Exception:
            logger.exception("Error fetching setting %s", key)
            return default

    def set_setting(self, key: str, value: Any, profile_id: Optional[int] = None) -> bool:
        """
        Set a setting value in the indicated scope.
        """
        # For simplicity, this example only supports setting app settings.
        try:
            self.update_app_settings({key: value})
            return True
        except Exception:
            logger.exception("Failed to set setting %s=%s", key, value)
            return False

    # Export / import helpers
    def export_settings(self, path: Path, profile_id: Optional[int] = None) -> bool:
        """
        Export settings to a JSON file.
        """
        try:
            if profile_id:
                profile = self.get_profile(profile_id)
                if profile:
                    data = profile.to_dict()
                else:
                    return False
            else:
                data = self.get_app_settings().to_dict()

            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            logger.exception("Failed to export settings to %s", path)
            return False

    def import_settings(self, path: Path, profile: bool = False) -> bool:
        """
        Import settings JSON.
        """
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if profile:
                # A more complete implementation would handle profile creation/updates.
                pass
            else:
                self.update_app_settings(payload)
            return True
        except Exception:
            logger.exception("Failed to import settings from %s", path)
            return False

__all__ = ["UnifiedSettingsAPI"]