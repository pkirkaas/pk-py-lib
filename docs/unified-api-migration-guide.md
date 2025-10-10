# Unified Settings API Migration Guide

**Version:** 1.0
**Date:** 2025-10-10
**Phase:** Phase 1 - Preparation Complete

---

## Overview

This guide provides practical examples for migrating from the old dual-system settings APIs to the new unified settings API in pk-py-lib.

### What Changed

The pk-py-lib project has consolidated two overlapping settings systems into a single unified architecture:

**Old Architecture (Deprecated):**
- `ConfigurationManager` - Legacy app & profile settings
- `SettingsProfilesManager` - Modern profile management
- Two parallel database schemas
- Inconsistent data models

**New Architecture (Phase 1):**
- `AppSettings` - Global application configuration
- `SettingsProfile` - Named profile configurations
- `UnifiedSettingsAPI` - Single consistent API
- Clear separation of concerns

---

## Migration Examples

### 1. Basic Profile Management

#### Old API (Deprecated)
```python
# OLD: Using dual system
from pk_py_lib.core.configuration import ConfigurationManager
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

# Create configuration manager
config_manager = ConfigurationManager()
config_manager.set("cache_size_mb", 1024)

# Create profiles manager
profiles_manager = SettingsProfilesManager()
profile = profiles_manager.create("My Profile", "Description")
profiles_manager.set_active(profile.id)
```

#### New Unified API
```python
# NEW: Single unified system
from pk_py_lib.core.models.settings import AppSettings, SettingsProfile
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

# Create application settings
app_settings = AppSettings(
    cache_size_mb=1024,
    gui_theme='dark',
    max_workers=8
)

# Create profile
profile = SettingsProfile(
    name="My Profile",
    description="Description",
    hash_algorithm="phash",
    similarity_threshold=0.90
)

# Use unified API
api = UnifiedSettingsAPI()
result = api.create_profile(
    name=profile.name,
    description=profile.description,
    json_data=profile.to_dict()
)
```

### 2. Profile CRUD Operations

#### Old API (Deprecated)
```python
# OLD: Multiple managers, inconsistent patterns
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

manager = SettingsProfilesManager()

# List profiles
profiles = manager.list()
for profile in profiles:
    print(f"{profile.name}: {profile.description}")

# Get specific profile
profile = manager.get("profile-id")

# Update profile
manager.update("profile-id", name="New Name", description="New Description")

# Delete profile
manager.delete("profile-id")
```

#### New Unified API
```python
# NEW: Consistent API patterns
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# List profiles
result = api.list_profiles()
if result.success:
    for profile in result.data:
        print(f"{profile['name']}: {profile['description']}")

# Get specific profile
result = api.get_profile("profile-id")
if result.success:
    profile = result.data

# Update profile
result = api.update_profile(
    "profile-id",
    name="New Name",
    description="New Description"
)

# Delete profile
result = api.delete_profile("profile-id")
```

### 3. Active Profile Management

#### Old API (Deprecated)
```python
# OLD: Inconsistent active profile handling
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

manager = SettingsProfilesManager()

# Get active profile
active = manager.get_active()

# Set active profile
manager.set_active("profile-id")
```

#### New Unified API
```python
# NEW: Consistent active profile patterns
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Get active profile
result = api.get_active_profile()
if result.success and result.data:
    active_profile = result.data
    print(f"Active: {active_profile['name']}")

# Set active profile
result = api.set_active_profile("profile-id")
if result.success:
    print("Profile activated successfully")
```

### 4. Profile Validation

#### Old API (Deprecated)
```python
# OLD: Inconsistent validation patterns
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

manager = SettingsProfilesManager()

# Validate profile name
is_valid = manager.validate_name("My Profile")

# Validate keys
keys = ["hash_algorithm", "similarity_threshold"]
is_valid = manager.validate_keys(keys)
```

#### New Unified API
```python
# NEW: Consistent validation with ApiResponse
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Validate profile name
result = api.validate_profile_name("My Profile")
if result.success:
    print(f"Name is valid: {result.data}")

# Validate keys
keys = ["hash_algorithm", "similarity_threshold"]
result = api.validate_keys(keys)
if result.success:
    print(f"Keys are valid: {result.data}")
```

### 5. Key-Value Operations

#### Old API (Deprecated)
```python
# OLD: Direct manager access, inconsistent patterns
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

manager = SettingsProfilesManager()

# Get values
values = manager.get_values("profile-id")
values = manager.get_values("profile-id", keys=["hash_algorithm"])

# Set values
manager.set_values("profile-id", {"hash_algorithm": "phash", "threshold": 0.90})

# Remove values
manager.remove_values("profile-id", ["old_key"])
```

#### New Unified API
```python
# NEW: Consistent ApiResponse patterns
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Get values
result = api.get_profile_values("profile-id")
if result.success:
    values = result.data

result = api.get_profile_values("profile-id", keys=["hash_algorithm"])
if result.success:
    values = result.data

# Set values
result = api.set_profile_values("profile-id", {
    "hash_algorithm": "phash",
    "similarity_threshold": 0.90
})
if result.success:
    print("Values updated successfully")

# Remove values
result = api.remove_profile_values("profile-id", ["old_key"])
if result.success:
    print("Values removed successfully")
```

### 6. Import/Export Operations

#### Old API (Deprecated)
```python
# OLD: Manager-specific export/import
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

manager = SettingsProfilesManager()

# Export profile
profile_data = manager.export_profile("profile-id")

# Import profile
manager.import_profile(profile_data, strategy="rename")
```

#### New Unified API
```python
# NEW: Consistent ApiResponse patterns
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Export profile
result = api.export_profile("profile-id")
if result.success:
    profile_data = result.data

# Import profile
result = api.import_profile(profile_data, strategy="rename")
if result.success:
    new_profile = result.data
    print(f"Imported profile: {new_profile['name']}")
```

### 7. Bootstrap and Initialization

#### Old API (Deprecated)
```python
# OLD: Manual initialization, inconsistent patterns
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

# Ensure default profile exists
manager = SettingsProfilesManager()
manager.ensure_default_profile()
```

#### New Unified API
```python
# NEW: Consistent initialization patterns
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

# Ensure default profile exists
api = UnifiedSettingsAPI()
result = api.ensure_default_profile()
if result.success:
    print("Default profile ensured")
```

---

## Migration Checklist

### ✅ Phase 1 Ready (Current)
- [x] New data models available (`AppSettings`, `SettingsProfile`)
- [x] Unified API available (`UnifiedSettingsAPI`)
- [x] Migration framework in place
- [x] Comprehensive test coverage
- [x] 100% backward compatibility maintained

### ⏳ Phase 2 Planned
- [ ] Database schema migration
- [ ] Data migration from old to new schema
- [ ] Migration validation and rollback

### ⏳ Phase 3 Planned
- [ ] Update all consumers to new APIs
- [ ] Deprecation warnings for old APIs
- [ ] Migration guide updates

### ⏳ Phase 4 Planned
- [ ] Remove deprecated code
- [ ] Final documentation updates

---

## Best Practices

### 1. Gradual Migration
```python
# Start with new models alongside old ones
from pk_py_lib.core.models.settings import AppSettings, SettingsProfile
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

# Use new models for new features
new_profile = SettingsProfile(
    name="New Feature Profile",
    hash_algorithm="whash",
    similarity_threshold=0.88
)

api = UnifiedSettingsAPI()
result = api.create_profile(
    name=new_profile.name,
    json_data=new_profile.to_dict()
)
```

### 2. Consistent Error Handling
```python
# Always check ApiResponse pattern
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Create profile with error handling
result = api.create_profile("My Profile", "Description")
if not result.success:
    print(f"Error: {result.error_message}")
    # Handle specific error codes
    if result.error_code == "DUPLICATE_NAME":
        print("Profile name already exists")
else:
    print(f"Created profile: {result.data['name']}")
```

### 3. Data Model Consistency
```python
# Use to_dict()/from_dict() for serialization
from pk_py_lib.core.models.settings import SettingsProfile

# Create profile
profile = SettingsProfile(
    name="My Profile",
    hash_algorithm="phash",
    similarity_threshold=0.90
)

# Serialize for storage
profile_data = profile.to_dict()

# Later, deserialize
restored_profile = SettingsProfile.from_dict(profile_data)

# Or use with API
api = UnifiedSettingsAPI()
result = api.create_profile(
    name=profile.name,
    json_data=profile.to_dict()
)
```

---

## Common Patterns

### Profile Creation with Defaults
```python
from pk_py_lib.core.models.settings import SettingsProfile, DEFAULT_PROFILES
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

# Use system defaults
default_profile = DEFAULT_PROFILES[0]  # "Exact Duplicates"

# Customize for specific use case
custom_profile = SettingsProfile(
    name="High Quality Photos",
    description="For professional photography",
    hash_algorithm="phash",
    similarity_threshold=0.95,
    quality_threshold=0.7  # Only high-quality images
)

# Create via API
api = UnifiedSettingsAPI()
result = api.create_profile(
    name=custom_profile.name,
    description=custom_profile.description,
    json_data=custom_profile.to_dict()
)
```

### Profile Cloning
```python
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Clone existing profile
result = api.duplicate_profile(
    source_profile_id="source-id",
    new_name="Copy of Source",
    description="Modified version",
    make_active=False
)

if result.success:
    cloned_profile = result.data
    print(f"Cloned profile: {cloned_profile['name']}")
```

### Batch Profile Operations
```python
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI

api = UnifiedSettingsAPI()

# Get all profiles
result = api.list_profiles()
if result.success:
    profiles = result.data

    # Update each profile
    for profile in profiles:
        api.update_profile(
            profile['id'],
            description=f"Updated: {profile['description']}"
        )

    print(f"Updated {len(profiles)} profiles")
```

---

## Troubleshooting

### Common Issues

**1. Import Errors**
```python
# ❌ Wrong import
from pk_py_lib.core.settings_profiles import SettingsProfilesManager

# ✅ Correct import
from pk_py_lib.api.settings.unified_api import UnifiedSettingsAPI
```

**2. Data Type Issues**
```python
# ❌ Wrong data types
result = api.create_profile(
    name=123,  # Should be string
    json_data="not a dict"  # Should be dict
)

# ✅ Correct usage
result = api.create_profile(
    name="My Profile",  # String
    json_data={"hash_algorithm": "phash"}  # Dict
)
```

**3. Error Handling**
```python
# ❌ Ignoring errors
result = api.create_profile("Name")
# Assume success - dangerous!

# ✅ Proper error handling
result = api.create_profile("Name")
if not result.success:
    print(f"Error {result.error_code}: {result.error_message}")
    # Handle appropriately
else:
    print(f"Success: {result.data}")
```

---

## Next Steps

### Immediate (Phase 1)
1. Start using new models for new features
2. Use unified API for new profile operations
3. Follow the patterns in this guide
4. Run tests to ensure compatibility

### Future Phases
1. **Phase 2**: Database migration (when ready)
2. **Phase 3**: Update existing code to new APIs
3. **Phase 4**: Remove deprecated code

---

## Related Documentation

- [Settings Migration Guide](docs/roo/settings-migration-guide.md) - Complete migration plan
- [Settings Consolidation Plan](docs/roo/settings-consolidation-plan.md) - Detailed implementation plan
- [Architecture Plan](architecture-plan.md) - Overall project architecture
- [API Documentation](docs/roo/img-app-api-specifications.md) - API specifications

---

## Support

For questions or issues:
1. Check this migration guide first
2. Review the test suite for examples
3. Consult the architecture documentation
4. Check existing issues and discussions

**Remember**: Phase 1 is preparation only. All existing code continues to work without changes!
