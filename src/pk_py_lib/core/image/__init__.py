"""
Image Processing Module

Core functionality for image loading, manipulation, analysis, transformation, and quality evaluation.
Quality evaluation scores are normalized such that higher float values indicate higher image quality
(implementation-specific scale, e.g., 0-100 where 100 is perfect quality).
"""

from .similarity import compute_similarity_hash, find_similar_images  # Existing imports; adjust if needed
from .quality.provider import get_active_image_quality_evaluator, set_active_evaluator


__all__ = [
    'compute_similarity_hash',
    'find_similar_images',
    'get_active_image_quality_evaluator',
    'set_active_evaluator'
]