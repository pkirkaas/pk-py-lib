"""
Tests for hash computation utilities.

This module tests the hash_utils.py module to ensure
proper functionality and error handling.
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from PIL import Image

from pk_py_lib.core.image.similarity.hash_utils import (
    load_image_with_fallback,
    validate_hash_parameters,
    normalize_hash_length,
    compute_color_channels,
    combine_color_hashes,
    compute_generic_color_hash,
    check_cache_for_hash,
    handle_image_loading_errors,
    get_effective_hash_size
)
from pk_py_lib.core.image.similarity.types import InvalidImageError, SimilarityError


class TestHashUtils:
    """Test hash computation utilities."""

    def test_load_image_with_fallback_valid_image(self, tmp_path):
        """Test loading valid image file."""
        # Create a simple test image
        test_image_path = tmp_path / "test_image.jpg"
        test_image = Image.new('RGB', (100, 100), color='red')
        test_image.save(test_image_path)

        # Test loading
        result = load_image_with_fallback(str(test_image_path))

        assert isinstance(result, np.ndarray)
        assert len(result.shape) == 3  # Should be 3D array
        assert result.shape[2] == 3   # Should have 3 channels (BGR)

    def test_load_image_with_fallback_invalid_file(self):
        """Test loading non-existent file raises error."""
        with pytest.raises(InvalidImageError):
            load_image_with_fallback("/non/existent/path.jpg")

    @patch('pk_py_lib.core.image.similarity.hash_utils.Image.open')
    def test_load_image_with_fallback_pil_failure_opencv_success(self, mock_pil_open, tmp_path):
        """Test PIL failure with OpenCV fallback success."""
        test_image_path = tmp_path / "test_image.jpg"
        test_image = Image.new('RGB', (100, 100), color='red')
        test_image.save(test_image_path)

        # Mock PIL to fail
        mock_pil_open.side_effect = Exception("PIL failed")

        # Test loading should still work with OpenCV fallback
        result = load_image_with_fallback(str(test_image_path))
        assert isinstance(result, np.ndarray)

    @patch('pk_py_lib.core.image.similarity.hash_utils.Image.open')
    @patch('pk_py_lib.core.image.similarity.hash_utils.cv2.imread')
    def test_load_image_with_fallback_both_fail(self, mock_cv2_imread, mock_pil_open, tmp_path):
        """Test both PIL and OpenCV failing."""
        test_image_path = tmp_path / "test_image.jpg"
        test_image = Image.new('RGB', (100, 100), color='red')
        test_image.save(test_image_path)

        # Mock both to fail
        mock_pil_open.side_effect = Exception("PIL failed")
        mock_cv2_imread.return_value = None

        with pytest.raises(SimilarityError):
            load_image_with_fallback(str(test_image_path))

    def test_validate_hash_parameters_valid(self):
        """Test parameter validation with valid inputs."""
        result = validate_hash_parameters(8, 'phash', False)
        assert result == (8, 'phash', False)

        result = validate_hash_parameters(16, 'WHASH', True)
        assert result == (16, 'whash', True)

    def test_validate_hash_parameters_invalid_algorithm(self):
        """Test parameter validation with invalid algorithm."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            validate_hash_parameters(8, 'invalid_algo')

    def test_validate_hash_parameters_invalid_size(self):
        """Test parameter validation with invalid hash size."""
        with pytest.raises(SimilarityError):  # validate_hash_size will raise SimilarityError
            validate_hash_parameters(2, 'phash')  # Too small

    def test_normalize_hash_length_valid(self):
        """Test hash length normalization with valid inputs."""
        result = normalize_hash_length("a1b2c3d4e5f67890")
        assert result == "a1b2c3d4e5f67890"

        result = normalize_hash_length("a1b2c3d4")
        assert result == "00000000a1b2c3d4"

    def test_normalize_hash_length_too_short(self):
        """Test hash length normalization with too short hash."""
        with pytest.raises(SimilarityError, match="too short"):
            normalize_hash_length("abcd")

    def test_normalize_hash_length_too_long(self):
        """Test hash length normalization with too long hash."""
        with pytest.raises(SimilarityError, match="too long"):
            normalize_hash_length("a" * 40)

    def test_compute_color_channels_valid(self):
        """Test color channel extraction with valid image."""
        # Create a simple BGR image
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:, :, 0] = 255  # Blue channel
        image[:, :, 1] = 128  # Green channel
        image[:, :, 2] = 64   # Red channel

        blue, green, red = compute_color_channels(image)

        assert blue.shape == (100, 100)
        assert green.shape == (100, 100)
        assert red.shape == (100, 100)
        assert np.all(blue == 255)
        assert np.all(green == 128)
        assert np.all(red == 64)

    def test_compute_color_channels_invalid_format(self):
        """Test color channel extraction with invalid image format."""
        # Test with grayscale image
        gray_image = np.zeros((100, 100), dtype=np.uint8)
        with pytest.raises(ValueError, match="3-channel BGR format"):
            compute_color_channels(gray_image)

        # Test with wrong number of channels
        wrong_channels = np.zeros((100, 100, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="3-channel BGR format"):
            compute_color_channels(wrong_channels)

    def test_combine_color_hashes_valid(self):
        """Test combining color hashes with valid inputs."""
        result = combine_color_hashes("a1b2c3d4e5f67890", "b2c3d4e5f6789012", "c3d4e5f678901234")

        assert isinstance(result, str)
        assert len(result) == 16
        assert all(c in '0123456789abcdef' for c in result.lower())

    def test_combine_color_hashes_invalid_hex(self):
        """Test combining color hashes with invalid hex strings."""
        with pytest.raises(ValueError):
            combine_color_hashes("invalid", "b2c3d4e5f6789012", "c3d4e5f678901234")

    def test_compute_generic_color_hash_valid(self, tmp_path):
        """Test generic color hash computation with valid inputs."""
        # Create a simple test image
        test_image_path = tmp_path / "test_image.jpg"
        test_image = Image.new('RGB', (100, 100), color='red')
        test_image.save(test_image_path)

        # Load image as numpy array
        image = load_image_with_fallback(str(test_image_path))

        # Mock hash function
        mock_hash_func = Mock()
        mock_hash_func.return_value = Mock()
        mock_hash_func.return_value.__str__ = Mock(return_value="a1b2c3d4e5f67890")

        result = compute_generic_color_hash(image, 8, mock_hash_func)

        assert isinstance(result, str)
        assert len(result) == 16
        assert mock_hash_func.call_count == 3  # Should be called for each channel

    def test_check_cache_for_hash_with_manager(self):
        """Test cache checking with cache manager."""
        mock_manager = Mock()
        mock_manager.get_hashes.return_value = {
            '/test/path.jpg': {'phash': 'a1b2c3d4e5f67890'}
        }

        result = check_cache_for_hash('/test/path.jpg', 'phash', mock_manager)
        assert result == 'a1b2c3d4e5f67890'

    def test_check_cache_for_hash_without_manager(self):
        """Test cache checking without cache manager."""
        result = check_cache_for_hash('/test/path.jpg', 'phash', None)
        assert result is None

    def test_check_cache_for_hash_miss(self):
        """Test cache checking with cache miss."""
        mock_manager = Mock()
        mock_manager.get_hashes.return_value = {
            '/test/path.jpg': {'phash': None}
        }

        result = check_cache_for_hash('/test/path.jpg', 'phash', mock_manager)
        assert result is None

    def test_handle_image_loading_errors_unsupported_format(self):
        """Test handling unsupported image format errors."""
        error = Exception("cannot identify image file")

        with pytest.raises(InvalidImageError):
            handle_image_loading_errors('/test/path.jpg', error)

    def test_handle_image_loading_errors_io_error(self):
        """Test handling IO errors."""
        error = OSError("Permission denied")  # IOError is OSError in Python 3

        with pytest.raises(OSError):
            handle_image_loading_errors('/test/path.jpg', error)

    def test_handle_image_loading_errors_general_error(self):
        """Test handling general errors."""
        error = Exception("Some other error")

        with pytest.raises(SimilarityError):
            handle_image_loading_errors('/test/path.jpg', error)

    def test_get_effective_hash_size_no_settings(self):
        """Test getting effective hash size without settings."""
        result = get_effective_hash_size(8, 'phash', None)
        assert result == 8

    def test_get_effective_hash_size_with_settings(self):
        """Test getting effective hash size with settings override."""
        settings = {
            'criteria': {
                'phash': {'hash_size': 16}
            }
        }

        result = get_effective_hash_size(8, 'phash', settings)
        assert result == 16

    def test_get_effective_hash_size_no_override(self):
        """Test getting effective hash size when no override in settings."""
        settings = {
            'criteria': {
                'whash': {'hash_size': 16}
            }
        }

        result = get_effective_hash_size(8, 'phash', settings)
        assert result == 8

    def test_get_effective_hash_size_empty_settings(self):
        """Test getting effective hash size with empty settings."""
        settings = {}

        result = get_effective_hash_size(8, 'phash', settings)
        assert result == 8
