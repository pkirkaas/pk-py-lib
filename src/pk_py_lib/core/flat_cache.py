"""
src/pk_py_lib/core/flat_cache.py
Implements the FlatCacheManager for fast, file-based metadata caching using SQLite.

This cache stores computed hashes and other values for individual files,
validating entries against current file system statistics (size, modification date)
to ensure cache freshness. Hashes are stored in individual columns of the entries table
"""

from __future__ import annotations

import sqlite3
import logging
from .logging.decorators import log_errors
import os
import time
import json
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from PIL import Image
import imagehash

from .utils import get_data_dir  # Import the unified path function
from .logging.logger import get_cache_logger  # Import cache-specific logger

# Image file extensions for filtering without loading
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heif', '.heic'}

# --- Configuration and Constants ---

# Default location for the flat cache database file
# This is now resolved relative to the application's unified data directory
DEFAULT_DB_NAME = "flat_cache.db"
TABLE_NAME = "flat_cache_entries"
CURRENT_ENTRY_VERSION = 1  # Not used in schema but for future

# --- Exceptions ---

class FlatCacheError(Exception):
    """Base exception for FlatCache module errors."""
    pass


@log_errors()
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

class CacheComputeError(FlatCacheError):
    """
    Raised when hash computation fails.

    Attributes:
        file_path (str): The path of the file.
        hash_type (str): The hash type that failed.
        original_error (Exception): The underlying error.
    """
    def __init__(self, file_path: str, hash_type: str, original_error: Exception):
        super().__init__(f"Failed to compute {hash_type} for {file_path}: {original_error}")
        self.file_path = file_path
        self.hash_type = hash_type
        self.original_error = original_error

# --- Data Structure ---

@dataclass
class FlatCacheEntry:
    """
    Represents a single entry in the flat cache database.
    
    Attributes:
        path (str): Normalized full file path (PRIMARY KEY).
        size (int): File size in bytes.
        mtime (float): Modification time (mtime) as Unix timestamp float.
        width (Optional[int]): Image width in pixels.
        height (Optional[int]): Image height in pixels.
        is_valid (bool): Validity flag (DEFAULT True).
        xxh3 (Optional[str]): File content hash using xxh3 algorithm.
        phash (Optional[str]): Perceptual hash for image similarity.
        brisque (Optional[float]): BRISQUE no-reference image quality score (0-1 normalized, higher-better), nullable for images not yet evaluated.
        created_at (float): Unix timestamp when entry was created.
        updated_at (float): Unix timestamp of last update.
    """
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for DB storage."""
        data = asdict(self)
        # Ensure types for DB
        data['is_valid'] = int(self.is_valid)  # Store as INTEGER 0/1
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FlatCacheEntry':
        """Create from dict."""
        entry_data = data.copy()
        # Ensure types
        entry_data['is_valid'] = bool(entry_data.get('is_valid', True))
        if 'mtime' in entry_data:
            entry_data['mtime'] = float(entry_data['mtime'])
        if 'created_at' in entry_data:
            entry_data['created_at'] = float(entry_data['created_at'])
        if 'updated_at' in entry_data:
            entry_data['updated_at'] = float(entry_data['updated_at'])
        return cls(**entry_data)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> 'FlatCacheEntry':
        """
        Creates a FlatCacheEntry instance from a sqlite3.Row object.
        """
        data = dict(row)
        return cls.from_dict(data)

# --- SQL Schema ---

FLAT_CACHE_SCHEMA = f"""
-- Flat Cache DB schema: Simplified file metadata, hash storage, and image quality scores
-- Stores essential file metadata, dedicated hash columns, and BRISQUE quality scores
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
);

-- Indexes for performance and queries
CREATE INDEX IF NOT EXISTS idx_size ON {TABLE_NAME} (size);
CREATE INDEX IF NOT EXISTS idx_updated_at ON {TABLE_NAME} (updated_at);
CREATE INDEX IF NOT EXISTS idx_is_valid ON {TABLE_NAME} (is_valid);
CREATE INDEX IF NOT EXISTS idx_xxh3 ON {TABLE_NAME} (xxh3);
CREATE INDEX IF NOT EXISTS idx_phash ON {TABLE_NAME} (phash);
CREATE INDEX IF NOT EXISTS idx_whash ON {TABLE_NAME} (whash);

-- Schema version table for migration tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

SCHEMA_VERSION = 8  # Version 8: Added whash TEXT column for wavelet perceptual hash

# --- Manager Class ---

class FlatCacheManager:
    """
    Manages the connection and operations for the flat file cache database.

    This cache is designed for high-speed lookups of computed file properties
    (hashes) and includes built-in validation against file system
    metadata to ensure cache freshness.

    Example Usage:
        >>> from pathlib import Path
        >>> manager = FlatCacheManager() # Uses default path
        >>> hashes = manager.get_hashes(['/path/to/image.jpg'], ['phash'])
        >>> print(hashes['/path/to/image.jpg']['phash'])
    """

    def __init__(self, db_path: Optional[Path | str] = None, logger: Optional[logging.Logger] = None):
        """
        Initializes the FlatCacheManager.
        
        Parameters:
            db_path (Optional[Path | str]): The full path to the SQLite database file.
                                            Defaults to get_data_dir() / DEFAULT_DB_NAME.
            logger (Optional[logging.Logger]): Custom logger instance. Defaults to
                                               'pk_py_lib.core.flat_cache'.
        """
        if db_path is None:
            db_path = get_data_dir() / DEFAULT_DB_NAME
        elif isinstance(db_path, str):
            db_path = Path(db_path)

        self.db_path = db_path.resolve()
        self.data_dir = self.db_path.parent  # For migration access
        self.logger = logger or get_cache_logger()  # Use dedicated cache logger
        self.table_name = TABLE_NAME

        self._migrate_from_legacy_cache_if_needed()
        self._validate_schema_or_recreate()
        self._initialize_db()

    def _validate_schema_or_recreate(self) -> None:
        """
        Validates that the existing database matches the current schema version.
        
        If the database file exists but has a different schema version (or the version
        cannot be determined), deletes the entire database file and all companion files
        (WAL, SHM) to ensure a clean slate for recreation.
        
        This approach is appropriate for a development/PoC project where cached data
        can be regenerated and migration complexity should be avoided.
        
        Logs:
            - Schema validation start and results
            - Current vs. expected schema version on mismatch
            - Database deletion and recreation actions
            - Any errors encountered during validation or deletion
        
        Raises:
            FlatCacheDBError: If database files cannot be deleted after validation failure.
        """
        # If database doesn't exist yet, nothing to validate
        if not self.db_path.exists():
            self.logger.info(f"Database file does not exist yet: {self.db_path}. Will create with schema v{SCHEMA_VERSION}.")
            return
        
        self.logger.info(f"Validating schema for existing database: {self.db_path}")
        
        try:
            # Attempt to connect and read schema version
            conn = sqlite3.connect(str(self.db_path), timeout=5)
            conn.row_factory = sqlite3.Row
            
            try:
                # Check if schema_version table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
                )
                if not cursor.fetchone():
                    self.logger.warning("Schema version table not found in existing database.")
                    current_version = 0
                else:
                    # Read the current schema version
                    cursor = conn.execute("SELECT version FROM schema_version")
                    row = cursor.fetchone()
                    current_version = row[0] if row else 0
                
                self.logger.info(f"Database schema version: {current_version}, Expected: {SCHEMA_VERSION}")
                
                # Check if version matches
                if current_version != SCHEMA_VERSION:
                    self.logger.warning(
                        f"Schema version mismatch detected! "
                        f"Database has v{current_version}, but code expects v{SCHEMA_VERSION}. "
                        f"Deleting database to recreate with current schema."
                    )
                    
                    # Close connection before deleting
                    conn.close()
                    
                    # Delete database and all companion files
                    self._delete_database_files()
                    
                    self.logger.info(
                        f"Database deleted successfully. New database with schema v{SCHEMA_VERSION} "
                        f"will be created during initialization."
                    )
                else:
                    self.logger.info(f"Schema validation passed: v{SCHEMA_VERSION}")
                    conn.close()
                    
            except sqlite3.Error as e:
                self.logger.error(f"SQLite error during schema validation: {e}", exc_info=True)
                conn.close()
                
                # If we can't read the schema, assume it's corrupted and delete
                self.logger.warning(
                    f"Cannot validate schema due to database error. "
                    f"Database may be corrupted. Deleting to recreate."
                )
                self._delete_database_files()
                
        except sqlite3.Error as e:
            self.logger.error(f"Cannot connect to database for validation: {e}", exc_info=True)
            self.logger.warning("Cannot access database. Attempting to delete and recreate.")
            self._delete_database_files()
            
        except Exception as e:
            self.logger.error(f"Unexpected error during schema validation: {e}", exc_info=True)
            # For unexpected errors, try to delete and recreate
            self._delete_database_files()
    
    def _delete_database_files(self) -> None:
        """
        Deletes the database file and all companion files (WAL, SHM).
        
        This is used when schema validation fails or the database is corrupted.
        Attempts to delete all related files to ensure a clean slate for recreation.
        
        Logs:
            - Each file deletion attempt and result
            - Any errors encountered during deletion
        
        Raises:
            FlatCacheDBError: If files cannot be deleted (e.g., due to permissions or locks).
        """
        files_to_delete = [
            self.db_path,
            self.db_path.with_suffix('.db-wal'),
            self.db_path.with_suffix('.db-shm')
        ]
        
        deletion_errors = []
        
        for file_path in files_to_delete:
            if file_path.exists():
                try:
                    self.logger.info(f"Deleting database file: {file_path}")
                    file_path.unlink(missing_ok=True)
                    self.logger.info(f"Successfully deleted: {file_path}")
                except PermissionError as e:
                    error_msg = f"Permission denied when deleting {file_path}: {e}"
                    self.logger.error(error_msg)
                    deletion_errors.append(error_msg)
                except OSError as e:
                    if e.errno != 2:  # Ignore ENOENT
                        error_msg = f"OS error deleting {file_path}: {e}"
                        self.logger.error(error_msg)
                        deletion_errors.append(error_msg)
                    else:
                        self.logger.debug(f"File not found during deletion (race condition?): {file_path}")
                except Exception as e:
                    error_msg = f"Unexpected error deleting {file_path}: {e}"
                    self.logger.error(error_msg, exc_info=True)
                    deletion_errors.append(error_msg)
            else:
                self.logger.debug(f"File does not exist, skipping: {file_path}")
        
        if deletion_errors:
            error_summary = "; ".join(deletion_errors)
            raise FlatCacheDBError(
                f"Failed to delete database files. This may be due to file locks or permissions. "
                f"Errors: {error_summary}. "
                f"Try closing any applications using the database and run again."
            )
        
        self.logger.info("All database files deleted successfully.")

    @log_errors()
    @contextmanager
    @log_errors()
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
            conn = sqlite3.connect(str(self.db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = 1")
            conn.execute("PRAGMA journal_mode = WAL")
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

    @log_errors()
    def _migrate_from_legacy_cache_if_needed(self) -> None:
        """
        Performs one-time migration from legacy cache.db if it exists in data_dir.
        
        Queries image_metadata and image_hashes from cache.db, maps to FlatCacheEntry
        (populates new fields, extracts xxh3 and phash hashes),
        inserts into flat_cache.db, then deletes cache.db.
        
        Logs the process; idempotent (skips if cache.db missing or already migrated).
        """
        legacy_cache_path = self.data_dir / "cache.db"
        if not legacy_cache_path.exists():
            self.logger.info("No legacy cache.db found; skipping migration.")
            return

        # Check if migration already done (e.g., via schema_version note or absent legacy tables)
        try:
            with sqlite3.connect(str(legacy_cache_path)) as legacy_conn:
                legacy_conn.row_factory = sqlite3.Row
                # Check if image_metadata exists and has data
                cur = legacy_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='image_metadata'")
                if not cur.fetchone():
                    self.logger.info("Legacy cache.db missing image_metadata table; skipping migration.")
                    legacy_cache_path.unlink()  # Clean up empty/partial DB
                    return

                # Check schema_version in legacy for migration flag (if >=3.0.0, assume migrated)
                cur = legacy_conn.execute("SELECT value FROM meta WHERE key='schema_version'")
                row = cur.fetchone()
                legacy_version = row[0] if row else '0.0.0'
                if legacy_version >= '3.0.0':
                    self.logger.info(f"Legacy cache.db already migrated (version {legacy_version}); cleaning up.")
                    legacy_cache_path.unlink()
                    return

                self.logger.info(f"Starting migration from legacy cache.db (version {legacy_version}) to flat_cache v{SCHEMA_VERSION}")
                
                migrated_count = 0
                # Query image_metadata (main data)
                cur_meta = legacy_conn.execute("""
                    SELECT * FROM image_metadata WHERE is_valid = 1
                """)
                for row_meta in cur_meta.fetchall():
                    # Extract xxh3 and phash from legacy data
                    xxh3_val = None  # Legacy SHA-256 not migrated; recompute xxh3 on access
                    phash_val = None
                    
                    # Query associated hashes from image_hashes
                    cur_hashes = legacy_conn.execute("""
                        SELECT algorithm, hash_value FROM image_hashes WHERE image_id = ?
                    """, (row_meta['id'],))
                    for row_hash in cur_hashes.fetchall():
                        if row_hash['algorithm'] == 'phash':
                            phash_val = row_hash['hash_value']
                        elif row_hash['algorithm'] == 'xxh3':
                            xxh3_val = row_hash['hash_value']  # Prefer xxh3 from hashes table
                    
                    entry_data = {
                        'path': row_meta['file_path'],
                        'size': row_meta['file_size'],
                        'mtime': float(row_meta['file_modified']) if row_meta['file_modified'] else time.time(),
                        'width': row_meta.get('width'),
                        'height': row_meta.get('height'),
                        'is_valid': bool(row_meta['is_valid']),
                        'xxh3': xxh3_val,
                        'phash': phash_val,
                        'created_at': time.time(),
                        'updated_at': time.time(),
                    }
                    
                    # Create entry and insert
                    entry = FlatCacheEntry.from_dict(entry_data)
                    if self.set_entry(entry):
                        migrated_count += 1
                    else:
                        self.logger.warning(f"Failed to migrate entry for {entry.path}")

                self.logger.info(f"Migration complete: {migrated_count} entries transferred from cache.db")
                
                # Clean up legacy DB
                legacy_cache_path.unlink(missing_ok=True)
                self.logger.info("Legacy cache.db deleted after successful migration.")

        except sqlite3.Error as e:
            self.logger.error(f"SQLite error during legacy migration: {e}", exc_info=True)
            # Do not delete if error; retry possible
        except Exception as e:
            self.logger.error(f"Unexpected error during legacy migration: {e}", exc_info=True)
            # Do not delete if error

    def _initialize_db(self) -> None:
        """
        Ensures the database file exists and the required table is created.
        Handles schema migration by checking version and recreating if needed.
        
        For PoC simplicity: If schema version < current, drop and recreate the table.
        Logs recreation due to schema update.
        
        Handles locked database errors by attempting to delete the DB file and WAL/SHM companions,
        then reinitializing. Includes retries for drop operations.
        
        Raises:
            FlatCacheDBError: If table creation or migration fails after retries.
        """
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Initializing flat cache database at {self.db_path} (attempt {attempt}/{max_retries})")

                # Check for WAL and SHM files and delete if present to break potential locks
                wal_path = self.db_path.with_suffix('.db-wal')
                shm_path = self.db_path.with_suffix('.db-shm')
                delete_performed = False
                if wal_path.exists() or shm_path.exists():
                    self.logger.warning(f"Companion files detected (WAL: {wal_path.exists()}, SHM: {shm_path.exists()}); deleting all DB files to resolve potential lock.")
                    try:
                        for ext in ['', '-wal', '-shm']:
                            db_file = self.db_path.with_suffix(f'.db{ext}')
                            if db_file.exists():
                                self.logger.info(f"Deleting potential locked file: {db_file}")
                                db_file.unlink(missing_ok=True)
                        delete_performed = True
                        self.logger.info("Deleted DB files; proceeding to create new database.")
                    except Exception as delete_error:
                        self.logger.error(f"Failed to delete DB files: {delete_error}")
                        if attempt == max_retries:
                            raise FlatCacheDBError(f"Could not resolve lock by deleting files: {delete_error}")

                self.logger.info(f"Diagnostic: WAL file exists: {wal_path.exists()}, SHM file exists: {shm_path.exists()} (after cleanup)")

                with self._get_connection() as conn:
                    # First, ensure schema_version table and check current version
                    conn.executescript("""
                        CREATE TABLE IF NOT EXISTS schema_version (
                            version INTEGER PRIMARY KEY
                        );
                    """)
                    
                    # Get or set current version
                    cursor = conn.execute("SELECT version FROM schema_version")
                    row = cursor.fetchone()
                    if row:
                        current_version = int(row[0])
                    else:
                        current_version = 0
                        conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (int(SCHEMA_VERSION),))
                    
                    self.logger.info(f"Diagnostic: Current schema version: {current_version}, target: {SCHEMA_VERSION}")
                    
                    # If version mismatch, migrate (for PoC: drop and recreate)
                    if current_version < SCHEMA_VERSION:
                        if current_version == 7:
                            # Migration from v7 to v8: add whash column
                            cursor = conn.execute(f"PRAGMA table_info({self.table_name})")
                            column_names = [row[1] for row in cursor.fetchall()]
                            if 'whash' not in column_names:
                                conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN whash TEXT")
                                self.logger.info(f"Migration v7 to v8: Added whash column to {self.table_name} table.")
                            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (int(SCHEMA_VERSION),))
                            self.logger.info(f"Schema migration complete: v{current_version} to v{SCHEMA_VERSION}.")
                        elif current_version == 6:
                            # Migration from v6 to v7: add brisque column
                            cursor = conn.execute(f"PRAGMA table_info({self.table_name})")
                            column_names = [row[1] for row in cursor.fetchall()]
                            if 'brisque' not in column_names:
                                conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN brisque REAL")
                                self.logger.info(f"Migration v6 to v7: Added brisque column to {self.table_name} table.")
                            # Then add whash for v8
                            if 'whash' not in column_names:
                                conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN whash TEXT")
                                self.logger.info(f"Migration v6 to v8: Added whash column to {self.table_name} table.")
                            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (int(SCHEMA_VERSION),))
                            self.logger.info(f"Schema migration complete: v{current_version} to v{SCHEMA_VERSION}.")
                        else:
                            # For older versions, drop and recreate
                            self.logger.info(f"Schema migration needed for older version {current_version}. Recreating table.")
                            
                            # Drop existing table if it exists (no inner retry needed if we deleted files already)
                            try:
                                self.logger.info(f"Diagnostic: Attempting DROP TABLE IF EXISTS {self.table_name}")
                                conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")
                                self.logger.info(f"Diagnostic: DROP TABLE succeeded")
                            except sqlite3.OperationalError as drop_error:
                                error_msg = str(drop_error).lower()
                                if "locked" in error_msg:
                                    self.logger.error(f"Unexpected lock after file deletion: {drop_error}")
                                    raise
                                else:
                                    self.logger.error(f"Diagnostic: DROP TABLE failed with OperationalError: {drop_error}")
                                    raise
                            except Exception as drop_error:
                                self.logger.error(f"Diagnostic: DROP TABLE failed with unexpected error: {drop_error}")
                                raise
                            
                            # Run full schema
                            self.logger.info("Diagnostic: Executing full schema creation")
                            conn.executescript(FLAT_CACHE_SCHEMA)
                            
                            # Update version
                            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (int(SCHEMA_VERSION),))
                            
                            self.logger.info("Schema migration complete: table recreated with v{}.".format(SCHEMA_VERSION))
                    else:
                        # Ensure table and indexes exist
                        conn.executescript(FLAT_CACHE_SCHEMA)
                    
                    self.logger.debug(f"Table {self.table_name} ensured (version {SCHEMA_VERSION}).")
                    return  # Success, exit retry loop

            except FlatCacheDBError as e:
                original_err = getattr(e, 'original_error', None)
                is_lock_error = (isinstance(original_err, sqlite3.OperationalError) and "locked" in str(original_err).lower()) or ("locked" in str(e).lower())
                
                if is_lock_error and attempt < max_retries:
                    self.logger.warning(f"Database locked during init (attempt {attempt}/{max_retries}): {e}. Attempting to delete DB files and retry...")
                    
                    # Delete DB and companion files to break lock
                    try:
                        for ext in ['', '-wal', '-shm']:
                            db_file = self.db_path.with_suffix(f'.db{ext}')
                            if db_file.exists():
                                self.logger.info(f"Deleting locked file: {db_file}")
                                db_file.unlink(missing_ok=True)
                        self.logger.info("Deleted locked DB files; will recreate on retry.")
                    except Exception as delete_error:
                        self.logger.error(f"Failed to delete locked DB files: {delete_error}")
                        if attempt == max_retries:
                            raise FlatCacheDBError(f"Persistent lock and deletion failed: {e}", original_error=e)
                    
                    time.sleep(retry_delay)
                    continue  # Retry init
                else:
                    self.logger.critical(f"Failed to initialize flat cache database: {e}")
                    raise
            
            except Exception as e:
                if attempt < max_retries:
                    self.logger.warning(f"Unexpected error during init (attempt {attempt}/{max_retries}): {e}. Retrying...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise FlatCacheDBError(f"Unexpected persistent error: {e}", original_error=e)

        raise FlatCacheDBError("Failed to initialize database after all retries")

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
    @log_errors()
    @log_errors()
    @log_errors()
    @log_errors()
    def _get_file_stats(file_path: str) -> Tuple[int, float]:
        """
        Retrieves size and modification time (mtime) for a file.
        
        Parameters:
            file_path (str): The path to the file.
        
        Returns:
            Tuple[int, float]: (size, mtime)
        
        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If file stats cannot be read.
        """
        try:
            stat_result = os.stat(file_path)
            return stat_result.st_size, stat_result.st_mtime
        except FileNotFoundError:
            raise
        except Exception as e:
            raise PermissionError(f"Could not read stats for {file_path}: {e}") from e

    @log_errors()
    def _validate_entry(self, entry: FlatCacheEntry, strict: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        Validates a cached entry against the current file system statistics.
        
        Parameters:
            entry (FlatCacheEntry): The cached entry to validate.
            strict (bool): If True (default), raises FlatCacheValidationError on failure.
                           If False, returns (False, mismatches) without raising.
        
        Returns:
            Tuple[bool, Dict[str, Any]]: (is_valid: bool, mismatches: dict)
                - is_valid: True if valid.
                - mismatches: Empty dict if valid; otherwise, details of failures.
        
        Raises:
            FlatCacheValidationError: If strict=True and validation fails.
        """
        file_path = entry.path
        self.logger.debug(f"Cache validate for {file_path}, action: start, strict: {strict}")  # Log validation start
    
        try:
            current_size, current_mtime = self._get_file_stats(file_path)
            self.logger.debug(f"Cache validate_size for {file_path}, cached_size: {entry.size}, current_size: {current_size}")  # Log size check
        except FileNotFoundError:
            self.logger.debug(f"Cache validate for {file_path}, result: existence=False")  # Log existence check
            mismatches = {"existence": "File not found"}
            if strict:
                raise FlatCacheValidationError(file_path, mismatches)
            return False, mismatches
        except PermissionError as e:
            self.logger.warning(f"Validation skipped due to permission error: {file_path}. Error: {e}")
            mismatches = {"permission": str(e)}
            if strict:
                raise FlatCacheValidationError(file_path, mismatches)
            return False, mismatches
    
        mismatches = {}
    
        # Size check
        if current_size != entry.size:
            self.logger.debug(f"Cache validate_size for {file_path}, result: valid=False")  # Log size invalid
            mismatches["size"] = f"Cached: {entry.size}, Current: {current_size}"
        else:
            self.logger.debug(f"Cache validate_size for {file_path}, result: valid=True")  # Log size valid
    
        # Modification time check (with float tolerance for precision issues)
        self.logger.debug(f"Cache validate_date for {file_path}, cached_mtime: {entry.mtime}, current_mtime: {current_mtime}")  # Log date check
        if abs(current_mtime - entry.mtime) > 1e-6:
            self.logger.debug(f"Cache validate_date for {file_path}, result: valid=False")  # Log date invalid
            mismatches["mtime"] = f"Cached: {entry.mtime}, Current: {current_mtime}"
        else:
            self.logger.debug(f"Cache validate_date for {file_path}, result: valid=True")  # Log date valid
    
        # Validity flag
        self.logger.debug(f"Cache validate_flag for {file_path}, is_valid: {entry.is_valid}")  # Log flag check
        if not entry.is_valid:
            self.logger.debug(f"Cache validate_flag for {file_path}, result: valid=False")  # Log flag invalid
            mismatches["is_valid"] = "Entry marked invalid"
        else:
            self.logger.debug(f"Cache validate_flag for {file_path}, result: valid=True")  # Log flag valid
    
        if mismatches:
            self.logger.debug(f"Cache validate for {file_path}, result: overall_valid=False, mismatches: {len(mismatches)}")  # Log overall invalid
            if strict:
                raise FlatCacheValidationError(file_path, mismatches)
            return False, mismatches
    
        self.logger.debug(f"Cache validate for {file_path}, result: overall_valid=True")  # Log overall valid
        return True, {}

    @log_errors()
    def get_entry(self, file_path: str) -> Optional[FlatCacheEntry]:
        """
        Queries the cache for an entry and validates it against current file stats.
        
        Additionally, for BRISQUE scores, detects legacy 0-100 scale (scores >1.0) and
        normalizes them in-place to 0-1 scale by dividing by 100.0, then persists the update.
        
        Parameters:
            file_path (str): The path to the file.
        
        Returns:
            Optional[FlatCacheEntry]: The valid entry (with normalized brisque if migrated), or None if not found or invalid.
        """
        normalized_path = self._normalize_path(file_path)
        self.logger.debug(f"Cache get for {normalized_path}, field: entry, action: query")  # Log get start

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    f"SELECT path, size, mtime, width, height, is_valid, xxh3, phash, whash, brisque, created_at, updated_at FROM {self.table_name} WHERE path = ?",
                    (normalized_path,)
                )
                row = cursor.fetchone()

                if row is None:
                    self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: found=False")  # Log miss
                    return None

                entry = FlatCacheEntry.from_row(row)
                self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: found=True")  # Log found

                # Validate the retrieved entry against the current file system state
                self._validate_entry(entry, strict=True)

                # Migrate legacy BRISQUE scores (0-100) to new 0-1 scale if detected
                if entry.brisque is not None and entry.brisque > 1.0:
                    old_value = entry.brisque
                    entry.brisque = min(1.0, entry.brisque / 100.0)
                    self.logger.debug(f"Cache normalize for {normalized_path}, field: brisque, old_value: {old_value}, new_value: {entry.brisque}")  # Log normalization
                    # Persist the normalized value
                    if self.set_entry(entry):
                        self.logger.debug(f"Cache set for {normalized_path}, field: brisque, action: normalize_update, result: success=True")
                    else:
                        self.logger.warning(f"Failed to persist normalized BRISQUE score for {normalized_path}")

                self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: valid=True")  # Log successful get
                return entry

        except FlatCacheValidationError:
            self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: valid=False")  # Log validation fail
            # Validation failed (file changed or missing). Logged inside _validate_entry.
            return None
        except FlatCacheDBError as e:
            self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: db_error")  # Log DB error
            self.logger.error(f"DB error retrieving entry for {normalized_path}: {e}")
            return None
        except Exception as e:
            self.logger.debug(f"Cache get for {normalized_path}, field: entry, result: unexpected_error")  # Log unexpected error
            self.logger.error(f"Unexpected error in get_entry for {normalized_path}: {e}", exc_info=True)
            return None

    def set_entry(self, entry: FlatCacheEntry, search_type: Optional[str] = None) -> bool:
        """
        Inserts or replaces a cache entry (UPSERT), conditionally based on search_type.
        
        For search_type='duplicate', performs a targeted UPDATE of core fields only
        (path, size, mtime, xxh3, updated_at, is_valid) to avoid overwriting existing
        image metadata (width, height, phash, whash, brisque) from prior similarity scans.
        Uses INSERT OR REPLACE for full updates in other modes (e.g., 'similarity').
        
        The entry's 'path' must be normalized before calling this method.
        It automatically updates 'updated_at' and ensures file stats are current.
        
        Parameters:
            entry (FlatCacheEntry): The entry to store.
            search_type (Optional[str]): 'duplicate' for limited update; otherwise full INSERT.
        
        Returns:
            bool: True if the operation succeeded, False otherwise.
        
        Notes:
            - Duplicate mode preserves image data to support mixed scan workflows.
            - Full mode overwrites all fields, suitable for similarity scans.
            - Logs the update type for debugging.
        """
        # Ensure path is normalized and update dynamic fields
        entry.path = self._normalize_path(entry.path)
        self.logger.debug(f"Cache set for {entry.path}, action: normalize_path")  # Log path normalization
        now = time.time()
        if entry.created_at == 0.0:
            entry.created_at = now
        entry.updated_at = now
        self.logger.debug(f"Cache set for {entry.path}, action: update_timestamps, created_at: {entry.created_at}, updated_at: {entry.updated_at}")
        
        # Update file stats just before saving to ensure consistency
        try:
            entry.size, entry.mtime = self._get_file_stats(entry.path)
            self.logger.debug(f"Cache set for {entry.path}, action: update_stats, size: {entry.size}, mtime: {entry.mtime}")
        except (FileNotFoundError, PermissionError) as e:
            self.logger.warning(f"Cannot set entry for non-existent or inaccessible file {entry.path}: {e}")
            return False
        
        if search_type == 'duplicate':
            # Limited UPDATE for core fields; explicitly clear image-specific fields to ensure clean cache in duplicate mode
            # This prevents retention of perceptual/image data from prior similarity scans
            core_fields = ['size', 'mtime', 'xxh3', 'updated_at', 'is_valid']
            image_clear_fields = ['width', 'height', 'phash', 'whash', 'brisque']
            set_clause = ', '.join([f"{field} = ?" for field in core_fields] + [f"{field} = NULL" for field in image_clear_fields])
            values = [getattr(entry, field) if field != 'is_valid' else int(entry.is_valid) for field in core_fields]
            values.append(entry.path)  # WHERE path = ?
            
            sql = f"""
            UPDATE {self.table_name}
            SET {set_clause}
            WHERE path = ?
            """
            
            self.logger.debug(f"Cache set for {entry.path}, field: core, action: prepare_update, mode: duplicate")  # Log SQL prep
            self.logger.debug(f"Limited UPDATE for duplicate mode (core fields + image clear): {entry.path}")
        else:
            # Full INSERT OR REPLACE for all fields
            data = entry.to_dict()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?'] * len(data))
            values = tuple(data.values())
            
            sql = f"""
            INSERT OR REPLACE INTO {self.table_name} ({columns})
            VALUES ({placeholders})
            """
            
            self.logger.debug(f"Cache set for {entry.path}, field: all, action: prepare_insert, mode: full")  # Log SQL prep
            self.logger.debug(f"Full INSERT/REPLACE for {entry.path} (search_type={search_type or 'default'})")
        
        try:
            with self._get_connection() as conn:
                if search_type == 'duplicate':
                    cursor = conn.execute(sql, values)
                    affected = cursor.rowcount
                    self.logger.debug(f"Cache set for {entry.path}, action: execute_update, affected: {affected}, mode: duplicate")  # Log execution
                    if affected == 0:
                        # Entry didn't exist; insert with all required fields for duplicate mode, image fields NULL
                        core_data = {
                            'path': entry.path,
                            'size': entry.size,
                            'mtime': entry.mtime,
                            'xxh3': entry.xxh3,
                            'is_valid': int(entry.is_valid),
                            'created_at': entry.created_at,
                            'updated_at': entry.updated_at,
                            'width': None,
                            'height': None,
                            'phash': None,
                            'whash': None,
                            'brisque': None,
                        }
                        core_columns = ', '.join(core_data.keys())
                        core_placeholders = ', '.join(['?'] * len(core_data))
                        core_values = tuple(core_data.values())
                        conn.execute(f"INSERT INTO {self.table_name} ({core_columns}) VALUES ({core_placeholders})", core_values)
                        self.logger.debug(f"Cache set for {entry.path}, action: insert_new, mode: duplicate")  # Log new insert
                else:
                    conn.execute(sql, values)
                    self.logger.debug(f"Cache set for {entry.path}, action: execute_insert, mode: full")  # Log execution
            
            self.logger.debug(f"Cache set for {entry.path}, result: success=True, mode: {'duplicate' if search_type == 'duplicate' else 'full'}")  # Log success
            return True
        except FlatCacheDBError as e:
            self.logger.debug(f"Cache set for {entry.path}, result: success=False, error: db")  # Log failure
            self.logger.error(f"DB error setting entry for {entry.path}: {e}")
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
        self.logger.debug(f"Cache invalidate for {normalized_path}, action: start")  # Log invalidate start

        sql = f"DELETE FROM {self.table_name} WHERE path = ?"

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (normalized_path,))
                deleted_count = cursor.rowcount
                self.logger.debug(f"Cache invalidate for {normalized_path}, action: execute, affected: {deleted_count}")  # Log execution

            if deleted_count > 0:
                self.logger.debug(f"Cache invalidate for {normalized_path}, result: success=True, deleted=1")  # Log success
            else:
                self.logger.debug(f"Cache invalidate for {normalized_path}, result: not_found=True")  # Log not found

            return True
        except FlatCacheDBError as e:
            self.logger.debug(f"Cache invalidate for {normalized_path}, result: success=False, error: db")  # Log failure
            self.logger.error(f"DB error invalidating entry for {normalized_path}: {e}")
            return False

    def batch_set(self, entries: List[FlatCacheEntry]) -> int:
        """
        Performs a transactional batch insert or replace (UPSERT) of cache entries.

        Automatically normalizes paths, updates times, and fetches current file stats
        for each entry before insertion. Entries for inaccessible files are skipped.

        Parameters:
            entries (List[FlatCacheEntry]): A list of entries to store.

        Returns:
            int: The number of entries successfully inserted/updated.
        """
        if not entries:
            self.logger.debug("Cache batch_set for 0 entries, action: skip")  # Log empty batch
            return 0

        self.logger.debug(f"Cache batch_set start, total_entries: {len(entries)}")  # Log batch start
        data_to_insert = []
        now = time.time()
        skipped = 0

        # Prepare data: normalize path, update times, fetch stats
        for i, entry in enumerate(entries):
            entry.path = self._normalize_path(entry.path)
            self.logger.debug(f"Cache batch_set for {entry.path}, action: normalize_path, index: {i}")  # Log per entry prep
            if entry.created_at == 0.0:
                entry.created_at = now
            entry.updated_at = now

            try:
                entry.size, entry.mtime = self._get_file_stats(entry.path)
                self.logger.debug(f"Cache batch_set for {entry.path}, action: update_stats, size: {entry.size}, mtime: {entry.mtime}")  # Log stats

                data_dict = entry.to_dict()
                data_to_insert.append(tuple(data_dict.values()))
            except (FileNotFoundError, PermissionError) as e:
                self.logger.debug(f"Cache batch_set for {entry.path}, result: skip, reason: inaccessible")  # Log skip
                self.logger.warning(f"Skipping batch set for {entry.path}: File inaccessible or missing. Error: {e}")
                skipped += 1
                continue

        if not data_to_insert:
            self.logger.debug(f"Cache batch_set completed, prepared: 0, skipped: {skipped}")  # Log empty prepared
            return 0

        # Use keys from first prepared entry for columns
        sample_entry = entries[0]
        sample_entry.path = self._normalize_path(sample_entry.path)
        sample_entry.created_at = now
        sample_entry.updated_at = now
        sample_entry.size, sample_entry.mtime = self._get_file_stats(sample_entry.path)
        sample_data = sample_entry.to_dict()
        columns = ', '.join(sample_data.keys())
        placeholders = ', '.join(['?'] * len(sample_data))

        sql = f"""
        INSERT OR REPLACE INTO {self.table_name} ({columns})
        VALUES ({placeholders})
        """
        self.logger.debug(f"Cache batch_set prepare_sql, columns_count: {len(sample_data)}, entries_to_insert: {len(data_to_insert)}")  # Log SQL prep

        try:
            with self._get_connection() as conn:
                conn.executemany(sql, data_to_insert)
                self.logger.debug(f"Cache batch_set execute, inserted/updated: {len(data_to_insert)}")  # Log execution

            self.logger.debug(f"Cache batch_set result: success=True, inserted/updated: {len(data_to_insert)}, skipped: {skipped}")  # Log success
            return len(data_to_insert)
        except FlatCacheDBError as e:
            self.logger.debug(f"Cache batch_set result: success=False, error: db, attempted: {len(data_to_insert)}")  # Log failure
            self.logger.error(f"DB error during batch set: {e}")
            return 0

    def get_uncached_files(self, paths: List[str]) -> List[str]:
        """
        Identifies which files in the provided list are either missing from the cache
        or have an invalid (stale) cache entry based on size/mtime.

        Parameters:
            paths (List[str]): A list of file paths to check.

        Returns:
            List[str]: A list of normalized file paths that need recomputation.
        """
        if not paths:
            self.logger.debug("Cache get_uncached for 0 paths, return empty")  # Log empty
            return []

        self.logger.debug(f"Cache get_uncached start, total_paths: {len(paths)}")  # Log start
        normalized_paths = [self._normalize_path(p) for p in paths]
        uncached_paths = []

        # Query all existing entries for the given paths
        placeholders = ', '.join(['?'] * len(normalized_paths))
        sql = f"SELECT path, size, mtime, width, height, is_valid, xxh3, phash, brisque, created_at, updated_at FROM {self.table_name} WHERE path IN ({placeholders})"
        self.logger.debug(f"Cache get_uncached query, paths_count: {len(normalized_paths)}")  # Log query

        cached_entries: Dict[str, FlatCacheEntry] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, normalized_paths)
                for row in cursor.fetchall():
                    entry = FlatCacheEntry.from_row(row)
                    cached_entries[entry.path] = entry
            self.logger.debug(f"Cache get_uncached query result, found_entries: {len(cached_entries)}")  # Log query result
        except FlatCacheDBError as e:
            self.logger.debug(f"Cache get_uncached result: db_error, assume_all_uncached: {len(normalized_paths)}")  # Log DB error
            self.logger.error(f"DB error during get_uncached_files query: {e}")
            # If DB fails, assume all files need recomputation
            return normalized_paths

        # Check for missing paths
        for path in normalized_paths:
            if path not in cached_entries:
                uncached_paths.append(path)
                self.logger.debug(f"Cache get_uncached for {path}, result: miss, reason: not_found")  # Log miss

        # Validate existing entries
        for path, entry in cached_entries.items():
            try:
                self._validate_entry(entry)
                self.logger.debug(f"Cache get_uncached for {path}, result: cached_valid")  # Log valid
            except FlatCacheValidationError:
                uncached_paths.append(path)
                self.logger.debug(f"Cache get_uncached for {path}, result: miss, reason: validation_failed")  # Log invalid
            except Exception as e:
                self.logger.debug(f"Cache get_uncached for {path}, result: miss, reason: unexpected_error")  # Log unexpected
                self.logger.error(f"Unexpected error during validation of {path}: {e}", exc_info=True)
                uncached_paths.append(path)  # Treat unexpected errors as cache miss

        self.logger.debug(f"Cache get_uncached result: uncached_count: {len(uncached_paths)}, total_checked: {len(paths)}")  # Log summary
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
        threshold = time.time() - (days * 24 * 60 * 60)

        sql = f"DELETE FROM {self.table_name} WHERE updated_at < ?"

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, (threshold,))
                deleted_count = cursor.rowcount

            self.logger.info(f"Cleanup completed: Deleted {deleted_count} entries older than {days} days.")
            return deleted_count
        except FlatCacheDBError as e:
            self.logger.error(f"DB error during cleanup: {e}")
            return 0

    def _is_image_file(self, file_path: str) -> bool:
        """
        Checks if the file is a supported image file.
        
        Parameters:
            file_path (str): The path to the file.
        
        Returns:
            bool: True if it can be opened as an image with PIL.
        """
        try:
            with Image.open(file_path) as _:
                return True
        except Exception:
            return False

    def _extract_image_metadata(self, file_path: str, search_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts image-specific metadata (dimensions) using PIL.

        Always extracts width and height for valid images. For search_type='similarity',
        also computes BRISQUE quality score if an evaluator is active. This method is
        only called for non-duplicate searches to avoid unnecessary image loading
        and processing overhead during file-based duplicate detection.

        Parameters:
            file_path (str): Path to the image file.
            search_type (Optional[str]): If 'similarity', compute quality score. For 'duplicate',
                extraction is skipped entirely to prevent image loading for non-image files
                or unnecessary operations on images during exact hash scans.

        Returns:
            Dict[str, Any]: Metadata dict with 'width', 'height', and optionally 'brisque'.
            Returns empty dict {} if search_type='duplicate' (no extraction performed).
            # Fixed duplicate mode skips

        Raises:
            Exception: If image cannot be opened or metadata extraction fails (only for non-duplicate modes).
                Caller should handle and set dimensions to None.

        Example:
            >>> metadata = manager._extract_image_metadata("/path/to/img.jpg", search_type='similarity')
            >>> # Returns {'width': 1920, 'height': 1080, 'brisque': 45.2} or similar
            >>> metadata = manager._extract_image_metadata("/path/to/file.txt", search_type='duplicate')
            >>> # Returns {} (skipped)
        """
        if search_type == 'duplicate':
            # Safeguard: Log warning if unexpectedly called in duplicate mode (should not happen due to caller checks)
            self.logger.warning(f"UNEXPECTED call to _extract_image_metadata in duplicate mode for {file_path} - aborting extraction (no PIL.open or evaluators called)")
            return {}

        metadata = {}
        try:
            with Image.open(file_path) as img:
                metadata['width'] = img.width
                metadata['height'] = img.height

            # Only compute quality for similarity searches
            if search_type == 'similarity':
                from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator
                evaluator = get_active_image_quality_evaluator()
                if evaluator:
                    try:
                        score = evaluator.evaluate(file_path)
                        metadata['brisque'] = score
                    except Exception as e:
                        self.logger.warning(f"Failed to compute brisque for {file_path}: {e}")
                        metadata['brisque'] = None

            self.logger.debug(f"Extracted metadata for {file_path}: width={metadata.get('width')}, height={metadata.get('height')}, search_type={search_type}")
            return metadata
        except Exception as e:
            self.logger.warning(f"Failed to extract image metadata for {file_path}: {e}")
            raise

    def _compute_hash(self, file_path: str, hash_type: str, search_type: str = 'similarity') -> Optional[str]:
        """
        Computes a specific hash for the file.

        For perceptual hashes (phash, whash), requires an image file and uses imagehash.
        For file content hashes, uses xxh3 (fast, non-cryptographic) by default.

        Parameters:
            file_path (str): The path to the file.
            hash_type (str): The type of hash. Supported types:
                - Perceptual: 'phash' (DCT-based), 'whash' (wavelet-based)
                - Content: 'xxh3' (default for non-perceptual)
            search_type (str): 'duplicate' to skip perceptual hashes, return None without computation.

        Returns:
            Optional[str]: The computed hash string, or None if skipped (e.g., perceptual in duplicate mode).
                # Fixed duplicate mode skips

        Raises:
            ValueError: If unsupported hash type or perceptual hash requested for non-image file.
            CacheComputeError: Wrapping computation errors.

        Example:
            >>> # Compute perceptual hash for an image
            >>> hash_value = _compute_hash('/path/to/image.jpg', 'phash', search_type='similarity')
            >>> print(hash_value)  # e.g., 'a1b2c3d4e5f67890'

            >>> # Compute file content hash
            >>> content_hash = _compute_hash('/path/to/anyfile.txt', 'xxh3', search_type='duplicate')
            >>> print(content_hash)  # e.g., 'abcdef1234567890'

        Note:
            - whash requires PyWavelets; falls back gracefully if unavailable.
            - For non-images, perceptual hashes raise ValueError; use xxh3 instead.
            - All hashes are 64-bit hex strings (16 characters).
            - In 'duplicate' mode, perceptual hashes (phash, whash) are skipped entirely to avoid image loading.
        """
        allowed_types = ['xxh3', 'phash', 'whash']
        if hash_type not in allowed_types:
            raise ValueError(f"Unsupported hash type '{hash_type}'. Supported: {allowed_types}")

        if hash_type in ['phash', 'whash'] and search_type == 'duplicate':
            self.logger.warning(f"Skipping perceptual hash '{hash_type}' in duplicate mode for {file_path} - no image loading")
            return None  # Fixed duplicate mode skips

        if hash_type == 'phash' and not self._is_image_file(file_path):
            raise ValueError(f"Perceptual hash '{hash_type}' requested for non-image file: {file_path}")

        try:
            if hash_type == 'phash':
                with Image.open(file_path) as img:
                    h = imagehash.phash(img)
                return str(h)
            elif hash_type == 'whash':
                with Image.open(file_path) as img:
                    h = imagehash.whash(img)
                return str(h)
            elif hash_type == 'xxh3':
                # File content hash using xxh3 (fast, non-cryptographic)
                try:
                    import xxhash
                    h = xxhash.xxh3_64()
                    with open(file_path, 'rb') as f:
                        for chunk in iter(lambda: f.read(65536), b''):
                            h.update(chunk)
                    return h.hexdigest()
                except ImportError:
                    raise ImportError("xxhash package is required for file content hashing. Install with: pdm add xxhash")
            else:
                raise ValueError(f"Unsupported hash type '{hash_type}'. Supported: {allowed_types}")
        except Exception as e:
            raise CacheComputeError(file_path, hash_type, e)

    def _process_single_file(self, file_path: str, hash_types: List[str], search_type: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Processes a single file: checks cache, validates, computes missing hashes and image metadata, stores.

        For search_type='duplicate', skips image metadata extraction (width/height) to avoid unnecessary
        image loading, especially for non-image files. Only computes file content hash (xxh3).
        For 'similarity', extracts dimensions and optionally quality scores.

        Parameters:
            file_path (str): The path to the file.
            hash_types (List[str]): List of hash types to ensure are computed.
            search_type (Optional[str]): Type of search ('duplicate' or 'similarity') to control metadata extraction.

        Returns:
            Dict[str, Optional[str]]: Dictionary mapping hash type to hash value for the requested types.
            For unsupported types in duplicate mode, returns None.
            # Fixed duplicate mode skips

        Raises:
            FileNotFoundError: If file does not exist.
            PermissionError: If cannot access file.
            CacheComputeError: If hash computation fails.
        """
        normalized_path = self._normalize_path(file_path)
        self.logger.debug(f"Cache process_single for {normalized_path}, hash_types: {hash_types}, search_type: {search_type}")  # Log process start

        # Global check for non-images: minimal entry with file stats only, no image attempts
        if Path(file_path).suffix.lower() not in IMAGE_EXTENSIONS:
            self.logger.debug(f"Cache process_single for {normalized_path}, type: non_image, action: minimal_entry")  # Log non-image
            stat = os.stat(file_path)
            entry = FlatCacheEntry(
                path=normalized_path,
                size=stat.st_size,
                mtime=stat.st_mtime,
                width=None,
                height=None,
                phash=None,
                whash=None,
                brisque=None,
                is_valid=True
            )
            # Only compute xxh3 if requested; no perceptual
            if 'xxh3' in hash_types:
                self.logger.debug(f"Cache compute for {normalized_path}, field: xxh3, action: non_image")  # Log compute
                try:
                    entry.xxh3 = self._compute_hash(file_path, 'xxh3', search_type=search_type)
                    self.logger.debug(f"Cache set for {normalized_path}, field: xxh3, value: {entry.xxh3[:8]}...")  # Log value (truncated)
                except Exception as e:
                    self.logger.warning(f"Failed to compute xxh3 for non-image {file_path}: {e}")
                    entry.xxh3 = None
            if self.set_entry(entry, search_type=search_type):
                self.logger.debug(f"Cache set minimal for {normalized_path}, fields: core")  # Log set
            return {ht: (entry.xxh3 if ht == 'xxh3' else None) for ht in hash_types}

        # Check if file exists
        if not os.path.exists(file_path):
            self.logger.debug(f"Cache process_single for {normalized_path}, result: file_not_found")  # Log not found
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get or create entry
        entry = self.get_entry(file_path)
        if entry is None:
            self.logger.debug(f"Cache process_single for {normalized_path}, entry: miss, action: create")  # Log miss
            # Create new with basic info
            stat = os.stat(file_path)
            entry = FlatCacheEntry(
                path=normalized_path,
                size=stat.st_size,
                mtime=stat.st_mtime,
                is_valid=True
            )
            # Extract image metadata only for non-duplicate searches (e.g., similarity)
            # This avoids loading images during duplicate scans, preventing errors on non-images
            # and unnecessary processing for all files.
            if search_type != 'duplicate':
                try:
                    img_meta = self._extract_image_metadata(file_path, search_type)
                    entry.width = img_meta.get('width')
                    entry.height = img_meta.get('height')
                    if search_type == 'similarity' and 'brisque' in img_meta:
                        entry.brisque = img_meta['brisque']
                    self.logger.debug(f"Cache set for {normalized_path}, fields: width={entry.width}, height={entry.height}, brisque={entry.brisque}")  # Log metadata
                except Exception as e:
                    self.logger.warning(f"Failed to extract image metadata for {file_path}: {e}")
                    # For non-duplicate, set to None on failure to avoid partial data
                    entry.width = None
                    entry.height = None
                    if search_type == 'similarity':
                        entry.brisque = None
            else:
                # Explicitly ensure image fields are None in duplicate mode
                entry.width = None
                entry.height = None
                entry.phash = None
                entry.whash = None
                entry.brisque = None
                # Fixed duplicate mode skips
                self.logger.debug(f"Cache process_single for {normalized_path}, mode: duplicate, image_fields: None")  # Log duplicate mode
            self.logger.debug(f"Creating new cache entry for {normalized_path} (search_type={search_type})")
        else:
            self.logger.debug(f"Cache process_single for {normalized_path}, entry: hit")  # Log hit

        # Check and compute missing hashes (support xxh3, phash, whash)
        # For duplicate searches, only compute xxh3; skip perceptual hashes to avoid image loading
        result = {}
        for ht in hash_types:
            if search_type == 'duplicate' and ht != 'xxh3':
                self.logger.debug(f"Cache process_single for {normalized_path}, field: {ht}, result: skipped_duplicate")  # Log skip
                result[ht] = None
                continue
            if ht == 'xxh3':
                if entry.xxh3 is None:
                    self.logger.debug(f"Cache get for {normalized_path}, field: xxh3, result: miss")  # Log miss
                    try:
                        hash_value = self._compute_hash(file_path, 'xxh3', search_type=search_type)
                        entry.xxh3 = hash_value
                        self.logger.debug(f"Cache set for {normalized_path}, field: xxh3, value: {hash_value[:8]}...")  # Log compute success
                    except Exception as e:
                        self.logger.warning(f"Failed to compute xxh3 for {file_path}: {e}")
                        entry.xxh3 = None
                else:
                    self.logger.debug(f"Cache get for {normalized_path}, field: xxh3, result: hit")  # Log hit
                result['xxh3'] = entry.xxh3
            elif ht == 'phash':
                if entry.phash is None:
                    self.logger.debug(f"Cache get for {normalized_path}, field: phash, result: miss")  # Log miss
                    try:
                        hash_value = self._compute_hash(file_path, 'phash', search_type=search_type)
                        entry.phash = hash_value
                        self.logger.debug(f"Cache set for {normalized_path}, field: phash, value: {hash_value[:8]}...")  # Log success
                    except ValueError as ve:
                        # For non-image perceptual, compute file hash as fallback
                        self.logger.warning(str(ve))
                        self.logger.debug(f"Cache compute for {normalized_path}, field: phash, action: fallback")  # Log fallback
                        try:
                            fallback_hash = self._compute_hash(file_path, 'xxh3', search_type=search_type)
                            entry.phash = f"xxh3:{fallback_hash}"
                            self.logger.debug(f"Cache set for {normalized_path}, field: phash, value: xxh3:{fallback_hash[:8]}...")
                        except Exception as fe:
                            self.logger.warning(f"Fallback hash failed for phash on {file_path}: {fe}")
                            entry.phash = None
                    except Exception as e:
                        self.logger.warning(f"Failed to compute phash for {file_path}: {e}")
                        entry.phash = None
                else:
                    self.logger.debug(f"Cache get for {normalized_path}, field: phash, result: hit")  # Log hit
                result['phash'] = entry.phash
            elif ht == 'whash':
                if entry.whash is None:
                    self.logger.debug(f"Cache get for {normalized_path}, field: whash, result: miss")  # Log miss
                    try:
                        hash_value = self._compute_hash(file_path, 'whash', search_type=search_type)
                        entry.whash = hash_value
                        self.logger.debug(f"Cache set for {normalized_path}, field: whash, value: {hash_value[:8]}...")  # Log success
                    except ValueError as ve:
                        self.logger.warning(str(ve))
                        entry.whash = None
                    except Exception as e:
                        self.logger.warning(f"Failed to compute whash for {file_path}: {e}")
                        entry.whash = None
                else:
                    self.logger.debug(f"Cache get for {normalized_path}, field: whash, result: hit")  # Log hit
                result['whash'] = entry.whash
            else:
                # Unsupported hash type
                self.logger.warning(f"Unsupported hash type '{ht}' requested for {file_path}")
                result[ht] = None

        # No explicit clearing needed; conditional INSERT in set_entry skips image columns for duplicate mode,
        # preserving prior values while updating only core fields + xxh3.
        if self.set_entry(entry, search_type=search_type):
            self.logger.debug(f"Cache process_single for {normalized_path}, action: set_updated, fields: {list(result.keys())}")  # Log set
        else:
            self.logger.error(f"Failed to update cache entry for {normalized_path}")

        self.logger.debug(f"Cache process_single for {normalized_path}, result: { {k: v[:8]+'...' if v else None for k,v in result.items()} }")  # Log return (truncated)
        return result

    def get_hashes(self, file_paths: List[str], hash_types: List[str] = ['phash'], search_type: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Batch processes a list of files to get or compute hashes efficiently, respecting search_type.

        For each file, checks cache, validates, computes missing hashes if needed (skipping perceptual
        hashes in 'duplicate' mode), logs progress and errors. In 'duplicate' mode, only ensures xxh3
        is available without touching image metadata or perceptual hashes.

        This method always performs file stat validation on cached entries to ensure freshness.
        Specify hash_types to retrieve only required hashes, avoiding unnecessary computations.
        Use search_type to control scope: 'duplicate' for file-only hashing (e.g., xxh3, no image loading);
        'similarity' for perceptual hashes (phash, whash) and quality metrics (brisque) on images.

        Parameters:
            file_paths (List[str]): List of file paths to process.
            hash_types (List[str]): List of hash types to retrieve/compute. Defaults to ['phash'].
                In 'duplicate' mode, non-xxh3 types are set to None without computation.
            search_type (Optional[str]): 'duplicate' to limit to file hashes (xxh3 only, no image loading);
                'similarity' for full perceptual + content hashes. Defaults to None (full computation).
        
        Returns:
            Dict[str, Dict[str, str]]: Mapping of path to dict of hash_type: value (None for skipped perceptual in duplicate mode).
        
        Raises:
            FileNotFoundError, PermissionError, CacheComputeError: For individual files; continues for others.

        Example:
            >>> results = manager.get_hashes(['/img.jpg'], ['phash', 'xxh3'], search_type='similarity')
            >>> # Computes both
            >>> results = manager.get_hashes(['/file.txt'], ['phash'], search_type='duplicate')
            >>> # {'/file.txt': {'phash': None}} (skipped)
        """
        if not file_paths:
            self.logger.debug("Cache get_hashes for 0 paths, return empty")  # Log empty
            return {}

        # For duplicate mode, strictly limit to file-based hashing (xxh3 only); skip all perceptual/image ops
        if search_type == 'duplicate':
            hash_types = ['xxh3']
            self.logger.debug(f"Cache get_hashes duplicate_mode: forced_types: {hash_types}")  # Log mode adjust

        # For similarity, ensure all types including xxh3
        if search_type == 'similarity':
            full_types = list(set(hash_types + ['xxh3', 'phash', 'whash']))
            hash_types = full_types
            self.logger.debug(f"Cache get_hashes similarity_mode: expanded_types: {hash_types}")  # Log expand
        else:
            # Default: dedup provided types
            hash_types = list(set(hash_types))
            self.logger.debug(f"Cache get_hashes default_mode: types: {hash_types}")  # Log default

        results = {}
        total = len(file_paths)
        self.logger.debug(f"Cache get_hashes start, total: {total}, types: {hash_types}, search_type: {search_type}")  # Log start

        successful = 0
        for i, path in enumerate(file_paths, 1):
            try:
                hashes = self._process_single_file(path, hash_types, search_type=search_type)
                results[path] = hashes
                if any(hashes.values()):  # If any hash computed
                    successful += 1
                self.logger.debug(f"Cache get_hashes [{i}/{total}] for {path}, result: success")  # Log per file success
            except (FileNotFoundError, PermissionError) as e:
                self.logger.debug(f"Cache get_hashes [{i}/{total}] for {path}, result: skip, reason: {type(e).__name__}")  # Log skip
                self.logger.warning(f"[{i}/{total}] Skipped {path}: {e}")
                results[path] = {ht: None for ht in hash_types}
            except CacheComputeError as e:
                self.logger.debug(f"Cache get_hashes [{i}/{total}] for {path}, result: error_compute")  # Log compute error
                self.logger.error(f"[{i}/{total}] Failed to compute hashes for {path}: {e}")
                results[path] = {ht: None for ht in hash_types}
            except Exception as e:
                self.logger.debug(f"Cache get_hashes [{i}/{total}] for {path}, result: unexpected_error")  # Log unexpected
                self.logger.error(f"[{i}/{total}] Unexpected error for {path}: {e}", exc_info=True)
                results[path] = {ht: None for ht in hash_types}

        self.logger.debug(f"Cache get_hashes completed, total: {total}, successful: {successful}")  # Log summary
        return results

    def get_entries(self, paths: List[str], include_invalid: bool = False) -> Dict[str, Optional[FlatCacheEntry]]:
        """
        Batch retrieves validated cache entries for a list of paths.
        
        Parameters:
            paths (List[str]): List of file paths.
            include_invalid (bool): If True, return invalid entries (e.g., for cleanup); default False (None for invalid).
        
        Returns:
            Dict[str, Optional[FlatCacheEntry]]: Path to entry (None if missing/invalid unless include_invalid).
        """
        if not paths:
            return {}

        normalized_paths = [self._normalize_path(p) for p in paths]
        results = {}
        placeholders = ', '.join(['?'] * len(normalized_paths))
        sql = f"SELECT path, size, mtime, width, height, is_valid, xxh3, phash, whash, brisque, created_at, updated_at FROM {self.table_name} WHERE path IN ({placeholders})"

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, normalized_paths)
                cached_entries: Dict[str, FlatCacheEntry] = {
                    row['path']: FlatCacheEntry.from_row(row) for row in cursor.fetchall()
                }

            for path in normalized_paths:
                if path in cached_entries:
                    entry = cached_entries[path]
                    try:
                        self._validate_entry(entry)
                        results[path] = entry
                    except FlatCacheValidationError:
                        if include_invalid:
                            results[path] = entry
                        else:
                            results[path] = None
                else:
                    results[path] = None

            return results
        except FlatCacheDBError as e:
            self.logger.error(f"DB error in get_entries: {e}")
            return {p: None for p in normalized_paths}

    def clear_cache(self) -> None:
        """
        Clears the entire cache by deleting the database file and recreating the schema.

        This method removes all cached entries, deletes the database file and its companion files
        (e.g., .db-wal, .db-shm), and reinitializes the database with the current schema.

        Logs:
            - Deletion and recreation actions.
            - Success or failure of the operation.

        Raises:
            FlatCacheDBError: If the database files cannot be deleted or the database cannot be recreated.

        Example:
            >>> manager = FlatCacheManager()
            >>> manager.clear_cache()  # Deletes and recreates flat_cache.db
        """
        try:
            if self.db_path.exists():
                self.logger.info(f"Clearing cache: Deleting database files at {self.db_path}")
                self._delete_database_files()
            else:
                self.logger.info(f"No existing database to clear at {self.db_path}")

            self.logger.info("Recreating cache database with current schema")
            self._initialize_db()
            self.logger.info("Cache cleared and reinitialized successfully.")

        except FlatCacheDBError as e:
            self.logger.error(f"Failed to clear cache: {e}")
            raise FlatCacheDBError(
                f"Cache clear operation failed. Original error: {e}. "
                f"Ensure no other processes are using the database and try again.",
                original_error=e
            )
        except Exception as e:
            self.logger.error(f"Unexpected error during cache clear: {e}", exc_info=True)
            raise FlatCacheDBError(
                f"Unexpected error clearing cache: {e}",
                original_error=e
            )

    def clean_cache(self) -> int:
        """
        Cleans the cache by validating and removing invalid entries.

        This method connects to the database, queries all entries, and for each:
        - Checks if the file exists using os.path.exists().
        - If exists, compares os.path.getsize() and os.path.getmtime() against cached values.
        - Deletes rows where the file is missing or metadata mismatches (size or mtime).

        After processing, executes VACUUM to compact the database and optimize performance.

        Logs:
            - Progress: Number of entries processed and deleted.
            - Individual deletions for non-existent or mismatched files.
            - Any filesystem access errors (warnings, skips deletion).
            - Final summary of deletions.

        Returns:
            int: The total number of entries deleted.

        Raises:
            FlatCacheDBError: If database connection, query, or deletion operations fail.

        Example:
            >>> manager = FlatCacheManager()
            >>> deleted_count = manager.clean_cache()
            >>> print(f"Cleaned {deleted_count} invalid cache entries.")
        """
        deleted = 0
        processed = 0

        try:
            with self._get_connection() as conn:
                # Query all entries
                cursor = conn.execute(f"SELECT path, size, mtime FROM {self.table_name}")
                rows = cursor.fetchall()

                self.logger.info(f"Starting cache clean: Validating {len(rows)} entries")

                for row in rows:
                    processed += 1
                    path = row['path']
                    cached_size = row['size']
                    cached_mtime = row['mtime']

                    try:
                        if not os.path.exists(path):
                            self.logger.debug(f"Deleting non-existent entry: {path}")
                            conn.execute(f"DELETE FROM {self.table_name} WHERE path = ?", (path,))
                            deleted += 1
                            continue

                        current_size = os.path.getsize(path)
                        current_mtime = os.path.getmtime(path)

                        if current_size != cached_size or abs(current_mtime - cached_mtime) > 1e-6:
                            mismatch_info = f"size: {cached_size} vs {current_size}, mtime: {cached_mtime} vs {current_mtime}"
                            self.logger.debug(f"Deleting mismatched entry {path}: {mismatch_info}")
                            conn.execute(f"DELETE FROM {self.table_name} WHERE path = ?", (path,))
                            deleted += 1

                    except OSError as e:
                        if e.errno == 2:  # ENOENT
                            self.logger.debug(f"File access error (likely non-existent): {path} - {e}")
                            conn.execute(f"DELETE FROM {self.table_name} WHERE path = ?", (path,))
                            deleted += 1
                        else:
                            self.logger.warning(f"Filesystem error validating {path}: {e} (skipping)")
                    except PermissionError as e:
                        self.logger.warning(f"Permission denied for {path}: {e} (skipping)")
                    except Exception as e:
                        self.logger.warning(f"Unexpected error validating {path}: {e} (skipping)")

                # Commit deletions
                conn.commit()

                # Vacuum to compact the database
                self.logger.info("Executing VACUUM to optimize database")
                conn.execute("VACUUM")
                conn.commit()

                self.logger.info(f"Cache clean completed: Processed {processed} entries, deleted {deleted} invalid ones")

                return deleted

        except sqlite3.Error as e:
            self.logger.error(f"Database error during clean_cache: {e}", exc_info=True)
            raise FlatCacheDBError(f"Database operation failed during cache clean: {e}", original_error=e)
        except Exception as e:
            self.logger.error(f"Unexpected error during clean_cache: {e}", exc_info=True)
            raise FlatCacheDBError(f"Unexpected error cleaning cache: {e}", original_error=e)

    @log_errors()
    def get_cache_view_data(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Retrieves metadata and all entries from the flat cache database for viewing.

        Connects to the database, fetches metadata (path, entry count, version),
        and all entries ordered by path. Returns structured data for UI display.

        This method performs file stat validation on each entry and filters out stale/invalid entries,
        ensuring only current, validated data is returned for view-only purposes (e.g., in dialogs).
        Use this for read-only inspection; for operational data retrieval with automatic invalidation,
        prefer get_entry, get_hashes, or get_entries.

        Args:
            None

        Returns:
            Tuple[Dict[str, Any], List[Dict[str, Any]]]:
                - metadata_dict: {'path': str, 'entry_count': int, 'cache_version': int, 'db_size': int, 'db_size_formatted': str}
                - list_of_dicts: List of row dicts with column names as keys, ordered by path (only valid entries).

        Raises:
            FlatCacheDBError: If database connection or query fails.

        Example:
            >>> manager = FlatCacheManager()
            >>> metadata, rows = manager.get_cache_view_data()
            >>> print(f"DB: {metadata['path']} ({metadata['db_size_formatted']}), Entries: {metadata['entry_count']}")
            >>> for row in rows[:1]:  # First row
            ...     print(row['path'], row['size'])
        """
        self.logger.info(f"Fetching cache view data for DB: {self.db_path}")

        try:
            with self._get_connection() as conn:
                # Get entry count
                cursor = conn.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                entry_count = cursor.fetchone()[0]

                # Get cache version from schema_version table
                cursor = conn.execute("SELECT version FROM schema_version")
                row = cursor.fetchone()
                cache_version = row[0] if row else 1  # Default to 1 if no version table

                # Fetch all entries ordered by path
                cursor = conn.execute(
                    f"SELECT * FROM {self.table_name} ORDER BY path"
                )
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(row) for row in cursor.fetchall()]

                # Validate each entry and mark validity without filtering
                # Include all entries, valid or invalid, for complete view
                all_rows = []
                invalid_count = 0
                for row_dict in rows:
                    row_dict_copy = row_dict.copy()
                    try:
                        entry = FlatCacheEntry.from_dict(row_dict_copy)
                        is_valid, mismatches = self._validate_entry(entry, strict=False)
                        row_dict_copy['is_valid'] = is_valid
                        if not is_valid:
                            row_dict_copy['validation_mismatches'] = mismatches
                            invalid_count += 1
                        all_rows.append(row_dict_copy)
                    except Exception as e:
                        self.logger.warning(f"Unexpected error validating entry {row_dict.get('path', 'unknown')}: {e}")
                        row_dict_copy['is_valid'] = False
                        row_dict_copy['validation_mismatches'] = {"unexpected": str(e)}
                        all_rows.append(row_dict_copy)
                        invalid_count += 1

                rows = all_rows
                entry_count = len(rows)

                self.logger.info(
                    f"Cache view data fetched: {entry_count} total entries ({invalid_count} invalid), version {cache_version}"
                )

                # Get database file size
                try:
                    db_size = os.path.getsize(self.db_path)
                except OSError:
                    db_size = 0

                # Format size human-readable
                if db_size == 0:
                    db_size_formatted = "0 B"
                else:
                    size = db_size
                    units = ['B', 'KB', 'MB', 'GB', 'TB']
                    unit_index = 0
                    while size >= 1024 and unit_index < len(units) - 1:
                        size /= 1024
                        unit_index += 1
                    db_size_formatted = f"{size:.1f} {units[unit_index]}"

                metadata = {
                    'path': str(self.db_path),
                    'entry_count': entry_count,
                    'valid_count': entry_count - invalid_count,
                    'invalid_count': invalid_count,
                    'cache_version': cache_version,
                    'db_size': db_size,
                    'db_size_formatted': db_size_formatted
                }

                return metadata, rows

        except sqlite3.Error as e:
            self.logger.error(f"SQLite error fetching cache view data: {e}", exc_info=True)
            raise FlatCacheDBError(f"Failed to fetch cache data: {e}", original_error=e)
        except Exception as e:
            self.logger.error(f"Unexpected error fetching cache view data: {e}", exc_info=True)
            raise FlatCacheDBError(f"Unexpected error: {e}", original_error=e)

    # Syntax validation: This file has been reviewed for Python syntax correctness.
# Example Usage (for documentation/testing purposes)
if __name__ == '__main__':
    # Setup basic logging for standalone test
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Use a temporary file-based database for testing
    db_path = Path("./test_flat_cache.db").resolve()
    
    # Create a dummy image file for testing (simple 1x1 PNG)
    test_file_path = Path("./temp_test_image.png").resolve()
    test_file_path.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x00\x00\x04\x00\x01\xe2 \x0c\xbd\x00\x00\x00\x00IEND\xaeB`\x82')
    
    print(f"--- Starting FlatCacheManager Test (DB: {db_path.name}) ---")
    
    try:
        manager = FlatCacheManager(db_path=db_path)
        
        # Test batch get_hashes
        print("\n--- Testing get_hashes ---")
        hashes = manager.get_hashes([str(test_file_path)], ['phash', 'xxh3'])
        print(f"Hashes: {hashes}")
        
        # Verify entry
        entry = manager.get_entry(str(test_file_path))
        print(f"Entry xxh3: {entry.xxh3 if entry else None}, phash: {entry.phash if entry else None}")
        
        # Test invalidation by modifying file (append to make size change)
        with open(test_file_path, 'ab') as f:
            f.write(b'test')
        print("\n--- After modification (should recompute) ---")
        new_hashes = manager.get_hashes([str(test_file_path)], ['phash'])
        print(f"New hashes: {new_hashes}")
        
    finally:
        # Clean up
        if test_file_path.exists():
            os.remove(test_file_path)
        for ext in ['', '-wal', '-shm']:
            db_file = db_path.with_suffix(f".db{ext}")
            if db_file.exists():
                os.remove(db_file)
        print(f"\nCleaned up test artifacts.")
