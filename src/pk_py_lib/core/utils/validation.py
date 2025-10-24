"""
Validation utilities for pk-py-lib.

This module provides validation functions and utilities used throughout
the library for ensuring data integrity and correctness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import re
import os


class ValidationError(Exception):
    """Base exception for validation errors."""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)


def validate_path(
    path: Union[str, Path],
    must_exist: bool = True,
    must_be_readable: bool = True
) -> Path:
    """
    Validate a file or directory path.

    Args:
        path: Path to validate
        must_exist: Whether the path must exist
        must_be_readable: Whether the path must be readable

    Returns:
        Validated Path object

    Raises:
        ValidationError: If path is invalid or doesn't meet requirements
    """
    try:
        path_obj = Path(path).resolve()
    except (OSError, ValueError) as e:
        raise ValidationError(f"Invalid path: {path}", field="path", value=path) from e

    if must_exist and not path_obj.exists():
        raise ValidationError(
            f"Path does not exist: {path_obj}",
            field="path",
            value=str(path_obj)
        )

    if must_be_readable and path_obj.exists():
        try:
            # Check readability
            if path_obj.is_file():
                with open(path_obj, 'rb') as f:
                    f.read(1)  # Try to read at least one byte
            elif path_obj.is_dir():
                # For directories, check if we can list contents
                next(os.scandir(path_obj), None)
        except (OSError, PermissionError) as e:
            raise ValidationError(
                f"Path is not readable: {path_obj}",
                field="path",
                value=str(path_obj)
            ) from e

    return path_obj


def validate_image_extension(path: Union[str, Path]) -> bool:
    """
    Validate that a path has a supported image extension.

    Args:
        path: Path to check

    Returns:
        True if extension is supported, False otherwise
    """
    supported_extensions = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp',
        '.tiff', '.tif', '.webp', '.heic', '.heif'
    }

    path_obj = Path(path)
    extension = path_obj.suffix.lower()

    return extension in supported_extensions


def validate_hash_algorithm(algorithm: str) -> str:
    """
    Validate hash algorithm name.

    Args:
        algorithm: Algorithm name to validate

    Returns:
        Normalized algorithm name

    Raises:
        ValidationError: If algorithm is not supported
    """
    supported_algorithms = {
        'phash', 'whash', 'xxh3', 'blake3'
    }

    normalized = algorithm.lower()
    if normalized not in supported_algorithms:
        raise ValidationError(
            f"Unsupported hash algorithm: {algorithm}. "
            f"Supported: {', '.join(sorted(supported_algorithms))}",
            field="algorithm",
            value=algorithm
        )

    return normalized


def validate_similarity_threshold(threshold: float) -> float:
    """
    Validate similarity threshold value.

    Args:
        threshold: Threshold value to validate (internal 0.0-1.0 range)

    Returns:
        Validated threshold value

    Raises:
        ValidationError: If threshold is out of range
    """
    if not isinstance(threshold, (int, float)):
        raise ValidationError(
            f"Threshold must be a number, got {type(threshold)}",
            field="threshold",
            value=threshold
        )

    if not 0.0 <= threshold <= 1.0:
        raise ValidationError(
            f"Threshold must be between 0.0 and 1.0, got {threshold}",
            field="threshold",
            value=threshold
        )

    return float(threshold)


def validate_ui_threshold(threshold: int) -> int:
    """
    Validate UI threshold value (0-100 range).

    Args:
        threshold: UI threshold value to validate

    Returns:
        Validated threshold value

    Raises:
        ValidationError: If threshold is out of range
    """
    if not isinstance(threshold, int):
        raise ValidationError(
            f"UI threshold must be an integer, got {type(threshold)}",
            field="threshold_ui",
            value=threshold
        )

    if not 0 <= threshold <= 100:
        raise ValidationError(
            f"UI threshold must be between 0 and 100, got {threshold}",
            field="threshold_ui",
            value=threshold
        )

    return threshold


def validate_profile_name(name: str) -> str:
    """
    Validate profile name according to canonical rules.

    Args:
        name: Profile name to validate

    Returns:
        Validated and normalized name

    Raises:
        ValidationError: If name is invalid
    """
    if not isinstance(name, str):
        raise ValidationError(
            f"Profile name must be a string, got {type(name)}",
            field="name",
            value=name
        )

    if not name.strip():
        raise ValidationError(
            "Profile name cannot be empty",
            field="name",
            value=name
        )

    # Length check
    if len(name) < 1 or len(name) > 64:
        raise ValidationError(
            f"Profile name must be 1-64 characters, got {len(name)}",
            field="name",
            value=name
        )

    # Character validation
    valid_pattern = re.compile(r'^[A-Za-z0-9 _-]+$')
    if not valid_pattern.match(name):
        raise ValidationError(
            "Profile name can only contain letters, numbers, spaces, underscores, and hyphens",
            field="name",
            value=name
        )

    return name.strip()


def validate_glob_pattern(pattern: str) -> str:
    """
    Validate glob pattern syntax.

    Args:
        pattern: Glob pattern to validate

    Returns:
        Validated pattern

    Raises:
        ValidationError: If pattern has syntax errors
    """
    import glob

    if not isinstance(pattern, str):
        raise ValidationError(
            f"Pattern must be a string, got {type(pattern)}",
            field="pattern",
            value=pattern
        )

    if not pattern:
        raise ValidationError(
            "Pattern cannot be empty",
            field="pattern",
            value=pattern
        )

    # Try to compile the pattern
    try:
        # Use glob.translate to check for syntax errors
        glob.translate(pattern)
    except Exception as e:
        raise ValidationError(
            f"Invalid glob pattern: {pattern}",
            field="pattern",
            value=pattern
        ) from e

    return pattern


def validate_file_size(size: int, max_size: Optional[int] = None) -> int:
    """
    Validate file size.

    Args:
        size: File size in bytes
        max_size: Optional maximum allowed size

    Returns:
        Validated file size

    Raises:
        ValidationError: If size is invalid
    """
    if not isinstance(size, int):
        raise ValidationError(
            f"File size must be an integer, got {type(size)}",
            field="size",
            value=size
        )

    if size < 0:
        raise ValidationError(
            f"File size cannot be negative, got {size}",
            field="size",
            value=size
        )

    if max_size is not None and size > max_size:
        raise ValidationError(
            f"File size {size} exceeds maximum allowed size {max_size}",
            field="size",
            value=size
        )

    return size


def validate_image_dimensions(
    width: int,
    height: int,
    min_dimension: int = 1,
    max_dimension: int = 50000
) -> tuple[int, int]:
    """
    Validate image dimensions.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        min_dimension: Minimum allowed dimension
        max_dimension: Maximum allowed dimension

    Returns:
        Tuple of (width, height)

    Raises:
        ValidationError: If dimensions are invalid
    """
    for name, value in [("width", width), ("height", height)]:
        if not isinstance(value, int):
            raise ValidationError(
                f"Image {name} must be an integer, got {type(value)}",
                field=name,
                value=value
            )

        if not min_dimension <= value <= max_dimension:
            raise ValidationError(
                f"Image {name} must be between {min_dimension} and {max_dimension}, got {value}",
                field=name,
                value=value
            )

    return width, height


def validate_settings_schema(
    settings: Dict[str, Any],
    schema: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate settings against a JSON schema.

    Args:
        settings: Settings dictionary to validate
        schema: JSON schema to validate against

    Returns:
        Validated settings

    Raises:
        ValidationError: If settings don't match schema
    """
    import jsonschema

    try:
        jsonschema.validate(instance=settings, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(
            f"Settings validation failed: {e.message}",
            field=e.absolute_path[0] if e.absolute_path else None,
            value=e.instance
        ) from e

    return settings
