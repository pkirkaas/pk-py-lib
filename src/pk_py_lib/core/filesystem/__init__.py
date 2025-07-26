"""
Filesystem Operations Module

Comprehensive file system operations including path manipulation, 
file monitoring, safe operations, and directory traversal.
"""

from .paths import PathOperations
from .operations import FileOperations, SafeFileOperations
from .traversal import DirectoryTraversal
from .organization import FileOrganizer

# Import monitoring submodule
from . import monitoring

__all__ = [
    "PathOperations",
    "FileOperations", 
    "SafeFileOperations",
    "DirectoryTraversal",
    "FileOrganizer",
    "monitoring"
]

# Convenience functions for common operations
def normalize_paths(paths):
    """Convenience function for path normalization."""
    return PathOperations.normalize_paths(paths)

def remove_contained_paths(paths):
    """Convenience function to remove contained paths."""
    return PathOperations.remove_contained_paths(paths)

def safe_move(source, destination, on_conflict="rename"):
    """Convenience function for safe file moves."""
    return FileOperations.safe_move(source, destination, on_conflict)