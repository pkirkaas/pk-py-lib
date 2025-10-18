"""
JSON schemas for the new JSON-based settings system.

This module contains the embedded JSON schemas for both app-settings.json
and search-profiles.json files, along with utilities for validation and
version management.

Design Notes:
- Schemas are embedded in code for simplicity and reliability
- Version numbers are incremented when breaking changes are made
- Error handling is simple: delete and recreate defaults on any issue
- No migration logic - fresh start approach
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import jsonschema

logger = logging.getLogger("pk_py_lib.core.settings.json_schemas")

# Current schema versions
APP_SETTINGS_SCHEMA_VERSION = 1
SEARCH_PROFILES_SCHEMA_VERSION = 1


# =============================================================================
# App Settings Schema (app-settings.json)
# =============================================================================

APP_SETTINGS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pk.dev/schemas/app-settings-v1.json",
    "title": "Application Settings",
    "type": "object",
    "properties": {
        "version": {
            "type": "integer",
            "minimum": 1,
            "description": "Schema version for compatibility checking"
        },
        "cache_enabled": {
            "type": "boolean",
            "default": True,
            "description": "Whether hash caching is enabled"
        },
        "cache_size_mb": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10000,
            "default": 500,
            "description": "Maximum cache size in megabytes"
        },
        "max_workers": {
            "type": "integer",
            "minimum": 1,
            "maximum": 32,
            "default": 4,
            "description": "Maximum number of worker threads"
        },
        "gui_theme": {
            "type": "string",
            "enum": ["light", "dark", "auto"],
            "default": "auto",
            "description": "GUI theme preference"
        },
        "log_level": {
            "type": "string",
            "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "default": "INFO",
            "description": "Logging level"
        },
        "recent_directories": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "description": "List of recently accessed directories"
        },
        "window_geometry": {
            "type": ["object", "null"],
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer", "minimum": 100},
                "height": {"type": "integer", "minimum": 100}
            },
            "default": None,
            "description": "Saved window position and size"
        },
        "last_updated": {
            "type": "string",
            "format": "date-time",
            "description": "Timestamp of last update"
        }
    },
    "required": ["version"]
}


# =============================================================================
# Search Profiles Schema (search-profiles.json)
# =============================================================================

SEARCH_PROFILES_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pk.dev/schemas/search-profiles-v1.json",
    "title": "Search Profiles",
    "type": "object",
    "properties": {
        "version": {
            "type": "integer",
            "minimum": 1,
            "description": "Schema version for compatibility checking"
        },
        "profiles": {
            "type": "array",
            "items": {"$ref": "#/$defs/profile"},
            "default": [],
            "description": "Array of search profile configurations"
        }
    },
    "required": ["version", "profiles"],
    "$defs": {
        "profile": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "Unique profile identifier"
                },
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 100,
                    "pattern": "^[A-Za-z0-9 _\\-()]+$",
                    "description": "Human-readable profile name"
                },
                "description": {
                    "type": "string",
                    "default": "",
                    "description": "Optional profile description"
                },
                "hash_algorithm": {
                    "type": "string",
                    "enum": ["xxh3", "phash", "whash"],
                    "default": "phash",
                    "description": "Hash algorithm to use for similarity detection"
                },
                "hash_size": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 64,
                    "default": 8,
                    "description": "Size of perceptual hash in bits"
                },
                "similarity_threshold": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.95,
                    "description": "Similarity threshold (0.0=exact, 1.0=any match)"
                },
                "clustering_method": {
                    "type": "string",
                    "enum": ["dbscan", "agglomerative"],
                    "default": "dbscan",
                    "description": "Clustering algorithm for grouping results"
                },
                "quality_threshold": {
                    "type": ["number", "null"],
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": None,
                    "description": "Minimum image quality threshold"
                },
                "min_resolution": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "default": None,
                    "description": "Minimum image resolution in pixels"
                },
                "max_resolution": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "default": None,
                    "description": "Maximum image resolution in pixels"
                },
                "color_mode": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to use color hashing"
                },
                "is_default": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether this is the default profile"
                },
                "is_system": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether this is a system profile (non-deletable)"
                },
                "created_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Profile creation timestamp"
                },
                "updated_at": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Last update timestamp"
                },
                "pools": {
                    "type": "object",
                    "properties": {
                        "A": {"$ref": "#/$defs/pool"},
                        "B": {"$ref": "#/$defs/pool"}
                    },
                    "description": "Pool configurations for search paths and file patterns"
                },
                "criteria": {
                    "type": "object",
                    "properties": {
                        "algorithm": {
                            "type": "string",
                            "enum": ["xxh3", "phash", "whash"],
                            "default": "phash"
                        },
                        "degree_ui": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "default": 90
                        },
                        "similarity_hash_algorithm": {
                            "type": "string",
                            "enum": ["phash", "whash"],
                            "default": "phash"
                        }
                    },
                    "description": "Algorithm and parameter settings"
                },
                "scope": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["single_pool", "two_pool"],
                            "default": "two_pool"
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["duplicates", "non_duplicates"],
                            "default": "duplicates"
                        }
                    },
                    "required": ["kind"],
                    "description": "Scope configuration for single vs two-pool operations"
                },
                "output": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["report_only"],
                            "default": "report_only"
                        }
                    },
                    "required": ["mode"],
                    "description": "Output mode and format settings"
                },
                "similarity": {
                    "type": "object",
                    "properties": {
                        "phash_threshold": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 64,
                            "default": 10
                        },
                        "whash_threshold": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 64,
                            "default": 12
                        },
                        "enabled_algorithms": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["phash", "whash"]},
                            "default": ["phash"]
                        }
                    },
                    "description": "Advanced similarity algorithm settings"
                },
                "image_quality_evaluator": {
                    "type": "string",
                    "enum": ["none", "brisque"],
                    "default": "brisque",
                    "description": "Image quality evaluation method"
                },
                "use_flat_cache": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to use flat cache for performance"
                },
                "profile_version": {
                    "type": "string",
                    "default": "1.0.0",
                    "description": "Profile format version"
                },
                "schema_version": {
                    "type": "string",
                    "default": "1.0",
                    "description": "Schema version for migration support"
                }
            },
            "required": ["id", "name", "created_at", "updated_at"],
            "allOf": [
                # xxh3 algorithm: similarity threshold should be null or absent
                {
                    "if": {"properties": {"hash_algorithm": {"const": "xxh3"}}},
                    "then": {
                        "properties": {
                            "similarity_threshold": {"type": ["null", "number"]}
                        }
                    }
                },
                # phash/whash algorithms: requires similarity threshold
                {
                    "if": {"properties": {"hash_algorithm": {"enum": ["phash", "whash"]}}},
                    "then": {
                        "properties": {
                            "similarity_threshold": {"type": "number"}
                        }
                    }
                }
            ]
        },
        "pool": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1,
                    "description": "List of directory paths to search"
                },
                "recurse": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to search subdirectories recursively"
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Maximum directory depth to search (0 = unlimited)"
                },
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["**/*"],
                    "description": "File glob patterns to include"
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "File glob patterns to exclude"
                },
                "follow_symlinks": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to follow symbolic links"
                },
                "include_hidden": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to include hidden files and directories"
                },
                "type_filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"],
                    "description": "File extensions to include in search"
                }
            },
            "required": ["paths"]
        }
    }
}


# =============================================================================
# Default Data Factories
# =============================================================================

def create_default_app_settings() -> Dict[str, Any]:
    """
    Create default application settings.

    Returns
    -------
    Dict[str, Any]
        Default app settings following the schema
    """
    return {
        "version": APP_SETTINGS_SCHEMA_VERSION,
        "cache_enabled": True,
        "cache_size_mb": 500,
        "max_workers": 4,
        "gui_theme": "auto",
        "log_level": "INFO",
        "recent_directories": [],
        "window_geometry": None,
        "last_updated": datetime.now().isoformat()
    }


def create_default_search_profiles() -> Dict[str, Any]:
    """
    Create default search profiles.

    Returns
    -------
    Dict[str, Any]
        Default search profiles following the schema
    """
    now = datetime.now().isoformat()

    return {
        "version": SEARCH_PROFILES_SCHEMA_VERSION,
        "profiles": [
            {
                "id": 1,
                "name": "Default",
                "description": "Default profile for finding exact duplicate files using xxh3 hashing",
                "hash_algorithm": "xxh3",
                "clustering_method": "dbscan",
                "is_default": True,
                "is_system": True,
                "pools": {
                    "A": {
                        "paths": [str(Path.home())],
                        "recurse": True,
                        "max_depth": 0,
                        "include": ["**/*"],
                        "exclude": [],
                        "follow_symlinks": False,
                        "include_hidden": False,
                        "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                    }
                },
                "criteria": {
                    "algorithm": "xxh3"
                },
                "scope": {
                    "kind": "single_pool"
                },
                "output": {
                    "mode": "report_only"
                },
                "image_quality_evaluator": "brisque",
                "use_flat_cache": True,
                "profile_version": "1.0.0",
                "schema_version": "1.0",
                "created_at": now,
                "updated_at": now
            },
            {
                "id": 2,
                "name": "Similarity Search",
                "description": "Default profile for finding similar images using perceptual hashing",
                "hash_algorithm": "phash",
                "hash_size": 8,
                "similarity_threshold": 0.95,
                "clustering_method": "dbscan",
                "is_default": False,
                "is_system": True,
                "pools": {
                    "A": {
                        "paths": [str(Path.home())],
                        "recurse": True,
                        "max_depth": 0,
                        "include": ["**/*"],
                        "exclude": [],
                        "follow_symlinks": False,
                        "include_hidden": False,
                        "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                    }
                },
                "criteria": {
                    "algorithm": "phash",
                    "degree_ui": 90,
                    "similarity_hash_algorithm": "phash"
                },
                "scope": {
                    "kind": "single_pool"
                },
                "output": {
                    "mode": "report_only"
                },
                "similarity": {
                    "phash_threshold": 10,
                    "whash_threshold": 12,
                    "enabled_algorithms": ["phash"]
                },
                "image_quality_evaluator": "brisque",
                "use_flat_cache": True,
                "profile_version": "1.0.0",
                "schema_version": "1.0",
                "created_at": now,
                "updated_at": now
            },
            {
                "id": 3,
                "name": "High Quality",
                "description": "Profile for high-quality image similarity with strict thresholds",
                "hash_algorithm": "whash",
                "hash_size": 16,
                "similarity_threshold": 0.90,
                "clustering_method": "agglomerative",
                "quality_threshold": 0.8,
                "is_default": False,
                "is_system": True,
                "pools": {
                    "A": {
                        "paths": [str(Path.home())],
                        "recurse": True,
                        "max_depth": 0,
                        "include": ["**/*"],
                        "exclude": [],
                        "follow_symlinks": False,
                        "include_hidden": False,
                        "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                    }
                },
                "criteria": {
                    "algorithm": "whash",
                    "degree_ui": 90,
                    "similarity_hash_algorithm": "whash"
                },
                "scope": {
                    "kind": "single_pool"
                },
                "output": {
                    "mode": "report_only"
                },
                "similarity": {
                    "phash_threshold": 10,
                    "whash_threshold": 12,
                    "enabled_algorithms": ["whash"]
                },
                "image_quality_evaluator": "brisque",
                "use_flat_cache": True,
                "profile_version": "1.0.0",
                "schema_version": "1.0",
                "created_at": now,
                "updated_at": now
            }
        ]
    }


# =============================================================================
# Validation Functions
# =============================================================================

class SettingsValidationError(Exception):
    """Raised when settings validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []
        self.message = message


def validate_app_settings(data: Dict[str, Any]) -> None:
    """
    Validate application settings against schema.

    Parameters
    ----------
    data : Dict[str, Any]
        Settings data to validate

    Raises
    ------
    SettingsValidationError
        If validation fails
    """
    try:
        jsonschema.validate(instance=data, schema=APP_SETTINGS_SCHEMA)
    except jsonschema.ValidationError as e:
        raise SettingsValidationError(f"App settings validation failed: {e.message}")


def validate_search_profiles(data: Dict[str, Any]) -> None:
    """
    Validate search profiles against schema.

    Parameters
    ----------
    data : Dict[str, Any]
        Profiles data to validate

    Raises
    ------
    SettingsValidationError
        If validation fails
    """
    try:
        jsonschema.validate(instance=data, schema=SEARCH_PROFILES_SCHEMA)
    except jsonschema.ValidationError as e:
        raise SettingsValidationError(f"Search profiles validation failed: {e.message}")


# =============================================================================
# Utility Functions
# =============================================================================

def normalize_app_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize app settings by applying defaults.

    Parameters
    ----------
    data : Dict[str, Any]
        Raw settings data

    Returns
    -------
    Dict[str, Any]
        Normalized settings with defaults applied
    """
    normalized = data.copy()

    # Apply defaults for missing fields
    defaults = create_default_app_settings()
    for key, default_value in defaults.items():
        if key not in normalized:
            normalized[key] = default_value

    # Update timestamp
    normalized["last_updated"] = datetime.now().isoformat()

    return normalized


def normalize_search_profiles(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize search profiles by applying defaults.

    Parameters
    ----------
    data : Dict[str, Any]
        Raw profiles data

    Returns
    -------
    Dict[str, Any]
        Normalized profiles with defaults applied
    """
    normalized = data.copy()

    # Ensure profiles array exists
    if "profiles" not in normalized:
        normalized["profiles"] = create_default_search_profiles()["profiles"]

    # Apply defaults to each profile
    defaults = create_default_search_profiles()
    default_profiles = {profile["name"]: profile for profile in defaults["profiles"]}

    for profile in normalized["profiles"]:
        # Apply defaults for missing fields
        default_profile = default_profiles.get(profile["name"])
        if default_profile:
            for key, default_value in default_profile.items():
                if key not in profile:
                    profile[key] = default_value

        # Map old format to new format if needed
        if "mode" in profile and "algorithm" in profile and "hash_algorithm" not in profile:
            # Convert old format: mode + algorithm -> hash_algorithm
            if profile["mode"] == "duplicates":
                profile["hash_algorithm"] = "xxh3"
            else:  # similarity mode
                profile["hash_algorithm"] = profile["algorithm"]

        # Ensure timestamps
        if "created_at" not in profile:
            profile["created_at"] = datetime.now().isoformat()
        profile["updated_at"] = datetime.now().isoformat()

    return normalized


def check_schema_version(data: Dict[str, Any], expected_version: int) -> bool:
    """
    Check if data matches expected schema version.

    Parameters
    ----------
    data : Dict[str, Any]
        Settings or profiles data
    expected_version : int
        Expected schema version

    Returns
    -------
    bool
        True if version matches, False otherwise
    """
    return data.get("version") == expected_version


__all__ = [
    "APP_SETTINGS_SCHEMA_VERSION",
    "SEARCH_PROFILES_SCHEMA_VERSION",
    "APP_SETTINGS_SCHEMA",
    "SEARCH_PROFILES_SCHEMA",
    "create_default_app_settings",
    "create_default_search_profiles",
    "validate_app_settings",
    "validate_search_profiles",
    "normalize_app_settings",
    "normalize_search_profiles",
    "check_schema_version",
    "SettingsValidationError"
]
