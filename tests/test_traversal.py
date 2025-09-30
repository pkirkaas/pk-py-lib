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
    scan_directory
)
from src.pk_py_lib.core.flat_cache import FlatCacheManager


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
            files = list(walk_files(Path(tmpdir), exclude_patterns=["*.jpg"], include_hidden=True))
            assert len(files) == 2  # txt and hidden
            assert jpg_file not in files

    def test_walk_files_recursion_control(self):
        """Test walk_files with recursion control."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root_file = root / "root.txt"
            level1 = root / "level1"
            file1 = level1 / "file1.txt"
            level2 = level1 / "level2"
            file2 = level2 / "file2.txt"
            level2.mkdir(parents=True)
            
            root_file.touch()
            file1.touch()
            file2.touch()
            
            # Test with max_depth=1 (should only get root files)
            files = list(walk_files(root, max_depth=1))
            assert len(files) == 1
            assert root_file in files
            assert file1 not in files
            assert file2 not in files
            
            # Test with max_depth=2 (should get root and level1 files)
            files = list(walk_files(root, max_depth=2))
            assert len(files) == 2
            assert root_file in files
            assert file1 in files
            assert file2 not in files
            
            # Test with max_depth=3 (should get all files)
            files = list(walk_files(root, max_depth=3))
            assert len(files) == 3
            assert root_file in files
            assert file1 in files
            assert file2 in files


    def test_scan_directory_with_flat_cache(self, tmp_path: Path):
        """Test scan_directory with FlatCacheManager, verifying no cache_manager arg error and hash caching."""
        # Create test image file
        test_image = tmp_path / "test.jpg"
        from PIL import Image
        import io
        img = Image.new('RGB', (64, 64), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG')
        test_image.write_bytes(img_byte_arr.getvalue())
        
        # Create FlatCacheManager
        flat_cache = FlatCacheManager(db_path=tmp_path / "flat.db")
        
        result = scan_directory(
            roots=[tmp_path],
            compute_hashes=True,
            algorithms=['phash'],
            flat_cache_manager=flat_cache,
            search_type='similarity',
            progress_callback=lambda *args: None,
            stop_event=lambda: False
        )
        
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 1
        file_info = result['files'][0]
        assert file_info['path'] == str(test_image)
        assert 'hashes' in file_info
        assert file_info['hashes']['phash'] is not None
        
        # Verify flat cache entry was created/updated
        entry = flat_cache.get_entry(str(test_image))
        assert entry is not None
        assert entry.phash is not None

    def test_scan_directory_no_cache_args(self, tmp_path: Path):
        """Test scan_directory without cache args, verifying no errors."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        result = scan_directory(
            roots=[tmp_path],
            patterns=None,
            compute_hashes=False,
            search_type='duplicate',
            progress_callback=lambda *args: None,
            stop_event=lambda: False
        )
        
        assert result is not None
        assert 'files' in result
        assert len(result['files']) == 1
        file_info = result['files'][0]
        assert file_info['path'] == str(test_file)
        assert file_info['hashes'] == {}
        assert 'exact_hash' in file_info
        assert file_info['exact_hash'] is not None

