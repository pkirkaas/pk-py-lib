# Settings Migration Guide

## Overview

This guide documents migration steps for settings profiles between legacy formats and the new structured JSON format (Option A). The goal is to preserve user data while transitioning to the more flexible, schema-validated structured profiles.

## Migration Strategy

1. **Detection**: On profile load, check `format` field:
   - `None` or missing: Legacy KV format
   - `"json"`: Structured format with `json_data`

2. **Conversion Path**:
   - Legacy → Structured: Map KV pairs to structured fields (e.g., `pools.A.paths` from keys like `pool_a_path1`)
   - Structured → Legacy: Flatten `json_data` back to KV (rare, only if UI forces legacy mode)

3. **Validation**: Always run schema validation post-conversion. Invalidate and prompt recreate if unrecoverable.

4. **Fallbacks**:
   - Missing required fields: Use defaults from `create_default_profile()`
   - Type mismatches: Coerce to expected types (str → list for paths, etc.)

## Recent Fixes

### Type Mismatch Fix (2025-10-13)

**Issue**: SettingsProfile dataclass instances were passed directly to the editor instead of dicts, causing failure to restore `json_data` (custom pools/mode) on load after restart. The editor expected dict format but received dataclass objects without proper conversion.

**Fix Applied**:
- In `img_app/img_app/main_window.py` (`_load_profile_into_editor`): Added type guard to convert SettingsProfile to dict via `to_dict()` or extract `json_data` if `is_json_format()`, fallback to `{}`.
- In `src/pk_py_lib/gui/settings_manager/structured_editor.py` (`load_profile`): Added initial type guard to handle SettingsProfile by converting to `json_data` or `{}`.
- In `src/pk_py_lib/gui/settings_manager/controller.py` (`get_profile` and `get_profile_with_values`): Ensured return of dict via `to_dict()` if available, or `dict(p.data)` for SettingsProfile.

**Verification**:
- Custom pools (e.g., added "/custom/path" to Pool A) and mode ("similarity") now persist after update/save/close/restart/load.
- No reversion to defaults observed in manual testing.

**Impact**: Transparent to users; existing profiles load correctly without data loss. New profiles created in structured format are unaffected.

## Implementation Details

### Legacy to Structured Mapping

| Legacy KV Key | Structured Field | Notes |
|---------------|------------------|-------|
| `profile_name` | `json_data.name` | Required, validated 1-64 chars |
| `pool_a_path1`, `pool_a_path2`... | `json_data.pools.A.paths` | List of strings; unlimited |
| `mode` | `json_data.mode` | "duplicates" or "similarity" |
| `similarity_algorithm` | `json_data.criteria.similarity_hash_algorithm` | "phash" or "whash" |
| `similarity_degree` | `json_data.criteria.degree_ui` | 0-100 integer |

### Structured Schema

Refer to `src/pk_py_lib/core/settings/schema.py` for full JSON schema.

Key sections:
- `pools`: Dict with "A" (required) and "B" (optional for two-pool)
- `mode`: Operation type
- `criteria`: Algorithm and thresholds
- `scope`: Single vs two-pool, direction
- `output`: Report vs move/copy actions

## Rollback Procedure

If issues arise:
1. Backup `settings.db`
2. Revert to legacy mode by setting all profiles `format=None`
3. Use `controller.delete_all_structured()` to clear json_data

## Testing Checklist

- [x] Load legacy profile → converts to structured without loss
- [x] Edit structured (add custom pool, change mode) → saves and reloads correctly
- [x] Restart app → custom values persist (no defaults)
- [ ] Two-pool mode with direction mapping
- [ ] Invalid data → graceful fallback to defaults
