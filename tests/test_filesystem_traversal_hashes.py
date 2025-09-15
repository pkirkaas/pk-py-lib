"""
tests/test_filesystem_traversal_hashes.py

Tests for scan_directory with hash computation in core/filesystem/traversal.py.
Focuses on integration with similarity.py for on-the-fly hashing during scans,
DB storage via DatabaseManager, and error handling. Uses mocks for traversal,
similarity computation, and DB inserts. Covers compute_hashes=True/False,
valid/invalid images, batch errors (continues scanning).

Uses pytest with mock.patch for os.walk, similarity.compute_phash, db.execute.
4-space indent, rich comments. Syntax validated via ast.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from typing import List, Dict, Any

from src.pk_py_lib.core.filesystem.traversal import scan_directory, IMAGE_EXTENSIONS
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.cache import CacheManager
from src.pk_py_lib.core.image.similarity import InvalidImageError


@pytest.fixture
def mock_db():
    """Mock DatabaseManager for insert tests."""
    db = MagicMock(spec=DatabaseManager)
    mock_conn = MagicMock()
    db.get_connection.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value = MagicMock(fetchone=lambda: (1,))  # image_id=1
    mock_conn.fetchone.return_value = None
    return db


@pytest.fixture
def mock_cache():
    """Mock CacheManager."""
    cache = MagicMock(spec=CacheManager)
    cache.get_hash.return_value = None
    return cache


@pytest.fixture
def sample_root(tmp_path: Path) -> Path:
    """Create sample root with test images."""
    root = tmp_path / "test_root"
    root.mkdir()
    img1 = root / "img1.jpg"
    img2 = root / "img2.png"
    invalid = root / "invalid.txt"
    img1.touch()
    img2.touch()
    invalid.touch()
    return root


class TestScanDirectoryHashes:
    """Tests for scan_directory with compute_hashes integration."""

    def test_scan_directory_no_hashes(self, sample_root: Path, mock_db: DatabaseManager):
        """Test compute_hashes=False: no hashes, basic file info only."""
        with patch("src.pk_py_lib.core.filesystem.traversal.DirectoryTraversal.walk_files") as mock_walk:
            mock_walk.return_value = [sample_root / "img1.jpg", sample_root / "img2.png"]

            results = scan_directory(
                sample_root,
                compute_hashes=False,
                db_manager=mock_db,
                **{}  # No walk kwargs
            )

            assert len(results) == 2
            for res in results:
                assert 'hashes' not in res
                assert res['path'] in [str(sample_root / "img1.jpg"), str(sample_root / "img2.png")]
                assert res['extension'] in ['.jpg', '.png']
            mock_db.get_connection.assert_not_called()  # No DB for no hashes

    def test_scan_directory_with_hashes_success(self, sample_root: Path, mock_db: DatabaseManager, mock_cache: CacheManager):
        """Test compute_hashes=True: computes hashes, stores in DB, returns with 'hashes'."""
        with patch("src.pk_py_lib.core.filesystem.traversal.DirectoryTraversal.walk_files") as mock_walk, \
             patch("src.pk_py_lib.core.image.similarity.compute_phash") as mock_phash:
            mock_walk.return_value = [sample_root / "img1.jpg"]
            mock_phash.return_value = "a1b2c3d4e5f67890"

            results = scan_directory(
                sample_root,
                compute_hashes=True,
                algorithms=["phash"],
                db_manager=mock_db,
                cache_manager=mock_cache,
                settings={"similarity": {"enabled_algorithms": ["phash"]}}
            )

            assert len(results) == 1
            res = results[0]
            assert res['path'] == str(sample_root / "img1.jpg")
            assert res['hashes'] == {'phash': 'a1b2c3d4e5f67890'}
            mock_phash.assert_called_once_with(str(sample_root / "img1.jpg"), cache_manager=mock_cache)
            # DB inserts called
            mock_db.get_connection.assert_called_once()
            mock_conn = mock_db.get_connection.return_value.__enter__.return_value
            assert mock_conn.execute.call_count >= 2  # metadata + hashes
            mock_conn.execute.assert_any_call(
                "INSERT OR IGNORE INTO image_metadata ...",  # Partial match
                ANY  # Params
            )
            mock_conn.execute.assert_any_call(
                "INSERT OR REPLACE INTO image_hashes ...",
                (1, 'phash', 'a1b2c3d4e5f67890')
            )

    def test_scan_directory_hash_error_handling(self, sample_root: Path, mock_db: DatabaseManager, mock_cache: CacheManager):
        """Test continues on hash error, logs warning, 'hashes' empty."""
        with patch("src.pk_py_lib.core.filesystem.traversal.DirectoryTraversal.walk_files") as mock_walk, \
             patch("src.pk_py_lib.core.image.similarity.compute_phash") as mock_phash, \
             patch("src.pk_py_lib.core.filesystem.traversal.logger") as mock_log:
            mock_walk.return_value = [sample_root / "img1.jpg"]
            mock_phash.side_effect = InvalidImageError("test", "corrupted")

            results = scan_directory(
                sample_root,
                compute_hashes=True,
                algorithms=["phash"],
                db_manager=mock_db,
                cache_manager=mock_cache
            )

            assert len(results) == 1
            assert 'hashes' not in results[0] or results[0]['hashes'] == {}  # Empty or absent
            mock_phash.assert_called_once()
            mock_log.warning.assert_called_once_with(
                "Batch failed for ... : Invalid image at test: corrupted"  # Match
            )
            # DB insert for metadata only, no hashes
            mock_conn = mock_db.get_connection.return_value.__enter__.return_value
            assert mock_conn.execute.call_count == 1  # Only metadata

    def test_scan_directory_non_image_skipped(self, sample_root: Path, mock_db: DatabaseManager):
        """Test non-image extensions skipped for hashing."""
        with patch("src.pk_py_lib.core.filesystem.traversal.DirectoryTraversal.walk_files") as mock_walk, \
             patch("src.pk_py_lib.core.image.similarity.compute_phash") as mock_phash:
            mock_walk.return_value = [sample_root / "txt.txt"]  # Not in IMAGE_EXTENSIONS

            results = scan_directory(
                sample_root,
                compute_hashes=True,
                algorithms=["phash"],
                db_manager=mock_db
            )

            assert len(results) == 1
            assert 'hashes' not in results[0]  # No hash for non-image
            mock_phash.assert_not_called()

    def test_scan_directory_db_storage_failure(self, sample_root: Path, mock_db: DatabaseManager, mock_cache: CacheManager):
        """Test DB error logged but scan continues, hash in result but no insert."""
        with patch("src.pk_py_lib.core.filesystem.traversal.DirectoryTraversal.walk_files") as mock_walk, \
             patch("src.pk_py_lib.core.image.similarity.compute_phash") as mock_phash, \
             patch("src.pk_py_lib.core.filesystem.traversal.logger") as mock_log:
            mock_walk.return_value = [sample_root / "img1.jpg"]
            mock_phash.return_value = "a1b2c3d4e5f67890"
            mock_db.get_connection.side_effect = Exception("DB error")  # Fail insert

            results = scan_directory(
                sample_root,
                compute_hashes=True,
                algorithms=["phash"],
                db_manager=mock_db,
                cache_manager=mock_cache
            )

            assert len(results) == 1
            assert results[0]['hashes'] == {'phash': 'a1b2c3d4e5f67890'}  # Hash computed
            mock_log.error.assert_called_once_with("DB storage failed for ... : DB error")
            mock_phash.assert_called_once()  # Computation not affected