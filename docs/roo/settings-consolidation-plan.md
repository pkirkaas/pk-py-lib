
# Settings/Configuration Architecture Consolidation Plan

**Document Version:** 1.0
**Date:** 2025-10-10
**Status:** Analysis Complete - Pending Approval

---

## Executive Summary

This document provides a detailed analysis and consolidation plan for the fragmented settings/configuration architecture in pk-py-lib, addressing issues identified in [`docs/roo/refactoring-plan.md`](docs/roo/refactoring-plan.md:66-103) Phase 2.

**Critical Findings:**
- **Dual Parallel Systems**: [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98) and [`SettingsProfilesManager`](src/pk_py_lib/core/settings/manager.py:1) implement overlapping functionality with different data models
- **Schema Fragmentation**: Two different database schemas for profile storage (`profiles`+`settings` vs `settings_profiles`+`settings_profile_items`)
- **Model Confusion**: Multiple Profile models ([`Profile`](src/pk_py_lib/core/configuration.py:64), [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78)) with different capabilities
- **Unclear Migration Path**: Legacy system still in use while new system is being adopted
- **API Layer Duplication**: Two API adapters ([`SettingsAPI`](src/pk_py_lib/api/settings_api.py:25), [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:88)) with overlapping responsibilities

**Recommendation:** Consolidate to single unified system based on [`UnifiedSettingsAPI`](src/pk_py_lib/api/settings/unified_api.py:1) with clear deprecation path for legacy [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98).

**Estimated Effort:** 38-48 hours over 4 weeks

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Problems Identified](#2-problems-identified)
3. [Proposed Consolidated Architecture](#3-proposed-consolidated-architecture)
4. [Implementation Roadmap](#4-implementation-roadmap)
5. [Migration Strategy](#5-migration-strategy)
6. [Risk Assessment](#6-risk-assessment)
7. [Success Metrics](#7-success-metrics)
8. [Conclusion](#8-conclusion)

---

## 1. Current State Analysis

### 1.1 Module Inventory

#### Core Configuration Modules

##### [`src/pk_py_lib/core/configuration.py`](src/pk_py_lib/core/configuration.py:1) (667 lines)

**Purpose:** Legacy configuration management system

**Key Classes:**
- [`AppSettings`](src/pk_py_lib/core/configuration.py:34) (dataclass) - Global application settings
- [`Profile`](src/pk_py_lib/core/configuration.py:64) (dataclass) - Named workflow configuration
- [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98) - Unified interface for app and profile settings

**Responsibilities:**
- Manage single-row `app_settings` table (global settings)
- Manage `profiles` table (profile metadata)
- Manage `settings` table (key-value storage per profile)
- Profile CRUD operations (name-based)
- Setting get/set with scope auto-detection (app vs profile)
- Profile switching (changes current active profile)

**Data Model:**
```
profiles (id INT, name TEXT UNIQUE, is_default BOOL, created_at, modified_at)
settings (profile_id INT FK, category TEXT, key TEXT, value TEXT, type TEXT)
app_settings (single row with typed columns)
```

**Storage Format:** Key-value pairs in `settings` table with category grouping (algorithm_defaults, file_handling, history)

**Dependencies:**
- Requires [`DatabaseManager`](src/pk_py_lib/core/database.py:1)
- No dependency on settings_profiles or settings_schema

**Used By:**
- [`src/pk_py_lib/api/settings_api.py`](src/pk_py_lib/api/settings_api.py:25) (primary API adapter)
- [`img_app/img_app/app.py`](img_app/img_app/app.py:36) (app initialization)
- [`src/pk_py_lib/core/logging/outputs/file.py`](src/pk_py_lib/core/logging/outputs/file.py:17) (logging configuration)
- `test_logging_lineendings.py` (tests)
- [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py:797) (cache dialog)

---

##### [`src/pk_py_lib/core/settings_profiles.py`](src/pk_py_lib/core/settings_profiles.py:1) (1341 lines)

**Purpose:** Modern settings profiles system with JSON schema support

**Key Classes:**
- [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78) (dataclass) - Profile with legacy OR JSON format support
- [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146) - Profile CRUD and active management

**Responsibilities:**
- Manage `settings_profiles` table (UUID-based, with optional `json_data` column)
- Manage `settings_profile_items` table (legacy key-value storage)
- Profile CRUD operations (ID-based, UUID primary keys)
- Active profile tracking via `meta` table key `'pk.settings_profiles'`
- Support both legacy key-value format AND new JSON schema format
- Schema validation (delegates to [`settings_schema.py`](src/pk_py_lib/core/settings_schema.py:1))
- Import/export with conflict resolution strategies
- Migration from legacy to JSON format
- Name uniqueness enforcement (case-insensitive)

**Data Model:**
```
settings_profiles (id TEXT UUID PK, name TEXT UNIQUE COLLATE NOCASE,
                  description TEXT, is_active INT, created_at, updated_at,
                  json_data TEXT)
settings_profile_items (id TEXT UUID, profile_id TEXT FK, key TEXT,
                       value TEXT JSON, created_at, updated_at)
meta (key='pk.settings_profiles', value JSON: {active_profile_id, schema_version})
```

**Storage Formats:**
1. **Legacy:** Key-value pairs in `settings_profile_items` table
2. **JSON:** Structured data in `json_data` column per [`SETTINGS_PROFILE_SCHEMA`](src/pk_py_lib/core/settings_schema.py:28)

**Dependencies:**
- Requires [`DatabaseManager`](src/pk_py_lib/core/database.py:1)
- Requires [`settings_schema`](src/pk_py_lib/core/settings_schema.py:1) for validation
- Adds `json_data` column dynamically if missing

**Used By:**
- [`src/pk_py_lib/api/settings_profiles.py`](src/pk_py_lib/api/settings_profiles.py:88) (primary API adapter)
- [`src/pk_py_lib/gui/settings_manager/`](src/pk_py_lib/gui/settings_manager/) (all GUI components)
- [`src/pk_py_lib/core/image/quality/provider.py`](src/pk_py_lib/core/image/quality/provider.py:196) (quality settings)
- [`img_app/img_app/app.py`](img_app/img_app/app.py:31) (app initialization)

**Key Features:**
- Backward compatible with legacy profiles
- Automatic migration to JSON format
- Validation for save vs run operations
- Unique name suggestion
- Duplicate profile with new name
- Invariant maintenance (exactly one active profile)

---

##### [`src/pk_py_lib/core/settings_schema.py`](src/pk_py_lib/core/settings_schema.py:1) (664 lines)

**Purpose:** JSON Schema definition and validation for structured profiles

**Key Components:**
- [`SETTINGS_PROFILE_SCHEMA`](src/pk_py_lib/core/settings_schema.py:28) - Complete JSON Schema for SettingsProfileOptionA
- [`validate_settings_schema()`](src/pk_py_lib/core/settings_schema.py:292) - Validate profile against schema
- [`normalize_settings()`](src/pk_py_lib/core/settings_schema.py:393) - Apply defaults and ensure consistency
- [`create_default_profile()`](src/pk_py_lib/core/settings_schema.py:516) - Generate default profile
- [`is_valid_for_save()`](src/pk_py_lib/core/settings_schema.py:587) - Validation including path checks
- [`is_valid_for_run()`](src/pk_py_lib/core/settings_schema.py:639) - Stricter validation for execution

**Responsibilities:**
- Define canonical schema structure (pools, mode, criteria, scope, output)
- Validate mode-algorithm compatibility (duplicates=blake3/xxh3, similarity=phash/whash)
- Validate scope-direction compatibility (single_pool vs two_pool)
- Apply Balanced Defaults (recursion, symlinks, type_filters, etc.)
- Normalize degree_ui values
- Validate path existence
- Custom validation beyond JSON schema

**Schema Features:**
- Supports duplicates mode (blake3/xxh3) and similarity mode (phash/whash with degree)
- Single-pool and two-pool configurations
- Pool-specific settings (paths, recurse, filters, constraints)
- Image quality evaluator selection
- Flat cache toggle

**Dependencies:**
- Uses `jsonschema` library for validation
- No dependencies on other pk_py_lib modules
- Pure schema/validation logic

**Used By:**
- [`settings_profiles.py`](src/pk_py_lib/core/settings_profiles.py:35) (validation during create/update)
- [`src/pk_py_lib/gui/settings_manager/structured_editor.py`](src/pk_py_lib/gui/settings_manager/structured_editor.py:61) (GUI validation)
- [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py:1570) (default profile creation)
- [`img_app/img_app/widgets/duplicate_manager.py`](img_app/img_app/widgets/duplicate_manager.py:268) (profile validation)

---

#### API Modules

##### [`src/pk_py_lib/api/settings_api.py`](src/pk_py_lib/api/settings_api.py:1) (166 lines)

**Purpose:** Lightweight API adapter over [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98)

**Key Class:**
- [`SettingsAPI`](src/pk_py_lib/api/settings_api.py:25) - Thin wrapper providing API-friendly interface

**Responsibilities:**
- Expose [`AppSettings`](src/pk_py_lib/core/configuration.py:34) operations (get, update)
- Expose [`Profile`](src/pk_py_lib/core/configuration.py:64) operations (get, list, switch by name)
- Generic get/set with scope auto-detection
- Export/import settings to JSON files
- Delegates all logic to [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98)

**API Surface:**
- `get_app_settings()` → [`AppSettings`](src/pk_py_lib/core/configuration.py:34)
- `update_app_settings(updates)` → [`AppSettings`](src/pk_py_lib/core/configuration.py:34)
- `get_profile(name=None)` → [`Profile`](src/pk_py_lib/core/configuration.py:64)
- `list_profiles()` → List[Dict]
- `get_setting(key, scope, profile)` → Any
- `set_setting(key, value, scope, profile)` → bool
- `export_settings(path, scope, profile)` → bool
- `import_settings(path, scope)` → bool

**Returns:** Raw Python objects (dataclasses, dicts, bools)

**Dependencies:**
- Requires [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98)
- Creates [`DatabaseManager`](src/pk_py_lib/core/database.py:1) if not provided

**Used By:**
- Limited usage in codebase (being phased out)
- Legacy compatibility layer

---

##### [`src/pk_py_lib/api/settings_profiles.py`](src/pk_py_lib/api/settings_profiles.py:1) (544 lines)

**Purpose:** Modern API adapter over [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146)

**Key Class:**
- [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:88) - Comprehensive API with ID-centric operations

**Responsibilities:**
- Bootstrap: `ensure_default_profile()`
- Profile CRUD: `list_profiles()`, `get_profile(id)`, `create()`, `update()`, `delete()`
- Duplication: `duplicate(source_id, new_name)`
- Active management: `get_active()`, `set_active(id)`
- Validation: `validate_name()`, `validate_keys()`, `validate_profile_for_save()`, `validate_profile_for_run()`
- Key-value ops: `get_values()`, `set_values()`, `remove_values()` (for legacy profiles)
- Import/export: `export_profile()`, `import_profile()`
- JSON schema: `migrate_to_json_format()`, `get_json_schema()`, `create_default_json_profile()`, `suggest_unique_name()`
- Maps exceptions to [`ErrorCodes`](src/pk_py_lib/api/__init__.py:1)

**API Surface:** ID-centric (UUID strings), returns [`ApiResponse[T]`](src/pk_py_lib/api/__init__.py:1) wrapper

**Returns:** [`ApiResponse`](src/pk_py_lib/api/__init__.py:1) with success/fail, data, error message, error code

**Dependencies:**
- Requires [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146)
- Uses [`settings_schema`](src/pk_py_lib/core/settings_schema.py:1) functions
- Returns [`ApiResponse`](src/pk_py_lib/api/__init__.py:1) objects

**Used By:**
- [`src/pk_py_lib/gui/settings_manager/`](src/pk_py_lib/gui/settings_manager/) (all GUI components)
- [`img_app/img_app/app.py`](img_app/img_app/app.py:31) (app initialization)
- All new code prefers this API

---

### 1.2 Dependency Graph

```
┌─────────────────────────────────────────────────────────────┐
│                     External Consumers                       │
├──────────────────────┬──────────────────────────────────────┤
│  App Initialization  │  GUI Components   │  Logging System  │
│  (img_app/app.py)   │  (settings_mgr)   │  (file.py)       │
└──────────┬───────────┴──────────┬────────┴──────────┬───────┘
           │                      │                    │
           │                      │                    │
┌──────────▼────────┐  ┌──────────▼─────────┐  ┌─────▼────────┐
│  SettingsAPI      │  │ SettingsProfilesAPI│  │ Config Mgr   │
│  (Legacy)         │  │ (Modern)           │  │ (Direct)     │
│  settings_api.py  │  │ settings_profiles  │  └──────────────┘
└─────────┬─────────┘  │ .py (API)          │
          │            └──────────┬──────────┘
          │                       │
   ┌──────▼──────────┐    ┌──────▼────────────────┐
   │ Configuration   │    │ SettingsProfiles      │
   │ Manager         │    │ Manager               │
   │ (Legacy Core)   │    │ (Modern Core)         │
   │ configuration   │    │ settings_profiles.py  │
   │ .py             │    └──────┬────────────────┘
   └────────┬────────┘           │
            │                    │
            │            ┌───────▼──────────┐
            │            │ Settings Schema  │
            │            │ (Validation)     │
            │            │ settings_schema  │
            │            │ .py              │
            │            └──────────────────┘
            │
   ┌────────▼────────────────────────────┐
   │      Database Manager               │
   │      (Shared Foundation)            │
   │      database.py                    │
   └─────────────────────────────────────┘

Database Tables:
  Legacy System:               Modern System:
  - profiles                   - settings_profiles
  - settings                   - settings_profile_items
  - app_settings              - meta (active tracking)
```

---

## 2. Problems Identified

### 2.1 Duplicate Functionality

#### Profile Management Operations

Both systems implement the same core operations:

| Operation | ConfigurationManager | SettingsProfilesManager |
|-----------|---------------------|------------------------|
| Create profile | [`create_profile(name, copy_from)`](src/pk_py_lib/core/configuration.py:452) | [`create_profile(name, desc, make_active, json_data)`](src/pk_py_lib/core/settings_profiles.py:506) |
| Delete profile | [`delete_profile(name)`](src/pk_py_lib/core/configuration.py:496) | [`delete_profile(profile_id)`](src/pk_py_lib/core/settings_profiles.py:659) |
| List profiles | [`list_profiles()`](src/pk_py_lib/core/configuration.py:400) | [`list_profiles()`](src/pk_py_lib/core/settings_profiles.py:378) |
| Switch/Set active | [`switch_profile(name)`](src/pk_py_lib/core/configuration.py:427) | [`set_active_profile(id)`](src/pk_py_lib/core/settings_profiles.py:476) |
| Get profile | [`get_current_profile()`](src/pk_py_lib/core/configuration.py:325) | [`get_profile(id)`](src/pk_py_lib/core/settings_profiles.py:424), [`get_active_profile()`](src/pk_py_lib/core/settings_profiles.py:461) |
| Duplicate | [`create_profile(name, copy_from)`](src/pk_py_lib/core/configuration.py:452) | [`duplicate_profile(src_id, new_name)`](src/pk_py_lib/core/settings_profiles.py:696) |

**Key Differences:**
- **Identification**: ConfigurationManager is name-based; SettingsProfilesManager is ID-based (UUID)
- **Active Tracking**: ConfigurationManager uses in-memory `_current_profile_id`; SettingsProfilesManager uses `meta` table
- **Data Models**: Different dataclasses ([`Profile`](src/pk_py_lib/core/configuration.py:64) vs [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78))

#### Settings Storage

Both systems store key-value settings per profile:

| Aspect | ConfigurationManager | SettingsProfilesManager |
|--------|---------------------|------------------------|
| Table | `settings` | `settings_profile_items` |
| Key structure | `category.key` (e.g., "file_handling.auto_scan") | Flat keys (e.g., "auto_scan") |
| Value storage | String with type column | JSON string |
| Categories | algorithm_defaults, file_handling, history | Free-form |
| Get operation | [`get_profile_setting(key)`](src/pk_py_lib/core/configuration.py:530) | [`get_values(profile_id, keys)`](src/pk_py_lib/core/settings_profiles.py:744) |
| Set operation | [`set_profile_setting(key, value)`](src/pk_py_lib/core/configuration.py:561) | [`set_values(profile_id, dict)`](src/pk_py_lib/core/settings_profiles.py:799) |

**Note:** SettingsProfilesManager supports both legacy key-value AND new JSON schema format, while ConfigurationManager only supports key-value.

---

### 2.2 Overlapping Responsibilities

#### Unclear Boundaries

**ConfigurationManager** manages:
- ✓ AppSettings (global settings) - **Unique functionality**
- ✓ Profile metadata (name, is_default)
- ✓ Profile settings (key-value per profile)
- ✓ Current active profile (in-memory)
- ✓ Profile CRUD operations
- ✓ Scope-aware get/set (app vs profile)

**SettingsProfilesManager** manages:
- ✗ No AppSettings equivalent
- ✓ Profile metadata (name, description, is_active)
- ✓ Profile settings (key-value OR JSON per profile)
- ✓ Active profile (in meta table)
- ✓ Profile CRUD operations
- ✓ Validation against JSON schema - **Unique functionality**
- ✓ Migration legacy→JSON - **Unique functionality**
- ✓ Import/export with strategies - **Enhanced functionality**
- ✓ Backward compatibility with legacy - **Unique functionality**

**Overlap:** ~70% of functionality is duplicated (profile CRUD, settings storage, active management)

**Unique to ConfigurationManager:** AppSettings management, scope auto-detection

**Unique to SettingsProfilesManager:** JSON schema support, validation, migration, richer import/export

---

### 2.3 Schema Fragmentation

#### Two Incompatible Database Schemas

**Legacy Schema (ConfigurationManager):**
```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP,
    modified_at TIMESTAMP
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id),
    category TEXT NOT NULL,  -- algorithm_defaults, file_handling, history
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    type TEXT NOT NULL,      -- json, int, float, bool, string
    UNIQUE(profile_id, category, key)
);

CREATE TABLE app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Single row
    theme TEXT, language TEXT, ui_scale REAL,
    max_threads INTEGER, max_memory_mb INTEGER, cache_size_mb INTEGER,
    logging_to_user_dir BOOLEAN, development BOOLEAN,
    window_geometry TEXT, panel_layout TEXT, shortcuts TEXT,
    created_at TIMESTAMP, modified_at TIMESTAMP
);
```

**Modern Schema (SettingsProfilesManager):**
```sql
CREATE TABLE settings_profiles (
    id TEXT PRIMARY KEY,                    -- UUID string
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    json_data TEXT,                        -- Optional: JSON schema data
    UNIQUE INDEX (lower(name))
);

CREATE TABLE settings_profile_items (
    id TEXT PRIMARY KEY,                   -- UUID string
    profile_id TEXT REFERENCES settings_profiles(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,                   -- JSON serialized
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE INDEX (profile_id, lower(key))
);

CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT,                            -- JSON: {active_profile_id, schema_version, ...}
    notes TEXT,
    updated_at TIMESTAMP
);
-- Key 'pk.settings_profiles' stores active profile ID
```

**Incompatibilities:**
1. **Primary Keys**: INTEGER (auto-increment) vs TEXT (UUID)
2. **Active Tracking**: `is_default` boolean flag vs `is_active` + meta table
3. **Settings Structure**: Categorized key-value vs flat key-value + optional JSON
4. **Name Uniqueness**: Simple UNIQUE vs case-insensitive UNIQUE INDEX
5. **Foreign Keys**: Direct reference vs UUID string reference with CASCADE
6. **Timestamps**: TIMESTAMP type vs TEXT ISO8601

**Migration Complexity:** Cannot simply merge or migrate without data transformation

---

### 2.4 Model Confusion

#### Multiple Profile Models

**[`Profile`](src/pk_py_lib/core/configuration.py:64) (configuration.py):**
```python
@dataclass
class Profile:
    id: Optional[int] = None              # Auto-increment integer
    name: str = "Default"
    is_default: bool = False              # Default profile flag
    algorithm_defaults: Dict[str, Any] = field(default_factory=dict)
    file_handling: Dict[str, Any] = field(default_factory=lambda: {...})
    history: Dict[str, Any] = field(default_factory=lambda: {...})
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
```

**[`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78) (settings_profiles.py):**
```python
@dataclass
class SettingsProfile:
    id: str                                # UUID string
    name: str
    description: Optional[str]
    is_active: bool                        # Active profile flag (not default)
    created_at: str                        # ISO8601 string
    updated_at: str                        # ISO8601 string
    json_data: Optional[Dict[str, Any]] = None      # JSON schema format
    legacy_items: Optional[Dict[str, Any]] = None   # Legacy key-value format

    def is_json_format(self) -> bool
    def to_dict(self) -> Dict[str, Any]
```

**Differences:**
- **ID Type**: int vs str (UUID)
- **Timestamps**: datetime objects vs ISO8601 strings
- **Storage**: Predefined dict structure vs flexible json_data/legacy_items
- **Active vs Default**: Different semantics (is_default vs is_active)
- **Description**: Not supported vs supported
- **Format Detection**: No method vs `is_json_format()`

**Impact:** Code using one model cannot easily work with the other; requires manual conversion

---

### 2.5 Naming Confusion

#### Module Name Collisions

**Problem:** Two modules with nearly identical names:

1. **Core:** [`src/pk_py_lib/core/settings_profiles.py`](src/pk_py_lib/core/settings_profiles.py:1)
   - Contains [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146) (core logic)

2. **API:** [`src/pk_py_lib/api/settings_profiles.py`](src/pk_py_lib/api/settings_profiles.py:1)
   - Contains [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:88) (API wrapper)

**Import Confusion:**
```python
# Which one is this importing from?
from pk_py_lib.settings_profiles import ...  # Ambiguous!

# Must be explicit:
from pk_py_lib.core.settings_profiles import SettingsProfilesManager
from pk_py_lib.api.settings_profiles import SettingsProfilesAPI
```

**Recommendation:** Rename to clarify purpose (e.g., `profiles_manager.py` vs `profiles_api.py`)

---

### 2.6 Unclear Migration Path

#### Transition in Progress

**Current State:**
- **Legacy System**: ConfigurationManager with profiles+settings tables - still in use
- **Modern System**: SettingsProfilesManager with settings_profiles+settings_profile_items tables - being adopted
- **No documented migration**: No clear instructions for moving existing code from legacy to modern
- **No deprecation warnings**: Legacy system not marked as deprecated
- **Coexistence**: Both systems run simultaneously, potentially accessing different data

**Evidence of Transition:**
- Main app uses SettingsProfilesAPI: [`img_app/img_app/app.py`](img_app/img_app/app.py:31)
- Logging still uses ConfigurationManager: [`src/pk_py_lib/core/logging/outputs/file.py`](src/pk_py_lib/core/logging/outputs/file.py:17)
- GUI uses SettingsProfilesAPI: [`src/pk_py_lib/gui/settings_manager/`](src/pk_py_lib/gui/settings_manager/)
- Tests use ConfigurationManager: `test_logging_lineendings.py`

**Risks:**
- Settings stored in one system not visible to the other
- Profile created in one system won't appear in the other
- Active profile tracking differs between systems
- Data inconsistency between parallel systems

---

## 3. Proposed Consolidated Architecture

### 3.1 Consolidation Strategy

**Approach:** Consolidate around [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146) as the single source of truth, while preserving AppSettings functionality.

**Rationale:**
1. **Modern Features**: SettingsProfilesManager already supports JSON schema, validation, migration
2. **Better Design**: ID-based (UUID) is more robust than name-based for references
3. **Adoption**: New code already prefers SettingsProfilesManager
4. **Flexibility**: Supports both legacy key-value AND modern JSON format
5. **Rich API**: More comprehensive operations (duplicate, import/export strategies, validation)

**Preserved from ConfigurationManager:**
- [`AppSettings`](src/pk_py_lib/core/configuration.py:34) management (global settings) - **No equivalent in SettingsProfilesManager**
- Scope-aware get/set (convenience methods)

**Key Decision:** Keep AppSettings separate; merge Profile management

---

### 3.2 Target Architecture

#### Proposed Module Structure

```
src/pk_py_lib/core/settings/
├── __init__.py              # Public API exports
├── app_settings.py          # AppSettings management (extracted from configuration.py)
├── profiles_manager.py      # Renamed from settings_profiles.py
├── schema.py                # Renamed from settings_schema.py
└── models.py                # Consolidated data models

src/pk_py_lib/api/settings/
├── __init__.py              # Public API exports
├── app_settings_api.py      # AppSettings API (extracted from settings_api.py)
└── profiles_api.py          # Renamed from settings_profiles.py (API)
```

#### Module Responsibilities

**[`app_settings.py`](src/pk_py_lib/core/settings/app_settings.py) (NEW - extracted)**
- Manage single-row `app_settings` table
- [`AppSettings`](src/pk_py_lib/core/configuration.py:34) dataclass (moved from configuration.py)
- `AppSettingsManager` class (extracted from ConfigurationManager)
- Get/set/update operations for global settings
- **No profile management** (removed overlap)

**[`profiles_manager.py`](src/pk_py_lib/core/settings/profiles_manager.py) (RENAMED)**
- Current [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146) becomes canonical
- Manage `settings_profiles` + `settings_profile_items` tables
- Profile CRUD, active management, import/export, validation
- Support both legacy key-value and JSON schema formats
- Migration helpers
- **Sole authority** for profile operations

**[`schema.py`](src/pk_py_lib/core/settings/schema.py) (RENAMED)**
- Current [`settings_schema.py`](src/pk_py_lib/core/settings_schema.py:1) unchanged
- JSON schema definition, validation, normalization
- No dependencies on other settings modules

**[`models.py`](src/pk_py_lib/core/settings/models.py) (NEW - consolidated)**
- [`AppSettings`](src/pk_py_lib/core/configuration.py:34) dataclass (from configuration.py)
- [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78) dataclass (from settings_profiles.py)
- Remove [`Profile`](src/pk_py_lib/core/configuration.py:64) dataclass (deprecated)
- Shared exception classes
- Shared enums (SettingScope, etc.)

**[`app_settings_api.py`](src/pk_py_lib/api/settings/app_settings_api.py) (NEW - extracted)**
- Thin wrapper over `AppSettingsManager`
- Get/update app settings
- Export/import app settings
- Returns [`ApiResponse`](src/pk_py_lib/api/__init__.py:1)

**[`profiles_api.py`](src/pk_py_lib/api/settings/profiles_api.py) (RENAMED)**
- Current [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:88) unchanged
- Wraps `ProfilesManager` (renamed from SettingsProfilesManager)
- Full profile CRUD, validation, import/export
- Returns [`ApiResponse`](src/pk_py_lib/api/__init__.py:1)

---

### 3.3 Unified Data Model

#### Single Profile Model

Use [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78) as the canonical model:

```python
@dataclass
class SettingsProfile:
    """
    Unified profile model supporting both legacy and JSON formats.

    Attributes:
        id: UUID string (primary key)
        name: Unique profile name (case-insensitive)
        description: Optional description
        is_active: Whether this profile is currently active
        created_at: ISO8601 timestamp string
        updated_at: ISO8601 timestamp string
        json_data: Structured JSON schema data (for modern profiles)
        legacy_items: Key-value items (for legacy profiles)
    """
    id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str
    json_data: Optional[Dict[str, Any]] = None
    legacy_items: Optional[Dict[str, Any]] = None

    def is_json_format(self) -> bool:
        """Check if profile uses JSON schema format."""
        return self.json_data is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        ...
```

**Migration from [`Profile`](src/pk_py_lib/core/configuration.py:64) to [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78):**

```python
def migrate_legacy_profile(old_profile: Profile) -> SettingsProfile:
    """Convert legacy Profile to SettingsProfile."""
    return SettingsProfile(
        id=str(uuid.uuid4()),  # Generate new UUID
        name=old_profile.name,
        description=None,  # Not in legacy model
        is_active=old_profile.is_default,  # Map default→active
        created_at=old_profile.created_at.isoformat() + "Z",
        updated_at=old_profile.modified_at.isoformat() + "Z",
        json_data=None,  # Will be populated during migration
        legacy_items={
            **old_profile.algorithm_defaults,
            **{f"file_handling.{k}": v for k, v in old_profile.file_handling.items()},
            **{f"history.{k}": v for k, v in old_profile.history.items()}
        }
    )
```

---

### 3.4 Database Consolidation

#### Target Schema

**Keep Modern Schema:**
- `settings_profiles` table (UUID-based, with json_data)
- `settings_profile_items` table (legacy support)
- `meta` table (active profile tracking)
- `app_settings` table (unchanged - global settings)

**Deprecate Legacy Schema:**
- `profiles` table → Migrate data to `settings_profiles`
- `settings` table → Migrate data to `settings_profile_items` or `json_data`

**Migration SQL:**

```sql
-- Step 1: Migrate profiles table → settings_profiles
INSERT INTO settings_profiles (id, name, description, is_active, created_at, updated_at)
SELECT
    lower(hex(randomblob(16))),  -- Generate UUID
    name,
    NULL as description,
    is_default as is_active,
    created_at,
    modified_at as updated_at
FROM profiles;

-- Step 2: Migrate settings table → settings_profile_items
-- (Requires mapping old profile.id to new settings_profiles.id)
INSERT INTO settings_profile_items (id, profile_id, key, value, created_at, updated_at)
SELECT
    lower(hex(randomblob(16))),
    sp.id,  -- New UUID from settings_profiles
    s.category || '.' || s.key as key,  -- Flatten category.key
    s.value,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM settings s
JOIN profiles p ON s.profile_id = p.id
JOIN settings_profiles sp ON sp.name = p.name;

-- Step 3: Set active profile in meta
INSERT OR REPLACE INTO meta (key, value, notes, updated_at)
SELECT
    'pk.settings_profiles',
    json_object('active_profile_id', sp.id, 'schema_version', 1),
    'Settings profiles manager state',
    CURRENT_TIMESTAMP
FROM settings_profiles sp
WHERE sp.is_active = 1
LIMIT 1;

-- Step 4: Drop legacy tables (after verification)
-- DROP TABLE settings;
-- DROP TABLE profiles;
```

---

### 3.5 API Consolidation

#### Unified API Layer

**Two Focused APIs:**

1. **[`AppSettingsAPI`](src/pk_py_lib/api/settings/app_settings_api.py)** - Global settings only
   ```python
   class AppSettingsAPI:
       def get_app_settings() -> ApiResponse[AppSettings]
       def update_app_settings(updates: Dict) -> ApiResponse[AppSettings]
       def export_app_settings(path: Path) -> ApiResponse[bool]
       def import_app_settings(path: Path) -> ApiResponse[bool]
   ```

2. **[`ProfilesAPI`](src/pk_py_lib/api/settings/profiles_api.py)** - Profile management only
   ```python
   class ProfilesAPI:  # Renamed from SettingsProfilesAPI
       # Bootstrap
       def ensure_default_profile() -> ApiResponse[Dict]

       # CRUD
       def list_profiles() -> ApiResponse[List[Dict]]
       def get_profile(profile_id: str) -> ApiResponse[Dict]
       def create(name, desc, make_active, json_data) -> ApiResponse[Dict]
       def update(profile_id, name, desc, json_data) -> ApiResponse[Dict]
       def delete(profile_id: str) -> ApiResponse[bool]
       def duplicate(src_id, new_name) -> ApiResponse[Dict]

       # Active management
       def get_active() -> ApiResponse[Optional[Dict]]
       def set_active(profile_id: str) -> ApiResponse[Dict]

       # Validation
       def validate_name(name: str) -> ApiResponse[bool]
       def validate_profile_for_save(profile_id) -> ApiResponse[Dict]
       def validate_profile_for_run(profile_id) -> ApiResponse[Dict]

       # Key-value operations (legacy profiles)
       def get_values(profile_id, keys) -> ApiResponse[Dict]
       def set_values(profile_id, values) -> ApiResponse[Dict]
       def remove_values(profile_id, keys) -> ApiResponse[Dict]

       # Import/export
       def export_profile(profile_id) -> ApiResponse[Dict]
       def import_profile(payload, strategy) -> ApiResponse[Dict]

       # JSON schema
       def migrate_to_json_format(profile_id) -> ApiResponse[Dict]
       def get_json_schema() -> ApiResponse[Dict]
       def create_default_json_profile(name) -> ApiResponse[Dict]
       def suggest_unique_name(base_name) -> ApiResponse[str]
   ```

**Remove:**
- [`SettingsAPI`](src/pk_py_lib/api/settings_api.py:25) - Split into AppSettingsAPI + ProfilesAPI
- Generic `get_setting()` / `set_setting()` with scope auto-detection - Too implicit; use explicit APIs

**Convenience Layer (Optional):**

```python
# src/pk_py_lib/api/settings/__init__.py
class UnifiedSettingsAPI:
    """
    Convenience wrapper combining AppSettingsAPI and ProfilesAPI.

    For code that needs both app and profile settings.
    """
    def __init__(self):
        self.app = AppSettingsAPI()
        self.profiles = ProfilesAPI()

    # Delegates to appropriate API
```

---

## 4. Implementation Roadmap

### 4.1 Phase 1: Preparation (Week 1) - 8-10 hours

**Goal:** Set up infrastructure without breaking existing code

#### Step 1.1: Create New Module Structure (2h)
- Create `src/pk_py_lib/core/settings/` directory
- Create `src/pk_py_lib/api/settings/` directory
- Add `__init__.py` files with minimal exports
- Add deprecation notices to old module locations

**Deliverables:**
- Empty module structure
- Import compatibility maintained

#### Step 1.2: Extract and Consolidate Models (3h)
- Create [`models.py`](src/pk_py_lib/core/settings/models.py) in new structure
- Move [`AppSettings`](src/pk_py_lib/core/configuration.py:34) from configuration.py
- Move [`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78) from settings_profiles.py
- Move shared exception classes
- Add conversion utilities (`Profile` → `SettingsProfile`)
- Update imports in existing files to use new models

**Deliverables:**
- [`src/pk_py_lib/core/settings/models.py`](src/pk_py_lib/core/settings/models.py)
- All existing imports still work (via re-exports)

#### Step 1.3: Write Comprehensive Tests (3-4h)
- Create test suite for migration utilities
- Create test suite for unified APIs
- Add integration tests for database migration
- Document test coverage baseline

**Deliverables:**
- `tests/test_settings_migration.py`
- `tests/test_settings_api_unified.py`
- >80% coverage for new code

#### Step 1.4: Create Migration Documentation (1h)
- Document migration path from legacy to modern
- Create code examples for common patterns
- Document breaking changes and workarounds

**Deliverables:**
- [`docs/roo/settings-migration-guide.md`](docs/roo/settings-migration-guide.md)

---

### 4.2 Phase 2: Core Refactoring (Week 2) - 12-16 hours

**Goal:** Consolidate core logic without breaking API contracts

#### Step 2.1: Rename and Move Core Modules (2h)
- Rename [`settings_profiles.py`](src/pk_py_lib/core/settings_profiles.py:1) → [`profiles_manager.py`](src/pk_py_lib/core/settings/profiles_manager.py)
- Rename [`settings_schema.py`](src/pk_py_lib/core/settings_schema.py:1) → [`schema.py`](src/pk_py_lib/core/settings/schema.py)
- Move both to `core/settings/` directory
- Update internal imports
- Add re-exports in old locations with deprecation warnings

**Deliverables:**
- New module locations
- Backward compatibility maintained

#### Step 2.2: Extract AppSettingsManager (4-5h)
- Create [`app_settings.py`](src/pk_py_lib/core/settings/app_settings.py)
- Extract AppSettings-related methods from [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98)
- Create `AppSettingsManager` class
- Remove profile-related code from ConfigurationManager
- Update [`SettingsAPI`](src/pk_py_lib/api/settings_api.py:25) to use both managers temporarily

**Deliverables:**
- [`src/pk_py_lib/core/settings/app_settings.py`](src/pk_py_lib/core/settings/app_settings.py)
- [`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98) marked as deprecated
- Tests passing

#### Step 2.3: Database Migration Script (4-6h)
- Implement data migration from profiles+settings → settings_profiles+settings_profile_items
- Add rollback capability
- Add data validation checks
- Test on copy of production database

**Deliverables:**
- [`src/pk_py_lib/core/settings/migration.py`](src/pk_py_lib/core/settings/migration.py)
- `migrate_legacy_to_modern()` function
- Rollback script
- Migration test suite

#### Step 2.4: Run Migration on Development Database (1-2h)
- Backup existing database
- Run migration script
- Verify data integrity
- Test both legacy and modern code paths
- Document any issues

**Deliverables:**
- Migrated development database
- Migration validation report

#### Step 2.5: Update ProfilesManager (1-2h)
- Rename class from `SettingsProfilesManager` → `ProfilesManager`
- Update docstrings and comments
- Remove references to "Settings" in class name (redundant)
- Keep all functionality intact

**Deliverables:**
- Renamed `ProfilesManager` class
- Updated documentation

---

### 4.3 Phase 3: API Refactoring (Week 3) - 10-12 hours

**Goal:** Create clean, focused API layer

#### Step 3.1: Create New API Modules (4-5h)
- Create [`app_settings_api.py`](src/pk_py_lib/api/settings/app_settings_api.py)
  - Extract app settings methods from [`SettingsAPI`](src/pk_py_lib/api/settings_api.py:25)
  - Wrap `AppSettingsManager`
  - Return [`ApiResponse`](src/pk_py_lib/api/__init__.py:1)
- Create [`profiles_api.py`](src/pk_py_lib/api/settings/profiles_api.py)
  - Copy current [`SettingsProfilesAPI`](src/pk_py_lib/api/settings_profiles.py:88)
  - Update to use renamed `ProfilesManager`
  - Keep all functionality

**Deliverables:**
- [`src/pk_py_lib/api/settings/app_settings_api.py`](src/pk_py_lib/api/settings/app_settings_api.py)
- [`src/pk_py_lib/api/settings/profiles_api.py`](src/pk_py_lib/api/settings/profiles_api.py)

#### Step 3.2: Create Unified Convenience API (2h)
- Create [`src/pk_py_lib/api/settings/__init__.py`](src/pk_py_lib/api/settings/__init__.py)
- Implement `UnifiedSettingsAPI` wrapper
- Provide migration helpers for code using old APIs
- Document usage patterns

**Deliverables:**
- Convenience API wrapper
- Usage examples

#### Step 3.3: Update GUI Components (3-4h)
- Update imports in [`src/pk_py_lib/gui/settings_manager/`](src/pk_py_lib/gui/settings_manager/)
- Change from `SettingsProfilesAPI` → `ProfilesAPI`
- Test all GUI workflows
- Fix any broken references

**Deliverables:**
- Updated GUI imports
- Working GUI settings manager

#### Step 3.4: Update Application Code (1-2h)
- Update [`img_app/img_app/app.py`](img_app/img_app/app.py:36)
- Update [`img_app/img_app/main_window.py`](img_app/img_app/main_window.py:797)
- Change ConfigurationManager → AppSettingsManager where appropriate
- Change SettingsProfilesAPI → ProfilesAPI where appropriate

**Deliverables:**
- Updated application code
- Application runs successfully

---

### 4.4 Phase 4: Cleanup and Documentation (Week 4) - 8-10 hours

**Goal:** Remove deprecated code, finalize documentation

#### Step 4.1: Add Deprecation Warnings (2h)
- Add `@deprecated` decorators to old classes
- Add runtime warnings when deprecated code is used
- Update import re-exports with warnings
- Set deprecation timeline (e.g., remove in version 2.0)

**Deliverables:**
- Deprecation warnings in place
- Clear messaging about timeline

#### Step 4.2: Update All Documentation (3-4h)
- Update [`architecture-plan.md`](architecture-plan.md:1)
- Update API specifications
- Update implementation guides
- Create migration guide for external users
- Document all breaking changes

**Deliverables:**
- Updated documentation
- Migration guide for users

#### Step 4.3: Remove Legacy Code (2-3h)
- Remove [`src/pk_py_lib/core/configuration.py`](src/pk_py_lib/core/configuration.py:1) (if fully migrated)
- Remove [`src/pk_py_lib/api/settings_api.py`](src/pk_py_lib/api/settings_api.py:1)
- Remove old table schemas (profiles, settings) after grace period
- Remove deprecated Profile model
- Clean up import re-exports

**Deliverables:**
- Removed legacy code
- Cleaned codebase

#### Step 4.4: Final Testing and Validation (1-2h)
- Run full test suite
- Manual testing of all workflows
- Performance testing
- Documentation review
- Create release notes

**Deliverables:**
- Passing test suite
- Release notes
- Consolidated architecture complete

---

## 5. Migration Strategy

### 5.1 Backward Compatibility Approach

**Principle:** Maintain compatibility during transition; break cleanly at major version

#### Phase A: Deprecation Warnings (Immediate)

```python
# src/pk_py_lib/core/configuration.py
import warnings

class ConfigurationManager:
    """
    DEPRECATED: Use ProfilesManager and AppSettingsManager instead.

    This class will be removed in version 2.0.

    Migration Guide: docs/roo/settings-migration-guide.md
    """

    def __init__(self, db_manager: DatabaseManager):
        warnings.warn(
            "ConfigurationManager is deprecated. "
            "Use ProfilesManager for profile operations and "
            "AppSettingsManager for app settings. "
            "See docs/roo/settings-migration-guide.md",
            DeprecationWarning,
            stacklevel=2
        )
        # Keep implementation for now
```

#### Phase B: Compatibility Layer (During Migration)

```python
# src/pk_py_lib/core/settings/__init__.py

# New imports
from .app_settings import AppSettingsManager, AppSettings
from .profiles_manager import ProfilesManager, SettingsProfile
from .schema import validate_settings_schema, normalize_settings
from .models import SettingsProfile, AppSettings

# Backward compatibility re-exports with deprecation
def _deprecated_import(name: str, new_location: str):
    def wrapper(*args, **kwargs):
        warnings.warn(
            f"{name} imported from old location. "
            f"Use {new_location} instead.",
            DeprecationWarning,
            stacklevel=2
        )
    return wrapper

# Allow old imports to work temporarily
from ..configuration import ConfigurationManager as _LegacyConfigManager
ConfigurationManager = _deprecated_import(
    "ConfigurationManager",
    "AppSettingsManager + ProfilesManager"
)(_LegacyConfigManager)
```

#### Phase C: Hard Break (Version 2.0)

- Remove all deprecated classes and re-exports
- Remove legacy database tables
- Update import paths (breaking change)
- Major version bump signals breaking changes

---

### 5.2 Code Migration Examples

#### Example 1: Basic Profile Operations

**Before (ConfigurationManager):**
```python
from src.pk_py_lib.core.configuration import ConfigurationManager
from src.pk_py_lib.core.database import DatabaseManager

db = DatabaseManager()
config = ConfigurationManager(db)

# Get current profile
profile = config.get_current_profile()
print(f"Active: {profile.name}")

# Switch profiles
config.switch_profile("My Workflow")

# Get setting
auto_scan = config.get_profile_setting("file_handling.auto_scan")
```

**After (ProfilesManager):**
```python
from src.pk_py_lib.core.settings import ProfilesManager
from src.pk_py_lib.core.database import DatabaseManager

db = DatabaseManager()
mgr = ProfilesManager(db)

# Get active profile
profile = mgr.get_active_profile()
print(f"Active: {profile.name}")

# Set active profile (by ID, not name)
profiles = mgr.list_profiles()
my_workflow = next(p for p in profiles if p.name == "My Workflow")
mgr.set_active_profile(my_workflow.id)

# Get setting (for legacy profiles)
values = mgr.get_values(profile.id, ["file_handling.auto_scan"])
auto_scan = values.get("file_handling.auto_scan")

# OR for JSON profiles:
if profile.is_json_format():
    auto_scan = profile.json_data.get("file_handling", {}).get("auto_scan")
```

#### Example 2: App Settings

**Before (ConfigurationManager):**
```python
from src.pk_py_lib.core.configuration import ConfigurationManager

config = ConfigurationManager(db)

# Get app settings
theme = config.get_app_setting("theme")
cache_size = config.get_app_setting("cache_size_mb")

# Update app settings
config.update_app_settings(theme="dark", cache_size_mb=10240)
```

**After (AppSettingsManager):**
```python
from src.pk_py_lib.core.settings import AppSettingsManager

app_mgr = AppSettingsManager(db)

# Get app settings
settings = app_mgr.get_app_settings()
theme = settings.theme
cache_size = settings.cache_size_mb

# Update app settings
app_mgr.update_app_settings(theme="dark", cache_size_mb=10240)
```

#### Example 3: API Usage

**Before (SettingsAPI):**
```python
from src.pk_py_lib.api.settings_api import SettingsAPI

api = SettingsAPI()

# Get profile
profile = api.get_profile()  # Current profile

# Generic get/set
value = api.get_setting("cache_size_mb")  # Auto-detects scope
api.set_setting("cache_size_mb", 8192)
```

**After (Unified API):**
```python
from src.pk_py_lib.api.settings import AppSettingsAPI, ProfilesAPI

app_api = AppSettingsAPI()
prof_api = ProfilesAPI()

# Get profile
response = prof_api.get_active()
if response.success:
    profile = response.data

# Explicit scope (no auto-detection)
response = app_api.get_app_settings()
if response.success:
    cache_size = response.data.cache_size_mb

response = app_api.update_app_settings({"cache_size_mb": 8192})
```

---

### 5.3 Database Migration Process

#### Migration Script Structure

```python
# src/pk_py_lib/core/settings/migration.py

def migrate_legacy_to_modern(db: DatabaseManager) -> MigrationReport:
    """
    Migrate data from legacy schema to modern schema.

    Steps:
    1. Backup existing data
    2. Create modern tables if needed
    3. Migrate profiles → settings_profiles
    4. Migrate settings → settings_profile_items OR json_data
    5. Set active profile in meta
    6. Validate migrated data
    7. Mark legacy tables for deprecation

    Returns:
        MigrationReport with success status and details
    """
    report = MigrationReport()

    try:
        with db.get_connection(db.settings_db) as conn:
            # Step 1: Backup
            report.backup_path = _backup_legacy_tables(conn)

            # Step 2: Create modern tables (idempotent)
            _ensure_modern_tables(conn)

            # Step 3: Migrate profiles
            profile_mapping = _migrate_profiles(conn, report)

            # Step 4: Migrate settings
            _migrate_settings(conn, profile_mapping, report)

            # Step 5: Set active profile
            _migrate_active_profile(conn, profile_mapping, report)

            # Step 6: Validate
            _validate_migration(conn, report)

            # Step 7: Mark legacy tables
            _mark_legacy_tables(conn)

            report.success = True

    except Exception as e:
        report.success = False
        report.error = str(e)
        logger.exception("Migration failed")
        _rollback_migration(db, report.backup_path)

    return report
```

#### Rollback Procedure

```python
def rollback_migration(db: DatabaseManager, backup_path: Path) -> bool:
    """
    Rollback migration to legacy schema.

    Steps:
    1. Restore legacy tables from backup
    2. Remove modern tables
    3. Validate legacy data

    Returns:
        True if rollback successful
    """
    try:
        with db.get_connection(db.settings_db) as conn:
            # Restore from backup
            backup_db = sqlite3.connect(backup_path)

            # Drop modern tables
            conn.execute("DROP TABLE IF EXISTS settings_profile_items")
            conn.execute("DROP TABLE IF EXISTS settings_profiles")

            # Restore legacy tables
            for table in ["profiles", "settings"]:
                backup_db.backup(conn, table)

            backup_db.close()
            return True

    except Exception as e:
        logger.exception("Rollback failed")
        return False
```

---

### 5.4 Testing Strategy

#### Test Coverage Requirements

**Unit Tests:**
- [ ] AppSettingsManager: get, update, all fields
- [ ] ProfilesManager: CRUD, active management, validation
- [ ] Schema validation: all modes, all configurations
- [ ] Model conversion: Profile → SettingsProfile
- [ ] Migration utilities: all conversion functions
- [ ] API adapters: all methods, error handling

**Integration Tests:**
- [ ] End-to-end profile creation and activation
- [ ] Legacy profile → JSON migration
- [ ] Database migration (full cycle)
- [ ] Rollback procedure
- [ ] API workflows (create, update, delete, etc.)
- [ ] GUI integration (settings manager dialog)

**Migration Tests:**
- [ ] Empty database → modern schema
- [ ] Legacy data → modern schema (profiles only)
- [ ] Legacy data → modern schema (profiles + settings)
- [ ] Legacy data → modern schema (complex settings)
- [ ] Migration rollback
- [ ] Data integrity validation

**Performance Tests:**
- [ ] Profile listing (100+ profiles)
- [ ] Settings retrieval (large JSON data)
- [ ] Migration time (large datasets)
- [ ] API response times

---

## 6. Risk Assessment

### 6.1 High-Risk Areas

#### Risk 1: Data Loss During Migration

**Likelihood:** Medium
**Impact:** Critical
**Affected:** All profiles and settings

**Mitigation:**
1. **Mandatory Backup:** Migration script creates automatic backup before any changes
2. **Validation:** Comprehensive validation of migrated data against source
3. **Rollback:** Automated rollback procedure if validation fails
4. **Testing:** Migration tested on copy of production data
5. **Grace Period:** Keep legacy tables for 1 release cycle as fallback

**Rollback Plan:**
```python
# Automatic rollback on validation failure
if not validate_migration(conn):
    logger.error("Migration validation failed, rolling back")
    restore_from_backup(backup_path)
    raise MigrationError("Data validation failed")
```

---

#### Risk 2: Breaking GUI Workflows

**Likelihood:** Medium
**Impact:** High
**Affected:** All GUI components using profiles

**Mitigation:**
1. **Comprehensive GUI Tests:** Test all settings manager workflows before deployment
2. **API Stability:** Keep ProfilesAPI interface stable (rename only)
3. **Gradual Migration:** Update GUI imports in phases
4. **Feature Flags:** Add flag to switch between legacy and modern if needed
5. **User Testing:** Manual testing of all GUI paths

**Testing Checklist:**
- [ ] Create new profile via GUI
- [ ] Edit existing profile via GUI
- [ ] Delete profile via GUI
- [ ] Duplicate profile via GUI
- [ ] Set active profile via GUI
- [ ] Import/export profile via GUI
- [ ] Validate profile via GUI
- [ ] Run with profile via GUI

---

#### Risk 3: Import Breaking in External Code

**Likelihood:** Low (internal project)
**Impact:** Medium
**Affected:** Any external code importing settings modules

**Mitigation:**
1. **Deprecation Period:** 1-2 release cycles before removing old imports
2. **Compatibility Re-exports:** Old import paths work with warnings
3. **Migration Guide:** Clear documentation of all import changes
4. **IDE Support:** Update type stubs for autocomplete
5. **Communication:** Announce breaking changes in release notes

**Example Compatibility:**
```python
# Old import still works with warning
from src.pk_py_lib.core.configuration import ConfigurationManager
# -> DeprecationWarning: Use ProfilesManager + AppSettingsManager

# New import (recommended)
from src.pk_py_lib.core.settings import ProfilesManager, AppSettingsManager
```

---

### 6.2 Medium-Risk Areas

#### Risk 4: Performance Regression

**Likelihood:** Low
**Impact:** Medium
**Affected:** Profile operations, settings retrieval

**Mitigation:**
1. **Benchmark Tests:** Measure performance before/after migration
2. **Index Optimization:** Ensure proper indexes on UUID columns
3. **Query Review:** Review all SQL queries for efficiency
4. **Profiling:** Profile critical paths (profile list, settings load)
5. **Monitoring:** Track performance metrics post-deployment

**Performance Targets:**
- Profile listing: <100ms for 100 profiles
- Settings load: <50ms for typical profile
- Migration: <10s for 1000 profiles
- API response time: <200ms for all operations

---

#### Risk 5: Schema Evolution Challenges

**Likelihood:** Medium
**Impact:** Low
**Affected:** Future schema changes

**Mitigation:**
1. **Version Tracking:** `meta` table includes schema_version
2. **Migration Framework:** Reusable migration utilities
3. **Incremental Changes:** Small, testable schema updates
4. **Backward Compatibility:** Support multiple schema versions temporarily
5. **Documentation:** Document all schema changes

**Schema Versioning:**
```python
# Check schema version before operations
def _ensure_schema_version(conn, required_version):
    meta = _read_meta(conn)
    current = meta.get("schema_version", 0)
    if current < required_version:
        raise SchemaVersionError(f"Schema v{current}, need v{required_version}")
```

---

### 6.3 Low-Risk Areas

#### Risk 6: Documentation Drift

**Likelihood:** High (if not maintained)
**Impact:** Low
**Affected:** Developer experience, onboarding

**Mitigation:**
1. **Update All Docs:** Systematic review of all documentation
2. **Code Examples:** Test all code examples in docs
3. **Architecture Diagrams:** Update all diagrams to reflect new structure
4. **API Reference:** Auto-generate from docstrings
5. **Regular Reviews:** Quarterly documentation audits

---

## 7. Success Metrics

### 7.1 Code Quality Metrics

**Baseline (Current):**
- Configuration modules: 5 files, ~3,600 total lines
- Duplicate code: ~70% overlap between systems
-

Test coverage: Unknown (need baseline)
- Number of settings-related modules: 5
- API inconsistency: 2 parallel APIs

**Target (Post-Consolidation):**
- Configuration modules: 3 files, ~2,500 total lines (30% reduction)
- Duplicate code: <5%
- Test coverage: >80%
- Number of settings-related modules: 3 (consolidated)
- API inconsistency: 0 (single unified approach)
- Zero deprecated imports remaining

---

### 7.2 Developer Experience Metrics

**Measure:**
- Time to understand settings architecture (new developer onboarding)
- Time to add new profile field
- Time to troubleshoot settings-related bugs
- Number of "which API should I use?" questions

**Target:**
- 50% reduction in onboarding time for settings
- 40% faster to add new profile features
- 60% faster bug resolution (single source of truth)
- Zero confusion about which API to use

---

### 7.3 Functional Metrics

**Verify:**
- All existing functionality preserved
- No data loss during migration
- All GUI workflows still functional
- All tests passing
- Performance maintained or improved

**Acceptance Criteria:**
- [ ] 100% of existing tests pass with new system
- [ ] 100% of profiles migrated successfully
- [ ] 100% of settings values preserved
- [ ] Zero data corruption issues
- [ ] Zero regression bugs reported

---

## 8. Conclusion

### 8.1 Summary

The consolidation plan addresses critical architectural debt in the pk-py-lib settings/configuration system by:

1. **Eliminating Duplication**: Merging parallel systems ([`ConfigurationManager`](src/pk_py_lib/core/configuration.py:98) and [`SettingsProfilesManager`](src/pk_py_lib/core/settings_profiles.py:146)) into single unified system
2. **Clarifying Responsibilities**: Separating app settings from profile settings with clear boundaries
3. **Modernizing Architecture**: Standardizing on ID-based (UUID) profiles with JSON schema support
4. **Simplifying APIs**: Replacing overlapping APIs with focused, purpose-built interfaces
5. **Ensuring Safety**: Providing comprehensive migration path with rollback capabilities

---

### 8.2 Benefits

**Immediate Benefits:**
- **Reduced Complexity**: Single source of truth for profile management
- **Better Testability**: Focused modules easier to test in isolation
- **Clearer APIs**: Explicit app vs profile operations
- **No Confusion**: Single model ([`SettingsProfile`](src/pk_py_lib/core/settings_profiles.py:78)) for all profile code

**Long-term Benefits:**
- **Easier Maintenance**: Less code to maintain (~30% reduction)
- **Faster Development**: Clear patterns for adding features
- **Better Extensibility**: JSON schema enables rich validation
- **Reduced Bugs**: Single implementation = fewer edge cases
- **Improved Documentation**: Simpler architecture easier to document

---

### 8.3 Estimated Total Effort

**Phase 1 (Preparation):** 8-10 hours
**Phase 2 (Core Refactoring):** 12-16 hours
**Phase 3 (API Refactoring):** 10-12 hours
**Phase 4 (Cleanup):** 8-10 hours

**Total:** 38-48 hours over 4 weeks

**Recommended Approach:**
- Execute phases sequentially (not parallel)
- Complete all testing before moving to next phase
- Maintain backward compatibility until Phase 4
- Keep stakeholders informed of progress weekly

---

### 8.4 Next Steps

1. **Review and Approve Plan:** Stakeholder review of this consolidation plan
2. **Create Issue Tracking:** Break down phases into trackable issues
3. **Establish Baseline Metrics:** Measure current code quality, coverage, performance
4. **Phase 1 Execution:** Begin with preparation phase (low risk)
5. **Iterative Review:** Review after each phase, adjust as needed

---

### 8.5 Questions for Decision

**Before Starting Implementation:**

1. **Timeline Approval**: Is 4-week timeline acceptable?
2. **Breaking Changes**: Acceptable to have breaking changes in major version 2.0?
3. **Deprecation Period**: 1-2 release cycles sufficient for deprecation?
4. **Testing Requirements**: >80% coverage target acceptable?
5. **Rollback Strategy**: Backup and rollback plan sufficient?
6. **Resource Allocation**: Can team commit ~10 hours/week for 4 weeks?

---

## Appendices

### Appendix A: File Mapping

**Files to Create:**
- `src/pk_py_lib/core/settings/__init__.py`
- `src/pk_py_lib/core/settings/models.py`
- `src/pk_py_lib/core/settings/app_settings.py`
- `src/pk_py_lib/core/settings/profiles_manager.py` (renamed from settings_profiles.py)
- `src/pk_py_lib/core/settings/schema.py` (renamed from settings_schema.py)
- `src/pk_py_lib/core/settings/migration.py`
- `src/pk_py_lib/api/settings/__init__.py`
- `src/pk_py_lib/api/settings/app_settings_api.py`
- `src/pk_py_lib/api/settings/profiles_api.py` (renamed from settings_profiles.py API)
- `docs/roo/settings-migration-guide.md`
- `tests/test_settings_migration.py`
- `tests/test_settings_api_unified.py`

**Files to Deprecate:**
- `src/pk_py_lib/core/configuration.py` (mark deprecated, remove in v2.0)
- `src/pk_py_lib/api/settings_api.py` (mark deprecated, remove in v2.0)

**Files to Update:**
- All files importing from deprecated modules
- All documentation referencing old architecture
- All tests using old APIs

---

### Appendix B: Import Migration Matrix

| Old Import | New Import | Notes |
|------------|------------|-------|
| `from src.pk_py_lib.core.configuration import ConfigurationManager` | `from src.pk_py_lib.core.settings import ProfilesManager, AppSettingsManager` | Split into two managers |
| `from src.pk_py_lib.core.configuration import Profile` | `from src.pk_py_lib.core.settings import SettingsProfile` | Use SettingsProfile model |
| `from src.pk_py_lib.core.configuration import AppSettings` | `from src.pk_py_lib.core.settings import AppSettings` | Moved to models.py |
| `from src.pk_py_lib.core.settings_profiles import SettingsProfilesManager` | `from src.pk_py_lib.core.settings import ProfilesManager` | Renamed |
| `from src.pk_py_lib.core.settings_profiles import SettingsProfile` | `from src.pk_py_lib.core.settings import SettingsProfile` | Moved to models.py |
| `from src.pk_py_lib.core.settings_schema import *` | `from src.pk_py_lib.core.settings.schema import *` | Moved to subdirectory |
| `from src.pk_py_lib.api.settings_api import SettingsAPI` | `from src.pk_py_lib.api.settings import AppSettingsAPI, ProfilesAPI` | Split into two APIs |
| `from src.pk_py_lib.api.settings_profiles import SettingsProfilesAPI` | `from src.pk_py_lib.api.settings import ProfilesAPI` | Renamed |

---

### Appendix C: Glossary

**Terms:**

- **AppSettings**: Global application-level settings (theme, cache size, etc.)
- **Profile**: Named configuration for a workflow (algorithm defaults, paths, etc.)
- **Active Profile**: The currently selected profile used by the application
- **Default Profile**: The profile to use on first launch (deprecated concept)
- **Legacy Format**: Key-value pairs in settings_profile_items table
- **JSON Format**: Structured data in json_data column following schema
- **Migration**: Converting legacy profiles to JSON format
- **Consolidation**: Merging duplicate systems into single unified system
- **UUID**: Universally Unique Identifier (string format for profile IDs)
- **ISO8601**: Standard timestamp format (e.g., "2025-10-10T12:00:00Z")

**Abbreviations:**

- **API**: Application Programming Interface
- **CRUD**: Create, Read, Update, Delete
- **DB**: Database
- **FK**: Foreign Key
- **GUI**: Graphical User Interface
- **JSON**: JavaScript Object Notation
- **PK**: Primary Key
- **SQL**: Structured Query Language
- **UUID**: Universally Unique Identifier

---

### Appendix D: References

**Related Documents:**
- [`docs/roo/refactoring-plan.md`](docs/roo/refactoring-plan.md:66-103) - Original refactoring plan identifying this issue
- [`architecture-plan.md`](architecture-plan.md:1) - Overall project architecture
- [`docs/roo/img-app-api-specifications.md`](docs/roo/img-app-api-specifications.md:1) - API specifications
- [`docs/roo/img-app-data-model.md`](docs/roo/img-app-data-model.md:1) - Data model specifications

**Key Source Files:**
- [`src/pk_py_lib/core/configuration.py`](src/pk_py_lib/core/configuration.py:1) - Legacy configuration system
- [`src/pk_py_lib/core/settings_profiles.py`](src/pk_py_lib/core/settings_profiles.py:1) - Modern profiles system
- [`src/pk_py_lib/core/settings_schema.py`](src/pk_py_lib/core/settings_schema.py:1) - JSON schema definitions
- [`src/pk_py_lib/api/settings_api.py`](src/pk_py_lib/api/settings_api.py:1) - Legacy API
- [`src/pk_py_lib/api/settings_profiles.py`](src/pk_py_lib/api/settings_profiles.py:1) - Modern API

---

**Document History:**
- v1.0 (2025-10-10): Initial comprehensive consolidation plan

---

**END OF DOCUMENT**
