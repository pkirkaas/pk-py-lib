# Unified Settings API Migration Guide

## Overview

This guide documents the migration to the updated UnifiedSettingsAPI in the img_app project. Recent enhancements include new methods for profile lifecycle management (`ensure_default_profile`, `get_active`, `set_active`, `validate_profile_name`) and standardization of return types using [`ApiResponse`](src/pk_py_lib/core/api/response.py) for most operations. This ensures consistent error handling and response structures across the API.

The changes promote robustness in settings management, particularly for profile activation and validation, while affecting callers that previously expected direct return values (e.g., lists or dicts). No breaking changes to core functionality, but update code to handle wrapped responses.

Key goals:
- Consistent error propagation via `ApiResponse` (with `success`, `data`, `error` fields).
- Simplified active profile handling without schema alterations.
- Validation to prevent invalid profile names early.

Refer to [`src/pk_py_lib/api/settings/unified_api.py`](src/pk_py_lib/api/settings/unified_api.py) for full implementation.

## New Methods

### ensure_default_profile() → ApiResponse

**Description**: Ensures a default profile exists in the settings database. If none exists, creates one using factory defaults from [`create_default_profile`](src/pk_py_lib/core/settings/profiles.py). This method is typically called on application startup to guarantee a fallback profile.

**Parameters**:
- None.

**Returns**: [`ApiResponse`](src/pk_py_lib/core/api/response.py)
  - `success`: `True` if default profile is ensured (created or already exists), `False` otherwise.
  - `data`: The name of the default profile (str) on success, `None` on failure.
  - `error`: Detailed error message (str) if creation or check fails (e.g., database error).

**Usage Example**:
```python
from pk_py_lib.api.settings import UnifiedSettingsAPI

api = UnifiedSettingsAPI()
response = api.ensure_default_profile()
if response.success:
    default_name = response.data
    print(f"Default profile ensured: {default_name}")
else:
    print(f"Error ensuring default: {response.error}")
```

**Migration Notes**: This is a new method; integrate it into initialization flows (e.g., app startup in [`img_app/img_app/app.py`](img_app/img_app/app.py)) to prevent nil-profile errors.

### get_active() → ApiResponse

**Description**: Retrieves the currently active settings profile. The active profile is determined by the `is_default` flag in the database (legacy compatibility) or explicit active marking in structured profiles. Returns the profile data if active, else `None`.

**Parameters**:
- None.

**Returns**: [`ApiResponse`](src/pk_py_lib/core/api/response.py)
  - `success`: `True` if active profile found or query succeeded, `False` on database error.
  - `data`: Dict representation of the active profile (from `to_dict()`) or `None` if no active profile.
  - `error`: Error details (e.g., "No active profile set").

**Usage Example**:
```python
response = api.get_active()
if response.success and response.data:
    active_profile = response.data
    print(f"Active mode: {active_profile.get('mode', 'unknown')}")
else:
    print(f"No active profile or error: {response.error}")
```

**Migration Notes**: Replaces ad-hoc active checks in callers (e.g., GUI controllers). Use `response.data` instead of direct returns.

### set_active(profile_name: str) → ApiResponse

**Description**: Sets the specified profile as active by updating its `is_default` flag (for legacy) or active status in structured data. Validates the profile exists before setting.

**Parameters**:
- `profile_name` (str): The name of the profile to activate (1-64 chars, alphanumeric + underscores/dashes).

**Returns**: [`ApiResponse`](src/pk_py_lib/core/api/response.py)
  - `success`: `True` if set successfully, `False` if profile not found or update failed.
  - `data`: `True` on success, `None` on failure.
  - `error`: Details (e.g., "Profile 'invalid_name' does not exist" or DB error).

**Usage Example**:
```python
response = api.set_active("my_custom_profile")
if response.success:
    print("Profile activated successfully")
else:
    print(f"Failed to activate: {response.error}")
```

**Migration Notes**: Update UI actions (e.g., profile selection in [`src/pk_py_lib/gui/settings_manager/controller.py`](src/pk_py_lib/gui/settings_manager/controller.py)) to call this after validation. Handles both legacy and structured profiles transparently.

### validate_profile_name(name: str) → ApiResponse

**Description**: Validates a proposed profile name against rules: 1-64 characters, alphanumeric, underscores, dashes; no spaces or special chars. Useful before create/save operations to provide immediate feedback.

**Parameters**:
- `name` (str): The profile name to validate.

**Returns**: [`ApiResponse`](src/pk_py_lib/core/api/response.py)
  - `success`: `True` if valid, `False` if invalid or error.
  - `data`: `True` if valid, `False` if invalid format.
  - `error`: Validation message (e.g., "Name too long: max 64 chars") or unexpected error.

**Usage Example**:
```python
response = api.validate_profile_name("my_profile_2025")
if response.success and response.data:
    print("Name is valid")
else:
    print(f"Invalid name: {response.error}")
```

**Migration Notes**: Integrate into GUI editors (e.g., [`src/pk_py_lib/gui/settings_manager/validators.py`](src/pk_py_lib/gui/settings_manager/validators.py)) for real-time validation. Prevents DB insertion errors.

## Return Type Changes

Several methods now wrap responses in [`ApiResponse`](src/pk_py_lib/core/api/response.py) for consistency:

- `list_profiles()`: Previously returned `list[dict]` directly; now `ApiResponse` with `data: list[dict]` (profile dicts from `to_dict()`).
- `get_profile(profile_name: str)`: Previously `dict or None`; now `ApiResponse` with `data: dict or None`.

**Migration for Callers Expecting Direct Objects**:
- Always check `response.success` before accessing `data`.
- Handle errors: `if not response.success: handle_error(response.error)`
- Example for `list_profiles`:
  ```python
  # Old
  profiles = api.list_profiles()

  # New
  response = api.list_profiles()
  if response.success:
      profiles = response.data  # list of dicts
  else:
      profiles = []  # fallback
      print(f"Error listing profiles: {response.error}")
  ```
- Similar for `get_profile`: Use `response.data` if `success`.

**Unaffected Methods**:
- `get_setting(key: str)`: Remains direct return (value or default); no wrapping for simple key-value access.

## General Migration Steps

1. **Update Imports**: Ensure `from pk_py_lib.core.api.response import ApiResponse`.
2. **Wrap Calls**: Replace direct calls with response handling (see examples).
3. **Error Handling**: Propagate `response.error` to logs/UI (e.g., via [`src/pk_py_lib/core/logging/logger.py`](src/pk_py_lib/core/logging/logger.py)).
4. **Testing**: Verify in GUI flows (e.g., profile load in main window) and CLI (e.g., `pdm run imgapp` with profile switches).
5. **Fallbacks**: For legacy code, add guards: `if hasattr(response, 'success'): ... else: ...` (though full update recommended).

## Impact on Settings Migration

These API changes integrate with structured profile migration (see [`docs/roo/settings-migration-guide.md`](docs/roo/settings-migration-guide.md)). Active profile handling uses existing `is_default` flag—no schema changes required. New validation prevents migration issues from invalid names.

For full API reference, see inline docstrings in [`unified_api.py`](src/pk_py_lib/api/settings/unified_api.py).
