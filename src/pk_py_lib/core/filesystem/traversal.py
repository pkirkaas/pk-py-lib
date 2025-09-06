"""
Directory Traversal Module

Efficient directory traversal with advanced filtering capabilities,
duplicate detection, and directory statistics.
"""

import os
from pathlib import Path
from typing import Iterator, Optional, List, Dict, Any, Pattern, Set, Union
import fnmatch
import re
from collections import defaultdict, Counter
from dataclasses import dataclass

from ..logging import get_logger

log = get_logger(__name__)


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
        """Internal recursive walking function."""
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
        
        def walk_recursive_internal(current_path: Path, current_depth: int = 0):
            """Recursive walking function."""
            if max_depth is not None and current_depth >= max_depth:
                return
            
            try:
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
                        
                        # Recurse into subdirectory
                        yield from walk_recursive_internal(item, current_depth + 1)
            
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
    
    def __init__(self, progress_callback: Optional[callable] = None):
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