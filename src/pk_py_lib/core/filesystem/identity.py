"""
src/pk_py_lib/core/filesystem/identity.py
Utilities and manager for computing and comparing filesystem identities for files.

This module provides robust file identity helpers used to detect moved/renamed files by combining
inode/device where available with persistent SHA-256 content hashing. It is intentionally generic:
DB lookup functions are provided by callers to keep the module decoupled from any specific DB layer.
"""

from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable, NamedTuple

from ..logging.decorators import log_errors
from ..logging import get_logger

logger = get_logger(__name__)

__all__ = ["FileIdentity", "compute_xxh3", "get_inode_device", "make_identity", "IdentityResolver"]


class FileIdentity(NamedTuple):
    """
    Lightweight immutable representation of a file identity.

    Attributes
    ----------
    xxh3 : Optional[str]
        Hex XXH3 digest of the file contents, when computed.
        XXH3 is a fast, non-cryptographic hash suitable for duplicate detection.
    inode : Optional[int]
        OS inode number where available (None on unsupported platforms).
    device : Optional[int]
        Device identifier (st_dev) where available.
    size : Optional[int]
        File size in bytes.
    mtime : Optional[int]
        Last modification time as integer epoch seconds.
    """
    xxh3: Optional[str]
    inode: Optional[int]
    device: Optional[int]
    size: Optional[int]
    mtime: Optional[int]


@log_errors()
def compute_xxh3(path: Path, chunk_size: int = 65536) -> str:
    """
    Compute XXH3 hash for a file by streaming it in chunks.
    
    XXH3 is an extremely fast non-cryptographic hash algorithm suitable for
    duplicate detection and file identity purposes.
    
    Parameters
    ----------
    path : Path
        Path to the file to hash.
    chunk_size : int
        Read buffer size in bytes.
        
    Returns
    -------
    str
        Hexadecimal XXH3 digest.
        
    Raises
    ------
    FileNotFoundError, PermissionError, OSError
        Propagates IO-related exceptions to caller.
    ImportError
        Raised if xxhash package is not available
    """
    try:
        import xxhash
    except ImportError:
        raise ImportError("xxhash package is required for XXH3 hashing. Install with: pdm add xxhash")
    
    h = xxhash.xxh3_64()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@log_errors()
def get_inode_device(path: Path) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    Obtain filesystem stat information useful for identity heuristics.

    Returns (inode, device, size, mtime) where any value may be None if unavailable.

    Parameters
    ----------
    path : Path
        Path to inspect.

    Returns
    -------
    Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]
    """
    try:
        st = path.stat()
        inode = int(st.st_ino) if hasattr(st, "st_ino") else None
        device = int(st.st_dev) if hasattr(st, "st_dev") else None
        size = int(st.st_size) if hasattr(st, "st_size") else None
        mtime = int(st.st_mtime) if hasattr(st, "st_mtime") else None
        return inode, device, size, mtime
    except Exception as e:
        logger.error(f"Failed to get inode/device for {path}: {e}")
        return None, None, None, None


def make_identity(path: Path, compute_hash: bool = True) -> FileIdentity:
    """
    Build a FileIdentity for the given path.

    Parameters
    ----------
    path : Path
        File path to inspect.
    compute_hash : bool
        Whether to compute and include the XXH3 content hash.

    Returns
    -------
    FileIdentity
    """
    inode, device, size, mtime = get_inode_device(path)
    xxh3_hash = None
    if compute_hash:
        try:
            xxh3_hash = compute_xxh3(path)
        except Exception:
            # If hashing fails (permissions, IO), leave xxh3 as None and rely on inode/device heuristics
            xxh3_hash = None
    return FileIdentity(xxh3=xxh3_hash, inode=inode, device=device, size=size, mtime=mtime)


class IdentityResolver:
    """
    High-level helper to compare and resolve file identities.

    It is intentionally decoupled from any specific database implementation.
    Callers should provide small DB lookup functions (callables) where needed.

    Example
    -------
    >>> resolver = IdentityResolver()
    >>> identity = resolver.resolve(Path("/photos/img.jpg"))
    >>> row = resolver.find_moved_by_hash(my_db_lookup_fn, identity.sha256)  # db lookup by hash
    """

    def __init__(self, compute_hash_by_default: bool = True):
        """
        Parameters
        ----------
        compute_hash_by_default : bool
            Whether to compute XXH3 by default when resolving identities.
        """
        self.compute_hash_by_default = bool(compute_hash_by_default)

    def resolve(self, path: Path, compute_hash: Optional[bool] = None) -> FileIdentity:
        """
        Resolve identity for a given file path.

        Parameters
        ----------
        path : Path
            Path to the file.
        compute_hash : Optional[bool]
            Override whether to compute the XXH3 hash for this call.

        Returns
        -------
        FileIdentity
        """
        if compute_hash is None:
            compute_hash = self.compute_hash_by_default
        return make_identity(path, compute_hash=compute_hash)

    def matches(self, a: FileIdentity, b: FileIdentity) -> bool:
        """
        Determine whether two FileIdentity objects refer to the same underlying file.

        Heuristic order:
        1. If both have xxh3 -> compare xxh3 equality.
        2. Else if both have inode and device -> compare device+inode equality.
        3. Else if size and mtime both equal (best-effort) -> consider match.
        4. Else -> not match

        Parameters
        ----------
        a : FileIdentity
        b : FileIdentity

        Returns
        -------
        bool
        """
        # 1: XXH3 equality
        if a.xxh3 and b.xxh3:
            return a.xxh3 == b.xxh3
        # 2: inode/device
        if a.inode is not None and b.inode is not None and a.device is not None and b.device is not None:
            return (a.inode == b.inode) and (a.device == b.device)
        # 3: size + mtime fallback (coarse)
        if (a.size is not None and b.size is not None and a.mtime is not None and b.mtime is not None):
            return (a.size == b.size) and (a.mtime == b.mtime)
        return False

    def find_moved_by_hash(self, db_lookup_by_hash: Callable[[str], Optional[Dict[str, Any]]], xxh3: str) -> Optional[Dict[str, Any]]:
        """
        Query a supplied DB lookup callable for an entry matching xxh3.

        Parameters
        ----------
        db_lookup_by_hash : Callable[[str], Optional[Dict[str, Any]]]
            Function that accepts an xxh3 hex string and returns a DB row dict or None.
        xxh3 : str
            XXH3 hex string to search for.

        Returns
        -------
        Optional[Dict[str, Any]]
            Returned DB row (dict-like) or None if not found.
        """
        try:
            return db_lookup_by_hash(xxh3)
        except Exception:
            # Caller will handle None / errors
            return None

    def find_moved_by_inode(self, db_lookup_by_inode: Callable[[int, int], Optional[Dict[str, Any]]], device: int, inode: int) -> Optional[Dict[str, Any]]:
        """
        Query DB lookup callable for an entry matching device+inode.

        Parameters
        ----------
        db_lookup_by_inode : Callable[[int, int], Optional[Dict[str, Any]]]
            Function that accepts (device, inode) and returns DB row dict or None.
        device : int
        inode : int

        Returns
        -------
        Optional[Dict[str, Any]]
        """
        try:
            return db_lookup_by_inode(device, inode)
        except Exception:
            return None

# End of module