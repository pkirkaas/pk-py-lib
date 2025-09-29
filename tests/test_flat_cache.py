"""
tests/test_flat_cache.py

Comprehensive unit tests for the FlatCacheManager and FlatCacheEntry implementation
in src/pk_py_lib/core/flat_cache.py.

These tests use mocking for file system interactions (os.stat, os.path.exists)
and temporary SQLite databases to ensure isolation and independence.

Syntax validation was performed with Python's ``ast`` module prior to inclusion.
"""

import pytest
import sqlite3
import os
import time
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta
from typing import Any

# Import the components to be tested
from src.pk_py_lib.core.flat_cache import (
    FlatCacheEntry,
    FlatCacheManager,
    FlatCacheError,
    FlatCacheDBError,
    FlatCacheValidationError,
    TABLE_NAME,
    CURRENT_ENTRY_VERSION
)

# --- Fixtures and Mocks ---

TEST_FILE_PATH = "/path/to/test/file.jpg"
TEST_NORMALIZED_PATH = Path(TEST_FILE_PATH).resolve().as_posix()
TEST_TIME = 1678886400  # March 15, 2023 00:00:00 UTC

@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provides a temporary, unique path for the SQLite database."""
    return tmp_path / "test_flat_cache.db"

@pytest.fixture
def mock_stat_result():
    """Provides a mock os.stat_result object for file system mocking."""
    mock_stat = MagicMock()
    mock_stat.st_size = 1024
    mock_stat.st_mtime = TEST_TIME
    mock_stat.st_ino = 123456789
    mock_stat.st_dev = 987654321
    return mock_stat

@pytest.fixture
def mock_time():
    """Mocks time.time() to return a fixed timestamp."""
    with patch('time.time', return_value=TEST_TIME):
        yield TEST_TIME

@pytest.fixture
def sample_entry(mock_stat_result) -> FlatCacheEntry:
    """Provides a fully populated, valid FlatCacheEntry."""
    return FlatCacheEntry(
        file=TEST_FILE_PATH,
        size=mock_stat_result.st_size,
        mod_date=int(mock_stat_result.st_mtime),
        file_inode=str(mock_stat_result.st_ino),
        file_device=str(mock_stat_result.st_dev),
        blake3_hash="b3_hash_value",
        phash="p_hash_value",
        brisque_score=50.5,
        quality_algorithm="brisque",
        computed_at=TEST_TIME,
        entry_version=CURRENT_ENTRY_VERSION
    )

@pytest.fixture
def flat_cache_manager(temp_db_path: Path, mock_stat_result: MagicMock, mock_time: int):
    """
    Initializes a FlatCacheManager with mocked os.stat and os.path.exists.
    The mock assumes the file exists and returns fixed stats.
    """
    # We patch os.stat globally for the duration of the test using this fixture
    with patch('os.stat', return_value=mock_stat_result):
        manager = FlatCacheManager(db_path=temp_db_path)
        yield manager

# --- Test FlatCacheEntry ---

def test_flat_cache_entry_creation(sample_entry: FlatCacheEntry):
    """Test basic creation and attribute access."""
    assert sample_entry.file == TEST_FILE_PATH
    assert sample_entry.size == 1024
    assert sample_entry.blake3_hash == "b3_hash_value"
    assert sample_entry.computed_at == TEST_TIME
    assert sample_entry.entry_version == CURRENT_ENTRY_VERSION

def test_flat_cache_entry_from_row(sample_entry: FlatCacheEntry):
    """Test creating an entry from a sqlite3.Row object."""
    # Simulate a sqlite3.Row object (which behaves like a dict/tuple)
    row_data = {
        'file': TEST_NORMALIZED_PATH,
        'size': 2048,
        'mod_date': 1678886500,
        'file_inode': '999',
        'file_device': '888',
        'blake3_hash': 'new_hash',
        'xxh3_hash': None,
        'phash': 'new_phash',
        'whash': None,
        'color_phash': None,
        'brisque_score': 60.0,
        'niqe_score': None,
        'piqe_score': None,
        'quality_algorithm': 'brisque',
        'computed_at': TEST_TIME + 100,
        'entry_version': CURRENT_ENTRY_VERSION
    }
    
    # Use MagicMock to simulate sqlite3.Row behavior
    mock_row = MagicMock(spec=sqlite3.Row)
    mock_row.__getitem__.side_effect = row_data.__getitem__
    mock_row.__iter__.side_effect = row_data.__iter__
    mock_row.keys.return_value = row_data.keys()
    
    entry = FlatCacheEntry.from_row(mock_row)
    
    assert entry.file == TEST_NORMALIZED_PATH
    assert entry.size == 2048
    assert entry.blake3_hash == 'new_hash'
    assert entry.brisque_score == 60.0
    assert entry.computed_at == TEST_TIME + 100

# --- Test FlatCacheManager Initialization and Connection ---

def test_manager_initialization_creates_db_and_table(temp_db_path: Path, mock_stat_result: MagicMock):
    """Test that initialization creates the DB file and the table, and sets WAL mode."""
    assert not temp_db_path.exists()
    
    with patch('os.stat', return_value=mock_stat_result):
        manager = FlatCacheManager(db_path=temp_db_path)
    
    assert temp_db_path.exists()
    
    # Check if the table exists
    with sqlite3.connect(str(temp_db_path)) as conn:
        cursor = conn.execute(f"PRAGMA table_info({TABLE_NAME})")
        columns = [row[1] for row in cursor.fetchall()]
        assert 'file' in columns
        assert 'blake3_hash' in columns
        
        # Check WAL mode (must use a fresh connection to verify PRAGMA was executed)
        with manager._get_connection() as conn_check:
            cursor = conn_check.execute("PRAGMA journal_mode")
            assert cursor.fetchone()[0] == 'wal'

def test_manager_initialization_unwritable_path(temp_db_path: Path):
    """Test error handling when the database path is unwritable."""
    unwritable_path = temp_db_path / "unwritable" / "db.db"
    
    # Mock Path.mkdir to raise an error, simulating permission issues
    with patch('pathlib.Path.mkdir', side_effect=OSError("Permission denied")), \
         pytest.raises(FlatCacheDBError) as excinfo:
        FlatCacheManager(db_path=unwritable_path)
        
    assert "Failed to initialize flat cache database" in str(excinfo.value)

def test_get_connection_handles_db_error():
    """Test that _get_connection catches sqlite3.Error and raises FlatCacheDBError."""
    manager = FlatCacheManager(db_path=Path(":memory:"))
    
    # Mock sqlite3.connect to raise an error immediately
    with patch('sqlite3.connect', side_effect=sqlite3.Error("Mock DB connection failure")), \
         pytest.raises(FlatCacheDBError) as excinfo:
        with manager._get_connection():
            pass
            
    assert "Database operation failed" in str(excinfo.value)

# --- Test File Stats and Validation ---

@patch('os.stat')
def test_get_file_stats_success(mock_os_stat, mock_stat_result):
    """Test successful retrieval of file stats."""
    mock_os_stat.return_value = mock_stat_result
    
    size, mtime, inode, device = FlatCacheManager._get_file_stats(TEST_FILE_PATH)
    
    assert size == 1024
    assert mtime == TEST_TIME
    assert inode == str(mock_stat_result.st_ino)
    assert device == str(mock_stat_result.st_dev)
    mock_os_stat.assert_called_once_with(TEST_FILE_PATH)

@patch('os.stat', side_effect=FileNotFoundError)
def test_get_file_stats_file_not_found(mock_os_stat):
    """Test FileNotFoundError handling in _get_file_stats."""
    with pytest.raises(FileNotFoundError):
        FlatCacheManager._get_file_stats(TEST_FILE_PATH)

@patch('os.stat', side_effect=OSError("Access denied"))
def test_get_file_stats_permission_error(mock_os_stat):
    """Test PermissionError handling in _get_file_stats."""
    with pytest.raises(PermissionError) as excinfo:
        FlatCacheManager._get_file_stats(TEST_FILE_PATH)
    assert "Could not read stats" in str(excinfo.value)

def test_validate_entry_success(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry):
    """Test validation succeeds when cached stats match current stats."""
    # The manager fixture already mocks os.stat to match sample_entry's stats
    assert flat_cache_manager._validate_entry(sample_entry) is True

@pytest.mark.parametrize("mismatch_field, current_value", [
    ("st_size", 999),
    ("st_mtime", TEST_TIME + 100),
    ("st_ino", 111111111),
    ("st_dev", 222222222),
])
def test_validate_entry_mismatch(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, mock_stat_result: MagicMock, mismatch_field: str, current_value: Any, caplog):
    """Test validation fails when a stat field mismatches."""
    
    # Update the mock stat result to cause a mismatch
    setattr(mock_stat_result, mismatch_field, current_value)
    
    # Ensure the entry's stats are different from the mock's new stats
    if mismatch_field == "st_mtime":
        sample_entry.mod_date = TEST_TIME # Original value
        current_value = int(current_value)
    elif mismatch_field == "st_ino":
        sample_entry.file_inode = str(sample_entry.file_inode) # Original value
        current_value = str(current_value)
    elif mismatch_field == "st_dev":
        sample_entry.file_device = str(sample_entry.file_device) # Original value
        current_value = str(current_value)
    else:
        sample_entry.size = 1024 # Original value
        
    with pytest.raises(FlatCacheValidationError) as excinfo:
        flat_cache_manager._validate_entry(sample_entry)
        
    # Check that the specific mismatch is reported in the exception
    mismatch_key = mismatch_field.replace("st_", "")
    assert mismatch_key in excinfo.value.mismatches
    
    # Check logging
    with caplog.at_level(logging.WARNING):
        try:
            flat_cache_manager._validate_entry(sample_entry)
        except FlatCacheValidationError:
            pass
    assert "Cache miss (validation failed)" in caplog.text
    assert mismatch_key in caplog.text

def test_validate_entry_file_not_found(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test validation fails when the file no longer exists."""
    
    # Mock _get_file_stats to raise FileNotFoundError
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=FileNotFoundError), \
         pytest.raises(FlatCacheValidationError) as excinfo:
        flat_cache_manager._validate_entry(sample_entry)
        
    assert "File not found" in excinfo.value.mismatches["existence"]
    
    with caplog.at_level(logging.DEBUG):
        try:
            flat_cache_manager._validate_entry(sample_entry)
        except FlatCacheValidationError:
            pass
    assert "Validation failed: File not found" in caplog.text

def test_validate_entry_permission_error(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test validation fails (raises ValidationError) on PermissionError."""
    
    # Mock _get_file_stats to raise PermissionError
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=PermissionError("Access denied")), \
         pytest.raises(FlatCacheValidationError) as excinfo:
        flat_cache_manager._validate_entry(sample_entry)
        
    assert "permission" in excinfo.value.mismatches
    assert "Access denied" in excinfo.value.mismatches["permission"]
    
    with caplog.at_level(logging.WARNING):
        try:
            flat_cache_manager._validate_entry(sample_entry)
        except FlatCacheValidationError:
            pass
    assert "Validation skipped due to permission error" in caplog.text

# --- Test get_entry ---

def test_get_entry_cache_miss_not_found(flat_cache_manager: FlatCacheManager, caplog):
    """Test cache miss when the entry is not in the DB."""
    result = flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert result is None
    with caplog.at_level(logging.DEBUG):
        flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert "Cache miss (not found)" in caplog.text

def test_get_entry_cache_hit_success(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, mock_time: int, caplog):
    """Test successful cache hit with validation passing."""
    # Insert the entry first (set_entry handles normalization and stat population)
    flat_cache_manager.set_entry(sample_entry)
    
    # Retrieve and validate
    retrieved_entry = flat_cache_manager.get_entry(TEST_FILE_PATH)
    
    assert retrieved_entry is not None
    assert retrieved_entry.blake3_hash == "b3_hash_value"
    assert retrieved_entry.computed_at == mock_time
    
    with caplog.at_level(logging.DEBUG):
        flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert "Cache hit (validation successful)" in caplog.text

def test_get_entry_validation_fail_returns_none(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, mock_stat_result: MagicMock, caplog):
    """Test that if validation fails (e.g., file size changed), get_entry returns None."""
    
    # 1. Insert the original entry
    flat_cache_manager.set_entry(sample_entry)
    
    # 2. Change the mock stat result to cause a mismatch (stale cache)
    mock_stat_result.st_size = 5000
    
    # 3. Attempt retrieval
    retrieved_entry = flat_cache_manager.get_entry(TEST_FILE_PATH)
    
    assert retrieved_entry is None
    
    # Check that the validation failure was logged
    with caplog.at_level(logging.WARNING):
        flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert "Cache miss (validation failed)" in caplog.text
    assert "size" in caplog.text

def test_get_entry_db_error_returns_none(flat_cache_manager: FlatCacheManager, caplog):
    """Test that DB errors during retrieval are caught and return None."""
    
    # Mock the internal connection context manager to raise a DB error
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Mock DB failure")), \
         caplog.at_level(logging.ERROR):
        result = flat_cache_manager.get_entry(TEST_FILE_PATH)
        
    assert result is None
    assert "DB error retrieving entry" in caplog.text

# --- Test set_entry ---

def test_set_entry_insert_success(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, mock_time: int):
    """Test successful insertion of a new entry."""
    
    # Ensure computed_at is updated and stats are fetched just before saving
    sample_entry.computed_at = 0 # Should be overwritten by mock_time
    
    result = flat_cache_manager.set_entry(sample_entry)
    assert result is True
    
    # Verify the entry was saved with correct dynamic fields
    retrieved = flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert retrieved is not None
    assert retrieved.computed_at == mock_time
    assert retrieved.file == TEST_NORMALIZED_PATH
    assert retrieved.size == 1024 # From mock_stat_result

def test_set_entry_update_success(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, mock_time: int):
    """Test successful update (UPSERT) of an existing entry."""
    
    # 1. Insert initial entry
    flat_cache_manager.set_entry(sample_entry)
    
    # 2. Create modified entry (different hash, later time)
    new_time = mock_time + 3600
    modified_entry = FlatCacheEntry(
        file=TEST_FILE_PATH,
        size=1024, # Stats must match mock_stat_result
        mod_date=TEST_TIME,
        file_inode=str(123456789),
        file_device=str(987654321),
        blake3_hash="new_hash_value",
        computed_at=0 # Will be overwritten by new_time mock
    )
    
    with patch('time.time', return_value=new_time):
        result = flat_cache_manager.set_entry(modified_entry)
        
    assert result is True
    
    # 3. Verify update
    retrieved = flat_cache_manager.get_entry(TEST_FILE_PATH)
    assert retrieved.blake3_hash == "new_hash_value"
    assert retrieved.computed_at == new_time

def test_set_entry_inaccessible_file_returns_false(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test that set_entry returns False if file stats cannot be read."""
    
    # Mock _get_file_stats to raise FileNotFoundError
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=FileNotFoundError), \
         caplog.at_level(logging.WARNING):
        result = flat_cache_manager.set_entry(sample_entry)
        
    assert result is False
    assert "Cannot set entry for non-existent or inaccessible file" in caplog.text
    
    # Verify no entry was created
    assert flat_cache_manager.get_entry(TEST_FILE_PATH) is None

def test_set_entry_db_error_returns_false(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test that DB errors during set_entry are caught and return False."""
    
    # Mock the internal connection context manager to raise a DB error
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Mock DB failure")), \
         caplog.at_level(logging.ERROR):
        result = flat_cache_manager.set_entry(sample_entry)
        
    assert result is False
    assert "DB error setting entry" in caplog.text

# --- Test batch_set ---

def test_batch_set_success(flat_cache_manager: FlatCacheManager, mock_stat_result: MagicMock, mock_time: int):
    """Test successful batch insertion of multiple entries."""
    
    entry1 = FlatCacheEntry(file="/file1.txt", size=100, mod_date=TEST_TIME, file_inode='1', file_device='1', blake3_hash="h1")
    entry2 = FlatCacheEntry(file="/file2.txt", size=200, mod_date=TEST_TIME, file_inode='2', file_device='2', blake3_hash="h2")
    
    # We need to mock _get_file_stats to return different values for different files
    def mock_get_file_stats(file_path):
        if "file1" in file_path:
            return 100, TEST_TIME, '1', '1'
        if "file2" in file_path:
            return 200, TEST_TIME, '2', '2'
        raise FileNotFoundError
        
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=mock_get_file_stats):
        count = flat_cache_manager.batch_set([entry1, entry2])
        
    assert count == 2
    
    # Verify entries exist
    assert flat_cache_manager.get_entry("/file1.txt").blake3_hash == "h1"
    assert flat_cache_manager.get_entry("/file2.txt").blake3_hash == "h2"

def test_batch_set_partial_success_skips_invalid(flat_cache_manager: FlatCacheManager, caplog):
    """Test that batch_set skips entries for inaccessible files."""
    
    entry1 = FlatCacheEntry(file="/valid.txt", size=100, mod_date=TEST_TIME, file_inode='1', file_device='1', blake3_hash="h_valid")
    entry2 = FlatCacheEntry(file="/invalid.txt", size=200, mod_date=TEST_TIME, file_inode='2', file_device='2', blake3_hash="h_invalid")
    
    def mock_get_file_stats(file_path):
        if "valid" in file_path:
            return 100, TEST_TIME, '1', '1'
        if "invalid" in file_path:
            raise PermissionError("Access denied")
        
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=mock_get_file_stats), \
         caplog.at_level(logging.WARNING):
        count = flat_cache_manager.batch_set([entry1, entry2])
        
    assert count == 1
    assert "Skipping batch set for /invalid.txt" in caplog.text
    
    # Verify only the valid entry was inserted
    assert flat_cache_manager.get_entry("/valid.txt") is not None
    assert flat_cache_manager.get_entry("/invalid.txt") is None

def test_batch_set_db_error_rollback(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test that a DB error causes the entire transaction to fail and returns 0."""
    
    # Mock _get_file_stats to ensure entries are prepared successfully
    def mock_get_file_stats(file_path):
        return 1024, TEST_TIME, '123456789', '987654321'
        
    # Mock the connection's executemany to raise a DB error
    mock_conn = MagicMock(spec=sqlite3.Connection)
    mock_conn.execute.return_value = MagicMock(rowcount=1)
    mock_conn.executemany.side_effect = sqlite3.Error("Mock executemany failure")
    
    @contextmanager
    def mock_get_connection():
        try:
            yield mock_conn
        except sqlite3.Error as e:
            mock_conn.rollback()
            raise FlatCacheDBError(f"Database operation failed: {e}", original_error=e)
        finally:
            mock_conn.close()

    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=mock_get_file_stats), \
         patch.object(flat_cache_manager, '_get_connection', side_effect=mock_get_connection), \
         caplog.at_level(logging.ERROR):
        
        # Need to use a list of entries that are prepared successfully
        entry1 = sample_entry
        entry2 = FlatCacheEntry(file="/file2.txt", size=1024, mod_date=TEST_TIME, file_inode='123456789', file_device='987654321', blake3_hash="h2")
        
        count = flat_cache_manager.batch_set([entry1, entry2])
        
    assert count == 0
    assert "DB error during batch set" in caplog.text
    
    # Verify rollback was called (implicitly checked by the mock_get_connection logic raising FlatCacheDBError)

# --- Test get_uncached_files ---

def test_get_uncached_files_all_missing(flat_cache_manager: FlatCacheManager):
    """Test returns all paths if cache is empty."""
    paths = ["/a.jpg", "/b.png"]
    normalized_paths = [Path(p).resolve().as_posix() for p in paths]
    
    # Mock os.stat to ensure files exist for validation check
    with patch.object(flat_cache_manager, '_get_file_stats', return_value=(100, TEST_TIME, '1', '1')):
        uncached = flat_cache_manager.get_uncached_files(paths)
        
    assert set(uncached) == set(normalized_paths)

def test_get_uncached_files_mixed_status(flat_cache_manager: FlatCacheManager, mock_stat_result: MagicMock):
    """Test returns only missing and stale files."""
    
    # Setup:
    # 1. Cached and valid: /valid.jpg (size 1024, mtime TEST_TIME)
    # 2. Cached but stale: /stale.jpg (cached size 1024, current size 5000)
    # 3. Missing: /missing.jpg
    
    valid_path = "/valid.jpg"
    stale_path = "/stale.jpg"
    missing_path = "/missing.jpg"
    
    # Insert valid entry
    valid_entry = FlatCacheEntry(file=valid_path, size=1024, mod_date=TEST_TIME, file_inode='1', file_device='1', blake3_hash="h_valid")
    flat_cache_manager.set_entry(valid_entry)
    
    # Insert stale entry (using current mock stats)
    stale_entry = FlatCacheEntry(file=stale_path, size=1024, mod_date=TEST_TIME, file_inode='1', file_device='1', blake3_hash="h_stale")
    flat_cache_manager.set_entry(stale_entry)
    
    # Mock _get_file_stats to simulate file changes for validation
    def mock_get_file_stats(file_path):
        if valid_path in file_path:
            return 1024, TEST_TIME, '1', '1' # Match
        if stale_path in file_path:
            return 5000, TEST_TIME, '1', '1' # Size mismatch
        if missing_path in file_path:
            raise FileNotFoundError
        # Default return for set_entry calls
        return 1024, TEST_TIME, '1', '1'
        
    paths_to_check = [valid_path, stale_path, missing_path]
    
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=mock_get_file_stats):
        uncached = flat_cache_manager.get_uncached_files(paths_to_check)
        
    # Expected: stale.jpg (validation failed) and missing.jpg (not in DB)
    expected_uncached = [Path(stale_path).resolve().as_posix(), Path(missing_path).resolve().as_posix()]
    assert set(uncached) == set(expected_uncached)

def test_get_uncached_files_db_error_returns_all(flat_cache_manager: FlatCacheManager):
    """Test that if DB query fails, all input paths are returned."""
    paths = ["/a.jpg", "/b.png"]
    normalized_paths = [Path(p).resolve().as_posix() for p in paths]
    
    # Mock the connection context manager to raise a DB error during the initial query
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Query failed")):
        uncached = flat_cache_manager.get_uncached_files(paths)
        
    assert set(uncached) == set(normalized_paths)

# --- Test invalidate_entry ---

def test_invalidate_entry_success(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry):
    """Test successful deletion of an entry."""
    
    # Insert entry
    flat_cache_manager.set_entry(sample_entry)
    assert flat_cache_manager.get_entry(TEST_FILE_PATH) is not None
    
    # Invalidate
    result = flat_cache_manager.invalidate_entry(TEST_FILE_PATH)
    assert result is True
    
    # Verify deletion
    assert flat_cache_manager.get_entry(TEST_FILE_PATH) is None

def test_invalidate_entry_not_exists(flat_cache_manager: FlatCacheManager, caplog):
    """Test no-op when entry does not exist."""
    
    with caplog.at_level(logging.DEBUG):
        result = flat_cache_manager.invalidate_entry("/non/existent/file.txt")
        
    assert result is True
    assert "Cache entry not found for invalidation" in caplog.text

def test_invalidate_entry_db_error_returns_false(flat_cache_manager: FlatCacheManager, caplog):
    """Test that DB errors during invalidation are caught and return False."""
    
    # Mock the internal connection context manager to raise a DB error
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Mock DB failure")), \
         caplog.at_level(logging.ERROR):
        result = flat_cache_manager.invalidate_entry(TEST_FILE_PATH)
        
    assert result is False
    assert "DB error invalidating entry" in caplog.text

# --- Test cleanup_old_entries ---

def test_cleanup_old_entries_success(flat_cache_manager: FlatCacheManager, mock_stat_result: MagicMock, mock_time: int):
    """Test cleanup deletes entries older than the threshold."""
    
    # Current time is TEST_TIME (1678886400)
    
    # 1. Entry 1: Old (31 days ago) -> Should be deleted by default (days=30)
    old_time = mock_time - (31 * 24 * 60 * 60)
    entry_old = FlatCacheEntry(file="/old.jpg", size=1024, mod_date=TEST_TIME, file_inode='1', file_device='1', computed_at=old_time)
    flat_cache_manager.set_entry(entry_old)
    
    # 2. Entry 2: Recent (1 day ago) -> Should be kept
    recent_time = mock_time - (1 * 24 * 60 * 60)
    entry_recent = FlatCacheEntry(file="/recent.jpg", size=1024, mod_date=TEST_TIME, file_inode='1', file_device='1', computed_at=recent_time)
    flat_cache_manager.set_entry(entry_recent)
    
    # Run cleanup with default 30 days
    deleted_count = flat_cache_manager.cleanup_old_entries(days=30)
    
    assert deleted_count == 1
    assert flat_cache_manager.get_entry("/old.jpg") is None
    assert flat_cache_manager.get_entry("/recent.jpg") is not None

def test_cleanup_old_entries_days_zero_is_skipped(flat_cache_manager: FlatCacheManager, sample_entry: FlatCacheEntry, caplog):
    """Test that days=0 is skipped and logs a warning."""
    
    flat_cache_manager.set_entry(sample_entry)
    
    with caplog.at_level(logging.WARNING):
        deleted_count = flat_cache_manager.cleanup_old_entries(days=0)
        
    assert deleted_count == 0
    assert "Cleanup skipped: 'days' parameter must be positive." in caplog.text
    assert flat_cache_manager.get_entry(TEST_FILE_PATH) is not None

def test_cleanup_old_entries_db_error_returns_zero(flat_cache_manager: FlatCacheManager, caplog):
    """Test that DB errors during cleanup are caught and return 0."""
    
    # Mock the internal connection context manager to raise a DB error
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Mock DB failure")), \
         caplog.at_level(logging.ERROR):
        deleted_count = flat_cache_manager.cleanup_old_entries(days=1)
        
    assert deleted_count == 0
    assert "DB error during cleanup" in caplog.text

# --- Test get_all_hashes_by_algorithm ---

def test_get_all_hashes_by_algorithm_success(flat_cache_manager: FlatCacheManager, mock_stat_result: MagicMock):
    """Test successful retrieval of hashes for a valid algorithm."""
    
    entry1 = FlatCacheEntry(file="/f1.jpg", size=1024, mod_date=TEST_TIME, file_inode='1', file_device='1', blake3_hash="h1", phash="p1")
    entry2 = FlatCacheEntry(file="/f2.jpg", size=1024, mod_date=TEST_TIME, file_inode='2', file_device='2', blake3_hash="h2", phash=None)
    entry3 = FlatCacheEntry(file="/f3.jpg", size=1024, mod_date=TEST_TIME, file_inode='3', file_device='3', blake3_hash="h3", phash="p3")
    
    # Mock _get_file_stats to ensure all entries are prepared successfully
    def mock_get_file_stats(file_path):
        if "f1" in file_path: return 1024, TEST_TIME, '1', '1'
        if "f2" in file_path: return 1024, TEST_TIME, '2', '2'
        if "f3" in file_path: return 1024, TEST_TIME, '3', '3'
        return 1024, TEST_TIME, '123456789', '987654321'
        
    with patch.object(flat_cache_manager, '_get_file_stats', side_effect=mock_get_file_stats):
        flat_cache_manager.batch_set([entry1, entry2, entry3])
        
    # Test blake3_hash (all 3 should be returned)
    blake3_hashes = flat_cache_manager.get_all_hashes_by_algorithm('blake3_hash')
    assert len(blake3_hashes) == 3
    assert blake3_hashes[Path("/f1.jpg").resolve().as_posix()] == "h1"
    
    # Test phash (only f1 and f3 should be returned, as f2 is None)
    phash_map = flat_cache_manager.get_all_hashes_by_algorithm('phash')
    assert len(phash_map) == 2
    assert Path("/f2.jpg").resolve().as_posix() not in phash_map
    assert phash_map[Path("/f3.jpg").resolve().as_posix()] == "p3"

def test_get_all_hashes_by_algorithm_invalid_algorithm():
    """Test that an invalid algorithm name raises FlatCacheError."""
    manager = FlatCacheManager(db_path=Path(":memory:"))
    with pytest.raises(FlatCacheError) as excinfo:
        manager.get_all_hashes_by_algorithm('invalid_hash')
        
    assert "Invalid hash algorithm specified" in str(excinfo.value)

def test_get_all_hashes_by_algorithm_db_error_returns_empty(flat_cache_manager: FlatCacheManager, caplog):
    """Test that DB errors during hash retrieval are caught and return empty dict."""
    
    # Mock the internal connection context manager to raise a DB error
    with patch.object(flat_cache_manager, '_get_connection', side_effect=FlatCacheDBError("Mock DB failure")), \
         caplog.at_level(logging.ERROR):
        results = flat_cache_manager.get_all_hashes_by_algorithm('phash')
        
    assert results == {}
    assert "DB error retrieving hashes for algorithm phash" in caplog.text

# --- Test Schema Migration (Implicitly via FlatCacheManager) ---

def test_manager_handles_older_schema_on_read(temp_db_path: Path, mock_stat_result: MagicMock):
    """
    Simulate an older schema (missing 'quality_algorithm') and ensure FlatCacheEntry.from_row
    can still read the data without error (as it filters fields).
    """
    
    # 1. Create a connection and manually create a table with an older schema
    with sqlite3.connect(str(temp_db_path)) as conn:
        conn.execute(f"""
            CREATE TABLE {TABLE_NAME} (
                file TEXT PRIMARY KEY NOT NULL,
                size INTEGER NOT NULL,
                mod_date INTEGER NOT NULL,
                file_inode TEXT NOT NULL,
                file_device TEXT NOT NULL,
                blake3_hash TEXT,
                computed_at INTEGER NOT NULL
            );
        """)
        conn.execute(f"""
            INSERT INTO {TABLE_NAME} (file, size, mod_date, file_inode, file_device, blake3_hash, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (TEST_NORMALIZED_PATH, 100, TEST_TIME, '1', '1', 'old_hash', TEST_TIME))
        conn.commit()
        
    # 2. Initialize the manager (it won't recreate the table if it exists)
    with patch('os.stat', return_value=mock_stat_result):
        manager = FlatCacheManager(db_path=temp_db_path)
        
    # 3. Retrieve the entry. FlatCacheEntry.from_row should handle the missing columns
    retrieved = manager.get_entry(TEST_FILE_PATH)
    
    assert retrieved is not None
    assert retrieved.blake3_hash == 'old_hash'
    # Missing fields should default to None/0 as defined in the dataclass
    assert retrieved.phash is None
    assert retrieved.brisque_score is None
    assert retrieved.entry_version == CURRENT_ENTRY_VERSION