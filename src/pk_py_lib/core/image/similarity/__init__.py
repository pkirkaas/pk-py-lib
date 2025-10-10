"""
src/pk_py_lib/core/image/similarity/__init__.py

Public API for the image similarity detection module.
Re-exports all public functions, classes, and constants for backward compatibility.
"""

# API Response infrastructure
from ...api.response import (
    ApiResponse,
    ErrorCode,
    ErrorDetail,
    success,
    error,
    from_exception,
    partial_success
)

# Types and Exceptions
from .types import (
    ExactDuplicateSet,
    InvalidImageError,
    SimilarityError,
    VALID_IMAGE_EXTENSIONS,
)

# Validation utilities
from .validation import (
    hamming_distance,
    is_image_extension,
    validate_and_normalize_hash,
    validate_hash_size,
    validate_image_path,
    validate_threshold,
)

# Metadata extraction
from .metadata import (
    compute_group_stats,
    format_timestamp,
    get_image_metadata,
    get_image_quality_score,
    get_resolution,
)

# Hash computation
from .hashing import (
    compute_color_hash,
    compute_color_phash,
    compute_color_whash,
    compute_phash,
    compute_phash_batch,
    compute_similarity_hash_batch,
    compute_whash,
    compute_whash_batch,
    get_similarity_hash,
)

# Hash utilities
from .hash_utils import (
    load_image_with_fallback,
    validate_hash_parameters,
    normalize_hash_length,
    compute_color_channels,
    combine_color_hashes,
    compute_generic_color_hash,
    check_cache_for_hash,
    handle_image_loading_errors,
    get_effective_hash_size,
)

# Algorithm utilities
from .algorithm_utils import (
    resolve_hash_algorithm,
    get_algorithm_info,
    get_default_hash_size,
    supports_color_hashing,
    list_supported_algorithms,
    initialize_algorithm_functions,
    validate_algorithm_parameters,
    get_algorithm_function,
    set_algorithm_function,
    get_algorithm_capabilities,
    get_recommended_algorithm_for_use_case,
    compare_algorithms,
    register_algorithm,
)

# Processing phases
from .phases import (
    PhaseContext,
    phase_algorithm_resolution,
    phase_exact_duplicate_detection,
    phase_perceptual_hash_computation,
    phase_similarity_clustering,
    execute_all_phases,
)

# Clustering and similarity detection
from .clustering import (
    detect_exact_duplicates,
    find_exact_duplicates,
    find_similar_images,
    find_similar_phash,
    find_similar_whash,
)

# Define public API
__all__ = [
    # API Response infrastructure
    'ApiResponse',
    'ErrorCode',
    'ErrorDetail',
    'success',
    'error',
    'from_exception',
    'partial_success',
    # Types and Exceptions
    'ExactDuplicateSet',
    'InvalidImageError',
    'SimilarityError',
    'VALID_IMAGE_EXTENSIONS',
    # Validation
    'hamming_distance',
    'is_image_extension',
    'validate_and_normalize_hash',
    'validate_hash_size',
    'validate_image_path',
    'validate_threshold',
    # Metadata
    'compute_group_stats',
    'format_timestamp',
    'get_image_metadata',
    'get_image_quality_score',
    'get_resolution',
    # Hashing
    'compute_color_hash',
    'compute_color_phash',
    'compute_color_whash',
    'compute_phash',
    'compute_phash_batch',
    'compute_similarity_hash_batch',
    'compute_whash',
    'compute_whash_batch',
    'get_similarity_hash',
    # Hash utilities
    'load_image_with_fallback',
    'validate_hash_parameters',
    'normalize_hash_length',
    'compute_color_channels',
    'combine_color_hashes',
    'compute_generic_color_hash',
    'check_cache_for_hash',
    'handle_image_loading_errors',
    'get_effective_hash_size',
    # Algorithm utilities
    'resolve_hash_algorithm',
    'get_algorithm_info',
    'get_default_hash_size',
    'supports_color_hashing',
    'list_supported_algorithms',
    'initialize_algorithm_functions',
    'validate_algorithm_parameters',
    'get_algorithm_function',
    'set_algorithm_function',
    'get_algorithm_capabilities',
    'get_recommended_algorithm_for_use_case',
    'compare_algorithms',
    'register_algorithm',
    # Processing phases
    'PhaseContext',
    'phase_algorithm_resolution',
    'phase_exact_duplicate_detection',
    'phase_perceptual_hash_computation',
    'phase_similarity_clustering',
    'execute_all_phases',
    # Clustering
    'detect_exact_duplicates',
    'find_exact_duplicates',
    'find_similar_images',
    'find_similar_phash',
    'find_similar_whash',
]
