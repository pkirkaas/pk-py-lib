"""
tests/test_traversal.py

Tests for the file traversal functionality with multiple path support.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

from src.pk_py_lib.core.filesystem.traversal import (
    walk_files,
    validate_paths,
    scan_directory,
    DirectoryTraversal
)
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.flat_cache import FlatCacheManager
from src.pk_py_lib.core.image.similarity import compute_phash


class TestTraversal:
    """Test file traversal with multiple path support."""

    def test_walk_files_single_path(self):
        """Test walk_files with a single path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file1 = Path(tmpdir) / "test1.txt"
            test_file2 = Path(tmpdir) / "subdir" / "test2.txt"
            test_file2.parent.mkdir(exist_ok=True)
            
            test_file1.touch()
            test_file2.touch()
            
            # Test with single path
            files = list(walk_files(Path(tmpdir)))
            assert len(files) == 2
            assert test_file1 in files
            assert test_file2 in files

    def test_walk_files_multiple_paths(self):
        """Test walk_files with multiple paths."""
        with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
            # Create test files in first directory
            test_file1 = Path(tmpdir1) / "test1.txt"
            test_file1.touch()
            
            # Create test files in second directory
            test_file2 = Path(tmpdir2) / "test2.txt"
            test_file2.touch()
            
            # Test with multiple paths
            files = list(walk_files([Path(tmpdir1), Path(tmpdir2)]))
            assert len(files) == 2
            assert test_file1 in files
            assert test_file2 in files

    def test_walk_files_mixed_paths(self):
        """Test walk_files with mixed directory and file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test directory and files
            test_dir = Path(tmpdir) / "subdir"
            test_dir.mkdir()
            
            test_file1 = test_dir / "test1.txt"
            test_file2 = Path(tmpdir) / "test2.txt"
            
            test_file1.touch()
            test_file2.touch()
            
            # Test with mixed paths (directory and file)
            files = list(walk_files([test_dir, test_file2]))
            assert len(files) == 2
            assert test_file1 in files
            assert test_file2 in files

    def test_walk_files_backward_compatibility(self):
        """Test that walk_files maintains backward compatibility with single path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            
            # Test with single Path object (old behavior)
            files_single = list(walk_files(Path(tmpdir)))
            
            # Test with list containing one path (new behavior)
            files_list = list(walk_files([Path(tmpdir)]))
            
            assert files_single == files_list
            assert len(files_single) == 1
            assert test_file in files_single

    def test_validate_paths_existing(self):
        """Test validate_paths with existing paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            
            # Test with existing directory and file
            errors = validate_paths([Path(tmpdir), test_file])
            assert len(errors) == 0

    def test_validate_paths_nonexistent(self):
        """Test validate_paths with non-existent paths."""
        errors = validate_paths([Path("/nonexistent/path"), Path("/another/nonexistent")])
        assert len(errors) == 2
        assert all("does not exist" in error for error in errors)

    def test_validate_paths_mixed(self):
        """Test validate_paths with mixed existing and non-existent paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.touch()
            
            errors = validate_paths([Path(tmpdir), test_file, Path("/nonexistent/path")])
            assert len(errors) == 1
            assert "does not exist" in errors[0]

    def test_walk_files_with_filters(self):
        """Test walk_files with include/exclude filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            txt_file = Path(tmpdir) / "test.txt"
            jpg_file = Path(tmpdir) / "image.jpg"
            hidden_file = Path(tmpdir) / ".hidden"
            
            txt_file.touch()
            jpg_file.touch()
            hidden_file.touch()
            
            # Test with include filter
            files = list(walk_files(Path(tmpdir), patterns=["*.txt"]))
            assert len(files) == 1
            assert txt_file in files
            assert jpg_file not in files
            
            # Test with exclude filter
            files = list(walk_files(Path(tmpdir), exclude_patterns=["*.jpg"]))
            assert len(files) == 2  # txt and hidden
            assert jpg_file not in files

    def test_walk_files_recursion_control(self):
        """Test walk_files with recursion control."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            level1 = Path(tmpdir) / "level1"
            level2 = level1 / "level2"
            level2.mkdir(parents=True)
            
            file1 = level1 / "file1.txt"
            file2 = level2 / "file2.txt"
            
            file1.touch()
            file2.touch()
            
            # Test with max_depth=1 (should only get level1 files)
            files = list(walk_files(Path(tmpdir), max_depth=1))
            assert len(files) == 1
            assert file1 in files
            assert file2 not in files
            
            # Test with max_depth=2 (should get both files)
            files = list(walk_files(Path(tmpdir), max_depth=2))
            assert len(files) == 2
            assert file1 in files
            assert file2 in files

    @patch('src.pk_py_lib.core.filesystem.traversal.Path')
    def test_walk_files_permission_error(self, mock_path):
        """Test walk_files handles permission errors gracefully."""
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.is_dir.return_value = True
        mock_path_instance.iterdir.side_effect = PermissionError("Access denied")
        mock_path.return_value = mock_path_instance
        
        # Should not raise exception, just skip inaccessible directory
        files = list(walk_files(mock_path_instance))
        assert len(files) == 0

    def test_scan_directory_with_flat_cache(self, tmp_path: Path):
        """Test scan_directory with FlatCacheManager, verifying no cache_manager arg error and hash caching."""
        # Create test image file
        test_image = tmp_path / "test.jpg"
        test_image.touch()
        
        # Mock DatabaseManager
        mock_db = MagicMock(spec=DatabaseManager)
        mock_db.cache_db = str(tmp_path / "cache.db")
        mock_db.get_connection.return_value.__enter__.return_value = MagicMock()
        
        # Create FlatCacheManager
        flat_cache = FlatCacheManager(db_path=tmp_path / "flat.db")
        
        # Mock compute_phash to avoid real computation
        with patch('src.pk_py_lib.core.image.similarity.compute_phash', return_value='mock_phash'):
            result = scan_directory(
                roots=[tmp_path],
                compute_hashes=True,
                algorithms=['phash'],
                db_manager=mock_db,
                flat_cache_manager=flat_cache,
                progress_callback=lambda *args: None,
                stop_event=lambda: False
            )
        
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 1
        file_info = result['files'][0]
        assert file_info['path'] == str(test_image)
        assert 'hashes' in file_info
        assert file_info['hashes']['phash'] == 'mock_phash'
        
        # Verify flat cache entry was created/updated
        entry = flat_cache.get_entry(str(test_image))
        assert entry is not None
        assert entry.phash == 'mock_phash'

    def test_scan_directory_no_cache_args(self, tmp_path: Path):
        """Test scan_directory without cache args, verifying no errors."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.touch()
        
        # Mock DatabaseManager
        mock_db = MagicMock(spec=DatabaseManager)
        mock_db.cache_db = str(tmp_path / "cache.db")
        mock_db.get_connection.return_value.__enter__.return_value = MagicMock()
        
        result = scan_directory(
            roots=[tmp_path],
            compute_hashes=False,
            db_manager=mock_db,
            progress_callback=lambda *args: None,
            stop_event=lambda: False
        )
        
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])