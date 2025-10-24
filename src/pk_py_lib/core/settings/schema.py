"""
Settings schema validation for pk-py-lib.

This module provides JSON schema validation and normalization
for settings profiles and application configuration.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from ...core.logging.logger import get_logger
from ...core.api.response import ApiResponse, ErrorCodes, create_success_response, create_error_response


logger = get_logger(__name__)


# JSON Schema for SettingsProfileOptionA (from data model)
SETTINGS_PROFILE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pk.dev/schemas/settings-profile-option-a-v1.json",
    "title": "SettingsProfileOptionA",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "name": {"type": "string", "pattern": "^[A-Za-z0-9 _-]{1,64}$"},
        "description": {"type": "string"},
        "profile_version": {"type": "string", "default": "1.0.0"},
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "schema_version": {"type": "string", "default": "1.0"},
        "pools": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "A": {"$ref": "#/$defs/pool"},
                "B": {"$ref": "#/$defs/pool"}
            },
            "required": ["A"]
        },
        "mode": {"type": "string", "enum": ["duplicates", "similarity"], "default": "duplicates"},
        "criteria": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "algorithm": {"type": "string", "enum": ["blake3", "pHash"], "default": "pHash"},
                "degree_ui": {"type": "integer", "minimum": 0, "maximum": 100, "default": 90},
                "phash": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "hash_size": {"type": "integer", "minimum": 4, "maximum": 64, "default": 8}
                    }
                }
            }
        },
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"type": "string", "enum": ["single_pool", "two_pool"], "default": "two_pool"},
                "direction": {
                    "type": "string",
                    "enum": ["A_TO_B", "B_TO_A", "A_WITHOUT_IN_B", "B_WITHOUT_IN_A"],
                    "default": "A_TO_B"
                },
                "single_pool_clustering": {
                    "type": "boolean",
                    "default": False
                }
            },
            "required": ["kind"]
        },
        "output": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "mode": {"type": "string", "enum": ["report_only"], "default": "report_only"}
            },
            "required": ["mode"]
        }
    },
    "required": ["id", "name", "created_at", "updated_at", "pools", "mode", "criteria", "scope", "output"],
    "$defs": {
        "pool": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 1
                },
                "recurse": {"type": "boolean", "default": True},
                "max_depth": {"type": "integer", "minimum": 0, "default": 0},
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["**/*"]
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": []
                },
                "follow_symlinks": {"type": "boolean", "default": False},
                "include_hidden": {"type": "boolean", "default": False},
                "type_filters": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                },
                "size_constraints": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "min_bytes": {"type": "integer", "minimum": 0},
                        "max_bytes": {"type": "integer", "minimum": 0}
                    }
                },
                "date_constraints": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "min_date": {"type": "string", "format": "date-time"},
                        "max_date": {"type": "string", "format": "date-time"}
                    }
                }
            },
            "required": ["paths"]
        }
    },
    "allOf": [
        {
            "if": {"properties": {"mode": {"const": "duplicates"}}},
            "then": {
                "properties": {
                    "criteria": {
                        "properties": {
                            "algorithm": {"const": "blake3", "default": "blake3"}
                        }
                    }
                },
                "not": {"properties": {"criteria": {"required": ["degree_ui"]}}}
            }
        },
        {
            "if": {"properties": {"mode": {"const": "similarity"}}},
            "then": {
                "properties": {
                    "criteria": {
                        "required": ["algorithm", "degree_ui"],
                        "properties": {"algorithm": {"default": "pHash"}}
                    }
                }
            }
        },
        {
            "if": {"properties": {"scope": {"properties": {"kind": {"const": "two_pool"}}}}},
            "then": {
                "properties": {
                    "pools": {"required": ["A", "B"]},
                    "scope": {
                        "required": ["kind", "direction"],
                        "not": {"required": ["single_pool_clustering"]}
                    }
                }
            },
            "else": {
                "properties": {
                    "scope": {"not": {"required": ["direction"]}}
                }
            }
        }
    ]
}


# App Settings Schema
APP_SETTINGS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://pk.dev/schemas/app-settings-v1.json",
    "title": "AppSettings",
    "type": "object",
    "properties": {
        "id": {"type": "integer", "default": 1},
        "theme": {"type": "string", "enum": ["light", "dark", "auto"], "default": "light"},
        "language": {"type": "string", "default": "en"},
        "ui_scale": {"type": "number", "minimum": 0.5, "maximum": 3.0, "default": 1.0},
        "max_threads": {"type": "integer", "minimum": 1, "maximum": 32, "default": 4},
        "max_memory_mb": {"type": "integer", "minimum": 512, "maximum": 65536, "default": 2048},
        "cache_size_mb": {"type": "integer", "minimum": 100, "maximum": 102400, "default": 5120},
        "window_geometry": {"type": ["object", "null"]},
        "panel_layout": {"type": ["object", "null"]},
        "shortcuts": {"type": ["object", "null"]},
        "created_at": {"type": "string", "format": "date-time"},
        "modified_at": {"type": "string", "format": "date-time"}
    },
    "additionalProperties": False
}


def validate_settings_schema(
    settings: Dict[str, Any],
    schema: Dict[str, Any]
) -> tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate settings against JSON schema.

    Args:
        settings: Settings dictionary to validate
        schema: JSON schema to validate against

    Returns:
        Tuple of (is_valid, errors, normalized_settings)
    """
    try:
        import jsonschema

        # Validate against schema
        jsonschema.validate(instance=settings, schema=schema)

        # Apply defaults for missing fields
        normalized = _apply_schema_defaults(settings, schema)

        return True, [], normalized

    except jsonschema.ValidationError as e:
        return False, [f"Schema validation failed: {e.message}"], {}
    except Exception as e:
        return False, [f"Validation error: {str(e)}"], {}


def _apply_schema_defaults(settings: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply default values from schema to settings.

    Args:
        settings: Settings dictionary
        schema: JSON schema

    Returns:
        Settings with defaults applied
    """
    result = settings.copy()

    # Apply defaults from properties
    if "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if prop_name not in result and "default" in prop_schema:
                result[prop_name] = prop_schema["default"]

    return result


def normalize_settings_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a settings profile with defaults applied.

    Args:
        profile: Profile dictionary to normalize

    Returns:
        Normalized profile with defaults
    """
    is_valid, errors, normalized = validate_settings_schema(profile, SETTINGS_PROFILE_SCHEMA)

    if not is_valid:
        logger.warning(f"Profile normalization had validation errors: {errors}")
        # Still return the normalized profile for best-effort use

    return normalized


def create_default_profile(name: str = "Default Profile") -> Dict[str, Any]:
    """
    Create a default settings profile.

    Args:
        name: Profile name

    Returns:
        Default profile dictionary
    """
    import uuid
    from datetime import datetime

    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "profile_version": "1.0.0",
        "schema_version": "1.0",
        "created_at": datetime.now().isoformat() + "Z",
        "updated_at": datetime.now().isoformat() + "Z",
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


def validate_profile_name(name: str) -> tuple[bool, str]:
    """
    Validate profile name.

    Args:
        name: Name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(name, str):
        return False, "Name must be a string"

    name = name.strip()

    if len(name) < 1:
        return False, "Name cannot be empty"

    if len(name) > 64:
        return False, "Name cannot be longer than 64 characters"

    import re
    if not re.match(r'^[A-Za-z0-9 _-]+$', name):
        return False, "Name can only contain letters, numbers, spaces, underscores, and hyphens"

    return True, ""


def suggest_unique_name(base_name: str, existing_names: List[str]) -> str:
    """
    Suggest a unique name based on a base name.

    Args:
        base_name: Base name to start with
        existing_names: List of existing names to avoid

    Returns:
        Unique name suggestion
    """
    if base_name not in existing_names:
        return base_name

    counter = 1
    while True:
        candidate = f"{base_name} ({counter})"
        if candidate not in existing_names:
            return candidate
        counter += 1
