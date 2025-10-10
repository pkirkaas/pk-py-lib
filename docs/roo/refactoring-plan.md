# Comprehensive Codebase Refactoring Plan for pk-py-lib

**Document Version:** 1.0
**Date:** 2025-10-10
**Project:** pk-py-lib Python Library & Image Application

---

## Executive Summary

This refactoring plan addresses technical debt accumulated through organic growth and multiple direction changes in the pk-py-lib project. The analysis identified significant code duplication (estimated ~15-20% redundancy), organizational inconsistencies, and opportunities for simplification that will improve maintainability, testability, and future extensibility.

**Key Findings:**
- **Critical Duplication:** Duplicate model definitions between `gui/dialog_models.py` and `gui/models.py`
- **Architectural Split:** Previously had dual cache systems, now consolidated to `FlatCacheManager`
- **Settings Fragmentation:** Configuration logic spread across 4+ modules
- **Monolithic Files:** `similarity.py` (2,150 lines) handling too many responsibilities
- **Repeated Patterns:** Hash computation, validation, and color variant logic duplicated

**Impact Assessment:**
- **High Priority:** Consolidate duplicate GUI models, unify cache architecture
- **Medium Priority:** Refactor similarity.py, consolidate settings management
- **Low Priority:** Extract utility functions, improve documentation accuracy

**Estimated Effort:** 40-60 developer hours over 2-3 weeks for high/medium priority items

---

## 1. Duplicate Code Analysis

### 1.1 Critical: Duplicate GUI Models

**Location:**
- `src/pk_py_lib/gui/dialog_models.py` (lines 27-240)
- `src/pk_py_lib/gui/models.py` (lines 54-303)

**Duplicate Classes:**
```python
# Both files define:
- DialogView(Enum)         # Exact duplication
- FileItem (dataclass)     # Near-identical with minor variations
- GroupStats (dataclass)   # Identical structure
- Group/FileGroup          # Similar structure, different names
```

**Analysis:**
The `dialog_models.py` file appears to be a newer, cleaner implementation intended to replace the older `models.py`. However, both are actively imported by different parts of the codebase:

- `dialog_models` imported by: `similarity.py`, `export_service.py`
- `models` imported by: GUI widgets, dialogs, main application

**Root Cause:** Incomplete migration from old model structure to new one.

**Recommendation:**
1. **Consolidate to single source:** Choose `models.py` as canonical location (more imports, better organized)
2. **Create migration guide:** Document all import changes needed
3. **Deprecation path:** Mark `dialog_models.py` classes as deprecated with warnings
4. **Update imports:** Systematically update all imports to use `models.py`

**Impact:** HIGH - Affects 15+ files across library and application

**Estimated Effort:** 6-8 hours

---

### 1.2 High: Duplicate Settings/Configuration Logic

**Locations:**
- `src/pk_py_lib/core/settings_profiles.py` (SettingsProfilesManager class)
- `src/pk_py_lib/api/settings_profiles.py` (appears to be API wrapper)
- `src/pk_py_lib/core/configuration.py` (ConfigurationManager)
- `src/pk_py_lib/core/settings_schema.py` (validation functions)

**Duplication Pattern:**
- Profile CRUD operations repeated across modules
- Settings validation logic scattered
- Schema definitions not centralized
- Overlapping responsibilities between ConfigurationManager and SettingsProfilesManager

**Recommendation:**
1. **Establish clear hierarchy:**
   ```
   core/settings/
   ├── schema.py          # Schema definitions only
   ├── profiles.py        # Profile CRUD operations
   ├── validation.py      # All validation logic
   └── configuration.py   # High-level configuration management
   ```

2. **Single responsibility per module:**
   - `schema.py`: Define data structures, defaults
   - `profiles.py`: Load/save/manage profiles
   - `validation.py`: Validate and normalize settings
   - `configuration.py`: Orchestrate above modules

3. **Consolidate API layer:**
   - `api/settings_api.py` should be thin wrapper over core functionality
   - No business logic in API layer

**Impact:** MEDIUM - Core functionality but well-isolated

**Estimated Effort:** 8-10 hours

---

### 1.3 Medium: Hash Computation Code Duplication

**Location:** `src/pk_py_lib/core/image/similarity.py`

**Duplicate Patterns:**

1. **Similar structure in compute_phash() and compute_whash():**
   - Lines 325-460 (compute_phash)
   - Lines 922-1063 (compute_whash)

   Both contain:
   - Identical parameter validation
   - Same cache lookup/storage logic
   - Nearly identical PIL/OpenCV fallback pattern
   - Repeated hash length validation and normalization

2. **Color variants duplicate base logic:**
   - `compute_color_phash()` (lines 462-590)
   - `compute_color_whash()` (lines 1065-1199)

   Both split RGB channels and average hashes - only difference is base hash function

**Recommendation:**
1. **Extract common validation:**
   ```python
   def _validate_hash_params(hash_size: int, image_path: str) -> Path:
       """Common validation for all hash functions"""
       if hash_size < 4 or hash_size > 64:
           raise SimilarityError(f"hash_size must be between 4 and 64")
       path = Path(image_path)
       if not path.is_file():
           raise InvalidImageError(image_path, "File does not exist")
       return path
   ```

2. **Extract image loading with fallback:**
   ```python
   def _load_image_with_fallback(path: Path) -> Image.Image:
       """Load image using PIL with OpenCV fallback"""
       # Consolidate the repeated try/except PIL/OpenCV pattern
   ```

3. **Generic color hash function:**
   ```python
   def compute_color_hash(
       image_path: str,
       base_hash_func: Callable,  # phash or whash
       hash_size: int = 8,
       **kwargs
   ) -> Optional[str]:
       """Generic color-aware hash using any base hash function"""
       # Eliminate compute_color_phash and compute_color_whash
   ```

**Impact:** MEDIUM - Improves maintainability, reduces test burden

**Estimated Effort:** 6-8 hours

---

### 1.4 Medium: Repeated Hash Validation Logic

**Locations:** Throughout `similarity.py`

**Pattern:**
Hash validation and normalization code repeated in:
- `find_similar_phash()` lines 704-747
- `find_similar_whash()` lines 1274-1318
- Multiple compute functions

**Example of repeated code:**
```python
# This pattern appears 4+ times with minor variations:
if len(hash_str) == 16:
    pass
elif len(hash_str) == 21:
    hex_digits = ''.join(c for c in hash_str if c in '0123456789abcdefABCDEF')
    hash_str = hex_digits[:16] if len(hex_digits) >= 16 else hex_digits.zfill(16)
elif len(hash_str) < 8:
    raise ValueError(f"Hash too short: {len(hash_str)}")
# ... etc
```

**Recommendation:**
Create utility module `src/pk_py_lib/core/image/hash_utils.py`:
```python
def validate_and_normalize_hash(
    hash_str: str,
    expected_length: int = 16,
    context: str = ""
) -> str:
    """Validate and normalize hash string to expected length"""
    # Centralize all hash validation logic
```

**Impact:** LOW-MEDIUM - Quality of life improvement

**Estimated Effort:** 3-4 hours

---

## 2. Structural Reorganization Recommendations

### 2.1 High Priority: Split similarity.py Monolith

**Current State:**
- Single file: 2,150 lines
- Multiple responsibilities: hashing, grouping, metadata, quality scoring
- Difficult to navigate and test

**Proposed Structure:**
```
src/pk_py_lib/core/image/
├── __init__.py
├── similarity/
│   ├── __init__.py          # Public API exports
│   ├── hashing.py           # Hash computation (phash, whash, xxh3)
│   ├── clustering.py        # Similarity grouping algorithms
│   ├── metadata.py          # Image metadata extraction
│   ├── validation.py        # Hash/parameter validation
│   └── models.py            # ExactDuplicateSet, etc.
└── quality/                 # Already well-organized
```

**Breakdown by Responsibility:**

**hashing.py** (~600 lines):
- `compute_phash()`, `compute_whash()`, `compute_xxh3()`
- `compute_color_hash()` (unified)
- `get_similarity_hash()`, batch variants
- Cache integration

**clustering.py** (~500 lines):
- `find_similar_phash()`, `find_similar_whash()`
- `detect_exact_duplicates()`
- `find_exact_duplicates()`, `find_similar_images()`
- Union-find and grouping logic

**metadata.py** (~300 lines):
- `get_image_metadata()`, `get_resolution()`
- `get_image_quality_score()`
- `compute_group_stats()`
- `format_timestamp()`, helper functions

**validation.py** (~200 lines):
- `validate_and_normalize_hash()`
- `hamming_distance()`
- `is_image_extension()`
- Parameter validation helpers

**models.py** (~100 lines):
- `ExactDuplicateSet`
- `InvalidImageError`, `SimilarityError`
- Any similarity-specific data classes

**Benefits:**
- Each module <600 lines, focused single responsibility
- Easier testing (can mock/patch individual modules)
- Clearer import paths
- Better code discoverability

**Migration Strategy:**
1. Create new directory structure
2. Copy code to new files with internal imports
3. Update `similarity/__init__.py` to re-export public API (backward compatibility)
4. Update imports throughout codebase gradually
5. Deprecate old `similarity.py` after migration complete

**Impact:** HIGH - Major structural improvement

**Estimated Effort:** 12-16 hours

---

### 2.2 Medium Priority: Consolidate Cache Architecture

**Current Dual System:**

1. **Legacy CacheManager** (REMOVED):
   - Previously handled thumbnail caching
   - LRU eviction
   - File-backed pickle storage
   - 381 lines

2. **New FlatCacheManager** (`core/flat_cache.py`):
   - Persistent file metadata cache
   - SQLite backend
   - File-stat validation
   - Hash storage (xxh3, phash, whash, brisque)
   - 1,730 lines

**Analysis:**
- FlatCache is clearly the future (more robust, better features)
- Legacy cache still used for thumbnails only
- Confusion about which to use for new features
- No migration path documented

**Recommendation:**

**Option A: Complete Migration (COMPLETED)**
1. ✅ Removed legacy CacheManager
2. ✅ All caching now uses FlatCacheManager
3. ✅ Simplified cache interface

**Option B: Clear Separation (NOT NEEDED)**
1. ✅ CacheManager completely removed
2. ✅ FlatCacheManager is sole caching solution
3. ✅ No architectural confusion remains

**Recommendation: Option A** - Complete migration reduces complexity

**Implementation Plan:**
1. Add thumbnail table to FlatCache SQLite schema:
   ```sql
   CREATE TABLE thumbnails (
       path TEXT PRIMARY KEY,
       size INTEGER,
       thumbnail BLOB,
       created_at REAL
   )
   ```

2. Implement thumbnail methods in FlatCacheManager:
   - `get_thumbnail(path, size) -> bytes`
   - `set_thumbnail(path, size, data: bytes)`
   - LRU eviction by size limit

3. Update all thumbnail consumers to use FlatCache

4. Remove `cache.py` after migration

**Impact:** MEDIUM - Simplifies architecture significantly

**Estimated Effort:** 10-12 hours

---

### 2.3 Low Priority: Reorganize GUI Module Structure

**Current Structure:**
```
src/pk_py_lib/gui/
├── __init__.py
├── dialog_models.py       # DUPLICATE - should be removed
├── models.py              # Keep as canonical
├── export_service.py
├── widgets.py             # 986 lines - too large
├── dialogs/
├── file_selector/
├── settings_manager/
└── utils/
```

**Issues:**
- `widgets.py` is monolithic (FileGroupView + SimilarityPreviewPane)
- Unclear which models file to use
- `export_service.py` in wrong location (should be in dialogs or utils)

**Proposed Structure:**
```
src/pk_py_lib/gui/
├── __init__.py
├── models.py              # Consolidated models only
├── dialogs/
│   ├── base_file_manager_dialog.py
│   ├── progress_dialog.py
│   ├── view_cache_dialog.py
│   └── export_service.py  # Move here - dialog-related
├── widgets/
│   ├── __init__.py
│   ├── file_group_view.py        # Extract from widgets.py
│   └── similarity_preview.py     # Extract from widgets.py
├── file_selector/
├── settings_manager/
└── utils/
```

**Benefits:**
- Clear separation of concerns
- Smaller, more focused files
- Better discoverability

**Impact:** LOW - Quality improvement, not urgent

**Estimated Effort:** 4-6 hours

---

## 3. Code Cleanup Items

### 3.1 Remove Unused/Dead Code

**Identified Dead Code:**

1. **Commented LSH code in similarity.py**
   - Lines 61: "# LSH removed; always use brute-force"
   - Commented references throughout
   - **Action:** Remove all LSH comments and dead code paths

2. **Duplicate Path imports**
   - `similarity.py` lines 18, 56, 57: `from pathlib import Path` (3 times!)
   - **Action:** Consolidate to single import at top

3. **Unused import statements**
   - Review all files for unused imports
   - Use automated tools (autoflake, pylint)

4. **Legacy cache files**
   - CacheManager removed, no cleanup needed

**Estimated Effort:** 2-3 hours

---

### 3.2 Consolidate Duplicate Imports

**Pattern Found:**
Many files have duplicate or redundant imports:

```python
# similarity.py example:
from pathlib import Path  # Line 18
from pk_py_lib.core.flat_cache import FlatCacheManager, FlatCacheDBError  # Line 51
from pk_py_lib.gui.dialog_models import FileItem, Group, GroupStats  # Line 53
from pathlib import Path  # Line 56 - DUPLICATE
from pathlib import Path  # Line 57 - DUPLICATE
```

**Action:**
- Automated cleanup with isort + autoflake
- Add pre-commit hooks to prevent future duplication

**Estimated Effort:** 1-2 hours

---

### 3.3 Remove Test/Debug Files from Root

**Files to Review:**
```
test_algorithm_selection_fix.py
test_comprehensive_hash_bug.py
test_gui_error_handling.py
test_hash_algorithm_selection.py
test_hash_comparison.py
test_log_dev.txt
test_log_errors_decorator.py
test_logging_lineendings.py
temp_set_logging.py
```

**Action:**
- Move to `tests/` directory if still needed
- Delete if obsolete/one-off debugging scripts
- Add to `.gitignore` pattern for temp test files

**Estimated Effort:** 1 hour

---

## 4. Simplification Opportunities

### 4.1 Simplify find_similar_images Multi-Phase Logic

**Current Complexity:**
- Lines 1864-2119 (255 lines)
- 4 distinct phases with complex branching
- Exact duplicate detection + perceptual hashing + expansion
- Difficult to follow and test

**Recommendation:**
Extract phases into separate, testable functions:

```python
def find_similar_images(
    paths: List[str],
    algorithm: Optional[str] = None,
    threshold: Optional[int] = None,
    settings: Optional[Dict] = None,
    flat_cache_manager: Optional[FlatCacheManager] = None,
    search_type: str = 'similarity'
) -> List[Group]:
    """
    Main orchestrator - delegates to phase functions
    """
    algorithm = _resolve_algorithm(algorithm, settings)

    if algorithm == 'exact':
        return _find_exact_duplicates_only(paths, flat_cache_manager, search_type)

    # Perceptual similarity path
    exact_sets, path_map = _detect_exact_duplicates_phase(paths, flat_cache_manager)
    representatives = _extract_representatives_phase(paths, exact_sets, path_map)
    perceptual_groups = _cluster_by_perceptual_hash_phase(
        representatives, algorithm, threshold, settings, flat_cache_manager, search_type
    )
    final_groups = _expand_with_exact_duplicates_phase(
        perceptual_groups, exact_sets, path_map, flat_cache_manager, search_type
    )

    return final_groups
```

**Benefits:**
- Each phase independently testable
- Clearer control flow
- Easier to optimize individual phases
- Better error handling per phase

**Impact:** MEDIUM - Improves maintainability significantly

**Estimated Effort:** 6-8 hours

---

### 4.2 Simplify Settings Algorithm Resolution

**Current Pattern:**
The algorithm resolution logic is repeated 3+ times with extensive debugging:
- `get_similarity_hash()` lines 1539-1572
- `compute_similarity_hash_batch()` lines 1615-1648
- `find_similar_images()` lines 1907-1938

**Each repetition includes:**
- ~35 lines of debugging logs
- Nested if/else for settings lookup
- Fallback to default
- Warning messages

**Recommendation:**
Create utility function:

```python
def resolve_algorithm(
    algorithm: Optional[str],
    settings: Optional[Dict],
    context: str = ""
) -> str:
    """
    Resolve hash algorithm from parameter or settings.

    Args:
        algorithm: Explicit algorithm or None
        settings: Settings dict to check for algorithm
        context: Context string for logging (e.g., "batch_compute")

    Returns:
        Resolved algorithm: 'phash' or 'whash'
    """
    if algorithm is not None:
        return algorithm

    if settings and 'criteria' in settings:
        return settings['criteria'].get('similarity_hash_algorithm', 'phash')

    logger.debug(f"{context}: Using default algorithm 'phash'")
    return 'phash'
```

**Benefits:**
- Reduce ~100 lines of duplicated code
- Consistent behavior across all functions
- Single place to update logging

**Impact:** LOW-MEDIUM - Code quality improvement

**Estimated Effort:** 2-3 hours

---

### 4.3 Simplify search_type Conditional Logic

**Pattern:**
Throughout `similarity.py`, there are repeated patterns:

```python
if search_type == 'duplicate':
    return "Unknown"  # Skip expensive operation
# ... else do the operation
```

This appears in:
- `get_resolution()`
- `get_image_metadata()`
- `get_image_quality_score()`
- Batch functions

**Recommendation:**
Use decorator pattern:

```python
def skip_for_duplicate_mode(return_value=None):
    """Decorator to skip function in duplicate mode"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, search_type='similarity', **kwargs):
            if search_type == 'duplicate':
                logger.debug(f"Skipping {func.__name__} in duplicate mode")
                return return_value
            return func(*args, search_type=search_type, **kwargs)
        return wrapper
    return decorator

@skip_for_duplicate_mode(return_value="Unknown")
def get_resolution(path: str, search_type: str = 'similarity') -> str:
    """Get image resolution"""
    # No more if/else for search_type!
    with Image.open(path) as img:
        return f"{img.size[0]}x{img.size[1]}"
```

**Benefits:**
- DRY principle - define behavior once
- Clearer function logic
- Easy to add new skip conditions

**Impact:** LOW - Nice to have

**Estimated Effort:** 3-4 hours

---

## 5. Documentation Accuracy Issues

### 5.1 Outdated Function Documentation

**Examples Found:**

1. **compute_phash() docstring** (lines 331-365):
   - Uses `flat_cache_manager` parameter
   - FlatCacheManager is the sole caching solution
   - **Action:** Remove legacy cache references

2. **compute_whash() docstring** (lines 931-969):
   - Uses `flat_cache_manager` parameter
   - ✅ Updated to reflect actual parameters

3. **Batch functions documentation**:
   - Reference `cache_manager` and `update_cache` parameters that don't exist
   - **Action:** Update all batch function docstrings

**Recommendation:**
- Systematic docstring review and update
- Add pre-commit hook to validate docstrings match signatures
- Consider using pydocstyle or darglint for automated checks

**Impact:** MEDIUM - Affects developer experience

**Estimated Effort:** 4-6 hours

---

### 5.2 Inconsistent Comment Style

**Observations:**
- Mix of inline comments and block comments
- Some functions over-commented, others under-commented
- Inconsistent use of type hints in comments vs annotations

**Recommendation:**
Establish and enforce style guide:
- Use type hints instead of type comments
- Block comments for complex logic
- Inline comments sparingly for non-obvious code
- No commented-out code (use git history)

**Estimated Effort:** 3-4 hours

---

## 6. Prioritized Action Items

### Phase 1: Critical Fixes (Week 1) - 20-26 hours

| Priority | Item | Effort | Risk | Impact |
|----------|------|--------|------|--------|
| **P0** | Consolidate duplicate GUI models | 6-8h | Medium | High |
| **P0** | Document model migration guide | 2h | Low | High |
| **P1** | Split similarity.py into modules | 12-16h | High | High |

**Rationale:** Addresses most confusing aspects of codebase, unblocks future work.

---

### Phase 2: Architectural Improvements (Week 2) - 18-22 hours

| Priority | Item | Effort | Risk | Impact |
|----------|------|--------|------|--------|
| **P1** | Consolidate settings/configuration logic | 8-10h | Medium | Medium |
| **P1** | Migrate to single cache system | 10-12h | High | Medium |

**Rationale:** Simplifies architecture, reduces maintenance burden.

---

### Phase 3: Code Quality (Week 3) - 15-20 hours

| Priority | Item | Effort | Risk | Impact |
|----------|------|--------|------|--------|
| **P2** | Extract hash computation utilities | 6-8h | Low | Medium |
| **P2** | Simplify find_similar_images logic | 6-8h | Medium | Medium |
| **P3** | Clean up dead code and test files | 3-4h | Low | Low |

**Rationale:** Improves code quality and testability.

---

### Phase 4: Polish (Ongoing) - 10-15 hours

| Priority | Item | Effort | Risk | Impact |
|----------|------|--------|------|--------|
| **P3** | Update documentation accuracy | 4-6h | Low | Medium |
| **P3** | Reorganize GUI structure | 4-6h | Low | Low |
| **P3** | Add code quality tools/pre-commit hooks | 2-3h | Low | Medium |

**Rationale:** Final polish, establish practices to prevent regression.

---

## 7. Risk Assessment & Mitigation

### 7.1 High-Risk Refactorings

#### Risk: Breaking Existing Functionality During Model Consolidation

**Likelihood:** Medium
**Impact:** High
**Affected:** All GUI components, similarity detection, export functionality

**Mitigation Strategies:**
1. **Comprehensive test coverage first:**
   - Write integration tests for all dialog workflows
   - Add tests for model serialization/deserialization
   - Test export functionality end-to-end

2. **Gradual migration approach:**
   ```python
   # Week 1: Add compatibility layer
   from .models import FileItem as CanonicalFileItem
   FileItem = CanonicalFileItem  # Temporary alias

   # Week 2-3: Update imports file by file
   # Week 4: Remove compatibility layer
   ```

3. **Feature flags for major changes:**
   - Environment variable to switch between old/new implementations
   - Allows quick rollback if issues found

4. **Deprecation warnings:**
   ```python
   import warnings
   warnings.warn(
       "dialog_models is deprecated, use models instead",
       DeprecationWarning,
       stacklevel=2
   )
   ```

---

#### Risk: Cache Migration Data Loss

**Likelihood:** Low
**Impact:** High (user data)
**Affected:** All cached thumbnails and metadata

**Mitigation Strategies:**
1. **Backup before migration:**
   ```python
   def backup_legacy_cache():
       """Create backup of legacy cache before migration"""
       import shutil
       cache_path = Path("cache/legacy_cache.pkl")
       if cache_path.exists():
           shutil.copy(cache_path, cache_path.with_suffix('.pkl.backup'))
   ```

2. **Migration script with validation:**
   ```python
   def migrate_cache_with_verification():
       """Migrate cache and verify data integrity"""
       new_cache = FlatCacheManager()

       for key, value in legacy_data.items():
           new_cache.set_entry(key, value)
           # Verify each entry after writing
           assert new_cache.get_entry(key) == value
   ```

3. **Fallback to recomputation:**
   - If migration fails, log error but continue
   - Gracefully recompute missing data on demand
   - User experience: slightly slower first run, no data loss

---

#### Risk: Breaking Changes in similarity.py Split

**Likelihood:** Medium
**Impact:** High
**Affected:** All code using similarity functions (app, tests, showcases)

**Mitigation Strategies:**
1. **Maintain backward compatibility:**
   ```python
   # similarity/__init__.py
   # Re-export all public functions
   from .hashing import compute_phash, compute_whash, get_similarity_hash
   from .clustering import find_similar_images, detect_exact_duplicates
   from .metadata import get_image_metadata

   __all__ = [
       'compute_phash', 'compute_whash', 'get_similarity_hash',
       'find_similar_images', 'detect_exact_duplicates',
       'get_image_metadata'
   ]
   ```

2. **Deprecation period:**
   - Keep old `similarity.py` as wrapper for 1-2 releases
   - Import from new modules internally
   - Emit deprecation warnings

3. **Update all imports atomically:**
   - Use IDE refactoring tools for bulk updates
   - Grep/sed scripts for automated updates
   - Test suite validates no import errors

---

### 7.2 Medium-Risk Refactorings

#### Risk: Settings Consolidation Breaking Configuration Files

**Likelihood:** Low
**Impact:** Medium (user inconvenience)

**Mitigation:**
- Configuration schema versioning
- Automatic migration for old config formats
- Validation with clear error messages
- Fallback to defaults on parse errors

---

#### Risk: Performance Regression from Refactoring

**Likelihood:** Low
**Impact:** Medium

**Mitigation:**
- Benchmark critical paths before/after
- Profile code to identify bottlenecks
- Keep existing algorithms, only reorganize
- Add performance tests to CI/CD

---

### 7.3 Low-Risk Refactorings

#### Simplification and Cleanup Items

**Risk Level:** Low
**Impact:** Low-Medium

These changes (dead code removal, documentation updates, code style) are low risk but should still:
- Be reviewed in pull requests
- Include tests where applicable
- Be deployed incrementally

---

## 8. Testing Strategy

### 8.1 Pre-Refactoring Test Coverage

**Action Items:**
1. **Measure baseline coverage:**
   ```bash
   pytest --cov=src/pk_py_lib --cov-report=html
   ```
   Target: Achieve >70% coverage before major refactoring

2. **Add critical path tests:**
   - Image similarity detection end-to-end
   - Cache operations (get/set/invalidate)
   - Settings load/save/validate
   - GUI model serialization

3. **Integration tests:**
   - Full workflow: scan directory → detect duplicates → export results
   - GUI integration: load dialog → select files → perform action

---

### 8.2 Refactoring Test Plan

**For Each Major Refactoring:**

1. **Create characterization tests:**
   - Capture current behavior (even if buggy)
   - Ensures refactoring doesn't change behavior
   - Can be updated if behavior should change

2. **Add unit tests for new modules:**
   - Each extracted module gets its own test file
   - Test edge cases and error conditions
   - Mock dependencies for isolation

3. **Regression testing:**
   - Run full test suite after each change
   - Manual testing of GUI workflows
   - Verify with real image datasets

---

## 9. Implementation Guidelines

### 9.1 Branch Strategy

```
main
├── refactor/phase1-models          # GUI model consolidation
├── refactor/phase1-similarity      # Split similarity.py
├── refactor/phase2-settings        # Settings consolidation
├── refactor/phase2-cache           # Cache unification
└── refactor/phase3-cleanup         # Code quality improvements
```

**Process:**
1. Create feature branch from main
2. Make changes incrementally with frequent commits
3. Keep PRs focused (<500 lines when possible)
4. Merge to main after review + tests pass
5. Monitor for issues before starting next phase

---

### 9.2 Code Review Checklist

For each refactoring PR:

- [ ] Tests added/updated for changed code
- [ ] Documentation updated (docstrings, markdown docs)
- [ ] Backward compatibility maintained or deprecation path documented
- [ ] No performance regression (benchmark if critical path)
- [ ] Type hints added/updated
- [ ] Import statements cleaned up
- [ ] No dead code or commented code
- [ ] Consistent code style (run black/isort)
- [ ] Changelog entry added

---

### 9.3 Rollback Plan

For each high-risk change:

1. **Feature flag for new code:**
   ```python
   USE_NEW_CACHE = os.getenv('USE_NEW_CACHE', 'false').lower() == 'true'
   ```

2. **Revert script:**
   ```bash
   git revert <commit-range>
   git push origin main
   ```

3. **Database rollback:**
   - Keep schema migrations reversible
   - Test downgrade path

4. **Communication:**
   - Document rollback procedure
   - Notify users if data format changes

---

## 10. Success Metrics

### 10.1 Code Quality Metrics

**Baseline (Current):**
- Lines of code: ~15,000
- Duplicate code: ~15-20% (estimated)
- Average file size: ~400 lines
- Largest file: 2,150 lines (similarity.py)
- Test coverage: Unknown (establish baseline)

**Target (Post-Refactoring):**
- Duplicate code: <5%
- Average file size: <300 lines
- Largest file: <800 lines
- Test coverage: >75%
- Zero critical TODOs or FIXME comments

---

### 10.2 Developer Experience Metrics

**Measure:**
- Time to onboard new developer (setup + understand codebase)
- Time to implement new feature (e.g., add new hash algorithm)
- Code review time (less confusion = faster reviews)

**Target:**
- 25% reduction in onboarding time
- 30% reduction in feature implementation time
- 20% faster code reviews

---

### 10.3 Performance Metrics

**Baseline and Monitor:**
- Image scan performance (images/second)
- Cache hit rate
- Memory usage
- GUI responsiveness

**Target:**
- No regression in performance
- Improved cache hit rate from better organization

---

## 11. Conclusion

This refactoring plan addresses significant technical debt while maintaining system stability. The phased approach with clear priorities, risk mitigation, and success metrics provides a roadmap for systematically improving the codebase.

**Key Takeaways:**
1. **Focus on high-impact items first:** Model consolidation and similarity.py split
2. **Maintain backward compatibility:** Use deprecation periods and compatibility layers
3. **Test thoroughly:** Increase coverage before and during refactoring
4. **Proceed incrementally:** Small, reviewable PRs reduce risk
5. **Measure success:** Track metrics to validate improvements

**Next Steps:**
1. Review and approve this plan with stakeholders
2. Establish baseline metrics (coverage, performance)
3. Begin Phase 1: Critical Fixes
4. Regular check-ins to assess progress and adjust plan

---

**Document History:**
- v1.0 (2025-10-10): Initial comprehensive refactoring plan
