"""
Path Operations Module

Utilities for path manipulation, validation, and deduplication.
Includes the critical remove_contained_paths() function for handling
mixed file/directory collections.
"""

from pathlib import Path
from typing import List, Set, Tuple, Optional, Dict
import os
from collections import defaultdict


class PathOperations:
    """
    Utilities for path manipulation and validation.
    
    This class provides static methods for common path operations needed
    when working with large collections of files and directories.
    """
    
    @staticmethod
    def normalize_paths(paths: List[Path]) -> List[Path]:
        """
        Normalize and deduplicate a list of paths.
        
        Args:
            paths: List of file/directory paths (can be relative or absolute)
            
        Returns:
            List of normalized, absolute, deduplicated paths
            
        Example:
            >>> paths = [Path("./images"), Path("/home/user/images/../images")]
            >>> normalized = PathOperations.normalize_paths(paths)
            >>> # Returns single resolved absolute path
        """
        if not paths:
            return []
            
        normalized = []
        seen = set()
        
        for path in paths:
            if path is None:
                continue
                
            # Convert to Path object if string
            if isinstance(path, str):
                path = Path(path)
            
            try:
                # Resolve to absolute path and normalize
                resolved = path.resolve()
                
                # Check if we've already seen this path
                if resolved not in seen:
                    normalized.append(resolved)
                    seen.add(resolved)
                    
            except (OSError, RuntimeError) as e:
                # Handle broken symlinks or permission issues
                # Log the error but continue processing
                print(f"Warning: Could not resolve path {path}: {e}")
                continue
        
        return sorted(normalized)
    
    @staticmethod
    def remove_contained_paths(paths: List[Path]) -> List[Path]:
        """
        Remove paths that are contained within other paths in the list.
        
        This is the key function you requested - it ensures no path in the
        result is contained within another path, preventing redundant processing.
        
        Args:
            paths: Mixed list of file and directory paths
            
        Returns:
            Minimal list with no path contained within another
            
        Example:
            >>> paths = [
            ...     Path("/images"),
            ...     Path("/images/vacation"),
            ...     Path("/images/vacation/beach.jpg"),
            ...     Path("/documents"),
            ...     Path("/images/work/project.jpg")
            ... ]
            >>> minimal = PathOperations.remove_contained_paths(paths)
            >>> # Returns [Path("/images"), Path("/documents")]
            >>> # because /images contains all the other /images/* paths
        """
        if not paths:
            return []
            
        # First normalize all paths
        normalized_paths = PathOperations.normalize_paths(paths)
        
        if len(normalized_paths) <= 1:
            return normalized_paths
        
        # Sort paths by length (shorter paths first)
        # This ensures parent directories come before their contents
        sorted_paths = sorted(normalized_paths, key=lambda p: len(str(p)))
        
        result = []
        
        for current_path in sorted_paths:
            is_contained = False
            
            # Check if current path is contained within any path already in result
            for existing_path in result:
                try:
                    # Check if current_path is relative to existing_path
                    current_path.relative_to(existing_path)
                    is_contained = True
                    break
                except ValueError:
                    # Not relative to existing_path, continue checking
                    continue
            
            # Only add if not contained within an existing path
            if not is_contained:
                result.append(current_path)
        
        return result
    
    @staticmethod
    def find_common_ancestor(paths: List[Path]) -> Optional[Path]:
        """
        Find the common ancestor directory of multiple paths.
        
        Args:
            paths: List of paths to find common ancestor for
            
        Returns:
            Common ancestor path, or None if no common ancestor
            
        Example:
            >>> paths = [
            ...     Path("/home/user/photos/vacation"),
            ...     Path("/home/user/photos/work"),
            ...     Path("/home/user/documents")
            ... ]
            >>> ancestor = PathOperations.find_common_ancestor(paths)
            >>> # Returns Path("/home/user")
        """
        if not paths:
            return None
            
        normalized_paths = PathOperations.normalize_paths(paths)
        
        if len(normalized_paths) == 1:
            # For single path, return its parent if it's a file, itself if directory
            path = normalized_paths[0]
            return path.parent if path.is_file() else path
        
        # Find common parts
        path_parts = [list(path.parts) for path in normalized_paths]
        
        if not path_parts:
            return None
        
        # Find the minimum length
        min_length = min(len(parts) for parts in path_parts)
        
        common_parts = []
        for i in range(min_length):
            # Check if all paths have the same part at position i
            current_part = path_parts[0][i]
            if all(parts[i] == current_part for parts in path_parts):
                common_parts.append(current_part)
            else:
                break
        
        if not common_parts:
            return None
            
        # Reconstruct path from common parts
        return Path(*common_parts)
    
    @staticmethod
    def group_by_directory(paths: List[Path]) -> Dict[Path, List[Path]]:
        """
        Group files by their parent directory.
        
        Args:
            paths: List of file paths
            
        Returns:
            Dictionary mapping directory paths to lists of files in that directory
            
        Example:
            >>> files = [
            ...     Path("/photos/img1.jpg"),
            ...     Path("/photos/img2.jpg"),
            ...     Path("/documents/doc1.txt")
            ... ]
            >>> grouped = PathOperations.group_by_directory(files)
            >>> # Returns {
            >>> #     Path("/photos"): [Path("/photos/img1.jpg"), Path("/photos/img2.jpg")],
            >>> #     Path("/documents"): [Path("/documents/doc1.txt")]
            >>> # }
        """
        grouped = defaultdict(list)
        
        normalized_paths = PathOperations.normalize_paths(paths)
        
        for path in normalized_paths:
            if path.is_file():
                parent_dir = path.parent
            else:
                # For directories, group under themselves
                parent_dir = path
                
            grouped[parent_dir].append(path)
        
        return dict(grouped)
    
    @staticmethod
    def validate_path_access(path: Path, check_read: bool = True, check_write: bool = False) -> bool:
        """
        Validate that a path exists and has required permissions.
        
        Args:
            path: Path to validate
            check_read: Whether to check read permission
            check_write: Whether to check write permission
            
        Returns:
            True if path is accessible with required permissions
        """
        try:
            if not path.exists():
                return False
                
            if check_read and not os.access(path, os.R_OK):
                return False
                
            if check_write and not os.access(path, os.W_OK):
                return False
                
            return True
            
        except (OSError, PermissionError):
            return False
    
    @staticmethod
    def get_path_info(path: Path) -> Dict[str, any]:
        """
        Get comprehensive information about a path.
        
        Args:
            path: Path to analyze
            
        Returns:
            Dictionary with path information including size, type, permissions, etc.
        """
        info = {
            "exists": False,
            "is_file": False,
            "is_directory": False,
            "is_symlink": False,
            "size": 0,
            "readable": False,
            "writable": False,
            "parent": None,
            "name": str(path.name),
            "suffix": path.suffix if hasattr(path, 'suffix') else '',
            "absolute_path": None
        }
        
        try:
            info["exists"] = path.exists()
            info["absolute_path"] = str(path.resolve())
            info["parent"] = str(path.parent)
            
            if info["exists"]:
                info["is_file"] = path.is_file()
                info["is_directory"] = path.is_dir()
                info["is_symlink"] = path.is_symlink()
                info["readable"] = os.access(path, os.R_OK)
                info["writable"] = os.access(path, os.W_OK)
                
                if info["is_file"]:
                    info["size"] = path.stat().st_size
                    
        except (OSError, PermissionError) as e:
            info["error"] = str(e)
            
        return info