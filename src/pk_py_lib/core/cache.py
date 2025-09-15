"""
src/pk_py_lib/core/cache.py

File-backed CacheManager for thumbnails and small cached artifacts.

Design decisions (canonical):
- Default cache dir: caller-provided. Canonical per-OS defaults are documented in
  `docs/roo/canonical-decisions.md`.
- Default max size: 5120 MB (configurable).
- Thumbnails stored as files:
    cache_dir/
      thumbnails/
        256/
          {cache_key}.jpg
          {cache_key}.meta.json
        512/
        1024/
- Cache keys are derived from (normalized) file path + file size + mtime to automatically
  invalidate stale thumbnails when source file changes.
- Eviction policy: LRU based on file access time. Cleanup triggers when total cache size
  exceeds CLEANUP_ON_SIZE_PERCENT of max_size.
"""

from __future__ import annotations

import json
import logging
import hashlib
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("pk_py_lib.core.cache")


class HashCache:
    """
    Simple in-memory cache for image hashes with TTL support.
    
    This class manages a dictionary-based cache where keys are strings
    (e.g., f"{image_path}:{algorithm}") and values are hex hash strings.
    Expired entries are automatically removed on access.
    
    Design:
    - Uses time.time() for expiration checks.
    - No persistence; purely in-memory for fast access during scans.
    - Integrated into CacheManager for unified caching.
    
    Args:
        ttl_default (int): Default TTL in seconds (3600 = 1 hour).
    
    Raises:
        ValueError: If TTL is negative.
    """
    def __init__(self, ttl_default: int = 3600):
        if ttl_default < 0:
            raise ValueError("TTL must be non-negative")
        self._cache: Dict[str, Tuple[str, float]] = {}
        self.ttl_default = ttl_default
    
    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """
        Store a hash value with optional TTL.
        
        Args:
            key (str): Cache key, e.g., "path/to/image.jpg:phash".
            value (str): Hex hash string (e.g., 16 chars for 64-bit).
            ttl (Optional[int]): Time-to-live in seconds; uses default if None.
        
        Raises:
            ValueError: If value is not a string or key is invalid.
        """
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")
        if not isinstance(value, str):
            raise ValueError("Value must be a string (hex hash)")
        expiry = time.time() + (ttl or self.ttl_default)
        self._cache[key] = (value, expiry)
    
    def get(self, key: str) -> Optional[str]:
        """
        Retrieve a hash value if not expired.
        
        Args:
            key (str): Cache key to lookup.
        
        Returns:
            Optional[str]: Hash value if valid, None if expired or missing.
        
        Raises:
            ValueError: If key is invalid.
        """
        if not isinstance(key, str) or not key:
            raise ValueError("Key must be a non-empty string")
        if key not in self._cache:
            return None
        value, expiry = self._cache[key]
        if time.time() > expiry:
            del self._cache[key]
            return None
        return value
    
    def clear(self) -> None:
        """Clear all cached hashes."""
        self._cache.clear()
    
    def size(self) -> int:
        """Return current cache size (active entries only)."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]
        return len(self._cache)


class CacheManager:
    """
    Manage a simple file-backed thumbnail cache with LRU eviction.

    This implementation favors simplicity and robustness for prototyping and
    early development (Phase 1). It intentionally avoids using a complex DB
    for thumbnails; instead it stores thumbnails as files and writes small
    metadata JSON files next to each thumbnail to support validation.

    Usage example
    -------------
    >>> cm = CacheManager(Path.home() / ".kdc_cache", max_size_mb=5120)
    >>> data = cm.get_thumbnail(Path("/photos/img.jpg"), 256)
    >>> if data is None:
    ...     thumb_bytes = generate_thumbnail_bytes(...)  # external
    ...     cm.cache_thumbnail(Path("/photos/img.jpg"), 256, thumb_bytes)
    """

    # Default policy constants
    DEFAULT_MAX_SIZE_MB = 5120  # 5120 MB (≈5 GB)
    CLEANUP_ON_SIZE_PERCENT = 0.90  # start cleanup when 90% full
    EVICTION_BATCH_SIZE = 50  # delete up to this many files per cleanup pass

    def __init__(self, cache_dir: Path, max_size_mb: int = DEFAULT_MAX_SIZE_MB, jpeg_quality: int = 85):
        """
        Initialize CacheManager.
        
        Parameters
        ----------
        cache_dir : Path
            Base directory where cache data will be stored.
        max_size_mb : int
            Maximum cache size in megabytes (default: 5120 MB, ≈5 GB).
        jpeg_quality : int
            Default JPEG quality used when generating thumbnails (informational).
        """
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.thumb_base = self.cache_dir / "thumbnails"
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.jpeg_quality = int(jpeg_quality)
        
        # In-memory cache for image hashes (perceptual similarity)
        self._hash_cache = HashCache(ttl_default=3600)

        # Ensure directories exist
        try:
            self.thumb_base.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.exception("Failed to create cache directory %s: %s", self.thumb_base, e)
            raise

    # ----------------------------
    # Public methods
    # ----------------------------
    def get_thumbnail(self, image_path: Path, size: int) -> Optional[bytes]:
        """
        Retrieve a cached thumbnail if present and still valid.

        Parameters
        ----------
        image_path : Path
            Absolute path to the original image file.
        size : int
            Thumbnail size (e.g., 256, 512, 1024).

        Returns
        -------
        Optional[bytes]
            Raw thumbnail bytes (JPEG) if cache hit and valid, otherwise None.
        """
        try:
            cache_file, meta_file = self._cache_paths(image_path, size)
            if not cache_file.exists() or not meta_file.exists():
                return None

            # Validate metadata
            meta = self._read_meta(meta_file)
            if not self._meta_matches(image_path, meta):
                # stale
                try:
                    cache_file.unlink(missing_ok=True)  # Python 3.8+: missing_ok param
                except TypeError:
                    # For older Python versions in CI, handle gracefully
                    if cache_file.exists():
                        cache_file.unlink()
                try:
                    meta_file.unlink(missing_ok=True)
                except TypeError:
                    if meta_file.exists():
                        meta_file.unlink()
                return None

            # Update access time for LRU behavior
            try:
                now = time.time()
                os.utime(cache_file, (now, cache_file.stat().st_mtime))
                os.utime(meta_file, (now, meta_file.stat().st_mtime))
            except Exception:
                # Non-fatal: continue without failing
                pass

            return cache_file.read_bytes()
        except Exception as e:
            logger.exception("Error retrieving cached thumbnail for %s size=%s: %s", image_path, size, e)
            return None

    def cache_thumbnail(self, image_path: Path, size: int, data: bytes) -> None:
        """
        Store thumbnail bytes in the cache.

        Parameters
        ----------
        image_path : Path
            Original image path used to compute the cache key.
        size : int
            Size of the thumbnail.
        data : bytes
            Binary thumbnail data (JPEG recommended).
        """
        try:
            cache_file, meta_file = self._cache_paths(image_path, size)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(data)
            # Write metadata to validate cache entries later
            meta = self._make_meta(image_path)
            meta_file.write_text(json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
            # Trigger cleanup if needed
            self._cleanup_if_needed()
        except Exception as e:
            logger.exception("Failed to cache thumbnail for %s size=%s: %s", image_path, size, e)

    def get_cache_info(self) -> Dict[str, Any]:
        """
        Return cache statistics.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing total_size_bytes, total_size_mb, thumbnail_count, max_size_bytes, max_size_mb.
        """
        total_size = self._get_total_cache_size()
        thumb_count = sum(1 for _ in self.thumb_base.rglob("*") if _.is_file())
        return {
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "thumbnail_count": thumb_count,
            "max_size_bytes": self.max_size_bytes,
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "used_percent": (total_size / self.max_size_bytes) * 100.0 if self.max_size_bytes > 0 else 0.0,
        }

    def clear_cache(self, older_than: Optional[timedelta] = None) -> int:
        """
        Clear cached thumbnails optionally older than a given age.
        
        Parameters
        ----------
        older_than : Optional[timedelta]
            If provided, only delete thumbnails older than this duration (based on metadata created_at).
        
        Returns
        -------
        int
            Number of files deleted.
        """
        deleted = 0
        cutoff_ts = None
        if older_than is not None:
            cutoff_ts = time.time() - older_than.total_seconds()

        for meta_file in self.thumb_base.rglob("*.meta.json"):
            try:
                meta = self._read_meta(meta_file)
                created_at = meta.get("created_at_ts")
                if cutoff_ts is None or (created_at is not None and created_at < cutoff_ts):
                    cache_file = meta_file.with_suffix("")  # original name before .meta.json
                    if cache_file.exists():
                        cache_file.unlink(missing_ok=True) if hasattr(cache_file, "unlink") else cache_file.unlink()
                    meta_file.unlink(missing_ok=True) if hasattr(meta_file, "unlink") else meta_file.unlink()
                    deleted += 1
            except Exception:
                # continue with best-effort deletions
                continue
        
        # Clear in-memory hash cache if requested
        if older_than is not None:
            # Approximate: clear if older_than < default TTL
            if older_than.total_seconds() < 3600:
                self._hash_cache.clear()
                deleted += self._hash_cache.size()
        
        return deleted
    
    def set_hash(self, key: str, value: str, ttl: int = 3600) -> None:
        """
        Store an image hash in the in-memory cache with TTL.
        
        Args:
            key (str): Cache key, typically f"{image_path}:{algorithm}".
            value (str): Hexadecimal hash value (e.g., 16 chars for 64-bit).
            ttl (int): Time-to-live in seconds (default: 3600).
        
        Raises:
            ValueError: If key or value is invalid.
            TypeError: If ttl is not an int.
        """
        self._hash_cache.set(key, value, ttl)
    
    def get_hash(self, key: str) -> Optional[str]:
        """
        Retrieve an image hash from the in-memory cache if not expired.
        
        Args:
            key (str): Cache key to lookup.
        
        Returns:
            Optional[str]: Hash value if present and valid, else None.
        
        Raises:
            ValueError: If key is invalid.
        """
        return self._hash_cache.get(key)
    
    def clear_hashes(self) -> int:
        """
        Clear all cached hashes.
        
        Returns:
            int: Number of hashes cleared.
        """
        count = self._hash_cache.size()
        self._hash_cache.clear()
        return count
    
    def get_hash_cache_info(self) -> Dict[str, Any]:
        """
        Get statistics for the hash cache.
        
        Returns:
            Dict[str, Any]: {"size": int, "ttl_default": int}.
        """
        return {
            "size": self._hash_cache.size(),
            "ttl_default": self._hash_cache.ttl_default,
        }

    # ----------------------------
    # Internal helpers
    # ----------------------------
    def _cache_paths(self, image_path: Path, size: int) -> (Path, Path):
        """
        Return (cache_file_path, meta_file_path) for a given image + size.

        Cache key is a sha256 over "normalized_path|size|file_size|mtime" to ensure
        invalidation when the source file changes.
        """
        key = self._compute_cache_key(image_path)
        folder = self.thumb_base / str(int(size))
        cache_file = folder / f"{key}.jpg"
        meta_file = folder / f"{key}.meta.json"
        return cache_file, meta_file

    def _compute_cache_key(self, image_path: Path) -> str:
        """
        Compute a deterministic cache key from the image path and its file metadata.

        Uses path (POSIX), file size and modification time. This avoids keeping stale
        thumbnails after the source file changes. If stat fails, falls back to path-only
        hashing.
        """
        try:
            stat = image_path.stat()
            token = f"{image_path.as_posix()}|{stat.st_size}|{int(stat.st_mtime)}"
        except Exception:
            token = f"{image_path.as_posix()}"
        h = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return h

    def _make_meta(self, image_path: Path) -> Dict[str, Any]:
        """
        Construct metadata for a cache entry.

        Fields:
        - original_path
        - file_size
        - file_mtime_ts
        - created_at_ts
        """
        meta: Dict[str, Any] = {
            "original_path": image_path.as_posix(),
            "created_at_ts": int(time.time()),
        }
        try:
            st = image_path.stat()
            meta["file_size"] = int(st.st_size)
            meta["file_mtime_ts"] = int(st.st_mtime)
        except Exception:
            # If file not accessible, leave file-specific fields absent
            pass
        return meta

    def _read_meta(self, meta_file: Path) -> Dict[str, Any]:
        """
        Read and parse metadata JSON next to a cached thumbnail.

        Returns empty dict on error.
        """
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _meta_matches(self, image_path: Path, meta: Dict[str, Any]) -> bool:
        """
        Validate that the cached thumbnail still corresponds to the given image_path.

        We compare file_size and file_mtime where available.
        """
        try:
            st = image_path.stat()
            if "file_size" in meta and int(meta["file_size"]) != int(st.st_size):
                return False
            if "file_mtime_ts" in meta and int(meta["file_mtime_ts"]) != int(st.st_mtime):
                return False
            return True
        except Exception:
            # If we cannot stat the source file, be conservative and consider invalid.
            return False

    def _get_total_cache_size(self) -> int:
        """
        Compute total size in bytes of the thumbnail cache directory.
        """
        total = 0
        for f in self.thumb_base.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except Exception:
                continue
        return total

    def _cleanup_if_needed(self) -> None:
        """
        Trigger cleanup if cache exceeds cleanup threshold.

        Strategy:
        - Compute total size, if > CLEANUP_ON_SIZE_PERCENT * max_size_bytes then:
            - Build list of candidate files (thumbnail files)
            - Sort by last access time (oldest first)
            - Delete files until usage < target_size (target = max_size_bytes * 0.8)
            - Stop after EVICTION_BATCH_SIZE deletions to avoid long blocking operations
        """
        try:
            total = self._get_total_cache_size()
            threshold = int(self.max_size_bytes * self.CLEANUP_ON_SIZE_PERCENT)
            if total <= threshold:
                return

            target = int(self.max_size_bytes * 0.80)  # aim to drop to 80% of max size
            # Collect candidate files (only thumbnail files, not metadata)
            candidates = []
            for size_dir in self.thumb_base.iterdir():
                if not size_dir.is_dir():
                    continue
                for f in size_dir.iterdir():
                    if not f.is_file():
                        continue
                    if f.name.endswith(".meta.json"):
                        continue
                    try:
                        atime = f.stat().st_atime
                        fsize = f.stat().st_size
                        candidates.append((atime, f, fsize))
                    except Exception:
                        continue

            # Sort oldest access first
            candidates.sort(key=lambda x: x[0])
            deleted_bytes = 0
            deleted_count = 0
            for atime, fpath, fsize in candidates:
                # Delete the thumbnail and its meta if present
                try:
                    meta = fpath.with_suffix(".meta.json")  # because fpath is *.jpg
                    # Delete file
                    fpath.unlink(missing_ok=True) if hasattr(fpath, "unlink") else fpath.unlink()
                    if meta.exists():
                        meta.unlink(missing_ok=True) if hasattr(meta, "unlink") else meta.unlink()
                    deleted_bytes += fsize
                    deleted_count += 1
                except Exception:
                    # ignore failures and continue
                    continue

                total -= fsize
                if total <= target or deleted_count >= self.EVICTION_BATCH_SIZE:
                    break

            logger.info("Cache cleanup removed %d entries, freed %d bytes", deleted_count, deleted_bytes)
        except Exception as e:
            logger.exception("Error during cache cleanup: %s", e)

# End of file