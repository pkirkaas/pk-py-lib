"""
Algorithm resolution utilities for image similarity detection.

This module provides centralized algorithm resolution and validation
to eliminate duplication across hash computation functions.
"""

from __future__ import annotations

import logging
from typing import Dict, Callable, Optional, List

from pk_py_lib.core.logging.logger import get_logger

logger = get_logger(__name__)


# Algorithm registry
HASH_ALGORITHMS: Dict[str, Dict[str, any]] = {
    'phash': {
        'name': 'Perceptual Hash',
        'function': None,  # Will be set after import to avoid circular dependency
        'default_size': 8,
        'supports_color': True,
        'description': 'Perceptual hash using DCT transformation'
    },
    'whash': {
        'name': 'Wavelet Hash',
        'function': None,  # Will be set after import
        'default_size': 8,
        'supports_color': True,
        'description': 'Wavelet hash using Haar wavelet transformation'
    },
    'ahash': {
        'name': 'Average Hash',
        'function': None,  # Will be set after import
        'default_size': 8,
        'supports_color': False,
        'description': 'Average hash using mean pixel value'
    },
    'dhash': {
        'name': 'Difference Hash',
        'function': None,  # Will be set after import
        'default_size': 8,
        'supports_color': False,
        'description': 'Difference hash using gradient comparison'
    }
}


def resolve_hash_algorithm(algorithm: str) -> str:
    """
    Resolve and validate hash algorithm name.

    Args:
        algorithm: Algorithm name (case-insensitive)

    Returns:
        Normalized algorithm name

    Raises:
        ValueError: If algorithm is not supported
    """
    if not algorithm:
        raise ValueError("Algorithm name cannot be empty")

    normalized_algorithm = algorithm.lower().strip()

    if normalized_algorithm not in HASH_ALGORITHMS:
        supported = ', '.join(HASH_ALGORITHMS.keys())
        raise ValueError(f"Unsupported algorithm: {algorithm}. Supported: {supported}")

    return normalized_algorithm


def get_algorithm_info(algorithm: str) -> Dict[str, any]:
    """
    Get information about a hash algorithm.

    Args:
        algorithm: Algorithm name

    Returns:
        Dictionary with algorithm information

    Raises:
        ValueError: If algorithm is not supported
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)

    # Return a copy to prevent modification of the registry
    return HASH_ALGORITHMS[normalized_algorithm].copy()


def get_default_hash_size(algorithm: str) -> int:
    """
    Get default hash size for algorithm.

    Args:
        algorithm: Algorithm name

    Returns:
        Default hash size
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)
    return HASH_ALGORITHMS[normalized_algorithm]['default_size']


def supports_color_hashing(algorithm: str) -> bool:
    """
    Check if algorithm supports color hashing.

    Args:
        algorithm: Algorithm name

    Returns:
        True if color hashing is supported
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)
    return HASH_ALGORITHMS[normalized_algorithm]['supports_color']


def list_supported_algorithms() -> Dict[str, str]:
    """
    List all supported hash algorithms.

    Returns:
        Dictionary mapping algorithm names to descriptions
    """
    return {
        name: info['description']
        for name, info in HASH_ALGORITHMS.items()
    }


def register_algorithm(
    name: str,
    function: Callable,
    default_size: int = 8,
    supports_color: bool = False,
    description: str = ""
) -> None:
    """
    Register a new hash algorithm.

    Args:
        name: Algorithm name
        function: Hash computation function
        default_size: Default hash size
        supports_color: Whether color hashing is supported
        description: Algorithm description
    """
    if not name or not isinstance(name, str):
        raise ValueError("Algorithm name must be a non-empty string")

    if not callable(function):
        raise ValueError("Algorithm function must be callable")

    normalized_name = name.lower().strip()

    if normalized_name in HASH_ALGORITHMS:
        logger.warning(f"Overriding existing algorithm: {normalized_name}")

    HASH_ALGORITHMS[normalized_name] = {
        'name': name,
        'function': function,
        'default_size': default_size,
        'supports_color': supports_color,
        'description': description or f"Custom algorithm: {name}"
    }

    logger.info(f"Registered hash algorithm: {normalized_name}")


def get_algorithm_function(algorithm: str) -> Optional[Callable]:
    """
    Get the hash computation function for an algorithm.

    Args:
        algorithm: Algorithm name

    Returns:
        Hash computation function or None if not set
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)
    return HASH_ALGORITHMS[normalized_algorithm]['function']


def set_algorithm_function(algorithm: str, function: Callable) -> None:
    """
    Set the hash computation function for an algorithm.

    This is used to avoid circular dependencies when importing.

    Args:
        algorithm: Algorithm name
        function: Hash computation function
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)

    if not callable(function):
        raise ValueError("Algorithm function must be callable")

    HASH_ALGORITHMS[normalized_algorithm]['function'] = function
    logger.debug(f"Set function for algorithm: {normalized_algorithm}")


def validate_algorithm_parameters(
    algorithm: str,
    hash_size: Optional[int] = None,
    color_mode: Optional[bool] = None,
    **kwargs
) -> Dict[str, any]:
    """
    Validate and normalize algorithm-specific parameters.

    Args:
        algorithm: Algorithm name
        hash_size: Optional hash size to validate
        color_mode: Optional color mode to validate
        **kwargs: Additional algorithm-specific parameters

    Returns:
        Dictionary with validated parameters

    Raises:
        ValueError: If parameters are invalid
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)
    algorithm_info = HASH_ALGORITHMS[normalized_algorithm]

    validated_params = {
        'algorithm': normalized_algorithm,
        'hash_size': hash_size or algorithm_info['default_size'],
        'color_mode': bool(color_mode) if color_mode is not None else False
    }

    # Validate color mode support
    if validated_params['color_mode'] and not algorithm_info['supports_color']:
        raise ValueError(f"Algorithm {algorithm} does not support color hashing")

    # Add any additional parameters
    validated_params.update(kwargs)

    return validated_params


def get_algorithm_capabilities(algorithm: str) -> Dict[str, any]:
    """
    Get capabilities and features supported by an algorithm.

    Args:
        algorithm: Algorithm name

    Returns:
        Dictionary with algorithm capabilities
    """
    normalized_algorithm = resolve_hash_algorithm(algorithm)
    algorithm_info = HASH_ALGORITHMS[normalized_algorithm]

    return {
        'name': algorithm_info['name'],
        'supports_color': algorithm_info['supports_color'],
        'default_size': algorithm_info['default_size'],
        'has_function': algorithm_info['function'] is not None,
        'description': algorithm_info['description']
    }


def initialize_algorithm_functions() -> None:
    """
    Initialize algorithm functions from imagehash module.

    This function should be called after imports to set up the
    algorithm functions and avoid circular dependencies.
    """
    try:
        import imagehash

        # Set up algorithm functions
        set_algorithm_function('phash', imagehash.phash)
        set_algorithm_function('whash', imagehash.whash)
        set_algorithm_function('ahash', imagehash.average_hash)
        set_algorithm_function('dhash', imagehash.dhash)

        logger.debug("Initialized algorithm functions from imagehash module")

    except ImportError as e:
        logger.error(f"Failed to import imagehash module: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to initialize algorithm functions: {e}")
        raise


def get_recommended_algorithm_for_use_case(use_case: str) -> str:
    """
    Get recommended hash algorithm for a specific use case.

    Args:
        use_case: Use case description (e.g., 'similarity', 'duplicates', 'quality')

    Returns:
        Recommended algorithm name
    """
    use_case = use_case.lower().strip()

    recommendations = {
        'similarity': 'phash',
        'duplicates': 'dhash',
        'quality': 'whash',
        'general': 'phash',
        'fast': 'ahash',
        'color': 'phash'  # phash has good color support
    }

    return recommendations.get(use_case, 'phash')


def compare_algorithms(algorithm1: str, algorithm2: str) -> Dict[str, any]:
    """
    Compare two hash algorithms and return their differences.

    Args:
        algorithm1: First algorithm name
        algorithm2: Second algorithm name

    Returns:
        Dictionary with comparison results
    """
    info1 = get_algorithm_capabilities(algorithm1)
    info2 = get_algorithm_capabilities(algorithm2)

    return {
        'algorithm1': info1,
        'algorithm2': info2,
        'both_support_color': info1['supports_color'] and info2['supports_color'],
        'same_default_size': info1['default_size'] == info2['default_size'],
        'recommendation': get_recommended_algorithm_for_use_case('general')
    }
