"""
Simplified flat file cache manager.

This module provides basic caching for image hashes and metadata
with simple versioning and size monitoring.
"""

import os
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional, Dict, List
from dataclasses import dataclass
import logging

from .api.response import ApiResponse, ErrorCode


@dataclass
class FlatCacheEntry:
    """Cache entry for file metadata and hashes."""

    path: str
    size: int
    mtime: float
    width: Optional[int] = None
    height: Optional[int] = None
    is_valid: bool = True
    xxh3: Optional[str] = None
    phash: Optional[str] = None
    brisque: Optional[float] = None
    whash: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0


class FlatCacheManager:
    """
    Simplified flat cache manager.

    Provides basic caching functionality without complex eviction policies
    or size limits. Includes simple versioning and size monitoring.
    """

    # Current cache version - increment to force cache rebuild
    CURRENT_VERSION = 1

    # Size warning threshold (100 GB in bytes)
    SIZE_WARNING_THRESHOLD = 100 * 1024 * 1024 * 1024

    def __init__(self, db_path: Optional[Path | str] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize simplified cache manager.

        Args:
            db_path: Path to cache database file
            logger: Logger instance
        """
        if db_path is None:
            from .utils import get_data_dir
            db_path = get_data_dir() / "flat_cache.db"
        elif isinstance(db_path, str):
            db_path = Path(db_path)

        self.db_path = db_path.resolve()
        self.data_dir = self.db_path.parent
        self.logger = logger or logging.getLogger(__name__)

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database with version checking
        self._init_database()

        # Cache counters for basic statistics
        self._cache_hits = 0
        self._cache_misses = 0
        self._invalid_entries = 0

        self.logger.info(f"Flat cache initialized: {self.db_path}")

    def _init_database(self) -> None:
        """Initialize SQLite database with simple schema and version checking."""
        # Check if database exists and has compatible version
        needs_rebuild = False

        if self.db_path.exists():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
                    version = cursor.fetchone()[0]
                    if version != self.CURRENT_VERSION:
                        self.logger.info(f"Cache version changed from {version} to {self.CURRENT_VERSION}, rebuilding cache")
                        needs_rebuild = True
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                # Database doesn't have version table or is corrupted
                self.logger.warning("Cache database missing version table or corrupted, rebuilding")
                needs_rebuild = True

        if needs_rebuild:
            # Remove old database
            if self.db_path.exists():
                self.db_path.unlink()
                self.logger.info("Removed old cache database")

        # Create fresh database
        with sqlite3.connect(self.db_path) as conn:
            # Create cache entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS flat_cache_entries (
                    path TEXT PRIMARY KEY NOT NULL,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    is_valid INTEGER NOT NULL DEFAULT 1,
                    xxh3 TEXT,
                    phash TEXT,
                    whash TEXT,
                    brisque REAL,
                    created_at REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0
                )
            """)

            # Create basic indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_size ON flat_cache_entries (size)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON flat_cache_entries (updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_is_valid ON flat_cache_entries (is_valid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_xxh3 ON flat_cache_entries (xxh3)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phash ON flat_cache_entries (phash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_whash ON flat_cache_entries (whash)")

            # Create version table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)

            # Set current version
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                        (self.CURRENT_VERSION,))

            conn.commit()

        # Check database size and warn if needed
        self._check_database_size()

    def _check_database_size(self) -> None:
        """Check database size and issue warning if exceeds threshold."""
        try:
            db_size = self.db_path.stat().st_size
            if db_size > self.SIZE_WARNING_THRESHOLD:
                size_gb = db_size / (1024 * 1024 * 1024)
                self.logger.warning(
                    f"Cache database size ({size_gb:.2f} GB) exceeds 100 GB threshold. "
                    f"Consider cleaning the cache if performance is affected."
                )
        except OSError as e:
            self.logger.warning(f"Failed to check database size: {e}")

    def get_hashes(self, file_paths: List[str], hash_types: List[str] = ['phash'],
                   search_type: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Get hashes for files from cache.

        Args:
            file_paths: List of file paths to get hashes for
            hash_types: List of hash types to retrieve
            search_type: Type of search (not used in simplified version)

        Returns:
            Dictionary mapping file paths to hash dictionaries
        """
        results = {}

        for path in file_paths:
            path_results = {}
            entry = self.get_entry(path)

            if entry:
                self._cache_hits += 1

                # Extract requested hash types
                for hash_type in hash_types:
                    if hasattr(entry, hash_type):
                        path_results[hash_type] = getattr(entry, hash_type)
                    else:
                        path_results[hash_type] = None
            else:
                self._cache_misses += 1

                # Return None for all hash types when entry not found
                for hash_type in hash_types:
                    path_results[hash_type] = None

            results[path] = path_results

        return results

    def get_entry(self, file_path: str) -> Optional[FlatCacheEntry]:
        """
        Get cache entry for a file.

        Args:
            file_path: Path to the file

        Returns:
            FlatCacheEntry if found, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT path, size, mtime, width, height, is_valid,
                           xxh3, phash, whash, brisque, created_at, updated_at
                    FROM flat_cache_entries
                    WHERE path = ?
                """, (file_path,))

                row = cursor.fetchone()
                if row:
                    return FlatCacheEntry(
                        path=row[0],
                        size=row[1],
                        mtime=row[2],
                        width=row[3],
                        height=row[4],
                        is_valid=bool(row[5]),
                        xxh3=row[6],
                        phash=row[7],
                        whash=row[8],
                        brisque=row[9],
                        created_at=row[10],
                        updated_at=row[11]
                    )
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            self.logger.error(f"Database error getting entry for {file_path}: {e}")

        return None

    def set_entry(self, entry: FlatCacheEntry, search_type: Optional[str] = None) -> bool:
        """
        Set cache entry for a file.

        Args:
            entry: FlatCacheEntry to store
            search_type: Type of search (not used in simplified version)

        Returns:
            True if successful, False otherwise
        """
        try:
            import time
            current_time = time.time()

            # Set timestamps
            if entry.created_at == 0.0:
                entry.created_at = current_time
            entry.updated_at = current_time

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO flat_cache_entries
                    (path, size, mtime, width, height, is_valid,
                     xxh3, phash, whash, brisque, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.path,
                    entry.size,
                    entry.mtime,
                    entry.width,
                    entry.height,
                    int(entry.is_valid),
                    entry.xxh3,
                    entry.phash,
                    entry.whash,
                    entry.brisque,
                    entry.created_at,
                    entry.updated_at
                ))
                conn.commit()

            # Check size after insertion
            self._check_database_size()
            return True

        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            self.logger.error(f"Database error setting entry for {entry.path}: {e}")
            return False

    def reset_counters(self) -> None:
        """Reset cache statistics counters."""
        self._cache_hits = 0
        self._cache_misses = 0
        self._invalid_entries = 0

    def get_counters(self) -> dict[str, int]:
        """Get cache statistics counters."""
        return {
            'hits': self._cache_hits,
            'misses': self._cache_misses,
            'invalid_entries': self._invalid_entries
        }

    def clear_cache(self) -> None:
        """Clear all cache entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM flat_cache_entries")
                conn.commit()
            self.logger.info("Cache cleared")
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            self.logger.error(f"Database error clearing cache: {e}")

    def clean_cache(self) -> int:
        """
        Clean cache by removing invalid entries.

        Returns:
            Number of entries cleaned
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM flat_cache_entries WHERE is_valid = 0")
                deleted_count = cursor.rowcount
                conn.commit()

            if deleted_count > 0:
                self.logger.info(f"Cleaned {deleted_count} invalid cache entries")

            return deleted_count

        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            self.logger.error(f"Database error cleaning cache: {e}")
            return 0

    def get_cache_info(self) -> Dict[str, Any]:
        """Get basic cache information."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Get total entries
                cursor = conn.execute("SELECT COUNT(*) FROM flat_cache_entries")
                total_entries = cursor.fetchone()[0]

                # Get valid entries
                cursor = conn.execute("SELECT COUNT(*) FROM flat_cache_entries WHERE is_valid = 1")
                valid_entries = cursor.fetchone()[0]

                # Get database size
                db_size = self.db_path.stat().st_size

                return {
                    'total_entries': total_entries,
                    'valid_entries': valid_entries,
                    'invalid_entries': total_entries - valid_entries,
                    'database_size_bytes': db_size,
                    'database_size_mb': db_size / (1024 * 1024),
                    'cache_version': self.CURRENT_VERSION,
                    'counters': self.get_counters()
                }

        except (sqlite3.OperationalError, sqlite3.DatabaseError, OSError) as e:
            self.logger.error(f"Error getting cache info: {e}")
            return {
                'error': str(e),
                'total_entries': 0,
                'valid_entries': 0,
                'invalid_entries': 0,
                'database_size_bytes': 0,
                'database_size_mb': 0,
                'cache_version': self.CURRENT_VERSION,
                'counters': self.get_counters()
            }

    def _get_file_stats(self, file_path: str) -> tuple[int, float]:
        """
        Get file statistics (size and modification time) for a file.

        This method is used by image quality evaluators to create new cache entries
        when an existing entry is not found or is invalid.

        Args:
            file_path: Path to the file

        Returns:
            Tuple of (size, mtime) where:
            - size: File size in bytes
            - mtime: File modification time as a float timestamp

        Raises:
            OSError: If the file doesn't exist or cannot be accessed
        """
        try:
            stat_info = os.stat(file_path)
            return stat_info.st_size, stat_info.st_mtime
        except OSError as e:
            self.logger.error(f"Failed to get file stats for {file_path}: {e}")
            raise

    def populate_cache_for_files(
        self,
        file_paths: List[str],
        compute_hashes: bool = True,
        compute_metadata: bool = True
    ) -> Dict[str, Any]:
        """
        Populate cache entries for a list of file paths.

        This method addresses the critical issues where:
        1. Directories and drives were being cached inappropriately
        2. XXH3 values were missing for all files
        3. Image-specific metadata was missing for image files

        Args:
            file_paths: List of file paths to process
            compute_hashes: Whether to compute perceptual hashes for images
            compute_metadata: Whether to compute image metadata

        Returns:
            Dictionary with processing results and statistics
        """
        from pk_py_lib.core.filesystem.identity import compute_xxh3
        from pk_py_lib.core.image.similarity.validation import is_image_extension
        from pk_py_lib.core.image.similarity.metadata import get_image_metadata
        from pk_py_lib.core.image.similarity.hashing import compute_phash, compute_whash

        results = {
            'processed': 0,
            'entries_created': 0,
            'entries_updated': 0,
            'skipped_directories': 0,
            'skipped_non_files': 0,
            'errors': [],
            'xxh3_computed': 0,
            'phash_computed': 0,
            'whash_computed': 0,
            'metadata_computed': 0
        }

        self.logger.info(f"Starting cache population for {len(file_paths)} files")

        for file_path in file_paths:
            try:
                # CRITICAL FIX: Skip directories and drives - only process actual files
                if not os.path.isfile(file_path):
                    if os.path.isdir(file_path):
                        results['skipped_directories'] += 1
                        self.logger.debug(f"Skipped directory: {file_path}")
                    else:
                        results['skipped_non_files'] += 1
                        self.logger.debug(f"Skipped non-file: {file_path}")
                    continue

                # Get file stats
                stat_info = os.stat(file_path)
                size = stat_info.st_size
                mtime = stat_info.st_mtime

                # Skip empty files
                if size == 0:
                    self.logger.debug(f"Skipped empty file: {file_path}")
                    continue

                # Check if entry already exists and is valid
                existing_entry = self.get_entry(file_path)
                if existing_entry and existing_entry.size == size and existing_entry.mtime == mtime:
                    self.logger.debug(f"Entry already exists and is valid: {file_path}")
                    results['processed'] += 1
                    continue

                # Create new entry
                entry = FlatCacheEntry(
                    path=file_path,
                    size=size,
                    mtime=mtime,
                    is_valid=True
                )

                # CRITICAL FIX: Compute XXH3 hash for ALL files (not just images)
                try:
                    from pathlib import Path
                    entry.xxh3 = compute_xxh3(Path(file_path))
                    results['xxh3_computed'] += 1
                    self.logger.debug(f"Computed XXH3 for {file_path}: {entry.xxh3[:16] if entry.xxh3 else None}...")
                except Exception as e:
                    self.logger.warning(f"Failed to compute XXH3 for {file_path}: {e}")
                    entry.xxh3 = None

                # CRITICAL FIX: Compute image-specific metadata for image files only
                if is_image_extension(file_path):
                    try:
                        # Get image metadata (includes dimensions)
                        if compute_metadata:
                            metadata = get_image_metadata(file_path, search_type='similarity')
                            if metadata.get('resolution') != "Unknown":
                                # Parse resolution string "WxH"
                                try:
                                    width_str, height_str = metadata['resolution'].split('x')
                                    entry.width = int(width_str)
                                    entry.height = int(height_str)
                                    results['metadata_computed'] += 1
                                except (ValueError, AttributeError):
                                    entry.width = None
                                    entry.height = None
                    except Exception as e:
                        self.logger.warning(f"Failed to get metadata for {file_path}: {e}")

                    # Compute perceptual hashes for images
                    if compute_hashes:
                        try:
                            entry.phash = compute_phash(file_path)
                            results['phash_computed'] += 1
                            self.logger.debug(f"Computed pHash for {file_path}: {entry.phash}")
                        except Exception as e:
                            self.logger.warning(f"Failed to compute pHash for {file_path}: {e}")
                            entry.phash = None

                        try:
                            entry.whash = compute_whash(file_path)
                            results['whash_computed'] += 1
                            self.logger.debug(f"Computed wHash for {file_path}: {entry.whash}")
                        except Exception as e:
                            self.logger.warning(f"Failed to compute wHash for {file_path}: {e}")
                            entry.whash = None

                # Store entry in cache
                if existing_entry:
                    # Update existing entry
                    if self.set_entry(entry):
                        results['entries_updated'] += 1
                        self.logger.debug(f"Updated cache entry for {file_path}")
                    else:
                        results['errors'].append(f"Failed to update cache entry for {file_path}")
                else:
                    # Create new entry
                    if self.set_entry(entry):
                        results['entries_created'] += 1
                        self.logger.debug(f"Created cache entry for {file_path}")
                    else:
                        results['errors'].append(f"Failed to store cache entry for {file_path}")

                results['processed'] += 1

            except Exception as e:
                results['errors'].append(f"Error processing {file_path}: {e}")
                self.logger.error(f"Error processing {file_path}: {e}")

        # Log summary
        self.logger.info(f"Cache population complete: {results['processed']} processed, "
                        f"{results['entries_created']} created, {results['entries_updated']} updated, "
                        f"{results['skipped_directories']} directories skipped, "
                        f"{len(results['errors'])} errors")

        if results['errors']:
            self.logger.warning(f"Cache population errors: {results['errors']}")

        return results


# Exceptions for error handling
class FlatCacheError(Exception):
    """Base exception for FlatCache module errors."""
    pass


class FlatCacheDBError(FlatCacheError):
    """Database operation error."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class FlatCacheValidationError(FlatCacheError):
    """Cache validation error."""
    def __init__(self, file_path: str, mismatches: Dict[str, Any]):
        super().__init__(f"Cache validation failed for {file_path}. Mismatches: {mismatches}")
        self.file_path = file_path
        self.mismatches = mismatches


class CacheComputeError(FlatCacheError):
    """Hash computation error."""
    def __init__(self, file_path: str, hash_type: str, original_error: Exception):
        super().__init__(f"Failed to compute {hash_type} for {file_path}: {original_error}")
        self.file_path = file_path
        self.hash_type = hash_type
        self.original_error = original_error


# Constants
DEFAULT_DB_NAME = "flat_cache.db"
TABLE_NAME = "flat_cache_entries"
CURRENT_ENTRY_VERSION = 1
SCHEMA_VERSION = 1  # Simplified schema version
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heif', '.heic'}


# Syntax validation: This file has been reviewed for Python syntax correctness.
# Example Usage (for documentation/testing purposes)
if __name__ == '__main__':
    # Setup basic logging for standalone test
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Test simplified cache manager
    print("--- Testing Simplified FlatCacheManager ---")

    cache_manager = FlatCacheManager(db_path="./test_flat_cache.db")

    # Test basic operations
    print("Testing basic entry operations...")

    # Create a test entry
    import time
    test_entry = FlatCacheEntry(
        path="/test/image.jpg",
        size=1024,
        mtime=time.time(),
        width=1920,
        height=1080,
        is_valid=True,
        xxh3="test_xxh3_hash",
        phash="test_phash_hash"
    )

    # Store entry
    success = cache_manager.set_entry(test_entry)
    print(f"Store entry: {success}")

    # Retrieve entry
    retrieved_entry = cache_manager.get_entry("/test/image.jpg")
    if retrieved_entry:
        print(f"Retrieved entry: {retrieved_entry.path}, xxh3: {retrieved_entry.xxh3}")
    else:
        print("Entry not found")

    # Test hash retrieval
    hashes = cache_manager.get_hashes(["/test/image.jpg"], ["xxh3", "phash"])
    print(f"Retrieved hashes: {hashes}")

    # Test cache info
    info = cache_manager.get_cache_info()
    print(f"Cache info: {info}")

    # Test counters
    counters = cache_manager.get_counters()
    print(f"Cache counters: {counters}")

    print("\n--- Simplified cache test completed ---")
