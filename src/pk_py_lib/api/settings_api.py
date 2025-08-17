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

from ..core.configuration import ConfigurationManager, AppSettings, Profile, SettingScope
from ..core.database import DatabaseManager

logger = logging.getLogger("pk_py_lib.api.settings_api")


class SettingsAPI:
    """
    Adapter that exposes configuration functions in an API-friendly shape.

    The adapter intentionally keeps the surface small and delegates heavy
    lifting to the underlying ConfigurationManager/database layer.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize SettingsAPI.

        Args:
            db_manager: Optional DatabaseManager. If omitted, a default
                        DatabaseManager is created and initialized lazily.
        """
        if db_manager is None:
            db_manager = DatabaseManager()
            db_manager.initialize()
        self.db_manager = db_manager
        self.config = ConfigurationManager(self.db_manager)

    # App-scoped methods
    def get_app_settings(self) -> AppSettings:
        """Return the strongly-typed AppSettings instance."""
        return self.config.get_app_settings()

    def update_app_settings(self, updates: Dict[str, Any]) -> AppSettings:
        """
        Apply partial updates to the AppSettings object and persist.

        Performs minimal validation via attribute existence checks.
        """
        settings = self.get_app_settings()
        valid_keys = set(asdict(settings).keys())
        filtered = {k: v for k, v in updates.items() if k in valid_keys}
        if not filtered:
            return settings
        self.config.update_app_settings(**filtered)
        return self.get_app_settings()

    # Profile-scoped methods
    def get_profile(self, name: Optional[str] = None) -> Profile:
        """
        Get the named profile or the current/default profile if name is None.

        Note: calling this with a name will switch the active profile via
        ConfigurationManager.switch_profile(name).
        """
        if name is None:
            return self.config.get_current_profile()
        return self.config.switch_profile(name)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Return a list of available profiles with metadata."""
        return self.config.list_profiles()

    # Generic get/set
    def get_setting(self, key: str, default: Any = None, scope: Optional[str] = None, profile: Optional[str] = None) -> Any:
        """
        Get a setting value, automatically resolving scope when not provided.
        """
        try:
            if scope == "app" or (scope is None and hasattr(self.get_app_settings(), key)):
                val = self.config.get_app_setting(key)
                return val if val is not None else default
            else:
                if profile:
                    self.config.switch_profile(profile)
                val = self.config.get_profile_setting(key)
                return val if val is not None else default
        except Exception:
            logger.exception("Error fetching setting %s", key)
            return default

    def set_setting(self, key: str, value: Any, scope: Optional[str] = None, profile: Optional[str] = None, persist: bool = True) -> bool:
        """
        Set a setting value in the indicated scope.

        Returns True on success, False on error.
        """
        try:
            if scope == "app" or (scope is None and hasattr(self.get_app_settings(), key)):
                self.config.set_app_setting(key, value)
                return True
            else:
                if profile:
                    self.config.switch_profile(profile)
                self.config.set_profile_setting(key, value)
                return True
        except Exception:
            logger.exception("Failed to set setting %s=%s", key, value)
            return False

    # Export / import helpers
    def export_settings(self, path: Path, scope: Optional[str] = "profile", profile: Optional[str] = None) -> bool:
        """
        Export settings to a JSON file. Scope 'app' exports AppSettings; 'profile' exports profile settings.
        """
        try:
            if scope == "app":
                data = asdict(self.get_app_settings())
            else:
                p = self.get_profile(profile) if profile else self.get_profile()
                # Build profile payload from its dataclass-like structure
                data = {
                    "id": p.id,
                    "name": p.name,
                    "is_default": p.is_default,
                    "algorithm_defaults": p.algorithm_defaults,
                    "file_handling": p.file_handling,
                    "history": p.history,
                }
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            logger.exception("Failed to export settings to %s", path)
            return False

    def import_settings(self, path: Path, scope: Optional[str] = "profile") -> bool:
        """
        Import settings JSON produced by export_settings. For profiles, creates a new profile.
        """
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if scope == "app":
                self.update_app_settings(payload)
                return True
            else:
                name = payload.get("name", f"Imported-{int(time.time())}")
                new_profile = self.config.create_profile(name)
                # Persist provided profile settings into settings table
                for cat in ("algorithm_defaults", "file_handling", "history"):
                    data = payload.get(cat, {})
                    for k, v in data.items():
                        self.config.set_profile_setting(f"{cat}.{k}", v, profile=new_profile)
                return True
        except Exception:
            logger.exception("Failed to import settings from %s", path)
            return False

__all__ = ["SettingsAPI"]