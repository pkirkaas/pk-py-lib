# Similarity Module Migration Guide

## Overview

The `similarity.py` monolithic file (2,150 lines) has been refactored into a modular structure for better maintainability and organization.

## What Changed

### Old Structure (Deprecated)
```
src/pk_py_lib/core/image/
└── similarity.py  # 2,150 lines - MOVED to _similarity_deprecated.py
```

### New Structure
```
src/pk_py_lib/core/image/
└── similarity/
    ├── __init__.py          # Public API re-exports
    ├── types.py             # Shared types and exceptions (~100 lines)
    ├── validation.py        # Parameter validation (~250 lines)
    ├── metadata.py          # Metadata extraction (~330 lines)
    ├── hashing.py           # Hash computation (~770 lines)
    └── clustering.py        # Similarity detection (~800 lines)
```

## Backward Compatibility

**✅ NO CODE CHANGES REQUIRED**

All existing imports continue to work without modification:

```python
# These imports still work exactly as before:
from pk_py_lib.core.image.similarity import compute_phash
from pk_py_lib.core.image.similarity import find_similar_images
from pk_py_lib.core.image.similarity import get_image_metadata
# ... etc
```

The `similarity/__init__.py` re-exports all public functions, maintaining 100% API compatibility.

## Benefits of Refactoring

1. **Better Organization**: Each module has a single, clear responsibility
2. **Easier Navigation**: Find functions faster in ~300-800 line files vs 2,150 lines
3. **Improved Testability**: Test individual modules in isolation
4. **Clearer Dependencies**: Import relationships are explicit
5. **Reduced Complexity**: Each module is easier to understand and maintain

## Module Responsibilities

### types.py
- `ExactDuplicateSet` dataclass
- `InvalidImageError`, `SimilarityError` exceptions
- `VALID_IMAGE_EXTENSIONS` constant

### validation.py
- `validate_hash_size()`, `validate_image_path()`
- `validate_and_normalize_hash()`, `validate_threshold()`
- `hamming_distance()` - Hamming distance calculation
- `is_image_extension()` - File extension validation

### metadata.py
- `get_image_metadata()` - Extract file metadata
- `get_resolution()` - Get image dimensions
- `get_image_quality_score()` - Compute quality scores
- `format_timestamp()` - Format modification dates
- `compute_group_stats()` - Aggregate statistics

### hashing.py
- `compute_phash()`, `compute_whash()` - Individual hash computation
- `compute_color_phash()`, `compute_color_whash()` - Color-aware variants
- `compute_phash_batch()`, `compute_whash_batch()` - Batch computation
- `get_similarity_hash()`, `compute_similarity_hash_batch()` - Generic dispatchers

### clustering.py
- `find_similar_phash()`, `find_similar_whash()` - Perceptual similarity grouping
- `detect_exact_duplicates()` - XXH3-based duplicate detection
- `find_exact_duplicates()` - Create groups from duplicate hashes
- `find_similar_images()` - Main dispatcher with two-phase processing

## Migration Timeline

- **Refactored**: 2025-10-10
- **Old File Location**: `_similarity_deprecated.py` (backup, will be removed in future release)
- **Deprecation Period**: None - seamless transition via re-exports

## For Developers

If you're working on similarity detection code:

1. **Import from submodules** for clarity (optional):
   ```python
   from pk_py_lib.core.image.similarity.hashing import compute_phash
   from pk_py_lib.core.image.similarity.clustering import find_similar_images
   ```

2. **Or use the package-level imports** (recommended for stability):
   ```python
   from pk_py_lib.core.image.similarity import compute_phash, find_similar_images
   ```

Both approaches work identically and are fully supported.

## Questions?

Refer to the refactoring plan at [`docs/roo/refactoring-plan.md`](../../../docs/roo/refactoring-plan.md) for detailed analysis and design decisions.
