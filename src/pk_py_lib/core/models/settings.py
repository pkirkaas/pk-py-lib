"""
Settings models for pk-py-lib.

This module contains the core data models for application settings
and profile management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path
import uuid


@dataclass
class AppSettings:
    """
    Global application settings.

    This class represents application-wide settings that are not
    profile-specific, such as UI preferences, performance settings,
    and global configuration.
    """

    # Identification
    id: int = 1  # Single row identifier

    # UI Preferences
    theme: str = "light"  # light, dark, auto
    language: str = "en"
    ui_scale: float = 1.0

    # Performance Settings
    max_threads: int = 4
    max_memory_mb: int = 2048
    cache_size_mb: int = 5120  # 5GB default

    # UI Preferences
    window_geometry: Optional[Dict[str, Any]] = None
    panel_layout: Optional[Dict[str, Any]] = None
    shortcuts: Optional[Dict[str, str]] = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "theme": self.theme,
            "language": self.language,
            "ui_scale": self.ui_scale,
            "max_threads": self.max_threads,
            "max_memory_mb": self.max_memory_mb,
            "cache_size_mb": self.cache_size_mb,
            "window_geometry": self.window_geometry,
            "panel_layout": self.panel_layout,
            "shortcuts": self.shortcuts,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppSettings:
        """Create from dictionary."""
        return cls(
            id=data.get("id", 1),
            theme=data.get("theme", "light"),
            language=data.get("language", "en"),
            ui_scale=data.get("ui_scale", 1.0),
            max_threads=data.get("max_threads", 4),
            max_memory_mb=data.get("max_memory_mb", 2048),
            cache_size_mb=data.get("cache_size_mb", 5120),
            window_geometry=data.get("window_geometry"),
            panel_layout=data.get("panel_layout"),
            shortcuts=data.get("shortcuts"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            modified_at=datetime.fromisoformat(data.get("modified_at", datetime.now().isoformat())),
        )


@dataclass
class SettingsProfile:
    """
    Settings profile for image processing workflows.

    This class represents a named configuration profile that defines
    how image processing operations should be performed, including
    pool configurations, algorithm settings, and processing options.
    """

    # Identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Profile"
    description: Optional[str] = None

    # Profile metadata
    profile_version: str = "1.0.0"
    schema_version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")

    # Profile state
    is_active: bool = False

    # Profile configuration data (JSON schema compliant)
    json_data: Optional[Dict[str, Any]] = None

    # Legacy support (for backward compatibility)
    legacy_items: Optional[Dict[str, Any]] = None

    def is_json_format(self) -> bool:
        """Check if profile uses JSON schema format."""
        return self.json_data is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "profile_version": self.profile_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
            "json_data": self.json_data,
            "legacy_items": self.legacy_items,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SettingsProfile:
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Default Profile"),
            description=data.get("description"),
            profile_version=data.get("profile_version", "1.0.0"),
            schema_version=data.get("schema_version", "1.0"),
            created_at=data.get("created_at", datetime.now().isoformat() + "Z"),
            updated_at=data.get("updated_at", datetime.now().isoformat() + "Z"),
            is_active=data.get("is_active", False),
            json_data=data.get("json_data"),
            legacy_items=data.get("legacy_items"),
        )


# Default profiles for common use cases
DEFAULT_PROFILES = [
    SettingsProfile(
        id="default-duplicates",
        name="Exact Duplicates",
        description="Find byte-for-byte identical files",
        json_data={
            "pools": {
                "A": {
                    "paths": [],
                    "recurse": True,
                    "max_depth": 0,
                    "include": ["**/*"],
                    "exclude": [],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                }
            },
            "mode": "duplicates",
            "criteria": {
                "algorithm": "blake3"
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }
    ),
    SettingsProfile(
        id="default-similarity",
        name="Similar Images",
        description="Find perceptually similar images",
        json_data={
            "pools": {
                "A": {
                    "paths": [],
                    "recurse": True,
                    "max_depth": 0,
                    "include": ["**/*"],
                    "exclude": [],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "pHash",
                "degree_ui": 90,
                "phash": {
                    "hash_size": 8
                }
            },
            "scope": {
                "kind": "single_pool"
            },
            "output": {
                "mode": "report_only"
            }
        }
    ),
    SettingsProfile(
        id="default-two-pool",
        name="Compare Collections",
        description="Compare two collections of images",
        json_data={
            "pools": {
                "A": {
                    "paths": [],
                    "recurse": True,
                    "max_depth": 0,
                    "include": ["**/*"],
                    "exclude": [],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                },
                "B": {
                    "paths": [],
                    "recurse": True,
                    "max_depth": 0,
                    "include": ["**/*"],
                    "exclude": [],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                }
            },
            "mode": "similarity",
            "criteria": {
                "algorithm": "pHash",
                "degree_ui": 90,
                "phash": {
                    "hash_size": 8
                }
            },
            "scope": {
                "kind": "two_pool",
                "direction": "A_TO_B"
            },
            "output": {
                "mode": "report_only"
            }
        }
    )
]
