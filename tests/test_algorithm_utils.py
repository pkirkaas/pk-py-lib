"""
Tests for algorithm resolution utilities.

This module tests the algorithm_utils.py module to ensure
proper algorithm registry, validation, and resolution functionality.
"""

import pytest
from unittest.mock import Mock, patch

from pk_py_lib.core.image.similarity.algorithm_utils import (
    resolve_hash_algorithm,
    get_algorithm_info,
    get_default_hash_size,
    supports_color_hashing,
    list_supported_algorithms,
    register_algorithm,
    get_algorithm_function,
    set_algorithm_function,
    validate_algorithm_parameters,
    get_algorithm_capabilities,
    initialize_algorithm_functions,
    get_recommended_algorithm_for_use_case,
    compare_algorithms,
    HASH_ALGORITHMS
)


class TestAlgorithmUtils:
    """Test algorithm resolution utilities."""

    def test_resolve_hash_algorithm_valid(self):
        """Test resolving valid algorithm names."""
        assert resolve_hash_algorithm('phash') == 'phash'
        assert resolve_hash_algorithm('PHASH') == 'phash'
        assert resolve_hash_algorithm('  phash  ') == 'phash'
        assert resolve_hash_algorithm('whash') == 'whash'
        assert resolve_hash_algorithm('ahash') == 'ahash'
        assert resolve_hash_algorithm('dhash') == 'dhash'

    def test_resolve_hash_algorithm_invalid(self):
        """Test resolving invalid algorithm names."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            resolve_hash_algorithm('invalid')

        with pytest.raises(ValueError, match="Algorithm name cannot be empty"):
            resolve_hash_algorithm('')

    def test_get_algorithm_info_valid(self):
        """Test getting algorithm info for valid algorithms."""
        info = get_algorithm_info('phash')

        assert 'name' in info
        assert 'default_size' in info
        assert 'supports_color' in info
        assert 'description' in info
        assert info['name'] == 'Perceptual Hash'
        assert info['default_size'] == 8
        assert info['supports_color'] is True

    def test_get_algorithm_info_invalid(self):
        """Test getting algorithm info for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            get_algorithm_info('invalid')

    def test_get_default_hash_size_valid(self):
        """Test getting default hash size for valid algorithms."""
        assert get_default_hash_size('phash') == 8
        assert get_default_hash_size('whash') == 8
        assert get_default_hash_size('ahash') == 8
        assert get_default_hash_size('dhash') == 8

    def test_get_default_hash_size_invalid(self):
        """Test getting default hash size for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            get_default_hash_size('invalid')

    def test_supports_color_hashing_valid(self):
        """Test checking color support for valid algorithms."""
        assert supports_color_hashing('phash') is True
        assert supports_color_hashing('whash') is True
        assert supports_color_hashing('ahash') is False
        assert supports_color_hashing('dhash') is False

    def test_supports_color_hashing_invalid(self):
        """Test checking color support for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            supports_color_hashing('invalid')

    def test_list_supported_algorithms(self):
        """Test listing all supported algorithms."""
        algorithms = list_supported_algorithms()

        assert isinstance(algorithms, dict)
        assert 'phash' in algorithms
        assert 'whash' in algorithms
        assert 'ahash' in algorithms
        assert 'dhash' in algorithms
        assert 'Perceptual hash' in algorithms['phash']
        assert 'Wavelet hash' in algorithms['whash']

    def test_register_algorithm_new(self):
        """Test registering a new algorithm."""
        def dummy_hash_func(img, hash_size):
            return "dummy_hash"

        register_algorithm(
            name='dummy',
            function=dummy_hash_func,
            default_size=16,
            supports_color=True,
            description='Dummy algorithm for testing'
        )

        # Verify registration
        assert 'dummy' in HASH_ALGORITHMS
        assert HASH_ALGORITHMS['dummy']['name'] == 'dummy'
        assert HASH_ALGORITHMS['dummy']['function'] == dummy_hash_func
        assert HASH_ALGORITHMS['dummy']['default_size'] == 16
        assert HASH_ALGORITHMS['dummy']['supports_color'] is True
        assert HASH_ALGORITHMS['dummy']['description'] == 'Dummy algorithm for testing'

    def test_register_algorithm_override(self):
        """Test overriding an existing algorithm."""
        def new_hash_func(img, hash_size):
            return "new_hash"

        # Register original
        register_algorithm('test_override', lambda x: "original")

        # Override with warning
        register_algorithm(
            name='test_override',
            function=new_hash_func,
            description='Overridden algorithm'
        )

        # Verify override
        assert HASH_ALGORITHMS['test_override']['function'] == new_hash_func
        assert HASH_ALGORITHMS['test_override']['description'] == 'Overridden algorithm'

    def test_register_algorithm_invalid_name(self):
        """Test registering algorithm with invalid name."""
        with pytest.raises(ValueError, match="Algorithm name must be a non-empty string"):
            register_algorithm('', lambda x: "dummy")

        with pytest.raises(ValueError, match="Algorithm name must be a non-empty string"):
            register_algorithm(None, lambda x: "dummy")

    def test_register_algorithm_invalid_function(self):
        """Test registering algorithm with invalid function."""
        with pytest.raises(ValueError, match="Algorithm function must be callable"):
            register_algorithm('invalid_func', "not_callable")

    def test_get_algorithm_function_valid(self):
        """Test getting algorithm function for valid algorithms."""
        # Functions are initialized when module is imported
        func = get_algorithm_function('phash')
        assert func is not None
        assert callable(func)

        # Set function and test
        def dummy_func(img, hash_size):
            return "dummy"

        set_algorithm_function('phash', dummy_func)
        assert get_algorithm_function('phash') == dummy_func

    def test_get_algorithm_function_invalid(self):
        """Test getting algorithm function for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            get_algorithm_function('invalid')

    def test_set_algorithm_function_valid(self):
        """Test setting algorithm function for valid algorithms."""
        def dummy_func(img, hash_size):
            return "dummy"

        set_algorithm_function('whash', dummy_func)
        assert HASH_ALGORITHMS['whash']['function'] == dummy_func

    def test_set_algorithm_function_invalid(self):
        """Test setting algorithm function for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            set_algorithm_function('invalid', lambda x: "dummy")

        with pytest.raises(ValueError, match="Algorithm function must be callable"):
            set_algorithm_function('phash', "not_callable")

    def test_validate_algorithm_parameters_valid(self):
        """Test validating algorithm parameters with valid inputs."""
        result = validate_algorithm_parameters(
            algorithm='phash',
            hash_size=16,
            color_mode=False
        )

        assert result['algorithm'] == 'phash'
        assert result['hash_size'] == 16
        assert result['color_mode'] is False

    def test_validate_algorithm_parameters_with_defaults(self):
        """Test validating algorithm parameters with defaults."""
        result = validate_algorithm_parameters(
            algorithm='phash'
        )

        assert result['algorithm'] == 'phash'
        assert result['hash_size'] == 8  # Default size
        assert result['color_mode'] is False  # Default

    def test_validate_algorithm_parameters_invalid_algorithm(self):
        """Test validating algorithm parameters with invalid algorithm."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            validate_algorithm_parameters(algorithm='invalid')

    def test_validate_algorithm_parameters_color_not_supported(self):
        """Test validating algorithm parameters with unsupported color mode."""
        with pytest.raises(ValueError, match="does not support color hashing"):
            validate_algorithm_parameters(
                algorithm='ahash',
                color_mode=True
            )

    def test_get_algorithm_capabilities_valid(self):
        """Test getting algorithm capabilities for valid algorithms."""
        capabilities = get_algorithm_capabilities('phash')

        assert 'name' in capabilities
        assert 'supports_color' in capabilities
        assert 'default_size' in capabilities
        assert 'has_function' in capabilities
        assert 'description' in capabilities
        assert capabilities['name'] == 'Perceptual Hash'
        assert capabilities['supports_color'] is True

    def test_get_algorithm_capabilities_invalid(self):
        """Test getting algorithm capabilities for invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            get_algorithm_capabilities('invalid')

    def test_initialize_algorithm_functions(self):
        """Test initializing algorithm functions from imagehash."""
        # This test verifies that functions are properly initialized
        # Since initialize_algorithm_functions is called on module import,
        # we just verify the functions are set
        func = get_algorithm_function('phash')
        assert func is not None
        assert callable(func)

        func = get_algorithm_function('whash')
        assert func is not None
        assert callable(func)

        func = get_algorithm_function('ahash')
        assert func is not None
        assert callable(func)

        func = get_algorithm_function('dhash')
        assert func is not None
        assert callable(func)

    def test_get_recommended_algorithm_for_use_case_valid(self):
        """Test getting recommended algorithm for valid use cases."""
        assert get_recommended_algorithm_for_use_case('similarity') == 'phash'
        assert get_recommended_algorithm_for_use_case('duplicates') == 'dhash'
        assert get_recommended_algorithm_for_use_case('quality') == 'whash'
        assert get_recommended_algorithm_for_use_case('general') == 'phash'
        assert get_recommended_algorithm_for_use_case('fast') == 'ahash'
        assert get_recommended_algorithm_for_use_case('color') == 'phash'
        assert get_recommended_algorithm_for_use_case('unknown') == 'phash'  # Default

    def test_compare_algorithms_valid(self):
        """Test comparing two valid algorithms."""
        comparison = compare_algorithms('phash', 'whash')

        assert 'algorithm1' in comparison
        assert 'algorithm2' in comparison
        assert 'both_support_color' in comparison
        assert 'same_default_size' in comparison
        assert 'recommendation' in comparison

        assert comparison['algorithm1']['name'] == 'Perceptual Hash'
        assert comparison['algorithm2']['name'] == 'Wavelet Hash'
        assert comparison['both_support_color'] is True
        assert comparison['same_default_size'] is True

    def test_compare_algorithms_invalid(self):
        """Test comparing with invalid algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            compare_algorithms('invalid', 'phash')

        with pytest.raises(ValueError, match="Unsupported algorithm"):
            compare_algorithms('phash', 'invalid')

    def test_compare_algorithms_different_capabilities(self):
        """Test comparing algorithms with different capabilities."""
        comparison = compare_algorithms('phash', 'ahash')

        assert comparison['algorithm1']['supports_color'] is True
        assert comparison['algorithm2']['supports_color'] is False
        assert comparison['both_support_color'] is False

    def test_algorithm_registry_immutability(self):
        """Test that get_algorithm_info returns a copy, not reference."""
        info1 = get_algorithm_info('phash')
        info2 = get_algorithm_info('phash')

        # Modify one
        info1['default_size'] = 999

        # Verify other is unchanged
        assert info2['default_size'] == 8
        assert get_algorithm_info('phash')['default_size'] == 8
