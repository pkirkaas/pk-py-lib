"""
src/pk_py_lib/core/flat_cache.py
Implements the FlatCacheManager for fast, file-based metadata caching using SQLite.

This cache stores computed hashes and quality scores for individual files,
validating entries against current file system statistics (size, modification date, inode)
to ensure cache freshness.
"""

from __future__ import annotations

import sqlite3
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .utils import get_data_dir # Import the unified path function

# --- Configuration and Constants ---

# Default location for the flat cache database file
# This is now resolved relative to the application's unified data directory
DEFAULT_DB_NAME = "flat_cache.db"
TABLE_NAME = "flat_cache_entries"
CURRENT_ENTRY_VERSION = 1

# --- Exceptions ---

class FlatCacheError(Exception):
    """Base exception for FlatCache module errors."""
    pass

class FlatCacheDBError(FlatCacheError):
    """
    Raised when a database operation fails unexpectedly.

    Args:
        message (str): Descriptive message about the DB failure.
        original_error (Exception, optional): The underlying sqlite3.Error or other exception.
    """
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error

class FlatCacheValidationError(FlatCacheError):
    """
    Raised when a cached entry fails validation against current file stats.

    Attributes:
        file_path (str): The path of the file that failed validation.
        mismatches (Dict[str, Any]): Dictionary detailing which fields mismatched.
    """
    def __init__(self, file_path: str, mismatches: Dict[str, Any]):
        super().__init__(f"Cache validation failed for {file_path}. Mismatches: {mismatches}")
        self.file_path = file_path
        self.mismatches = mismatches

# --- Data Structure ---

@dataclass
class FlatCacheEntry:
    """
    Represents a single entry in the flat cache database.

    Attributes:
        file (str): Normalized full file path (PRIMARY KEY).
        size (int): File size in bytes.
        mod_date (int): Unix timestamp of modification time (mtime).
        file_inode (str): Inode number (or equivalent string representation).
        file_device (str): Device ID (or equivalent string representation).
        blake3_hash (Optional[str]): Blake3 hash value.
        xxh3_hash (Optional[str]): XXH3 hash value.
        phash (Optional[str]): Perceptual hash (pHash).
        whash (Optional[str]): Wavelet hash (wHash).
        color_phash (Optional[str]): Color perceptual hash.
        brisque_score (Optional[float]): BRISQUE image quality score.
        niqe_score (Optional[float]): NIQE image quality score.
        piqe_score (Optional[float]): PIQE image quality score.
        quality_algorithm (Optional[str]): Algorithm used for quality score calculation.
        computed_at (int): Unix timestamp of last update.
        entry_version (int): Schema version of the entry.
    """
    file: str
    size: int
    mod_date: int
    file_inode: str
    file_device: str
    blake3_hash: Optional[str] = None
    xxh3_hash: Optional[str] = None
    phash: Optional[str] = None
    whash: Optional[str] = None
    color_phash: Optional[str] = None
    brisque_score: Optional[float] = None
    niqe_score: Optional[float] = None
    piqe_score: Optional[float] = None
    quality_algorithm: Optional[str] = None
    computed_at: int = 0
    entry_version: int = CURRENT_ENTRY_VERSION

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> FlatCacheEntry:
        """
        Creates a FlatCacheEntry instance from a sqlite3.Row object.

        Parameters:
            row (sqlite3.Row): The database row fetched from SQLite.

        Returns:
            FlatCacheEntry: An instance populated with data from the row.
        """
        # Convert sqlite3.Row to dict, then filter out keys not in dataclass fields
        data = dict(row)
        field_names = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered_data)

# --- SQL Schema ---

FLAT_CACHE_SCHEMA = f"""
-- Flat Cache DB schema for file metadata, hashes, and quality scores
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    file TEXT PRIMARY KEY NOT NULL,
    size INTEGER NOT NULL,
    mod_date INTEGER NOT NULL,
    file_inode TEXT NOT NULL,
    file_device TEXT NOT NULL,
    blake3_hash TEXT,
    xxh3_hash TEXT,
    phash TEXT,
    whash TEXT,
    color_phash TEXT,
    brisque_score REAL,
    niqe_score REAL,
    piqe_score REAL,
    quality_algorithm TEXT,
    computed_at INTEGER NOT NULL,
    entry_version INTEGER DEFAULT {CURRENT_ENTRY_VERSION}
);

-- Index for cleanup queries
CREATE INDEX IF NOT EXISTS idx_computed_at ON {TABLE_NAME} (computed_at);
"""

# --- Manager Class ---

class FlatCacheManager:
    """
    Manages the connection and operations for the flat file cache database.

    This cache is designed for high-speed lookups of computed file properties
    (hashes, quality scores) and includes built-in validation against file system
    metadata to ensure cache freshness.

    Example Usage:
        >>> from pathlib import Path
        >>> manager = FlatCacheManager() # Uses default path: Path.home() / '.pk_py_lib' / 'flat_cache.db'
        >>> # Assuming a file exists at '/path/to/image.jpg'
        >>> entry = manager.get_entry('/path/to/image.jpg')
        >>> if entry is None:
        >>>     # Compute hashes/scores
        >>>     new_entry = FlatCacheEntry(file='/path/to/image.jpg', size=100, mod_date=12345, file_inode='1', file_device='1', phash='abc')
        >>>     manager.set_entry(new_entry)
    """

    def __init__(self, db_path: Optional[Path | str] = None, logger: Optional[logging.Logger] = None):
        """
        Initializes the FlatCacheManager.

        Parameters:
            db_path (Optional[Path | str]): The full path to the SQLite database file.
                                            Defaults to Path.home() / '.pk_py_lib' / DEFAULT_DB_NAME.
            logger (Optional[logging.Logger]): Custom logger instance. Defaults to
                                               'pk_py_lib.core.flat_cache'.
        """
        if db_path is None:
            # Default to unified application data directory location
            db_path = get_data_dir() / DEFAULT_DB_NAME
        elif isinstance(db_path, str):
            db_path = Path(db_path)

        self.db_path = db_path.resolve()
        self.logger = logger if logger else logging.getLogger("pk_py_lib.core.flat_cache")
        self.table_name = TABLE_NAME

        self._initialize_db()

    @contextmanager
    def _get_connection(self) -> sqlite3.Connection:
        """
        Context manager yielding a sqlite3.Connection with automatic commit/rollback,
        WAL mode, and row factory set to sqlite3.Row.

        Yields:
            sqlite3.Connection: An active database connection.

        Raises:
            FlatCacheDBError: If a database error occurs during connection or transaction.
        """
        conn = None
        try:
            # Use a timeout for better handling of concurrent access
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            # Enforce foreign keys (good practice)
            conn.execute("PRAGMA foreign_keys = ON")
            # Enable Write-Ahead Logging for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"SQLite error during transaction: {e}", exc_info=True)
            if conn:
                conn.rollback()
            raise FlatCacheDBError(f"Database operation failed: {e}", original_error=e)
        except Exception as e:
            self.logger.error(f"Unexpected error during transaction: {e}", exc_info=True)
            if conn:
                conn.rollback()
            raise FlatCacheDBError(f"Unexpected error: {e}", original_error=e)
        finally:
            if conn:
                conn.close()

    def _initialize_db(self) -> None:
        """
        Ensures the database file exists and the required table is created.

        Raises:
            FlatCacheDBError: If table creation fails.
        """
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Initializing flat cache database at {self.db_path}")
            with self._get_connection() as conn:
                conn.executescript(FLAT_CACHE_SCHEMA)
                self.logger.debug(f"Table {self.table_name} ensured.")
        except FlatCacheDBError as e:
            self.logger.critical(f"Failed to initialize flat cache database: {e}")
            raise

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """
        Normalizes a file path to a canonical, absolute, POSIX-style string for consistent storage.

        Parameters:
            file_path (str): The input file path.

        Returns:
            str: The normalized POSIX path.
        """
        return Path(file_path).resolve().as_posix()

    @staticmethod
    def _get_file_stats(file_path: str) -> Tuple[int, int, str, str]:
        """
        Retrieves size, modification date (mtime), inode, and device ID for a file.

        Parameters:
            file_path (str): The path to the file.

        Returns:
            Tuple[int, int, str, str]: (size, mod_date, file_inode, file_device)
        
        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If file stats cannot be read.
        """
        try:
            stat_result = os.stat(file_path)
            # Use str() for inode and device to ensure cross-platform compatibility
            # (Windows inodes/devices might be less meaningful but we store them anyway)
            return (
                stat_result.st_size,
                int(stat_result.st_mtime),
                str(stat_result.st_ino),
                str(stat_result.st_dev)
            )
        except FileNotFoundError:
            raise
        except Exception as e:
            # Catch all other os.stat errors (e.g., permission denied)
            raise PermissionError(f"Could not read stats for {file_path}: {e}") from e

    def _validate_entry(self, entry: FlatCacheEntry) -> bool:
        """
        Validates a cached entry against the current file system statistics.

        Parameters:
            entry (FlatCacheEntry): The cached entry to validate.

        Returns:
            bool: True if the entry is valid.

        Raises:
            FlatCacheValidationError: If validation fails, providing mismatch details.
        """
        file_path = entry.file
        
        try:
            current_size, current_mtime, current_inode, current_device = self._get_file_stats(file_path)
        except FileNotFoundError:
            self.logger.debug(f"Validation failed: File not found: {file_path}")
            raise FlatCacheValidationError(file_path, {"existence": "File not found"})
        except PermissionError as e:
            self.logger.warning(f"Validation skipped due to permission error: {file_path}. Error: {e}")
            # Treat permission errors as validation failure to force recomputation if needed
            raise FlatCacheValidationError(file_path, {"permission": str(e)})

        mismatches = {}

        # 1. Size check
        if current_size != entry.size:
            mismatches["size"] = f"Cached: {entry.size}, Current: {current_size}"

        # 2. Modification date check (mtime)
        # Note: mtime comparison should be exact for cache validation
        if current_mtime != entry.mod_date:
            mismatches["mod_date"] = f"Cached: {entry.mod_date}, Current: {current_mtime}"

        # 3. Inode check (robust check for file identity)
        if current_inode != entry.file_inode:
            mismatches["file_inode"] = f"Cached: {entry.file_inode}, Current: {current_inode}"

        # 4. Device check (useful for detecting moves across filesystems)
        if current_device != entry.file_device:
            mismatches["file_device"] = f"Cached: {entry.file_device}, Current: {current_device}"

        if mismatches:
            self.logger.warning(f"Cache miss (validation failed) for {file_path}. Mismatches: {mismatches}")
            raise FlatCacheValidationError(file_path, mismatches)
        
        self.logger.debug(f"Cache hit (validation successful) for {file_path}")
        return True

    def get_entry(self, file_path: str) -> Optional[FlatCacheEntry]:
        """
        Queries the cache for an entry and validates it against current file stats.

        Parameters:
            file_path (str): The path to the file.

        Returns:
            Optional[FlatCacheEntry]: The valid entry, or None if not found or invalid.
        """
        normalized_path = self._normalize_path(file_path)
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    f"SELECT * FROM {self.table_name} WHERE file = ?", 
                    (normalized_path,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    self.logger.debug(f"Cache miss (not found) for {normalized_path}")
                    return None
                
                entry = FlatCacheEntry.from_row(row)
                
                # Validate the retrieved entry against the current file system state
                self._validate_entry(entry)
                
                return entry

        except FlatCacheValidationError:
            # Validation failed (file changed or missing). Logged inside _validate_entry.
            return None
        except FlatCacheDBError as e:
            self.logger.error(f"DB error retrieving entry for {normalized_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in get_entry for {normalized_path}: {e}", exc_info=True)
            return None

    def set_entry(self, entry: FlatCacheEntry) -> bool:
        """
        Inserts or replaces a cache entry (UPSERT).

        The entry's 'file' path must be normalized before calling this method.
        It automatically updates 'computed_at' and ensures file stats are current.

        Parameters:
            entry (FlatCacheEntry): The entry to store.

        Returns:
            bool: True if the operation succeeded, False otherwise.
        """
        # Ensure path is normalized and update dynamic fields
        entry.file = self._normalize_path(entry.file)
        entry.computed_at = int(time.time())
        
        # Update file stats just before saving to ensure consistency
        try:
            size, mtime, inode, device = self._get_file_stats(entry.file)
            entry.size = size
            entry.mod_date = mtime
            entry.file_inode = inode
            entry.file_device = device
        except (FileNotFoundError, PermissionError) as e:
            self.logger.warning(f"Cannot set entry for non-existent or inaccessible file {entry.file}: {e}")
            return False

        data = asdict(entry)
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        values = tuple(data.values())

        sql = f"""
        INSERT OR REPLACE INTO {self.table_name} ({columns})
        VALUES ({placeholders})
        """
        
        try:
            with self._get_connection() as conn:
                conn.execute(sql, values)
            self.logger.info(f"Cache entry set/updated for {entry.file}")
            return True
        except FlatCacheDBError as e:
            self.logger.error(f"DB error setting entry for {entry.file}: {e}")
            return False

    def invalidate_entry(self, file_path: str) -> bool:
        """
        Deletes a cache entry by its normalized file path.

        Parameters:
            file_path (str): The path to the file.

        Returns:
            bool: True if the operation succeeded (entry deleted or not found), False on DB error.
        """
        normalized_path = self._normalize_path(file_path)
        sql = f"DELETE FROM {self.table_name} WHERE file = ?"
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (normalized_path,))
                deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                self.logger.info(f"Cache entry invalidated for {normalized_path}")
            else:
                self.logger.debug(f"Cache entry not found for invalidation: {normalized_path}")
            
            return True
        except FlatCacheDBError as e:
            self.logger.error(f"DB error invalidating entry for {normalized_path}: {e}")
            return False

    def batch_set(self, entries: List[FlatCacheEntry]) -> int:
        """
        Performs a transactional batch insert or replace (UPSERT) of cache entries.

        Automatically normalizes paths, updates computed_at, and fetches current file stats
        for each entry before insertion. Entries for inaccessible files are skipped.

        Parameters:
            entries (List[FlatCacheEntry]): A list of entries to store.

        Returns:
            int: The number of entries successfully inserted/updated.
        """
        if not entries:
            return 0

        data_to_insert = []
        
        # Prepare data: normalize path, update computed_at, fetch stats
        for entry in entries:
            entry.file = self._normalize_path(entry.file)
            entry.computed_at = int(time.time())
            
            try:
                size, mtime, inode, device = self._get_file_stats(entry.file)
                entry.size = size
                entry.mod_date = mtime
                entry.file_inode = inode
                entry.file_device = device
                
                data = asdict(entry)
                data_to_insert.append(tuple(data.values()))
            except (FileNotFoundError, PermissionError) as e:
                self.logger.warning(f"Skipping batch set for {entry.file}: File inaccessible or missing. Error: {e}")
                continue

        if not data_to_insert:
            self.logger.info("Batch set completed: 0 entries successfully prepared for insertion.")
            return 0

        # Assuming all entries have the same structure (based on FlatCacheEntry dataclass)
        # We must use the keys from the dataclass definition to ensure correct column order
        sample_entry = entries[0]
        columns = ', '.join(asdict(sample_entry).keys())
        placeholders = ', '.join(['?'] * len(asdict(sample_entry)))
        
        sql = f"""
        INSERT OR REPLACE INTO {self.table_name} ({columns})
        VALUES ({placeholders})
        """

        try:
            with self._get_connection() as conn:
                conn.executemany(sql, data_to_insert)
                # Note: conn.total_changes is unreliable for counting UPSERTs in executemany
                # We return the count of prepared entries instead.
            
            self.logger.info(f"Batch set completed: {len(data_to_insert)} entries inserted/updated.")
            return len(data_to_insert)
        except FlatCacheDBError as e:
            self.logger.error(f"DB error during batch set: {e}")
            return 0

    def get_uncached_files(self, paths: List[str]) -> List[str]:
        """
        Identifies which files in the provided list are either missing from the cache
        or have an invalid (stale) cache entry.

        Parameters:
            paths (List[str]): A list of file paths to check.

        Returns:
            List[str]: A list of normalized file paths that need recomputation.
        """
        if not paths:
            return []

        normalized_paths = [self._normalize_path(p) for p in paths]
        uncached_paths = []
        
        # 1. Query all existing entries for the given paths
        placeholders = ', '.join(['?'] * len(normalized_paths))
        sql = f"SELECT * FROM {self.table_name} WHERE file IN ({placeholders})"
        
        cached_entries: Dict[str, FlatCacheEntry] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, normalized_paths)
                for row in cursor.fetchall():
                    entry = FlatCacheEntry.from_row(row)
                    cached_entries[entry.file] = entry
        except FlatCacheDBError as e:
            self.logger.error(f"DB error during get_uncached_files query: {e}")
            # If DB fails, assume all files need recomputation
            return normalized_paths

        # 2. Check for missing paths (not in cached_entries)
        for path in normalized_paths:
            if path not in cached_entries:
                uncached_paths.append(path)
                self.logger.debug(f"Uncached: File not found in DB: {path}")

        # 3. Validate existing entries
        for path, entry in cached_entries.items():
            try:
                self._validate_entry(entry)
            except FlatCacheValidationError:
                # Validation failed (logged inside _validate_entry)
                uncached_paths.append(path)
            except Exception as e:
                self.logger.error(f"Unexpected error during validation of {path}: {e}", exc_info=True)
                uncached_paths.append(path) # Treat unexpected errors as cache miss

        self.logger.info(f"Found {len(uncached_paths)} files requiring recomputation out of {len(paths)} checked.")
        return uncached_paths

    def cleanup_old_entries(self, days: int = 30) -> int:
        """
        Deletes cache entries older than the specified number of days.

        Parameters:
            days (int): The age threshold in days. Defaults to 30 days.

        Returns:
            int: The number of entries deleted.
        """
        if days <= 0:
            self.logger.warning("Cleanup skipped: 'days' parameter must be positive.")
            return 0

        # Calculate the Unix timestamp threshold
        threshold = int(time.time()) - (days * 24 * 60 * 60)
        
        sql = f"DELETE FROM {self.table_name} WHERE computed_at < ?"
        
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (threshold,))
                deleted_count = cursor.rowcount
            
            self.logger.info(f"Cleanup completed: Deleted {deleted_count} entries older than {days} days.")
            return deleted_count
        except FlatCacheDBError as e:
            self.logger.error(f"DB error during cleanup: {e}")
            return 0

    def get_all_hashes_by_algorithm(self, algorithm: str) -> Dict[str, str]:
        """
        Queries all file paths and their corresponding hash values for a specific algorithm.

        The algorithm name must match one of the hash columns in FlatCacheEntry 
        (e.g., 'phash', 'blake3_hash', 'xxh3_hash').

        Parameters:
            algorithm (str): The name of the hash column to retrieve.

        Returns:
            Dict[str, str]: A dictionary mapping normalized file paths to hash strings.
        
        Raises:
            FlatCacheError: If the algorithm name is not a valid hash column.
        """
        valid_hash_columns = [
            'blake3_hash', 'xxh3_hash', 'phash', 'whash', 'color_phash'
        ]
        
        if algorithm not in valid_hash_columns:
            raise FlatCacheError(f"Invalid hash algorithm specified: {algorithm}. Must be one of {valid_hash_columns}")

        # Use the column name directly in the SQL query
        sql = f"SELECT file, {algorithm} FROM {self.table_name} WHERE {algorithm} IS NOT NULL"
        
        results: Dict[str, str] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql)
                for row in cursor.fetchall():
                    # Access the columns by name
                    results[row['file']] = row[algorithm]
            
            self.logger.debug(f"Retrieved {len(results)} entries for algorithm '{algorithm}'.")
            return results
        except FlatCacheDBError as e:
            self.logger.error(f"DB error retrieving hashes for algorithm {algorithm}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Unexpected error retrieving hashes for algorithm {algorithm}: {e}", exc_info=True)
            return {}

# Example Usage (for documentation/testing purposes)
if __name__ == '__main__':
    # Setup basic logging for standalone test
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Use a temporary file-based database for testing persistence and file stats
    # Note: For __main__ test, we still use a temporary path to ensure cleanup.
    db_path = Path("./test_flat_cache.db").resolve()
    
    # Create a dummy file for testing stats validation
    test_file_path = Path("./temp_test_file.txt").resolve()
    
    print(f"--- Starting FlatCacheManager Test (DB: {db_path.name}) ---")
    
    try:
        # Ensure the test file exists
        test_file_path.write_text("Initial content")
        initial_stats = os.stat(test_file_path)
        
        manager = FlatCacheManager(db_path=db_path) # Explicit path for test cleanup
        
        # 1. Create a new entry
        new_entry = FlatCacheEntry(
            file=test_file_path.as_posix(),
            size=initial_stats.st_size,
            mod_date=int(initial_stats.st_mtime),
            file_inode=str(initial_stats.st_ino),
            file_device=str(initial_stats.st_dev),
            blake3_hash="hash_123",
            phash="p_hash_abc",
            computed_at=int(time.time())
        )
        print(f"\n--- Setting initial entry for {test_file_path.name} ---")
        manager.set_entry(new_entry)
        
        # 2. Get valid entry (Cache Hit)
        print("\n--- Attempting Cache Hit ---")
        retrieved_entry = manager.get_entry(test_file_path.as_posix())
        print(f"Retrieved Hash: {retrieved_entry.blake3_hash if retrieved_entry else 'None'}")
        
        # 3. Invalidate entry by modifying the file (Cache Miss)
        print("\n--- Modifying file to cause Cache Miss ---")
        time.sleep(0.1) # Ensure mtime changes
        test_file_path.write_text("Modified content with different size and mtime")
        
        retrieved_entry_stale = manager.get_entry(test_file_path.as_posix())
        print(f"Retrieved Hash (stale): {retrieved_entry_stale.blake3_hash if retrieved_entry_stale else 'None'}")
        
        # 4. Get uncached files
        print("\n--- Getting uncached files ---")
        uncached = manager.get_uncached_files([test_file_path.as_posix(), "/non/existent/file.jpg"])
        print(f"Uncached paths: {uncached}")
        
        # 5. Cleanup (should delete nothing yet)
        print("\n--- Running Cleanup (0 days) ---")
        deleted = manager.cleanup_old_entries(days=0)
        print(f"Deleted entries: {deleted}")
        
        # 6. Batch set (re-cache the modified file)
        print("\n--- Batch setting modified entry ---")
        modified_stats = os.stat(test_file_path)
        modified_entry = FlatCacheEntry(
            file=test_file_path.as_posix(),
            size=modified_stats.st_size,
            mod_date=int(modified_stats.st_mtime),
            file_inode=str(modified_stats.st_ino),
            file_device=str(modified_stats.st_dev),
            blake3_hash="hash_456",
            phash="p_hash_def",
            computed_at=int(time.time())
        )
        manager.batch_set([modified_entry])
        
        # 7. Get all hashes by algorithm
        print("\n--- Getting all pHashes ---")
        phash_map = manager.get_all_hashes_by_algorithm('phash')
        print(f"pHashes found: {phash_map}")
        
        # 8. Invalidate explicitly
        print("\n--- Invalidating explicitly ---")
        manager.invalidate_entry(test_file_path.as_posix())
        
        retrieved_after_delete = manager.get_entry(test_file_path.as_posix())
        print(f"Retrieved Hash after delete: {retrieved_after_delete.blake3_hash if retrieved_after_delete else 'None'}")

    finally:
        # Clean up dummy file and database files
        if test_file_path.exists():
            os.remove(test_file_path)
        
        # Clean up DB files (main file, WAL, and SHM)
        if db_path.exists():
            os.remove(db_path)
        if db_path.with_suffix(".db-wal").exists():
            os.remove(db_path.with_suffix(".db-wal"))
        if db_path.with_suffix(".db-shm").exists():
            os.remove(db_path.with_suffix(".db-shm"))
            
        print(f"\nCleaned up test artifacts.")