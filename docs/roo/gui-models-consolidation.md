# GUI Models Consolidation - Migration Guide

## Overview

The duplicate data model classes in `pk_py_lib.gui.dialog_models` and `pk_py_lib.gui.models` have been consolidated to eliminate code duplication and establish a single source of truth.

**Date**: October 10, 2025
**Status**: ✅ Complete

## What Changed

### Consolidated Classes (Now in `models.py`)

The following classes have been consolidated into [`src/pk_py_lib/gui/models.py`](../../src/pk_py_lib/gui/models.py):

1. **`FileItem`** - Immutable file representation with metadata
   - ✅ Merged additional fields from dialog_models version:
     - `quality_score: Optional[float]` - Image quality score
     - `quality_algorithm: Optional[str]` - Quality algorithm name (e.g., 'brisque')
     - `exact_set_id: Optional[int]` - Identifier for exact duplicate sets

2. **`GroupStats`** - Statistics for file groups
   - ✅ Identical in both files, canonical version now in `models.py`

3. **`DialogView`** - View mode enumeration (TREE, PREVIEW, REPORT)
   - ✅ Identical in both files, canonical version now in `models.py`

4. **`SelectionStore`** - Thread-safe selection state manager
   - ✅ Already defined only in `models.py`, now re-exported from `dialog_models.py`

### Classes Still in `dialog_models.py`

The following classes remain in [`src/pk_py_lib/gui/dialog_models.py`](../../src/pk_py_lib/gui/dialog_models.py):

- **`Group`** - List-based group container (uses `List[FileItem]`)
- **`DialogState`** - Mutable dialog state container

**Note**: For new code, consider using `FileGroup` from `models.py` which uses immutable `Tuple[FileItem, ...]` instead of `List[FileItem]`.

## Migration Path

### For New Code

**Always import from the canonical source:**

```python
# ✅ CORRECT - Import from models.py
from pk_py_lib.gui.models import FileItem, GroupStats, DialogView, SelectionStore

# ✅ Also correct - Import via package namespace
from pk_py_lib.gui import FileItem, GroupStats, DialogView

# ❌ DEPRECATED - Avoid importing from dialog_models.py
from pk_py_lib.gui.dialog_models import FileItem, GroupStats, DialogView
```

### For Existing Code

Existing code that imports from `dialog_models.py` will continue to work with backward compatibility:

- **`dialog_models.py` now re-exports** the consolidated classes from `models.py`
- **Deprecation warnings** are issued when importing from `dialog_models.py`
- This provides a smooth transition period

### Updated Import Statements

The following files were updated to use canonical imports:

1. **`src/pk_py_lib/core/image/_similarity_deprecated.py`**
   - Changed: `FileItem`, `GroupStats` → import from `models.py`
   - Kept: `Group` → still imports from `dialog_models.py` (List-based)

2. **`src/pk_py_lib/core/image/similarity/metadata.py`**
   - Changed: `FileItem`, `GroupStats` → import from `models.py`

3. **`src/pk_py_lib/core/image/similarity/clustering.py`**
   - Changed: `FileItem` → import from `models.py`
   - Kept: `Group` → still imports from `dialog_models.py` (List-based)

4. **`src/pk_py_lib/gui/__init__.py`**
   - Now exports all model classes from `models.py` for convenience

## FileItem API Changes

The consolidated `FileItem` in `models.py` now includes all fields from both versions:

### Original Fields
```python
path: str                      # Absolute filesystem path
size: int                      # File size in bytes
resolution: str                # Image resolution (e.g., "1920x1080")
mod_date: str                  # Modification date
score: Optional[float]         # Similarity score (0.0-1.0)
file_type: str                 # File extension/type (e.g., "JPEG")
savings: int                   # Potential space savings in bytes
```

### New Fields (from dialog_models version)
```python
quality_score: Optional[float]     # Image quality score (normalized, higher = better)
quality_algorithm: Optional[str]   # Quality algorithm name (e.g., 'brisque')
exact_set_id: Optional[int]        # Identifier for exact duplicate sets
```

**All existing code remains compatible** - the new fields default to `None`.

## Package Exports

The `pk_py_lib.gui` package now exports common models:

```python
from pk_py_lib.gui import (
    # File management models
    FileItem,
    GroupStats,
    DialogView,
    SelectionStore,
    FileGroup,         # Immutable tuple-based groups
    FileGroupModel,    # Advanced filtering and direction support
    PoolDirection,
    # Similarity models
    SimilarityStats,
    SimilarityImage,
    SimilarityGroup,
)
```

## Deprecation Timeline

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Consolidate classes, add deprecation warnings |
| **Phase 2** | 🔄 Current | Transition period - both import paths work |
| **Phase 3** | 📅 Future | Remove `dialog_models.py` or reduce to minimal shim |

During Phase 2 (current):
- ✅ Imports from `dialog_models.py` work but issue deprecation warnings
- ✅ All functionality preserved
- ✅ Backward compatibility maintained

## Testing

After consolidation, verify:

1. ✅ Run application: `pdm run imgapp`
2. ✅ Check for deprecation warnings in console
3. ✅ Verify file management dialogs function correctly
4. ✅ Test similarity comparison features
5. ✅ Confirm duplicate detection works

## Benefits

### Before Consolidation
- ❌ Duplicate class definitions in two files
- ❌ Risk of diverging implementations
- ❌ Import confusion (which file to use?)
- ❌ Maintenance burden keeping both in sync

### After Consolidation
- ✅ Single source of truth in `models.py`
- ✅ All functionality merged and preserved
- ✅ Clear import guidance
- ✅ Reduced maintenance burden
- ✅ Backward compatibility maintained

## Best Practices

### For Library Developers

1. **Always add new model fields to `models.py`**
2. **Export new models from `gui/__init__.py`** for convenience
3. **Update this documentation** when making model changes
4. **Keep `dialog_models.py` in sync** during transition period

### For Application Developers

1. **Import from `models.py`** or package namespace
2. **Use `FileGroup`** for new immutable group code
3. **Use `FileGroupModel`** for advanced filtering needs
4. **Avoid `dialog_models.py`** imports (deprecated)

## Related Documentation

- [`refactoring-plan.md`](./refactoring-plan.md) - Overall refactoring strategy
- [`file-management-dialogs-architecture.md`](./file-management-dialogs-architecture.md) - Dialog architecture
- [`src/pk_py_lib/gui/models.py`](../../src/pk_py_lib/gui/models.py) - Canonical model source
- [`src/pk_py_lib/gui/dialog_models.py`](../../src/pk_py_lib/gui/dialog_models.py) - Deprecated imports

## Questions or Issues?

If you encounter issues during migration:

1. Check deprecation warnings for guidance
2. Review this migration guide
3. Examine updated import examples in the codebase
4. Consult the canonical `models.py` docstrings

## Summary

The consolidation successfully:
- ✅ Eliminated duplicate class definitions
- ✅ Established single source of truth in `models.py`
- ✅ Preserved all functionality and fields
- ✅ Maintained backward compatibility
- ✅ Provided clear migration path
- ✅ Updated all internal imports to canonical source
- ✅ Added comprehensive documentation

All code continues to work during the transition period, with clear deprecation warnings guiding developers toward the canonical import location.
