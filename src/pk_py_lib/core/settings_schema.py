"""
src/pk_py_lib/core/settings_schema.py

JSON Schema and validation for structured settings profiles.

This module defines the canonical JSON Schema for SettingsProfileOptionA
and provides validation functions to ensure settings compatibility.

Note: Syntax validation performed per project rules using Python ast.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime
import jsonschema
from jsonschema import validate, ValidationError

logger = logging.getLogger("pk_py_lib.settings_schema")

# -----------------------------------------------------------------------------
# JSON Schema Definition for SettingsProfileOptionA
# -----------------------------------------------------------------------------

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
                    "default": "A_TO_B",
                    "description": "Default A_TO_B; UI enables direction choice only when both pools validate."
                },
                "single_pool_clustering": {
                    "type": "boolean",
                    "default": False,
                    "description": "Applies only when scope.kind='single_pool'; ignored/disallowed for two_pool."
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
                            "algorithm": {"const": "blake3"},
                            "degree_ui": {"not": {}},
                            "phash": {"not": {}}
                        }
                    }
                }
            }
        },
        {
            "if": {"properties": {"mode": {"const": "similarity"}}},
            "then": {
                "properties": {
                    "criteria": {
                        "properties": {
                            "algorithm": {"const": "pHash"},
                            "degree_ui": {"type": "integer", "minimum": 0, "maximum": 100}
                        },
                        "required": ["degree_ui"]
                    }
                }
            }
        },
        {
            "if": {"properties": {"scope": {"properties": {"kind": {"const": "single_pool"}}}}},
            "then": {
                "properties": {
                    "scope": {
                        "properties": {
                            "direction": {"not": {}},
                            "single_pool_clustering": {"type": "boolean"}
                        }
                    }
                }
            }
        },
        {
            "if": {"properties": {"scope": {"properties": {"kind": {"const": "two_pool"}}}}},
            "then": {
                "properties": {
                    "pools": {
                        "required": ["A", "B"]
                    },
                    "scope": {
                        "required": ["direction"],
                        "properties": {
                            "single_pool_clustering": {"not": {}}
                        }
                    }
                }
            }
        }
    ]
}

# -----------------------------------------------------------------------------
# Validation Functions
# -----------------------------------------------------------------------------

class SettingsValidationError(Exception):
    """Raised when settings validation fails."""
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []
        self.message = message

    def __str__(self):
        if self.errors:
            return f"{self.message}: {', '.join(self.errors)}"
        return self.message


def validate_settings_schema(profile_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate profile data against the JSON schema.
    
    Parameters
    ----------
    profile_data : Dict[str, Any]
        The profile data to validate
        
    Returns
    -------
    Tuple[bool, List[str]]
        (is_valid, error_messages)
    """
    errors = []
    
    try:
        validate(instance=profile_data, schema=SETTINGS_PROFILE_SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")
        return False, errors
    
    # Additional custom validation beyond JSON schema
    custom_errors = _validate_custom_rules(profile_data)
    if custom_errors:
        errors.extend(custom_errors)
        return False, errors
    
    return True, []


def _validate_custom_rules(profile_data: Dict[str, Any]) -> List[str]:
    """
    Apply custom validation rules beyond JSON schema.
    
    Parameters
    ----------
    profile_data : Dict[str, Any]
        The profile data to validate
        
    Returns
    -------
    List[str]
        List of error messages, empty if valid
    """
    errors = []
    
    # Validate path existence for multiple paths
    pools = profile_data.get("pools", {})
    pool_a = pools.get("A", {})
    pool_b = pools.get("B", {})
    
    # Check Pool A paths
    if "paths" in pool_a:
        for i, path_str in enumerate(pool_a["paths"]):
            path = Path(path_str)
            if not path.exists():
                errors.append(f"Pool A path does not exist: {path_str}")
    
    # Check Pool B paths if present
    if "paths" in pool_b:
        for i, path_str in enumerate(pool_b["paths"]):
            path = Path(path_str)
            if not path.exists():
                errors.append(f"Pool B path does not exist: {path_str}")
    
    # Validate scope-direction compatibility
    scope = profile_data.get("scope", {})
    if scope.get("kind") == "two_pool" and "B" not in pools:
        errors.append("Two-pool scope requires Pool B configuration")
    
    # Validate mode-algorithm compatibility
    mode = profile_data.get("mode")
    criteria = profile_data.get("criteria", {})
    
    if mode == "duplicates" and criteria.get("algorithm") != "blake3":
        errors.append("Duplicates mode requires algorithm 'blake3'")
    
    if mode == "similarity" and criteria.get("algorithm") != "pHash":
        errors.append("Similarity mode requires algorithm 'pHash'")
    
    return errors


def normalize_settings(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize profile data by applying defaults and ensuring consistency.
    
    Parameters
    ----------
    profile_data : Dict[str, Any]
        The profile data to normalize
        
    Returns
    -------
    Dict[str, Any]
        Normalized profile data
    """
    normalized = profile_data.copy()
    
    # Apply defaults from schema
    normalized.setdefault("profile_version", "1.0.0")
    normalized.setdefault("schema_version", "1.0")
    normalized.setdefault("mode", "duplicates")
    
    # Ensure pools exist
    pools = normalized.setdefault("pools", {})
    pool_a = pools.setdefault("A", {})
    
    # Apply pool defaults
    pool_a.setdefault("recurse", True)
    pool_a.setdefault("max_depth", 0)
    pool_a.setdefault("include", ["**/*"])
    pool_a.setdefault("exclude", [])
    pool_a.setdefault("follow_symlinks", False)
    pool_a.setdefault("include_hidden", False)
    pool_a.setdefault("type_filters", [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"])
    
    # Ensure criteria exist
    criteria = normalized.setdefault("criteria", {})
    criteria.setdefault("algorithm", "pHash")
    
    if normalized["mode"] == "similarity":
        criteria.setdefault("degree_ui", 90)
        phash = criteria.setdefault("phash", {})
        phash.setdefault("hash_size", 8)
    
    # Ensure scope exists
    scope = normalized.setdefault("scope", {})
    scope.setdefault("kind", "two_pool")
    
    if scope["kind"] == "two_pool":
        scope.setdefault("direction", "A_TO_B")
        # Ensure Pool B exists with defaults
        pool_b = pools.setdefault("B", {})
        pool_b.setdefault("recurse", True)
        pool_b.setdefault("max_depth", 0)
        pool_b.setdefault("include", ["**/*"])
        pool_b.setdefault("exclude", [])
        pool_b.setdefault("follow_symlinks", False)
        pool_b.setdefault("include_hidden", False)
        pool_b.setdefault("type_filters", [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"])
    
    # Ensure output exists
    output = normalized.setdefault("output", {})
    output.setdefault("mode", "report_only")
    
    return normalized


def create_default_profile(name: str, description: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a new profile with default values.
    
    Parameters
    ----------
    name : str
        Profile name
    description : Optional[str]
        Profile description
        
    Returns
    -------
    Dict[str, Any]
        Default profile data
    """
    from uuid import uuid4
    from datetime import datetime, timezone
    
    profile_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    profile = {
        "id": profile_id,
        "name": name,
        "description": description,
        "profile_version": "1.0.0",
        "schema_version": "1.0",
        "created_at": now,
        "updated_at": now,
        "pools": {
            "A": {
                "paths": [],  # Must be set by user
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
    
    return normalize_settings(profile)


# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

def is_valid_for_save(profile_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Check if profile data is valid for saving (includes path validation).
    
    Parameters
    ----------
    profile_data : Dict[str, Any]
        The profile data to validate
        
    Returns
    -------
    Tuple[bool, List[str]]
        (is_valid, error_messages)
    """
    # First validate schema
    is_valid, errors = validate_settings_schema(profile_data)
    if not is_valid:
        return False, errors
    
    # Additional validation for save operation
    pools = profile_data.get("pools", {})
    pool_a = pools.get("A", {})
    
    # Pool A must have at least one valid path for saving
    if not pool_a.get("paths") or len(pool_a["paths"]) == 0:
        errors.append("Pool A must have at least one path configured")
        return False, errors
    
    # Validate each path in Pool A
    for i, path_str in enumerate(pool_a["paths"]):
        path = Path(path_str)
        if not path.exists():
            errors.append(f"Pool A path does not exist: {path_str}")
            return False, errors
    
    # For two-pool mode, Pool B must also be valid
    if profile_data.get("scope", {}).get("kind") == "two_pool":
        pool_b = pools.get("B", {})
        if not pool_b.get("paths") or len(pool_b["paths"]) == 0:
            errors.append("Pool B must have at least one path configured for two-pool mode")
            return False, errors
        
        # Validate each path in Pool B
        for i, path_str in enumerate(pool_b["paths"]):
            path = Path(path_str)
            if not path.exists():
                errors.append(f"Pool B path does not exist: {path_str}")
                return False, errors
    
    return True, errors


def is_valid_for_run(profile_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Check if profile data is valid for running (stricter than save validation).
    
    Parameters
    ----------
    profile_data : Dict[str, Any]
        The profile data to validate
        
    Returns
    -------
    Tuple[bool, List[str]]
        (is_valid, error_messages)
    """
    return is_valid_for_save(profile_data)  # Same validation for now


__all__ = [
    "SETTINGS_PROFILE_SCHEMA",
    "SettingsValidationError",
    "validate_settings_schema",
    "normalize_settings",
    "create_default_profile",
    "is_valid_for_save",
    "is_valid_for_run"
]