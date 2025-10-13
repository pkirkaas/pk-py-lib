"""
Directory Traversal Module

Efficient directory traversal with advanced filtering capabilities,
duplicate detection, and directory statistics.
"""

import os
import traceback
from pathlib import Path
from typing import Iterator, Optional, List, Dict, Any, Pattern, Set, Union, Callable
import fnmatch
import re
from collections import defaultdict, Counter
from dataclasses import dataclass

from ..logging import get_logger
from ..image import similarity
from ..flat_cache import FlatCacheManager # Import FlatCacheManager
import hashlib

# Logger instance 'log = get_logger(__name__)' is used for consistent logging throughout the module
log = get_logger(__name__)

# Image file extensions for similarity hash computation
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heif', '.heic'}


@dataclass
class FileInfo:
    """Information about a discovered file."""
    path: Path
    size: int
    modified_time: float
    is_symlink: bool
    extension: str

    @classmethod
    def from_path(cls, path: Path) -> 'FileInfo':
        """Create FileInfo from a path."""
        try:
            stat = path.stat()
            return cls(
                path=path,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                is_symlink=path.is_symlink(),
                extension=path.suffix.lower()
            )
        except OSError:
            # Handle broken symlinks or permission issues
            return cls(
                path=path,
                size=0,
                modified_time=0,
                is_symlink=path.is_symlink(),
                extension=path.suffix.lower() if hasattr(path, 'suffix') else ''
            )


class DirectoryTraversal:
    """
    Efficient directory traversal with advanced filtering.

    Provides powerful file discovery with pattern matching,
    size filtering, and smart exclusions.
    """

    @staticmethod
    def walk_files(
        roots: Union[Path, List[Path]],
        patterns: Optional[List[str]] = None,  # e.g., ["*.jpg", "*.png"]
        exclude_patterns: Optional[List[str]] = None,  # e.g., ["*.tmp", ".*"]
        follow_symlinks: bool = False,
        max_depth: Optional[int] = None,
        min_size: int = 0,
        max_size: Optional[int] = None,
        include_hidden: bool = False
    ) -> Iterator[Path]:
        """
        Walk directory tree(s) with advanced filtering.

        Args:
            roots: Single root directory or list of root directories to traverse
            patterns: Include patterns (glob-style)
            exclude_patterns: Exclude patterns (glob-style)
            follow_symlinks: Whether to follow symbolic links
            max_depth: Maximum recursion depth (None for unlimited)
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes (None for unlimited)
            include_hidden: Whether to include hidden files

        Yields:
            Path objects for matching files

        Example:
            >>> # Single root
            >>> for image in DirectoryTraversal.walk_files(
            ...     Path("/photos"),
            ...     patterns=["*.jpg", "*.png"],
            ...     exclude_patterns=["*thumbnail*", ".*"],
            ...     max_depth=3
            ... ):
            ...     print(image)

            >>> # Multiple roots
            >>> for image in DirectoryTraversal.walk_files(
            ...     [Path("/photos"), Path("/backup/photos")],
            ...     patterns=["*.jpg", "*.png"]
            ... ):
            ...     print(image)
        """
        # Normalize to list of paths
        if isinstance(roots, Path):
            roots = [roots]
        elif not isinstance(roots, list):
            raise TypeError("roots must be a Path or list of Path objects")

        # Compile patterns for efficiency (for single file case)
        include_compiled = None
        if patterns:
            include_compiled = [re.compile(fnmatch.translate(p)) for p in patterns]

        exclude_compiled = None
        if exclude_patterns:
            exclude_compiled = [re.compile(fnmatch.translate(p)) for p in exclude_patterns]

        for root in roots:
            if not root.exists():
                log.warning(f"Root path does not exist: {root}")
                continue

            if root.is_file():
                # Handle single file
                if DirectoryTraversal._should_include_file_compiled(
                    root, include_compiled, exclude_compiled, min_size, max_size, include_hidden
                ):
                    yield root
            elif root.is_dir():
                yield from DirectoryTraversal._walk_recursive(
                    root,
                    patterns,
                    exclude_patterns,
                    follow_symlinks,
                    max_depth,
                    min_size,
                    max_size,
                    include_hidden
                )
            else:
                log.warning(f"Root path is not a file or directory: {root}")

    @staticmethod
    def _should_include_file_compiled(
        file_path: Path,
        include_compiled: Optional[List[Pattern]],
        exclude_compiled: Optional[List[Pattern]],
        min_size: int,
        max_size: Optional[int],
        include_hidden: bool
    ) -> bool:
        """
        Determine if a file should be included based on compiled include/exclude patterns,
        size constraints, and hidden-file policy.

        This helper centralizes single-file checks for both single-root-file cases and
        recursive traversal yields.

        Args:
            file_path: Candidate file path
            include_compiled: List of compiled regex patterns to include (matches on file name)
            exclude_compiled: List of compiled regex patterns to exclude (matches on file name)
            min_size: Minimum file size in bytes (inclusive)
            max_size: Maximum file size in bytes (inclusive when provided)
            include_hidden: Whether dot-prefixed names are allowed

        Returns:
            True when the file should be included.
        """
        try:
            name = file_path.name
            if not include_hidden and name.startswith('.'):
                return False

            if include_compiled:
                if not any(p.match(name) for p in include_compiled):
                    return False

            if exclude_compiled:
                if any(p.match(name) for p in exclude_compiled):
                    return False

            try:
                fsize = file_path.stat().st_size
            except OSError:
                return False

            if fsize < min_size:
                return False
            if max_size is not None and fsize > max_size:
                return False

            return True
        except Exception:
            # Be conservative on unexpected errors: exclude the file
            return False

    @staticmethod
    def _walk_recursive(
        root: Path,
        patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        follow_symlinks: bool = False,
        max_depth: Optional[int] = None,
        min_size: int = 0,
        max_size: Optional[int] = None,
        include_hidden: bool = False
    ) -> Iterator[Path]:
        """Internal recursive walking function with circular reference protection."""
        # Compile patterns for efficiency
        include_compiled = None
        if patterns:
            include_compiled = [re.compile(fnmatch.translate(p)) for p in patterns]

        exclude_compiled = None
        if exclude_patterns:
            exclude_compiled = [re.compile(fnmatch.translate(p)) for p in exclude_patterns]

        def should_include_file(file_path: Path) -> bool:
            """Check if file matches inclusion criteria."""
            # Check hidden files
            if not include_hidden and file_path.name.startswith('.'):
                return False

            # Check include patterns
            if include_compiled:
                if not any(pattern.match(file_path.name) for pattern in include_compiled):
                    return False

            # Check exclude patterns
            if exclude_compiled:
                if any(pattern.match(file_path.name) for pattern in exclude_compiled):
                    return False

            # Check file size
            try:
                file_size = file_path.stat().st_size
                if file_size < min_size:
                    return False
                if max_size is not None and file_size > max_size:
                    return False
            except OSError:
                # File might be a broken symlink
                return False

            return True

        def walk_recursive_internal(current_path: Path, current_depth: int = 0, visited: Optional[Set[Path]] = None):
            """Recursive walking function with circular reference detection."""
            if visited is None:
                visited = set()

            if max_depth is not None and current_depth >= max_depth:
                return

            try:
                # Resolve the current path to handle symlinks properly
                try:
                    resolved_path = current_path.resolve()
                except OSError:
                    # If we can't resolve, use the original path
                    resolved_path = current_path

                # Check for circular reference
                if resolved_path in visited:
                    # Capture full call stack details for debugging circular references
                    call_stack = traceback.format_stack()
                    call_stack_details = []

                    # Parse the call stack to extract file names, function names, line numbers, and calling context
                    for frame_info in call_stack[:-1]:  # Exclude current frame
                        # Extract file path, line number, function name from frame info
                        lines = frame_info.strip().split('\n')
                        if lines:
                            # First line contains file path, line number, and function name
                            first_line = lines[0]
                            # Format: '  File "filepath", line lineno, in function_name'
                            parts = first_line.split(',')
                            if len(parts) >= 2:
                                file_part = parts[0].strip()
                                line_part = parts[1].strip()

                                # Extract filename from file path
                                file_path = file_part.replace('File "', '').replace('"', '')
                                filename = os.path.basename(file_path) if file_path else 'unknown'

                                # Extract line number
                                line_number = line_part.replace('line ', '') if line_part.startswith('line ') else 'unknown'

                                # Extract function name from the third part if available
                                function_name = 'unknown'
                                if len(parts) >= 3:
                                    func_part = parts[2].strip()
                                    if 'in ' in func_part:
                                        function_name = func_part.replace('in ', '')

                                # Extract calling context (code snippet if available)
                                calling_context = ''
                                if len(lines) > 1:
                                    # Get the next few lines that contain the actual code
                                    for line in lines[1:]:
                                        line = line.strip()
                                        if line and not line.startswith('File "'):
                                            calling_context = line
                                            break

                                call_stack_details.append({
                                    'filename': filename,
                                    'file_path': file_path,
                                    'line_number': line_number,
                                    'function_name': function_name,
                                    'calling_context': calling_context
                                })

                    # Format the detailed call stack information for logging
                    stack_summary = []
                    for detail in call_stack_details[-5:]:  # Show last 5 frames to avoid too much output
                        stack_summary.append(
                            f"  {detail['filename']}:{detail['line_number']} in {detail['function_name']}()"
                        )
                        if detail['calling_context']:
                            # Truncate long context lines
                            context = detail['calling_context'][:60] + '...' if len(detail['calling_context']) > 60 else detail['calling_context']
                            stack_summary.append(f"    Context: {context}")

                    stack_info = '\n'.join(stack_summary)

                    log.warning(
                        f"Circular reference detected, skipping: {current_path}\n"
                        f"Call stack trace (last 5 frames):\n{stack_info}\n"
                        f"Full call stack available in debug logs"
                    )

                    # Also log the full traceback at debug level for complete analysis
                    full_traceback = ''.join(call_stack)
                    log.debug(
                        f"Complete call stack for circular reference at {current_path}:\n"
                        f"Visited paths count: {len(visited)}\n"
                        f"Resolved path: {resolved_path}\n"
                        f"Full traceback:\n{full_traceback}"
                    )
                    return

                # Add current directory to visited set
                visited.add(resolved_path)

                for item in current_path.iterdir():
                    # Skip broken symlinks
                    if item.is_symlink() and not follow_symlinks:
                        if not item.exists():
                            continue

                    if item.is_file():
                        if DirectoryTraversal._should_include_file_compiled(
                            item, include_compiled, exclude_compiled, min_size, max_size, include_hidden
                        ):
                            yield item

                    elif item.is_dir():
                        # Check if we should traverse this directory
                        if not include_hidden and item.name.startswith('.'):
                            continue

                        # Skip if directory matches exclude patterns
                        if exclude_compiled:
                            if any(pattern.match(item.name) for pattern in exclude_compiled):
                                continue

                        # Recurse into subdirectory with updated visited set
                        yield from walk_recursive_internal(item, current_depth + 1, visited.copy())

            except PermissionError:
                log.warning(f"Permission denied accessing: {current_path}")
            except OSError as e:
                log.warning(f"Error accessing {current_path}: {e}")

        yield from walk_recursive_internal(root)

    @staticmethod
    def find_duplicate_filenames(
        roots: List[Path],
        case_sensitive: bool = True,
        include_size: bool = True
    ) -> Dict[str, List[Path]]:
        """
        Find files with duplicate names across multiple directories.

        Args:
            roots: List of root directories to search
            case_sensitive: Whether filename comparison is case-sensitive
            include_size: Whether to consider file size in duplicate detection

        Returns:
            Dictionary mapping filenames to lists of paths with that name

        Example:
            >>> duplicates = DirectoryTraversal.find_duplicate_filenames([
            ...     Path("/photos/2023"),
            ...     Path("/backup/photos")
            ... ])
            >>> for filename, paths in duplicates.items():
            ...     if len(paths) > 1:
            ...         print(f"Duplicate: {filename} found in {len(paths)} locations")
        """
        filename_map = defaultdict(list)

        for file_path in DirectoryTraversal.walk_files(roots):
            # Get filename key
            filename = file_path.name
            if not case_sensitive:
                filename = filename.lower()

            # Add size to key if requested
            key = filename
            if include_size:
                try:
                    size = file_path.stat().st_size
                    key = f"{filename}_{size}"
                except OSError:
                    continue

            filename_map[key].append(file_path)

        # Return only entries with duplicates
        return {k: v for k, v in filename_map.items() if len(v) > 1}

    @staticmethod
    def calculate_directory_stats(root: Path, include_subdirs: bool = True) -> Dict[str, Any]:
        """
        Calculate comprehensive statistics for a directory tree.

        Args:
            root: Root directory to analyze
            include_subdirs: Whether to include per-subdirectory stats

        Returns:
            Dictionary with comprehensive directory statistics

        Example:
            >>> stats = DirectoryTraversal.calculate_directory_stats(Path("/photos"))
            >>> print(f"Total size: {stats['total_size_mb']:.1f} MB")
            >>> print(f"File count: {stats['file_count']}")
        """
        if not root.exists() or not root.is_dir():
            return {"error": f"Invalid directory: {root}"}

        stats = {
            "directory": str(root),
            "total_size": 0,
            "total_size_mb": 0,
            "total_size_gb": 0,
            "file_count": 0,
            "dir_count": 0,
            "file_types": Counter(),
            "size_distribution": {
                "tiny": 0,      # < 1KB
                "small": 0,     # 1KB - 1MB
                "medium": 0,    # 1MB - 100MB
                "large": 0,     # 100 MB – 1024 MB (≈1 GB)
                "huge": 0       # > 1024 MB (≈1 GB)
            },
            "largest_files": [],
            "oldest_file": None,
            "newest_file": None,
            "subdirectories": {} if include_subdirs else None
        }

        oldest_time = float('inf')
        newest_time = 0
        largest_files = []  # Will keep top 10

        try:
            for item in DirectoryTraversal.walk_files(root):
                try:
                    file_info = FileInfo.from_path(item)

                    # Update totals
                    stats["file_count"] += 1
                    stats["total_size"] += file_info.size

                    # Update file types
                    stats["file_types"][file_info.extension] += 1

                    # Update size distribution
                    size_mb = file_info.size / (1024 * 1024)
                    if file_info.size < 1024:
                        stats["size_distribution"]["tiny"] += 1
                    elif size_mb < 1:
                        stats["size_distribution"]["small"] += 1
                    elif size_mb < 100:
                        stats["size_distribution"]["medium"] += 1
                    elif size_mb < 1024:
                        stats["size_distribution"]["large"] += 1
                    else:
                        stats["size_distribution"]["huge"] += 1

                    # Track largest files
                    largest_files.append((file_info.size, item))
                    largest_files.sort(reverse=True)
                    largest_files = largest_files[:10]  # Keep top 10

                    # Track oldest/newest
                    if file_info.modified_time < oldest_time:
                        oldest_time = file_info.modified_time
                        stats["oldest_file"] = str(item)

                    if file_info.modified_time > newest_time:
                        newest_time = file_info.modified_time
                        stats["newest_file"] = str(item)

                except OSError:
                    continue

            # Count directories
            for item in root.rglob('*'):
                if item.is_dir():
                    stats["dir_count"] += 1

            # Finalize stats
            stats["total_size_mb"] = stats["total_size"] / (1024 * 1024)
            stats["total_size_gb"] = stats["total_size_mb"] / 1024
            stats["largest_files"] = [
                {"path": str(path), "size": size, "size_mb": size / (1024 * 1024)}
                for size, path in largest_files
            ]

            # Calculate subdirectory stats if requested
            if include_subdirs:
                for subdir in root.iterdir():
                    if subdir.is_dir():
                        subdir_stats = DirectoryTraversal.calculate_directory_stats(
                            subdir, include_subdirs=False
                        )
                        stats["subdirectories"][subdir.name] = subdir_stats

        except Exception as e:
            stats["error"] = str(e)
            log.error(f"Error calculating directory stats for {root}", exception=e)

        return stats

    @staticmethod
    def find_empty_directories(root: Path) -> List[Path]:
        """
        Find all empty directories in a tree.

        Args:
            root: Root directory to search

        Returns:
            List of empty directory paths
        """
        empty_dirs = []

        if not root.exists() or not root.is_dir():
            return empty_dirs

        try:
            for item in root.rglob('*'):
                if item.is_dir():
                    try:
                        # Check if directory is empty
                        if not any(item.iterdir()):
                            empty_dirs.append(item)
                    except OSError:
                        # Permission denied or other error
                        continue

        except Exception as e:
            log.error(f"Error finding empty directories in {root}", exception=e)

        return empty_dirs

    @staticmethod
    def find_broken_symlinks(root: Path) -> List[Path]:
        """
        Find all broken symbolic links in a tree.

        Args:
            root: Root directory to search

        Returns:
            List of broken symlink paths
        """
        broken_links = []

        if not root.exists() or not root.is_dir():
            return broken_links

        try:
            for item in root.rglob('*'):
                if item.is_symlink() and not item.exists():
                    broken_links.append(item)

        except Exception as e:
            log.error(f"Error finding broken symlinks in {root}", exception=e)

        return broken_links

    @staticmethod
    def find_large_files(
        root: Path,
        min_size_mb: float = 100.0,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Find large files in a directory tree.

        Args:
            root: Root directory to search
            min_size_mb: Minimum file size in MB
            limit: Maximum number of files to return

        Returns:
            List of file info dictionaries sorted by size
        """
        large_files = []
        min_size_bytes = int(min_size_mb * 1024 * 1024)

        try:
            for file_path in DirectoryTraversal.walk_files(
                root,
                min_size=min_size_bytes
            ):
                try:
                    stat = file_path.stat()
                    large_files.append({
                        "path": str(file_path),
                        "size": stat.st_size,
                        "size_mb": stat.st_size / (1024 * 1024),
                        "size_gb": stat.st_size / (1024 * 1024 * 1024),
                        "modified": stat.st_mtime
                    })
                except OSError:
                    continue

            # Sort by size (largest first)
            large_files.sort(key=lambda x: x["size"], reverse=True)

            # Apply limit if specified
            if limit:
                large_files = large_files[:limit]

        except Exception as e:
            log.error(f"Error finding large files in {root}", exception=e)

        return large_files


class SmartTraversal:
    """
    Intelligent traversal with caching and progress tracking.

    Provides optimized traversal for large directory trees with
    progress callbacks and result caching.
    """

    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        Initialize smart traversal.

        Args:
            progress_callback: Function to call with progress updates
        """
        self.progress_callback = progress_callback
        self.cache = {}

    def traverse_with_progress(
        self,
        roots: Union[Path, List[Path]],
        **kwargs
    ) -> Iterator[Path]:
        """
        Traverse with progress reporting.

        Args:
            roots: Single root directory or list of root directories
            **kwargs: Arguments passed to walk_files

        Yields:
            Path objects with progress updates
        """
        # First pass: estimate total files for progress
        total_estimate = sum(1 for _ in DirectoryTraversal.walk_files(roots, **kwargs))

        if self.progress_callback:
            self.progress_callback(0, total_estimate, "Starting traversal...")

        # Second pass: actual traversal with progress
        processed = 0
        for file_path in DirectoryTraversal.walk_files(roots, **kwargs):
            yield file_path
            processed += 1

            if self.progress_callback and processed % 100 == 0:
                self.progress_callback(
                    processed,
                    total_estimate,
                    f"Processed {processed}/{total_estimate} files"
                )

        if self.progress_callback:
            self.progress_callback(
                processed,
                total_estimate,
                f"Completed: {processed} files processed"
            )


# Standalone functions for backward compatibility and convenience
def walk_files(
    roots: Union[Path, List[Path]],
    patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    follow_symlinks: bool = False,
    max_depth: Optional[int] = None,
    min_size: int = 0,
    max_size: Optional[int] = None,
    include_hidden: bool = False
) -> Iterator[Path]:
    """
    Standalone function for walking files with multiple path support.

    This is a convenience wrapper around DirectoryTraversal.walk_files
    for backward compatibility and simpler imports.

    Args:
        roots: Single root directory or list of root directories to traverse
        patterns: Include patterns (glob-style)
        exclude_patterns: Exclude patterns (glob-style)
        follow_symlinks: Whether to follow symbolic links
        max_depth: Maximum recursion depth (None for unlimited)
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes (None for unlimited)
        include_hidden: Whether to include hidden files

    Yields:
        Path objects for matching files
    """
    return DirectoryTraversal.walk_files(
        roots=roots,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
        follow_symlinks=follow_symlinks,
        max_depth=max_depth,
        min_size=min_size,
        max_size=max_size,
        include_hidden=include_hidden
    )


def compute_xxh3_hash(path: Path) -> str:
    """Compute XXH3 hash of file content in 64KB chunks for large files."""
    try:
        import xxhash
    except ImportError:
        raise ImportError("xxhash package is required for XXH3 hashing. Install with: pdm add xxhash")

    hasher = xxhash.xxh3_64()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_directory(
    roots: Union[Path, List[Path]],
    profile_name: Optional[str] = None,
    patterns: Optional[List[str]] = None,
    compute_hashes: bool = False,
    exact_grouping: bool = False,
    algorithms: Optional[List[str]] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    settings: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    stop_event: Optional[Callable[[], bool]] = None,
    search_type: Optional[str] = None,
    **walk_kwargs
) -> Optional[Dict[str, Any]]:
    """
    Scan a directory for files and compute hashes/metadata based on search_type.

    For search_type='duplicate': Traverses all files (patterns=None), computes only file-based
    hashes (xxh3) via flat_cache_manager.get_hashes (limited mode: no image loading, no perceptual
    hashes, no metadata extraction). Groups by exact xxh3 for duplicate detection. Preserves
    existing image data in cache from prior similarity scans.

    For search_type='similarity': Filters to images (patterns=image extensions), computes perceptual
    hashes (phash/whash) and extracts dimensions/quality scores. Full cache update including
    image metadata.

    Uses flat_cache_manager for efficient caching with file stat validation. Supports progress
    reporting and cooperative cancellation. Manual computation fallback (no cache) respects
    search_type to skip image loading in duplicate mode.

    Args:
        roots (Union[Path, List[Path]]): Root directory or list of roots to scan.
        patterns (Optional[List[str]]): Glob patterns for files. Defaults based on search_type.
        compute_hashes (bool): If True, compute perceptual hashes for images (default: False).
            For 'duplicate', set to True internally for xxh3 grouping.
        exact_grouping (bool): If True, group files by exact xxh3 hash (default for 'duplicate').
        algorithms (Optional[List[str]]): Algorithms to compute. For 'duplicate': ['xxh3'].
            For 'similarity': ['phash', 'whash'] or from settings.
        flat_cache_manager (Optional[FlatCacheManager]): For caching with stat validation and
            conditional updates based on search_type.
        settings (Optional[Dict[str, Any]]): Settings dict for algorithm/threshold overrides.
        progress_callback (Optional[Callable[[int, int, str, str], None]]): Progress updates.
            Signature: (processed, total, current_path, status_message).
        stop_event (Optional[Callable[[], bool]]): Returns True if cancellation requested.
        search_type (Optional[str]): 'duplicate' or 'similarity' to control computation scope.
            Defaults to None (treated as 'similarity' for backward compatibility).
        **walk_kwargs: Passed to walk_files (e.g., exclude_patterns, max_depth).

    Returns:
        Optional[Dict[str, Any]]: {'files': List[Dict], 'exact_groups': Dict (if exact_grouping),
            'error_details': List[Dict]} or None if cancelled.

    Raises:
        ValueError: Invalid roots, algorithms, or search_type.
        SimilarityError: Hash computation failures (logged, scan continues).

    Example:
        >>> # Duplicate scan (all files, xxh3 only, no image loading)
        >>> results = scan_directory(
        ...     [Path("/mixed_files")], search_type='duplicate',
        ...     flat_cache_manager=manager, exact_grouping=True
        ... )
        >>> # Results: files with xxh3, groups by exact hash; width/phash remain None or prior values

        >>> # Similarity scan (images only, perceptual + metadata)
        >>> results = scan_directory(
        ...     [Path("/photos")], search_type='similarity',
        ...     flat_cache_manager=manager, compute_hashes=True
        ... )
        >>> # Results: files with phash/whash, width/height populated

    Note:
        - Duplicate mode: Fast, file-hash only; skips PIL.open() to handle non-images safely.
        - Similarity mode: Image-focused; extracts dimensions and quality (BRISQUE if enabled).
        - Cache: Conditional updates prevent overwriting image data in duplicate mode.
        - PoC: Sequential processing; no parallelism. Extension-based image filtering.
        - Errors: Per-file failures logged; scan continues. Full traceback in error_details.
    """
    # Normalize roots to list
    if isinstance(roots, Path):
        roots = [roots]
    elif not isinstance(roots, list):
        raise TypeError("roots must be a Path or list of Path objects")

    # Validate at least one valid root
    valid_roots = [r for r in roots if r.exists() and r.is_dir()]
    if not valid_roots:
        raise ValueError(f"No valid root directories provided: {roots}")

    # Default patterns based on search_type for optimal traversal
    if patterns is None:
        if search_type == 'duplicate':
            # Traverse all files for comprehensive exact duplicate detection across any type
            patterns = None
            log.debug("Duplicate mode: No patterns (includes all files for xxh3 hashing)")
        else:
            # Filter to images for perceptual hashing and metadata extraction efficiency
            patterns = [f"*{ext}" for ext in IMAGE_EXTENSIONS]
            log.debug(f"Similarity mode: Image patterns: {patterns}")

    # Resolve algorithms with search_type awareness
    if algorithms is None:
        if search_type == 'duplicate':
            # Only file content hash for exact grouping; no perceptual
            algorithms = ['xxh3']
            compute_hashes = True  # Enable for xxh3 grouping
            exact_grouping = True
            log.debug("Duplicate mode: Algorithms limited to ['xxh3']")
        elif settings and 'criteria' in settings and 'similarity_hash_algorithm' in settings['criteria']:
            # Use the specific algorithm selected in criteria
            selected_algorithm = settings['criteria']['similarity_hash_algorithm']
            algorithms = [selected_algorithm]
        else:
            if search_type == 'similarity':
                algorithms = ['phash', 'whash']
            else:
                algorithms = ['phash']
    if search_type == 'duplicate':
        # Override to ensure only xxh3; ignore perceptual requests
        algorithms = ['xxh3']
    else:
        # Filter to valid perceptual algorithms
        algorithms = [alg.lower() for alg in algorithms if alg.lower() in ['phash', 'whash']]

    if not algorithms:
        raise ValueError("No valid algorithms specified for the given search_type")

    # Traverse files: all for duplicate, images for similarity
    all_paths = []
    for root_path in roots:
        # Filter out invalid kwargs for walk_files
        filtered_kwargs = {k: v for k, v in walk_kwargs.items() if k not in ['db_manager', 'profile_name']}
        paths = list(DirectoryTraversal.walk_files(root_path, patterns=patterns, **filtered_kwargs))
        all_paths.extend(paths)
    # Deduplicate paths (handles overlapping roots)
    unique_paths = list({p.as_posix(): p for p in all_paths}.values())

    # Ensure compute_hashes for similarity (perceptual + grouping)
    if search_type == 'similarity':
        compute_hashes = True

    results: List[Dict[str, Any]] = []
    error_details: List[Dict[str, Any]] = []
    file_count = len(unique_paths)
    log.info(f"Scanning {file_count} files from {len(roots)} roots (search_type={search_type})")

    processed_count = 0
    if progress_callback:
        progress_callback(processed_count, file_count, "", f"Starting {search_type} scan of {file_count} files...")

    groups: Dict[str, List[str]] = defaultdict(list) if exact_grouping else None

    for path in unique_paths:
        # Cooperative cancellation check
        if stop_event and stop_event():
            log.info("Scan cancelled by stop event.")
            if progress_callback:
                progress_callback(processed_count, file_count, str(path), "Scan cancelled.")
            return None

        try:
            file_info = FileInfo.from_path(path)
            if file_info.size == 0:
                processed_count += 1
                continue  # Skip empty/broken files

            # Prefer flat_cache_manager for conditional hashing based on search_type
            if flat_cache_manager:
                # all_types includes only relevant hashes; get_hashes handles skipping perceptual in duplicate mode
                all_types = list(set(algorithms + ['xxh3']))
                log.debug(f"DEBUG: Calling get_hashes for {path} with types {all_types}, search_type={search_type}")
                hashes_dict = flat_cache_manager.get_hashes([str(path)], all_types, search_type=search_type)
                hashes = hashes_dict[str(path)]
                exact_hash = hashes.get('xxh3')
                perceptual_hashes = {k: v for k, v in hashes.items() if k != 'xxh3'}
                log.debug(f"DEBUG: Retrieved hashes for {path}: {hashes}. exact_hash={exact_hash}")
                log.debug(f"Cache-based hashes for {path}: xxh3={bool(exact_hash)}, perceptual={list(perceptual_hashes.keys())}")
            else:
                # Manual fallback: respect search_type to avoid image loading in duplicate mode
                log.debug(f"DEBUG: Manual fallback - computing xxh3 for {path}")
                exact_hash = compute_xxh3_hash(path)
                log.debug(f"DEBUG: Computed manual xxh3 for {path}: {exact_hash}")
                perceptual_hashes = {}
                if compute_hashes and file_info.extension in IMAGE_EXTENSIONS and search_type != 'duplicate':
                    # Only compute perceptual if similarity mode and image file
                    for alg in algorithms:
                        try:
                            if alg == 'phash':
                                perceptual_hashes[alg] = similarity.compute_phash(str(path), settings=settings)
                            elif alg == 'whash':
                                perceptual_hashes[alg] = similarity.compute_whash(str(path), settings=settings)
                        except similarity.SimilarityError as e:
                            log.error(f"Perceptual hash failed for {path} ({alg}): {e}")
                            continue
                    log.debug(f"Manual perceptual hashes for {path}: {list(perceptual_hashes.keys())}")
                else:
                    if search_type == 'duplicate':
                        log.debug(f"Manual mode: Skipped perceptual for duplicate scan: {path}")
                    else:
                        log.debug(f"Manual mode: Skipped non-image or non-compute: {path}")

            result: Dict[str, Any] = {
                'path': str(path),
                'size': file_info.size,
                'modified_time': file_info.modified_time,
                'extension': file_info.extension,
                'exact_hash': exact_hash,
                'hashes': perceptual_hashes  # Empty {} for duplicate mode
            }

            results.append(result)
            processed_count += 1

            # Progress reporting with mode-specific status
            if progress_callback:
                status = f"Processing file {processed_count}/{file_count} ({search_type} mode)"
                if exact_hash:
                    status += f" (xxh3 computed)"
                if perceptual_hashes:
                    status += f" (perceptual: {', '.join(perceptual_hashes.keys())})"
                progress_callback(processed_count, file_count, str(path), status)

        except Exception as e:
            import traceback
            log.error(f"Error processing {path}: {e}", exc_info=True)
            error_details.append({
                'path': str(path),
                'error': str(e),
                'traceback': traceback.format_exc()
            })
            processed_count += 1
            continue

    # Build exact groups if requested (only for duplicate mode with xxh3)
    if exact_grouping:
        log.debug(f"DEBUG: Building exact groups from {len(results)} results")
        for f in results:
            eh = f.get('exact_hash')
            log.debug(f"DEBUG: File {f['path']} exact_hash: {eh}")
            if eh:
                groups[eh].append(f)
        # Filter to groups with 2+ files
        groups = {h: fs for h, fs in groups.items() if len(fs) > 1}
        log.debug(f"DEBUG: Found {len(groups)} exact groups")

    # Mode-specific logging
    log.info(f"Scan complete: {len(results)} files processed (search_type={search_type})")
    if exact_grouping:
        total_grouped_files = sum(len(g) for g in groups.values())
        log.info(f"Exact duplicate groups: {len(groups)} groups with {total_grouped_files} files")
    if compute_hashes and search_type == 'similarity':
        perceptual_count = sum(1 for r in results if 'hashes' in r and r['hashes'])
        log.info(f"Perceptual hash computation complete: {perceptual_count} images processed")

    if progress_callback:
        progress_callback(file_count, file_count, "", f"{search_type.capitalize()} scan completed successfully.")

    return {
        'files': results,
        'exact_groups': dict(groups) if exact_grouping else None,
        'error_details': error_details
    }


def validate_paths(paths: List[Path]) -> List[str]:
    """
    Validate that paths exist and are accessible.

    Args:
        paths: List of paths to validate

    Returns:
        List of error messages for invalid paths, empty list if all valid
    """
    errors = []
    for path in paths:
        if not path.exists():
            errors.append(f"Path does not exist: {path}")
        elif not os.access(str(path), os.R_OK):
            errors.append(f"Path is not readable: {path}")
    return errors
