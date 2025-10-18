"""
Comprehensive verification tests for the new JSON settings system.

Tests the complete JSON-based settings architecture including:
- JSON schema validation
- Settings persistence and loading
- Profile management functionality
- Unified settings manager integration
- Error handling and recovery
- File operations and atomic writes

This test suite provides complete coverage for the JSON settings system
to ensure all functionality works correctly.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime
import shutil

from pk_py_lib.core.models.settings import AppSettings, SettingsProfile
from pk_py_lib.core.settings.json_schemas import (
    APP_SETTINGS_SCHEMA_VERSION,
    SEARCH_PROFILES_SCHEMA_VERSION,
    create_default_app_settings,
    create_default_search_profiles,
    validate_app_settings,
    validate_search_profiles,
    normalize_app_settings,
    normalize_search_profiles,
    check_schema_version,
    SettingsValidationError
)
from pk_py_lib.core.settings.json_manager import (
    JSONSettingsManager,
    SettingsFileManager
)
from pk_py_lib.core.settings.json_app_settings import JSONAppSettingsManager
from pk_py_lib.core.settings.json_profiles import JSONProfilesManager
from pk_py_lib.core.settings.json_unified_manager import JSONSettingsManager as UnifiedJSONSettingsManager


class TestJSONSchemas:
    """Tests for JSON schema validation and utilities."""

    def test_app_settings_schema_version(self):
        """Test app settings schema version is correct."""
        assert isinstance(APP_SETTINGS_SCHEMA_VERSION, int)
        assert APP_SETTINGS_SCHEMA_VERSION > 0

    def test_search_profiles_schema_version(self):
        """Test search profiles schema version is correct."""
        assert isinstance(SEARCH_PROFILES_SCHEMA_VERSION, int)
        assert SEARCH_PROFILES_SCHEMA_VERSION > 0

    def test_create_default_app_settings(self):
        """Test default app settings creation."""
        defaults = create_default_app_settings()

        assert defaults["version"] == APP_SETTINGS_SCHEMA_VERSION
        assert defaults["cache_enabled"] is True
        assert defaults["cache_size_mb"] == 500
        assert defaults["max_workers"] == 4
        assert defaults["gui_theme"] == "auto"
        assert defaults["log_level"] == "INFO"
        assert isinstance(defaults["recent_directories"], list)
        assert defaults["window_geometry"] is None
        assert "last_updated" in defaults

        # Validate against schema
        validate_app_settings(defaults)

    def test_create_default_search_profiles(self):
        """Test default search profiles creation."""
        defaults = create_default_search_profiles()

        assert defaults["version"] == SEARCH_PROFILES_SCHEMA_VERSION
        assert "profiles" in defaults
        assert len(defaults["profiles"]) >= 3

        # Check profile structure
        for profile in defaults["profiles"]:
            assert "id" in profile
            assert "name" in profile
            assert "hash_algorithm" in profile
            assert "created_at" in profile
            assert "updated_at" in profile

        # Validate against schema
        validate_search_profiles(defaults)

    def test_validate_app_settings_valid(self):
        """Test validation of valid app settings."""
        valid_settings = create_default_app_settings()
        validate_app_settings(valid_settings)  # Should not raise

    def test_validate_app_settings_invalid_version(self):
        """Test validation fails for invalid version."""
        invalid_settings = create_default_app_settings()
        invalid_settings["version"] = 999

        with pytest.raises(SettingsValidationError):
            validate_app_settings(invalid_settings)

    def test_validate_app_settings_invalid_theme(self):
        """Test validation fails for invalid theme."""
        invalid_settings = create_default_app_settings()
        invalid_settings["gui_theme"] = "invalid_theme"

        with pytest.raises(SettingsValidationError):
            validate_app_settings(invalid_settings)

    def test_validate_search_profiles_valid(self):
        """Test validation of valid search profiles."""
        valid_profiles = create_default_search_profiles()
        validate_search_profiles(valid_profiles)  # Should not raise

    def test_validate_search_profiles_invalid_hash_algorithm(self):
        """Test validation fails for invalid hash algorithm."""
        invalid_profiles = create_default_search_profiles()
        invalid_profiles["profiles"][0]["hash_algorithm"] = "invalid_algorithm"

        with pytest.raises(SettingsValidationError):
            validate_search_profiles(invalid_profiles)

    def test_normalize_app_settings(self):
        """Test app settings normalization."""
        partial_settings = {
            "version": APP_SETTINGS_SCHEMA_VERSION,
            "cache_enabled": False  # Only partial data
        }

        normalized = normalize_app_settings(partial_settings)

        # Should have all required fields
        assert normalized["cache_enabled"] is False
        assert normalized["cache_size_mb"] == 500  # Default value
        assert normalized["max_workers"] == 4      # Default value
        assert "last_updated" in normalized

    def test_normalize_search_profiles(self):
        """Test search profiles normalization."""
        partial_profiles = {
            "version": SEARCH_PROFILES_SCHEMA_VERSION,
            "profiles": [
                {
                    "name": "Test Profile",
                    "hash_algorithm": "xxh3"
                    # Missing timestamps and other fields
                }
            ]
        }

        normalized = normalize_search_profiles(partial_profiles)

        # Should have all required fields
        profile = normalized["profiles"][0]
        assert profile["name"] == "Test Profile"
        assert "created_at" in profile
        assert "updated_at" in profile

    def test_check_schema_version(self):
        """Test schema version checking."""
        current_data = {"version": APP_SETTINGS_SCHEMA_VERSION}
        old_data = {"version": APP_SETTINGS_SCHEMA_VERSION - 1}
        future_data = {"version": APP_SETTINGS_SCHEMA_VERSION + 1}

        assert check_schema_version(current_data, APP_SETTINGS_SCHEMA_VERSION) is True
        assert check_schema_version(old_data, APP_SETTINGS_SCHEMA_VERSION) is False
        assert check_schema_version(future_data, APP_SETTINGS_SCHEMA_VERSION) is False


class TestJSONSettingsManager:
    """Tests for the core JSON settings manager."""

    def test_init_creates_directory(self):
        """Test initialization creates settings directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            assert manager.settings_dir == settings_dir
            assert settings_dir.exists()

    def test_load_app_settings_creates_defaults(self):
        """Test loading app settings creates defaults for non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            settings = manager.load_app_settings()

            assert settings["version"] == APP_SETTINGS_SCHEMA_VERSION
            assert settings["cache_enabled"] is True
            assert settings_dir.exists()
            assert manager.app_settings_file.exists()

    def test_load_app_settings_loads_existing(self):
        """Test loading app settings loads existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Create settings file manually
            test_settings = create_default_app_settings()
            test_settings["cache_enabled"] = False
            test_settings["cache_size_mb"] = 1000

            with open(manager.app_settings_file, 'w') as f:
                json.dump(test_settings, f)

            # Load settings
            loaded = manager.load_app_settings()

            assert loaded["cache_enabled"] is False
            assert loaded["cache_size_mb"] == 1000

    def test_load_app_settings_corrupted_file(self):
        """Test loading handles corrupted JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Create corrupted file
            with open(manager.app_settings_file, 'w') as f:
                f.write("invalid json content {")

            # Should create defaults
            loaded = manager.load_app_settings()
            assert loaded["version"] == APP_SETTINGS_SCHEMA_VERSION

    def test_save_app_settings(self):
        """Test saving app settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            settings = create_default_app_settings()
            settings["cache_enabled"] = False
            settings["cache_size_mb"] = 2048

            manager.save_app_settings(settings)

            # Verify file exists and content
            assert manager.app_settings_file.exists()
            with open(manager.app_settings_file, 'r') as f:
                saved = json.load(f)

            assert saved["cache_enabled"] is False
            assert saved["cache_size_mb"] == 2048

    def test_save_app_settings_creates_backup(self):
        """Test saving creates backup file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Create initial settings
            initial_settings = create_default_app_settings()
            manager.save_app_settings(initial_settings)

            # Modify and save again
            initial_settings["cache_enabled"] = False
            manager.save_app_settings(initial_settings)

            # Verify backup exists
            backup_file = manager.app_settings_file.with_suffix('.json.bak')
            assert backup_file.exists()

    def test_load_search_profiles_creates_defaults(self):
        """Test loading search profiles creates defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            profiles = manager.load_search_profiles()

            assert profiles["version"] == SEARCH_PROFILES_SCHEMA_VERSION
            assert "profiles" in profiles
            assert len(profiles["profiles"]) >= 3

    def test_save_and_load_search_profiles(self):
        """Test saving and loading search profiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Load defaults
            profiles = manager.load_search_profiles()

            # Modify a profile
            profiles["profiles"][0]["name"] = "Modified Profile"

            # Save
            manager.save_search_profiles(profiles)

            # Load again
            reloaded = manager.load_search_profiles()

            assert reloaded["profiles"][0]["name"] == "Modified Profile"

    def test_reset_to_defaults(self):
        """Test resetting to defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Create custom settings
            custom_settings = create_default_app_settings()
            custom_settings["cache_enabled"] = False
            manager.save_app_settings(custom_settings)

            # Reset to defaults
            manager.reset_to_defaults()

            # Verify defaults restored
            restored = manager.load_app_settings()
            assert restored["cache_enabled"] is True

    def test_get_file_paths(self):
        """Test getting file paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            paths = manager.get_file_paths()

            assert "app_settings" in paths
            assert "search_profiles" in paths
            assert paths["app_settings"] == manager.app_settings_file
            assert paths["search_profiles"] == manager.search_profiles_file


class TestSettingsFileManager:
    """Tests for the high-level settings file manager."""

    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            assert manager.json_manager is not None
            assert manager._app_settings is None
            assert manager._search_profiles is None

    def test_load_all_settings_first_time(self):
        """Test loading all settings on first run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            result = manager.load_all_settings()

            assert "app_settings" in result
            assert "search_profiles" in result
            assert "issues" in result
            assert len(result["issues"]) == 0  # No issues expected

            # Cache should be populated
            assert manager._app_settings is not None
            assert manager._search_profiles is not None

    def test_load_all_settings_with_corruption(self):
        """Test loading with corrupted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            # Create corrupted app settings file
            app_settings_file = settings_dir / "app-settings.json"
            with open(app_settings_file, 'w') as f:
                f.write("corrupted json")

            result = manager.load_all_settings()

            # Should handle corruption gracefully
            assert "app_settings" in result
            assert "search_profiles" in result
            assert len(result["issues"]) > 0  # Should report issues

    def test_get_cached_settings(self):
        """Test getting cached settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            # Load all settings first
            manager.load_all_settings()

            # Get cached versions
            app_settings = manager.get_app_settings()
            search_profiles = manager.get_search_profiles()

            assert app_settings is not None
            assert search_profiles is not None

    def test_save_app_settings_updates_cache(self):
        """Test saving app settings updates cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            # Load defaults
            manager.load_all_settings()

            # Modify and save
            settings = manager.get_app_settings()
            settings["cache_enabled"] = False

            manager.save_app_settings(settings)

            # Cache should be updated
            assert manager._app_settings["cache_enabled"] is False

    def test_reset_to_defaults_clears_cache(self):
        """Test resetting to defaults clears cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = SettingsFileManager(settings_dir)

            # Load settings
            manager.load_all_settings()

            # Reset to defaults
            manager.reset_to_defaults()

            # Cache should be cleared
            assert manager._app_settings is None
            assert manager._search_profiles is None


class TestJSONAppSettingsManager:
    """Tests for the JSON app settings manager."""

    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            assert manager.settings_dir == settings_dir
            assert manager.file_manager is not None
            assert manager._settings is None

    def test_load_creates_defaults(self):
        """Test loading creates defaults for new installation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            settings = manager.load()

            assert isinstance(settings, AppSettings)
            assert settings.cache_enabled is True
            assert settings.cache_size_mb == 500

    def test_save_and_load(self):
        """Test saving and loading settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            # Create custom settings
            settings = AppSettings(
                cache_enabled=False,
                cache_size_mb=1024,
                max_workers=8,
                gui_theme="dark",
                log_level="DEBUG"
            )

            # Save
            manager.save(settings)

            # Load in new manager instance
            manager2 = JSONAppSettingsManager(settings_dir)
            loaded = manager2.load()

            # Verify
            assert loaded.cache_enabled is False
            assert loaded.cache_size_mb == 1024
            assert loaded.max_workers == 8
            assert loaded.gui_theme == "dark"
            assert loaded.log_level == "DEBUG"

    def test_reload(self):
        """Test reloading settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            # Load initial settings
            initial = manager.load()
            initial.cache_enabled = False

            # Reload (should discard cached changes)
            reloaded = manager.reload()

            # Should have original values
            assert reloaded.cache_enabled is True

    def test_update_setting(self):
        """Test updating a single setting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            # Load settings
            manager.load()

            # Update single setting
            manager.update_setting("cache_enabled", False)

            # Verify
            updated = manager.get_settings()
            assert updated.cache_enabled is False

    def test_update_unknown_setting(self):
        """Test updating unknown setting is ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            # Load settings
            manager.load()

            # Try to update unknown setting
            manager.update_setting("unknown_setting", "value")

            # Should not crash, just log warning

    def test_concurrent_access(self):
        """Test thread-safe access."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONAppSettingsManager(settings_dir)

            # Multiple loads should work
            settings1 = manager.load()
            settings2 = manager.load()

            assert settings1.cache_enabled == settings2.cache_enabled


class TestJSONProfilesManager:
    """Tests for the JSON profiles manager."""

    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            assert manager.settings_dir == settings_dir
            assert manager.file_manager is not None
            assert len(manager._profiles) == 0

    def test_create_profile(self):
        """Test creating a new profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile
            profile = SettingsProfile(
                name="Test Profile",
                description="Test description",
                hash_algorithm="phash",
                similarity_threshold=0.90
            )

            created = manager.create(profile)

            # Verify
            assert created.id is not None
            assert created.name == "Test Profile"
            assert created.description == "Test description"
            assert isinstance(created.created_at, datetime)
            assert isinstance(created.updated_at, datetime)

    def test_create_profile_duplicate_name_fails(self):
        """Test creating profile with duplicate name fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create first profile
            profile1 = SettingsProfile(name="Test", hash_algorithm="xxh3")
            manager.create(profile1)

            # Try to create duplicate
            profile2 = SettingsProfile(name="Test", hash_algorithm="phash")

            with pytest.raises(ValueError, match="already exists"):
                manager.create(profile2)

    def test_get_by_id(self):
        """Test getting profile by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile
            profile = SettingsProfile(name="Test", hash_algorithm="xxh3")
            created = manager.create(profile)

            # Get by ID
            retrieved = manager.get_by_id(created.id)

            assert retrieved is not None
            assert retrieved.id == created.id
            assert retrieved.name == "Test"

    def test_get_all(self):
        """Test getting all profiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Get initial profiles (should create defaults)
            profiles = manager.get_all()

            assert len(profiles) >= 3
            assert all(isinstance(p, SettingsProfile) for p in profiles)

    def test_update_profile(self):
        """Test updating a profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile
            profile = SettingsProfile(name="Test", hash_algorithm="xxh3")
            created = manager.create(profile)

            # Update
            created.similarity_threshold = 0.85
            created.description = "Updated description"
            manager.update(created)

            # Verify
            updated = manager.get_by_id(created.id)
            assert updated.similarity_threshold == 0.85
            assert updated.description == "Updated description"

    def test_delete_profile(self):
        """Test deleting a profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile
            profile = SettingsProfile(name="Temp", hash_algorithm="xxh3")
            created = manager.create(profile)

            # Delete
            success = manager.delete(created.id)
            assert success is True

            # Verify deleted
            assert manager.get_by_id(created.id) is None

    def test_cannot_delete_system_profile(self):
        """Test that system profiles cannot be deleted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Get a system profile
            profiles = manager.get_all()
            system_profile = next(p for p in profiles if p.is_system)

            # Try to delete
            success = manager.delete(system_profile.id)
            assert success is False

    def test_set_active(self):
        """Test setting active profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Get a non-default profile
            profiles = manager.get_all()
            profile = next(p for p in profiles if not p.is_default)

            # Set as active
            success = manager.set_active(profile.id)
            assert success is True

            # Verify
            active = manager.get_active()
            assert active.id == profile.id

    def test_validate_name(self):
        """Test profile name validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Load defaults first
            manager.get_all()

            # Test unique name
            assert manager.validate_name("New Profile") is True

            # Test duplicate name
            assert manager.validate_name("Default") is False


class TestUnifiedJSONSettingsManager:
    """Tests for the unified JSON settings manager."""

    def test_init(self):
        """Test initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            assert manager.settings_dir == settings_dir
            assert manager.app_settings is not None
            assert manager.profiles is not None

    def test_init_default_directory(self):
        """Test initialization with default directory."""
        manager = UnifiedJSONSettingsManager()

        # Should use platform-specific directory
        expected_dir = Path.home() / ".pk-py-lib" / "settings"
        assert manager.settings_dir == expected_dir

    def test_load_all(self):
        """Test loading all settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            result = manager.load_all()

            assert "app_settings" in result
            assert "profiles" in result
            assert isinstance(result["app_settings"], AppSettings)
            assert isinstance(result["profiles"], list)

    def test_save_all(self):
        """Test saving all settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Load current settings
            current = manager.load_all()

            # Modify settings
            current["app_settings"].cache_enabled = False

            # Save all
            manager.save_all(current["app_settings"], current["profiles"])

            # Load again to verify
            reloaded = manager.load_all()
            assert reloaded["app_settings"].cache_enabled is False

    def test_reset_to_defaults(self):
        """Test resetting to defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Modify settings
            current = manager.load_all()
            current["app_settings"].cache_enabled = False
            manager.save_all(current["app_settings"], current["profiles"])

            # Reset to defaults
            manager.reset_to_defaults()

            # Verify defaults restored
            restored = manager.load_all()
            assert restored["app_settings"].cache_enabled is True

    def test_get_settings_summary(self):
        """Test getting settings summary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            summary = manager.get_settings_summary()

            assert "settings_dir" in summary
            assert "app_settings_file" in summary
            assert "profiles_file" in summary
            assert "app_settings_count" in summary
            assert "profiles_count" in summary

    def test_validate_integrity(self):
        """Test integrity validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Should be valid initially
            result = manager.validate_integrity()
            assert result["valid"] is True
            assert len(result["issues"]) == 0

    def test_validate_integrity_with_corruption(self):
        """Test integrity validation with corrupted files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Corrupt app settings file
            app_settings_file = settings_dir / "app-settings.json"
            with open(app_settings_file, 'w') as f:
                f.write("corrupted")

            # Validate integrity
            result = manager.validate_integrity()
            assert result["valid"] is False
            assert len(result["issues"]) > 0


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    def test_complete_workflow(self):
        """Test complete settings workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"

            # Initialize manager
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Load initial settings
            data = manager.load_all()
            assert data["app_settings"].cache_enabled is True

            # Modify app settings
            data["app_settings"].cache_enabled = False
            data["app_settings"].cache_size_mb = 2048

            # Save changes
            manager.save_all(data["app_settings"], data["profiles"])

            # Create custom profile
            custom_profile = SettingsProfile(
                name="Custom Finder",
                description="Custom similarity finder",
                hash_algorithm="phash",
                similarity_threshold=0.95,
                hash_size=16
            )
            manager.profiles.create(custom_profile)

            # Verify persistence
            manager2 = UnifiedJSONSettingsManager(settings_dir)
            reloaded = manager2.load_all()

            assert reloaded["app_settings"].cache_enabled is False
            assert reloaded["app_settings"].cache_size_mb == 2048

            # Find custom profile
            custom_found = None
            for profile in reloaded["profiles"]:
                if profile.name == "Custom Finder":
                    custom_found = profile
                    break

            assert custom_found is not None
            assert custom_found.similarity_threshold == 0.95

    def test_error_recovery(self):
        """Test error recovery scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = UnifiedJSONSettingsManager(settings_dir)

            # Get initial state
            initial = manager.load_all()

            # Corrupt settings file
            app_settings_file = settings_dir / "app-settings.json"
            with open(app_settings_file, 'w') as f:
                f.write("corrupted json")

            # Should recover gracefully
            recovered = manager.load_all()
            assert recovered["app_settings"].cache_enabled is True  # Back to defaults

            # Should report issues
            integrity = manager.validate_integrity()
            assert integrity["valid"] is False

    def test_concurrent_operations(self):
        """Test concurrent operations safety."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"

            # Create two manager instances
            manager1 = UnifiedJSONSettingsManager(settings_dir)
            manager2 = UnifiedJSONSettingsManager(settings_dir)

            # Both load settings
            data1 = manager1.load_all()
            data2 = manager2.load_all()

            # Both modify settings
            data1["app_settings"].cache_enabled = False
            data2["app_settings"].gui_theme = "dark"

            # Save both
            manager1.save_all(data1["app_settings"], data1["profiles"])
            manager2.save_all(data2["app_settings"], data2["profiles"])

            # Final state should reflect last save
            final = manager1.load_all()
            assert final["app_settings"].cache_enabled is False
            assert final["app_settings"].gui_theme == "dark"


class TestPathPersistence:
    """Tests for path persistence in profile configurations."""

    def test_profile_path_persistence_comprehensive(self):
        """Test that search paths, file patterns, and pool configurations are correctly persisted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile with comprehensive path configuration
            profile = SettingsProfile(
                name="Path Persistence Test",
                description="Profile to test path persistence functionality",
                hash_algorithm="phash",
                similarity_threshold=0.90
            )

            # Configure pools with various path settings
            profile.pools = {
                "A": {
                    "paths": [
                        str(Path.home() / "Pictures"),
                        str(Path.home() / "Documents" / "Photos"),
                        "/mnt/external/images",
                        "~/Downloads/images"
                    ],
                    "recurse": True,
                    "max_depth": 5,
                    "include": [
                        "**/*.jpg",
                        "**/*.jpeg",
                        "**/*.png",
                        "**/*.webp",
                        "**/*.tiff",
                        "**/*.bmp",
                        "**/*.gif"
                    ],
                    "exclude": [
                        "**/temp/**",
                        "**/*.tmp",
                        "**/cache/**",
                        "**/thumbnails/**"
                    ],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]
                },
                "B": {
                    "paths": [
                        str(Path.home() / "Desktop" / "Screenshots"),
                        "/var/images"
                    ],
                    "recurse": False,
                    "max_depth": 1,
                    "include": ["*.png", "*.jpg"],
                    "exclude": ["**/temp/**"],
                    "follow_symlinks": True,
                    "include_hidden": True,
                    "type_filters": [".png", ".jpg", ".jpeg"]
                }
            }

            # Configure criteria with algorithm settings
            profile.criteria = {
                "algorithm": "phash",
                "degree_ui": 90,
                "similarity_hash_algorithm": "phash",
                "hash_size": 16
            }

            # Configure scope settings
            profile.scope = {
                "kind": "single_pool",
                "compare_within_pool": True,
                "compare_across_pools": False
            }

            # Configure output settings
            profile.output = {
                "mode": "report_only",
                "save_results": True,
                "output_directory": str(Path.home() / "image_results")
            }

            # Configure similarity settings
            profile.similarity = {
                "phash_threshold": 8,
                "whash_threshold": 10,
                "enabled_algorithms": ["phash", "whash"],
                "cross_algorithm_comparison": True
            }

            # Create the profile
            created_profile = manager.create(profile)
            assert created_profile.id is not None

            # Create a new manager instance to simulate loading from file
            manager2 = JSONProfilesManager(settings_dir)

            # Load the profile back
            loaded_profile = manager2.get_by_id(created_profile.id)
            assert loaded_profile is not None

            # Verify basic profile data
            assert loaded_profile.name == "Path Persistence Test"
            assert loaded_profile.description == "Profile to test path persistence functionality"
            assert loaded_profile.hash_algorithm == "phash"
            assert loaded_profile.similarity_threshold == 0.90

            # Verify pool configurations are preserved exactly
            assert loaded_profile.pools is not None
            assert "A" in loaded_profile.pools
            assert "B" in loaded_profile.pools

            # Verify Pool A configuration
            pool_a = loaded_profile.pools["A"]
            expected_paths_a = [
                str(Path.home() / "Pictures"),
                str(Path.home() / "Documents" / "Photos"),
                "/mnt/external/images",
                "~/Downloads/images"
            ]
            assert pool_a["paths"] == expected_paths_a
            assert pool_a["recurse"] is True
            assert pool_a["max_depth"] == 5
            assert pool_a["include"] == [
                "**/*.jpg", "**/*.jpeg", "**/*.png", "**/*.webp",
                "**/*.tiff", "**/*.bmp", "**/*.gif"
            ]
            assert pool_a["exclude"] == [
                "**/temp/**", "**/*.tmp", "**/cache/**", "**/thumbnails/**"
            ]
            assert pool_a["follow_symlinks"] is False
            assert pool_a["include_hidden"] is False
            assert pool_a["type_filters"] == [".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp", ".gif", ".heic", ".heif"]

            # Verify Pool B configuration
            pool_b = loaded_profile.pools["B"]
            expected_paths_b = [
                str(Path.home() / "Desktop" / "Screenshots"),
                "/var/images"
            ]
            assert pool_b["paths"] == expected_paths_b
            assert pool_b["recurse"] is False
            assert pool_b["max_depth"] == 1
            assert pool_b["include"] == ["*.png", "*.jpg"]
            assert pool_b["exclude"] == ["**/temp/**"]
            assert pool_b["follow_symlinks"] is True
            assert pool_b["include_hidden"] is True
            assert pool_b["type_filters"] == [".png", ".jpg", ".jpeg"]

            # Verify criteria configuration
            assert loaded_profile.criteria is not None
            assert loaded_profile.criteria["algorithm"] == "phash"
            assert loaded_profile.criteria["degree_ui"] == 90
            assert loaded_profile.criteria["similarity_hash_algorithm"] == "phash"
            assert loaded_profile.criteria["hash_size"] == 16

            # Verify scope configuration
            assert loaded_profile.scope is not None
            assert loaded_profile.scope["kind"] == "single_pool"
            assert loaded_profile.scope["compare_within_pool"] is True
            assert loaded_profile.scope["compare_across_pools"] is False

            # Verify output configuration
            assert loaded_profile.output is not None
            assert loaded_profile.output["mode"] == "report_only"
            assert loaded_profile.output["save_results"] is True
            assert loaded_profile.output["output_directory"] == str(Path.home() / "image_results")

            # Verify similarity configuration
            assert loaded_profile.similarity is not None
            assert loaded_profile.similarity["phash_threshold"] == 8
            assert loaded_profile.similarity["whash_threshold"] == 10
            assert loaded_profile.similarity["enabled_algorithms"] == ["phash", "whash"]
            assert loaded_profile.similarity["cross_algorithm_comparison"] is True

    def test_profile_path_persistence_with_special_characters(self):
        """Test path persistence with special characters and unicode paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile with paths containing special characters
            profile = SettingsProfile(
                name="Special Path Test",
                description="Test paths with special characters",
                hash_algorithm="xxh3"
            )

            # Configure pools with special character paths
            profile.pools = {
                "A": {
                    "paths": [
                        str(Path.home() / "Documents" / "My Pictures (2023)"),
                        "/media/user/Photos & Videos",
                        "~/Pictures/Screenshots tést",
                        "/mnt/nas/[backup] images"
                    ],
                    "recurse": True,
                    "max_depth": 3,
                    "include": ["**/*.jpg", "**/*.png"],
                    "exclude": ["**/temp/**", "**/* (copy)/**"],
                    "follow_symlinks": False,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".png"]
                }
            }

            # Create and save profile
            created_profile = manager.create(profile)

            # Load in new manager instance
            manager2 = JSONProfilesManager(settings_dir)
            loaded_profile = manager2.get_by_id(created_profile.id)

            # Verify special character paths are preserved
            assert loaded_profile is not None
            assert loaded_profile.pools is not None
            pool_a = loaded_profile.pools["A"]

            expected_paths = [
                str(Path.home() / "Documents" / "My Pictures (2023)"),
                "/media/user/Photos & Videos",
                "~/Pictures/Screenshots tést",
                "/mnt/nas/[backup] images"
            ]
            assert pool_a["paths"] == expected_paths
            assert pool_a["exclude"] == ["**/temp/**", "**/* (copy)/**"]

    def test_profile_path_persistence_round_trip_verification(self):
        """Test complete round-trip verification of path persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"

            # Test with unified manager for complete workflow
            from pk_py_lib.core.settings.json_unified_manager import JSONSettingsManager as UnifiedJSONSettingsManager

            manager = UnifiedJSONSettingsManager(settings_dir)

            # Load initial settings
            initial = manager.load_all()
            original_profile_count = len(initial["profiles"])

            # Create test profile with complex path configuration
            test_profile = SettingsProfile(
                name="Round Trip Test",
                description="Test complete round-trip path persistence",
                hash_algorithm="whash",
                hash_size=16,
                similarity_threshold=0.85
            )

            # Add comprehensive pool configuration
            test_profile.pools = {
                "main": {
                    "paths": [
                        "/home/user/Pictures",
                        "/home/user/Documents/Images",
                        "~/Downloads/Photos"
                    ],
                    "recurse": True,
                    "max_depth": 10,
                    "include": ["**/*"],
                    "exclude": [],
                    "follow_symlinks": True,
                    "include_hidden": False,
                    "type_filters": [".jpg", ".jpeg", ".png", ".gif", ".webp"]
                }
            }

            # Add via profiles manager
            manager.profiles.create(test_profile)

            # Save all settings
            manager.save_all(initial["app_settings"], manager.profiles.get_all())

            # Create new manager instance and load
            manager2 = UnifiedJSONSettingsManager(settings_dir)
            reloaded = manager2.load_all()

            # Verify profile count increased
            assert len(reloaded["profiles"]) == original_profile_count + 1

            # Find our test profile
            test_profile_loaded = None
            for profile in reloaded["profiles"]:
                if profile.name == "Round Trip Test":
                    test_profile_loaded = profile
                    break

            assert test_profile_loaded is not None

            # Verify all path data is preserved exactly
            assert test_profile_loaded.pools is not None
            assert "main" in test_profile_loaded.pools

            main_pool = test_profile_loaded.pools["main"]
            assert main_pool["paths"] == [
                "/home/user/Pictures",
                "/home/user/Documents/Images",
                "~/Downloads/Photos"
            ]
            assert main_pool["recurse"] is True
            assert main_pool["max_depth"] == 10
            assert main_pool["include"] == ["**/*"]
            assert main_pool["exclude"] == []
            assert main_pool["follow_symlinks"] is True
            assert main_pool["include_hidden"] is False
            assert main_pool["type_filters"] == [".jpg", ".jpeg", ".png", ".gif", ".webp"]

            # Verify other profile settings
            assert test_profile_loaded.hash_algorithm == "whash"
            assert test_profile_loaded.hash_size == 16
            assert test_profile_loaded.similarity_threshold == 0.85


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_very_long_profile_names(self):
        """Test handling of very long profile names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONProfilesManager(settings_dir)

            # Create profile with long name
            long_name = "A" * 100
            profile = SettingsProfile(name=long_name, hash_algorithm="xxh3")

            # Should handle gracefully or validate appropriately
            try:
                created = manager.create(profile)
                # If created, should be retrievable
                retrieved = manager.get_by_id(created.id)
                assert retrieved.name == long_name
            except ValueError:
                # Should fail validation if name too long
                pass

    def test_special_characters_in_paths(self):
        """Test handling of special characters in paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directory with special characters
            special_dir = Path(tmpdir) / "settings with spaces & symbols"
            manager = JSONSettingsManager(special_dir)

            # Should handle gracefully
            settings = manager.load_app_settings()
            assert settings["version"] == APP_SETTINGS_SCHEMA_VERSION

    def test_empty_directory_operations(self):
        """Test operations on empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"

            # Ensure directory is empty
            if settings_dir.exists():
                shutil.rmtree(settings_dir)

            manager = UnifiedJSONSettingsManager(settings_dir)

            # Should create defaults
            data = manager.load_all()
            assert data["app_settings"] is not None
            assert len(data["profiles"]) > 0

    def test_permission_errors(self):
        """Test handling of permission errors."""
        # Skip on Windows if we can't create read-only files
        pytest.importorskip("os")
        import os
        import stat

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_dir = Path(tmpdir) / "settings"
            manager = JSONSettingsManager(settings_dir)

            # Create settings file
            settings = manager.load_app_settings()

            # Make file read-only
            app_settings_file = manager.app_settings_file
            if app_settings_file.exists():
                os.chmod(app_settings_file, stat.S_IRUSR)  # Read-only

                try:
                    # Try to save - should handle gracefully
                    settings["cache_enabled"] = False
                    manager.save_app_settings(settings)

                    # File should still be readable
                    reloaded = manager.load_app_settings()
                    # Should either succeed or create defaults
                    assert reloaded is not None

                finally:
                    # Restore permissions for cleanup
                    os.chmod(app_settings_file, stat.S_IWUSR)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
