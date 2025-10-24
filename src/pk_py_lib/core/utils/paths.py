"""
Path utilities for pk-py-lib.

This module provides utilities for path manipulation, normalization,
and validation used throughout the library.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Set, Union
import os


def normalize_path(path: Union[str, Path]) -> str:
    """
    Normalize a path to a consistent format.

    Args:
        path: Path to normalize

    Returns:
        Normalized absolute path as string
    """
    try:
        path_obj = Path(path).resolve()
        return str(path_obj)
    except (OSError, ValueError) as e:
        raise ValueError(f"Cannot normalize path {path}: {e}") from e


def remove_contained_paths(paths: List[Union[str, Path]]) -> List[str]:
    """
    Remove paths that are contained within other paths.

    For example, if both "/photos" and "/photos/vacation" are in the list,
    only "/photos" will be kept.

    Args:
        paths: List of paths to filter

    Returns:
        List of paths with contained paths removed
    """
    if not paths:
        return []

    # Normalize all paths
    normalized_paths = [normalize_path(p) for p in paths]

    # Sort by length (shortest first) to check containment properly
    sorted_paths = sorted(normalized_paths, key=len)

    result = []
    for path in sorted_paths:
        # Check if this path is contained in any already selected path
        is_contained = False
        for selected_path in result:
            try:
                Path(path).relative_to(selected_path)
                is_contained = True
                break
            except ValueError:
                # Path is not relative to selected_path, so not contained
                continue

        if not is_contained:
            result.append(path)

    return result


def get_common_prefix(paths: List[Union[str, Path]]) -> str:
    """
    Find the common prefix path for a list of paths.

    Args:
        paths: List of paths to analyze

    Returns:
        Common prefix path, or empty string if no common prefix
    """
    if not paths:
        return ""

    normalized_paths = [Path(p) for p in paths]

    try:
        # Find common prefix
        common = normalized_paths[0]
        for path in normalized_paths[1:]:
            common = Path(os.path.commonpath([common, path]))

        return str(common)
    except ValueError:
        # No common path
        return ""


def is_path_relative_to(child: Union[str, Path], parent: Union[str, Path]) -> bool:
    """
    Check if a path is relative to another path.

    Args:
        child: Potential child path
        parent: Potential parent path

    Returns:
        True if child is relative to parent
    """
    try:
        child_path = Path(child).resolve()
        parent_path = Path(parent).resolve()
        child_path.relative_to(parent_path)
        return True
    except (ValueError, OSError):
        return False


def find_files_by_extension(
    directory: Union[str, Path],
    extensions: List[str],
    recursive: bool = True
) -> List[Path]:
    """
    Find all files with specified extensions in a directory.

    Args:
        directory: Directory to search
        extensions: List of file extensions (e.g., ['.jpg', '.png'])
        recursive: Whether to search subdirectories

    Returns:
        List of matching file paths
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Directory does not exist: {directory}")

    pattern = "**/*" if recursive else "*"
    result = []

    for ext in extensions:
        # Ensure extension starts with dot
        if not ext.startswith('.'):
            ext = '.' + ext

        search_pattern = pattern + ext
        result.extend(directory.glob(search_pattern))

    return sorted(result)


def get_relative_path(path: Union[str, Path], base: Union[str, Path]) -> str:
    """
    Get a path relative to a base path.

    Args:
        path: Path to make relative
        base: Base path for relative calculation

    Returns:
        Relative path as string

    Raises:
        ValueError: If path is not relative to base
    """
    try:
        path_obj = Path(path).resolve()
        base_obj = Path(base).resolve()
        relative = path_obj.relative_to(base_obj)
        return str(relative)
    except ValueError as e:
        raise ValueError(f"Path {path} is not relative to {base}") from e


def ensure_parent_directory(file_path: Union[str, Path]) -> Path:
    """
    Ensure the parent directory of a file path exists.

    Args:
        file_path: File path whose parent directory should exist

    Returns:
        Path object for the file path

    Raises:
        OSError: If directory cannot be created
    """
    path_obj = Path(file_path)
    try:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"Cannot create directory {path_obj.parent}: {e}") from e

    return path_obj


def split_path_into_components(path: Union[str, Path]) -> List[str]:
    """
    Split a path into its component parts.

    Args:
        path: Path to split

    Returns:
        List of path components
    """
    path_obj = Path(path)
    components = []

    # Add each parent component
    for parent in reversed(path_obj.parents):
        if parent != Path('.'):
            components.append(parent.name)

    # Add the final component
    if path_obj.is_file():
        components.append(path_obj.name)
    else:
        components.append(path_obj.name)

    return components


def get_path_depth(path: Union[str, Path]) -> int:
    """
    Get the depth of a path (number of directories from root).

    Args:
        path: Path to analyze

    Returns:
        Depth as integer (0 for root, 1 for direct children, etc.)
    """
    path_obj = Path(path)
    return len(path_obj.parts) - 1


def is_safe_path(path: Union[str, Path], allowed_roots: List[Union[str, Path]]) -> bool:
    """
    Check if a path is safe (doesn't escape allowed roots).

    Args:
        path: Path to check
        allowed_roots: List of allowed root directories

    Returns:
        True if path is within allowed roots
    """
    try:
        normalized_path = Path(path).resolve()
        normalized_roots = [Path(root).resolve() for root in allowed_roots]

        for root in normalized_roots:
            try:
                normalized_path.relative_to(root)
                return True
            except ValueError:
                continue

        return False
    except (OSError, ValueError):
        return False
