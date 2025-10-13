"""
src/pk_py_lib/core/settings_schema.py

JSON Schema and validation for structured settings profiles.

This module defines the canonical JSON Schema for SettingsProfileOptionA
and provides validation functions to ensure settings compatibility.

Also includes SQL schema definitions for v2 unified settings tables.

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
# SQL Schema Definitions for V2 Unified Settings
# -----------------------------------------------------------------------------

# Schema version tracking table
SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
)
"""

# Unified application settings table (v2)
APP_SETTINGS_V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings_v2 (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    cache_enabled BOOLEAN NOT NULL DEFAULT 1,
    cache_size_mb INTEGER NOT NULL DEFAULT 500,
    max_workers INTEGER NOT NULL DEFAULT 4,
    default_profile_id INTEGER,
    gui_theme TEXT NOT NULL DEFAULT 'auto',
    log_level TEXT NOT NULL DEFAULT 'INFO',
    recent_directories TEXT,
    window_geometry TEXT,
    last_updated TEXT,
    FOREIGN KEY (default_profile_id) REFERENCES settings_profiles_v2(id),
    CHECK (cache_size_mb > 0),
    CHECK (max_workers > 0),
    CHECK (gui_theme IN ('light', 'dark', 'auto')),
    CHECK (log_level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
)
"""

# Unified settings profiles table (v2)
SETTINGS_PROFILES_V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings_profiles_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    hash_algorithm TEXT NOT NULL DEFAULT 'phash',
    hash_size INTEGER NOT NULL DEFAULT 8,
    similarity_threshold REAL NOT NULL DEFAULT 0.95,
    min_resolution INTEGER,
    max_resolution INTEGER,
    color_mode BOOLEAN NOT NULL DEFAULT 0,
    clustering_method TEXT NOT NULL DEFAULT 'dbscan',
    quality_threshold REAL,
    is_default BOOLEAN NOT NULL DEFAULT 0,
    is_system BOOLEAN NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (similarity_threshold >= 0.0 AND similarity_threshold <= 1.0),
    CHECK (hash_algorithm IN ('phash', 'whash', 'blake3', 'xxh3')),
    CHECK (clustering_method IN ('dbscan', 'agglomerative')),
    CHECK (hash_size > 0)
)
"""

# Create index for profile name lookups
SETTINGS_PROFILES_V2_INDEX = """
CREATE INDEX IF NOT EXISTS idx_profiles_v2_name
ON settings_profiles_v2(name COLLATE NOCASE)
"""

# Create index for default profile lookups
SETTINGS_PROFILES_V2_DEFAULT_INDEX = """
CREATE INDEX IF NOT EXISTS idx_profiles_v2_default
ON settings_profiles_v2(is_default) WHERE is_default = 1
"""


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

        "similarity": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "phash_threshold": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 64,
                    "default": 10,
                    "description": "Hamming distance threshold for pHash similarity (0=exact match, 64=maximum difference for 8x8 hash). Lower values are stricter. Default 10 (~84% similarity for 8x8 hash). Used in find_similar_phash; groups form transitively where all pairs ≤ threshold."
                },
                "whash_threshold": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 64,
                    "default": 12,
                    "description": "Hamming distance threshold for wHash similarity (0=exact, 64=maximum for 8x8). wHash uses wavelet transform (db1 default), robust to structural changes (e.g., cropping, rotation) vs. pHash's DCT focus on frequency. Default 12 (~81% similarity). Falls back to pHash if wHash fails (e.g., unsupported format). Example: Use 8 for stricter wavelet matching."
                },
                "enabled_algorithms": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["phash", "whash"]},
                    "default": ["phash"],
                    "description": "List of enabled perceptual hashing algorithms for similarity detection. Supports 'phash' (DCT-based, default) and 'whash' (wavelet-based via imagehash.whash with 8x8 resize and db1 wavelet). 'whash' is robust to structural changes like cropping or rotation but may be slower; falls back to 'phash' if computation fails. Defaults to ['phash']. Example: ['phash', 'whash'] for multi-algorithm support."
                },
                "max_distance": {"type": "integer", "minimum": 0, "maximum": 64, "default": 15},
                "lsh_num_perm": {
                    "type": "integer",
                    "minimum": 64,
                    "maximum": 1024,
                    "default": 128,
                    "description": "Number of hash permutations in MinHash sketches for LSH (Locality-Sensitive Hashing). Higher values improve accuracy (fewer false negatives) but increase build/query time and memory. Used when n > 1000 images for scalable similarity detection. Default 128 provides good balance; 256 for higher precision."
                },
                "lsh_threshold": {
                    "type": ["number", "null"],
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": None,
                    "description": "Override for LSH similarity threshold (0.0-1.0). If null, defaults to 1 - (threshold / 64.0) based on Hamming threshold (e.g., for threshold=10, ~0.844). Lower values retrieve more candidates (safer but slower). Used for large-scale similarity detection with MinHashLSH."
                },
                "clustering_algorithm": {
                    "type": "string",
                    "enum": ["unionfind", "hdbscan"],
                    "default": "hdbscan",
                    "description": "Clustering algorithm for similarity grouping. 'unionfind' uses traditional Union-Find with transitive chaining (O(n²) brute-force, may produce false positives). 'hdbscan' uses Hierarchical Density-Based Spatial Clustering with noise detection (O(n log n), better scalability, reduces false positives via density-based clustering). Default 'hdbscan' for improved accuracy and performance."
                },
                "hdbscan_min_cluster_size": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 1000,
                    "default": 2,
                    "description": "HDBSCAN minimum cluster size parameter. Minimum number of points required to form a cluster. Smaller values (e.g., 2) allow smaller clusters but may increase noise sensitivity. Larger values (e.g., 5-10) require denser clusters but reduce false positives. Used only when clustering_algorithm='hdbscan'."
                },
                "hdbscan_min_samples": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "maximum": 100,
                    "default": None,
                    "description": "HDBSCAN minimum samples parameter. Number of neighboring points required for core point classification. If None, automatically determined based on data density. Smaller values increase cluster formation sensitivity but may create more small clusters. Larger values require denser regions. Used only when clustering_algorithm='hdbscan'."
                },
                "hdbscan_cluster_selection_epsilon": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.0,
                    "description": "HDBSCAN cluster selection epsilon parameter. Distance threshold for cluster selection method. Value of 0.0 uses 'eom' (excess of mass) method, >0.0 uses 'leaf' method with epsilon threshold. Higher values create larger, more inclusive clusters. Used only when clustering_algorithm='hdbscan'."
                },
                "hdbscan_adaptive_tuning": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable adaptive parameter tuning for HDBSCAN. When true, automatically adjusts min_samples and cluster_selection_epsilon based on distance distribution statistics (e.g., 5th-95th percentile of pairwise distances). When false, uses explicit parameter values. Recommended true for automatic optimization. Used only when clustering_algorithm='hdbscan'."
                }
            }
        },

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
                "algorithm": {"type": "string", "enum": ["blake3", "phash", "xxh3", "whash"], "default": "phash"},
                "degree_ui": {"type": "integer", "minimum": 0, "maximum": 100, "default": 90},
                "phash": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "hash_size": {"type": "integer", "minimum": 4, "maximum": 64, "default": 8}
                    }
                },
                "similarity_hash_algorithm": {
                    "type": "string",
                    "enum": ["phash", "whash"],
                    "default": "phash",
                    "description": "The hash algorithm to use for similarity comparisons: 'phash' (DCT-based) or 'whash' (wavelet-based)."
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
                    "enum": ["duplicates", "non_duplicates"],
                    "default": "duplicates",
                    "description": "Two-pool comparison: 'duplicates' lists B items that duplicate A; 'non_duplicates' lists B items not found in A."
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
        },
        "image_quality_evaluator": {
            "type": "string",
            "default": "brisque",
            "enum": ["none", "brisque"],
            "description": "The active image quality evaluator to use. Options: 'none' (disables quality evaluation), 'brisque' (BRISQUE-based scoring). Scores are normalized such that higher floats indicate higher quality when enabled."
        },
        "use_flat_cache": {
            "type": "boolean",
            "default": True,
            "description": "Enable flat SQLite cache for hashes and quality metrics (stored per file path/stats)."
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
                            "algorithm": {"enum": ["blake3", "xxh3"]},
                            "degree_ui": {"not": {}},
                            "phash": {"not": {}},
                            "similarity_hash_algorithm": {"not": {}}
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
                            "algorithm": {"enum": ["phash", "whash"]},
                            "degree_ui": {"type": "integer", "minimum": 0, "maximum": 100},
                            "similarity_hash_algorithm": {"type": "string", "enum": ["phash", "whash"], "default": "phash"}
                        },
                        "required": ["degree_ui", "similarity_hash_algorithm"]
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

    # Backward-compat: migrate legacy direction tokens before schema validation
    # to support previously saved profiles. We avoid mutating the caller payload.
    to_validate = dict(profile_data or {})
    try:
        scope_in = dict((to_validate.get("scope") or {}))
        if scope_in.get("kind") == "two_pool":
            d = scope_in.get("direction")
            if d in ("A_TO_B", "B_TO_A"):
                scope_in["direction"] = "duplicates"
            elif d in ("A_WITHOUT_IN_B", "B_WITHOUT_IN_A"):
                scope_in["direction"] = "non_duplicates"
            # do not auto-insert direction when absent; schema requires it explicitly
            to_validate["scope"] = scope_in
    except Exception:
        # If anything goes wrong, fall back to original object
        to_validate = profile_data

    try:
        validate(instance=to_validate, schema=SETTINGS_PROFILE_SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message}")
        return False, errors

    # Additional custom validation beyond JSON schema
    custom_errors = _validate_custom_rules(to_validate)
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

    if mode == "duplicates" and criteria.get("algorithm") not in ["blake3", "xxh3"]:
        errors.append("Duplicates mode requires algorithm 'blake3' or 'xxh3'")

    if mode == "similarity" and criteria.get("similarity_hash_algorithm") not in ["phash", "whash"]:
        errors.append("Similarity mode requires algorithm 'phash' or 'whash'")

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

    # Ensure criteria exist
    criteria = normalized.setdefault("criteria", {})
    # For duplicates mode, default to xxh3; for similarity, derive from explicit selection, enabled list, or safe default
    if normalized["mode"] == "duplicates":
        criteria.setdefault("algorithm", "xxh3")
    else:
        similarity_section = normalized.setdefault("similarity", {})
        enabled_algorithms = similarity_section.get("enabled_algorithms")
        sim_hash: str
        if "similarity_hash_algorithm" in criteria and criteria["similarity_hash_algorithm"] in ("phash", "whash"):
            sim_hash = criteria["similarity_hash_algorithm"]
        elif isinstance(enabled_algorithms, list) and enabled_algorithms:
            candidate = enabled_algorithms[0]
            sim_hash = candidate if candidate in ("phash", "whash") else "phash"
        elif "algorithm" in criteria and criteria["algorithm"] in ("phash", "whash"):
            sim_hash = criteria["algorithm"]
        else:
            sim_hash = "phash"
        criteria["similarity_hash_algorithm"] = sim_hash
        criteria["algorithm"] = sim_hash
        logger.info(
            "normalize_settings: mode=%s, resolved similarity_hash_algorithm=%s, algorithm=%s",
            normalized["mode"],
            sim_hash,
            criteria["algorithm"],
        )

    if normalized["mode"] == "similarity":
        criteria.setdefault("degree_ui", 90)
        phash = criteria.setdefault("phash", {})
        phash.setdefault("hash_size", 8)

    # Ensure similarity section
    similarity = normalized.setdefault("similarity", {})
    similarity.setdefault("phash_threshold", 10)
    similarity.setdefault("whash_threshold", 12)

    if normalized["mode"] == "similarity":
        similarity_hash_algorithm = criteria.get("similarity_hash_algorithm")
        if similarity_hash_algorithm in ("phash", "whash"):
            similarity["enabled_algorithms"] = [similarity_hash_algorithm]
            logger.info(
                "normalize_settings: aligned similarity.enabled_algorithms with [%s]",
                similarity_hash_algorithm,
            )
        else:
            similarity["enabled_algorithms"] = ["phash"]
            logger.warning(
                "normalize_settings: missing/invalid similarity_hash_algorithm, defaulting enabled_algorithms to ['phash']",
            )
    else:
        similarity["enabled_algorithms"] = ["phash"]

    similarity.setdefault("max_distance", 15)

    # Set LSH defaults for scalability
    similarity.setdefault("lsh_num_perm", 128)
    # lsh_threshold defaults to null to use auto-calculation based on Hamming threshold
    similarity.setdefault("lsh_threshold", None)

    # Set HDBSCAN defaults
    similarity.setdefault("clustering_algorithm", "hdbscan")
    similarity.setdefault("hdbscan_min_cluster_size", 2)
    similarity.setdefault("hdbscan_min_samples", None)
    similarity.setdefault("hdbscan_cluster_selection_epsilon", 0.0)
    similarity.setdefault("hdbscan_adaptive_tuning", True)

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

    # Ensure scope exists
    scope = normalized.setdefault("scope", {})
    scope.setdefault("kind", "two_pool")

    if scope["kind"] == "two_pool":
        # Migrate legacy direction tokens to the simplified choices
        dir_token = scope.get("direction")
        if dir_token in ("A_TO_B", "B_TO_A"):
            scope["direction"] = "duplicates"
        elif dir_token in ("A_WITHOUT_IN_B", "B_WITHOUT_IN_A"):
            scope["direction"] = "non_duplicates"
        # Apply default for new schema
        scope.setdefault("direction", "duplicates")
        # Ensure Pool B exists with defaults
        pool_b = pools.setdefault("B", {})
        pool_b.setdefault("recurse", True)
        pool_b.setdefault("max_depth", 0)
        pool_b.setdefault("include", ["**/*"])
        pool_b.setdefault("exclude", [])
        pool_b.setdefault("follow_symlinks", True)
        pool_b.setdefault("include_hidden", True)
        pool_b.setdefault("type_filters", [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"])

    # Ensure output exists
    output = normalized.setdefault("output", {})
    output.setdefault("mode", "report_only")
    normalized.setdefault("image_quality_evaluator", "brisque")
    normalized.setdefault("use_flat_cache", True)

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
        "similarity": {
            "phash_threshold": 10,
            "whash_threshold": 12,
            "enabled_algorithms": ["phash"],
            "max_distance": 15,
            "lsh_num_perm": 128,
            "lsh_threshold": None,
            "clustering_algorithm": "hdbscan",
            "hdbscan_min_cluster_size": 2,
            "hdbscan_min_samples": None,
            "hdbscan_cluster_selection_epsilon": 0.0,
            "hdbscan_adaptive_tuning": True
        },
        "pools": {
            "A": {
                "paths": [str(Path.home())],  # Default to user's home directory
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
            "algorithm": "xxh3"
        },
        "scope": {
            "kind": "single_pool"
        },
        "output": {
            "mode": "report_only"
        },
        "image_quality_evaluator": "brisque",
        "use_flat_cache": True
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
    # JSON Schema
    "SETTINGS_PROFILE_SCHEMA",
    "SettingsValidationError",
    "validate_settings_schema",
    "normalize_settings",
    "create_default_profile",
    "is_valid_for_save",
    "is_valid_for_run",
    # SQL Schema v2
    "SCHEMA_VERSION_TABLE",
    "APP_SETTINGS_V2_SCHEMA",
    "SETTINGS_PROFILES_V2_SCHEMA",
    "SETTINGS_PROFILES_V2_INDEX",
    "SETTINGS_PROFILES_V2_DEFAULT_INDEX",
]
