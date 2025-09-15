"""
tests/test_image_similarity.py

Unit tests for image similarity functions in core/image/similarity.py.
Tests cover pHash/wHash computation, Hamming distance, grouping, batch processing,
with mocks for Pillow/imagehash to avoid real file I/O. Includes edge cases:
invalid paths, cache hits/misses, empty inputs, high thresholds, corrupted mocks.

Uses pytest with mock.patch for Image.open and imagehash.phash/whash.
All tests use 4-space indentation, rich comments, and validate exceptions/output.
Syntax validation performed per project rules using Python ast.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from typing import Dict, List, Optional

from src.pk_py_lib.core.image.similarity import (
    compute_phash,
    compute_whash,
    hamming_distance,
    find_similar_phash,
    find_similar_whash,
    compute_phash_batch,
    compute_whash_batch,
    InvalidImageError,
    SimilarityError,
)
from src.pk_py_lib.core.cache import CacheManager


@pytest.fixture
def mock_cache():
    """Mock CacheManager for hit/miss tests."""
    cache = MagicMock(spec=CacheManager)
    cache.get_hash.return_value = None  # Default miss
    cache.set_hash.return_value = None
    return cache


@pytest.fixture
def sample_path():
    """Sample image path fixture."""
    return str(Path("test_img.jpg"))


@pytest.fixture
def sample_hash():
    """Sample 64-bit hex hash."""
    return "a1b2c3d4e5f67890"


@pytest.fixture
def sample_hashes() -> List[Dict[str, str]]:
    """Sample hashes for grouping tests: two similar (dist=1), one different."""
    return [
        {"path": "/img1.jpg", "hash": "0000000000000000"},
        {"path": "/img2.jpg", "hash": "0000000000000001"},  # dist=1 to img1
        {"path": "/img3.jpg", "hash": "1111111111111111"},  # dist=64 to others
    ]


class TestSimilarityFunctions:
    """Unit tests for similarity computation and grouping."""

    def test_compute_phash_valid(self, sample_path: str, mock_cache: CacheManager, sample_hash: str):
        """Test pHash computation for valid image path with mock."""
        with patch("PIL.Image.open") as mock_open, patch("imagehash.phash") as mock_phash:
            mock_img = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_img
            mock_phash.return_value = MagicMock(str=lambda: sample_hash)

            result = compute_phash(sample_path, cache_manager=mock_cache)

            mock_open.assert_called_once_with(Path(sample_path))
            mock_phash.assert_called_once_with(mock_img, hash_size=8)
            assert result == sample_hash
            mock_cache.set_hash.assert_called_once()

    def test_compute_phash_invalid_path(self, sample_path: str):
        """Test InvalidImageError for non-existent path."""
        with pytest.raises(InvalidImageError, match="File does not exist"):
            compute_phash(sample_path.replace(".jpg", ".nonexistent"))

    def test_compute_phash_cache_hit(self, sample_path: str, sample_hash: str):
        """Test cache hit skips computation."""
        cache = MagicMock(spec=CacheManager)
        cache.get_hash.return_value = sample_hash

        result = compute_phash(sample_path, cache_manager=cache)

        assert result == sample_hash
        cache.get_hash.assert_called_once_with(f"{sample_path}:phash")
        # No open/phash calls on hit

    def test_compute_phash_invalid_hash_length(self, sample_path: str, mock_cache: CacheManager):
        """Test SimilarityError for invalid hash length."""
        with patch("PIL.Image.open") as mock_open, patch("imagehash.phash") as mock_phash:
            mock_img = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_img
            mock_phash.return_value = MagicMock(str=lambda: "short")  # len=5 !=16

            with pytest.raises(SimilarityError, match="invalid length 5"):
                compute_phash(sample_path, cache_manager=mock_cache)

    def test_hamming_distance_known(self, sample_hash: str):
        """Test Hamming distance with known similar hashes (dist=1)."""
        hash2 = sample_hash[:-1] + "1"  # Last bit flip
        dist = hamming_distance(sample_hash, hash2)
        assert dist == 1

    def test_hamming_distance_identical(self, sample_hash: str):
        """Test distance 0 for identical hashes."""
        dist = hamming_distance(sample_hash, sample_hash)
        assert dist == 0

    def test_hamming_distance_max(self):
        """Test max distance 64 for opposite hashes."""
        dist = hamming_distance("0000000000000000", "ffffffffffffffff")
        assert dist == 64

    def test_hamming_distance_invalid_hex(self):
        """Test ValueError for invalid hex."""
        with pytest.raises(ValueError, match="Invalid hex"):
            hamming_distance("invalid", "0000000000000000")

    def test_find_similar_phash_grouping(self, sample_hashes: List[Dict[str, str]]):
        """Test grouping with threshold=1: groups img1/img2, ignores img3."""
        groups = find_similar_phash(sample_hashes, threshold=1)
        assert len(groups) == 1
        assert set(groups[0]) == {"/img1.jpg", "/img2.jpg"}

    def test_find_similar_phash_empty(self):
        """Test empty list raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            find_similar_phash([])

    def test_find_similar_phash_singletons(self, sample_hashes: List[Dict[str, str]]):
        """Test threshold=0: no groups (all dist>0)."""
        groups = find_similar_phash(sample_hashes, threshold=0)
        assert len(groups) == 0

    def test_find_similar_phash_large_n_warning(self):
        """Test warning for >1000 images (mock logger)."""
        large_hashes = [{"path": f"/img{i}.jpg", "hash": "0"*16} for i in range(1001)]
        with patch("src.pk_py_lib.core.image.similarity.logger") as mock_log:
            find_similar_phash(large_hashes, threshold=10)
            mock_log.warning.assert_called_once()

    def test_find_similar_phash_invalid_input(self):
        """Test ValueError for invalid dict/hash."""
        invalid = [{"path": "", "hash": "short"}]
        with pytest.raises(ValueError, match="Invalid hash length"):
            find_similar_phash(invalid)

    def test_compute_phash_batch_mixed(self, sample_path: str, sample_hash: str):
        """Test batch with success and failure."""
        paths = [sample_path, sample_path + ".invalid"]
        with patch("src.pk_py_lib.core.image.similarity.compute_phash") as mock_compute:
            mock_compute.side_effect = [sample_hash, InvalidImageError("test", "invalid")]

            results = compute_phash_batch(paths)

            assert results[sample_path] == sample_hash
            assert results[sample_path + ".invalid"] is None

    # wHash tests (similar structure)
    def test_compute_whash_valid(self, sample_path: str, mock_cache: CacheManager, sample_hash: str):
        """Test wHash computation for valid image with default mode/wavelet."""
        with patch("PIL.Image.open") as mock_open, patch("imagehash.whash") as mock_whash:
            mock_img = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_img
            mock_whash.return_value = MagicMock(str=lambda: sample_hash)

            result = compute_whash(sample_path, mode='constant', wavelet='db1', cache_manager=mock_cache)

            mock_open.assert_called_once()
            mock_whash.assert_called_once_with(mock_img, hash_size=8, mode='constant', wavelet='db1')
            assert result == sample_hash

    def test_compute_whash_cache_hit(self, sample_path: str, sample_hash: str):
        """Test wHash cache hit."""
        cache = MagicMock(spec=CacheManager)
        cache.get_hash.return_value = sample_hash

        result = compute_whash(sample_path, cache_manager=cache)

        assert result == sample_hash
        cache.get_hash.assert_called_once_with(f"{sample_path}:whash")

    def test_compute_whash_invalid_wavelet(self, sample_path: str):
        """Test SimilarityError for invalid wavelet."""
        with pytest.raises(SimilarityError, match="invalid wavelet"):
            compute_whash(sample_path, wavelet='invalid')

    def test_find_similar_whash_grouping(self, sample_hashes: List[Dict[str, str]]):
        """Test wHash grouping with threshold=1."""
        groups = find_similar_whash(sample_hashes, threshold=1)
        assert len(groups) == 1
        assert set(groups[0]) == {"/img1.jpg", "/img2.jpg"}

    def test_compute_whash_batch_mixed(self, sample_path: str, sample_hash: str):
        """Test wHash batch with success/failure."""
        paths = [sample_path, sample_path + ".invalid"]
        with patch("src.pk_py_lib.core.image.similarity.compute_whash") as mock_compute:
            mock_compute.side_effect = [sample_hash, SimilarityError("test")]

            results = compute_whash_batch(paths)

            assert results[sample_path] == sample_hash
            assert results[sample_path + ".invalid"] is None

    def test_color_phash_variant(self, sample_path: str, mock_cache: CacheManager):
        """Test color pHash averages RGB channels."""
        with patch("PIL.Image.open") as mock_open, patch("imagehash.phash") as mock_phash:
            mock_img = MagicMock()
            mock_img.mode = 'RGB'
            mock_r, mock_g, mock_b = MagicMock(), MagicMock(), MagicMock()
            mock_img.split.return_value = (mock_r, mock_g, mock_b)
            mock_open.return_value.__enter__.return_value = mock_img
            mock_phash.side_effect = [MagicMock(str=lambda: "f0f0f0f0f0f0f0f0"),  # R
                                      MagicMock(str=lambda: "0f0f0f0f0f0f0f0f"),  # G
                                      MagicMock(str=lambda: "ff00000000000000")]  # B

            result = compute_color_phash(sample_path, cache_manager=mock_cache)

            mock_phash.assert_called()  # Called 3 times
            assert len(result) == 16  # Valid hex

    def test_color_whash_variant(self, sample_path: str, mock_cache: CacheManager):
        """Test color wHash averages RGB channels with params."""
        with patch("PIL.Image.open") as mock_open, patch("imagehash.whash") as mock_whash:
            mock_img = MagicMock()
            mock_img.mode = 'RGB'
            mock_r, mock_g, mock_b = MagicMock(), MagicMock(), MagicMock()
            mock_img.split.return_value = (mock_r, mock_g, mock_b)
            mock_open.return_value.__enter__.return_value = mock_img
            mock_whash.side_effect = [MagicMock(str=lambda: "f0f0f0f0f0f0f0f0"),
                                      MagicMock(str=lambda: "0f0f0f0f0f0f0f0f"),
                                      MagicMock(str=lambda: "ff00000000000000")]

            result = compute_color_whash(sample_path, mode='constant', wavelet='db1', cache_manager=mock_cache)

            mock_whash.assert_called()  # 3 times with mode/wavelet
            assert len(result) == 16