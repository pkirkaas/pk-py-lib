"""
Tests for unified settings architecture.

Tests the new consolidated settings system including:
- Data models (AppSettings, SettingsProfile)
- Database schema
- Migration utilities

This test suite provides comprehensive coverage for Phase 1
of the settings consolidation plan.
"""

import pytest
from datetime import datetime
from pathlib import Path

from pk_py_lib.core.settings.app_settings import AppSettingsManager
from pk_py_lib.core.settings.profiles import ProfilesManager


class TestAppSettings:
    """Tests for AppSettings model."""

    def test_default_values(self):
        """Test that AppSettings has sensible defaults."""
        settings = AppSettings()
        assert settings.cache_enabled is True
        assert settings.cache_size_mb == 500
        assert settings.max_workers == 4
        assert settings.gui_theme == 'auto'
        assert settings.log_level == 'INFO'
        assert settings.recent_directories == []
        assert settings.window_geometry is None
        assert settings.default_profile_id is None
        assert settings.last_updated is None

    def test_custom_values(self):
        """Test creating AppSettings with custom values."""
        settings = AppSettings(
            cache_enabled=False,
            cache_size_mb=1000,
            max_workers=8,
            gui_theme='dark',
            log_level='DEBUG',
        )
        assert settings.cache_enabled is False
        assert settings.cache_size_mb == 1000
        assert settings.max_workers == 8
        assert settings.gui_theme == 'dark'
        assert settings.log_level == 'DEBUG'

    def test_to_dict(self):
        """Test conversion to dictionary."""
        settings = AppSettings(
            cache_enabled=False,
            cache_size_mb=1000,
            max_workers=8,
            gui_theme='dark',
            recent_directories=['/home/user/photos'],
        )
        data = settings.to_dict()

        assert data['cache_enabled'] is False
        assert data['cache_size_mb'] == 1000
        assert data['max_workers'] == 8
        assert data['gui_theme'] == 'dark'
        assert data['recent_directories'] == ['/home/user/photos']

    def test_to_dict_with_timestamp(self):
        """Test to_dict converts timestamps to ISO strings."""
        now = datetime.now()
        settings = AppSettings(last_updated=now)
        data = settings.to_dict()

        assert 'last_updated' in data
        assert isinstance(data['last_updated'], str)
        assert data['last_updated'] == now.isoformat()

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            'cache_enabled': False,
            'cache_size_mb': 1000,
            'max_workers': 8,
            'gui_theme': 'dark',
            'log_level': 'WARNING',
            'recent_directories': ['/test/path'],
        }
        settings = AppSettings.from_dict(data)

        assert settings.cache_enabled is False
        assert settings.cache_size_mb == 1000
        assert settings.max_workers == 8
        assert settings.gui_theme == 'dark'
        assert settings.log_level == 'WARNING'
        assert settings.recent_directories == ['/test/path']

    def test_from_dict_with_timestamp(self):
        """Test from_dict parses ISO timestamp strings."""
        now = datetime.now()
        data = {
            'cache_size_mb': 500,
            'last_updated': now.isoformat(),
        }
        settings = AppSettings.from_dict(data)

        assert settings.last_updated is not None
        assert isinstance(settings.last_updated, datetime)
        # Compare as strings to avoid microsecond precision issues
        assert settings.last_updated.isoformat() == now.isoformat()

    def test_round_trip(self):
        """Test that to_dict/from_dict roundtrip works correctly."""
        original = AppSettings(
            cache_enabled=False,
            cache_size_mb=2048,
            max_workers=16,
            gui_theme='light',
            recent_directories=['/a', '/b'],
        )

        data = original.to_dict()
        restored = AppSettings.from_dict(data)

        assert restored.cache_enabled == original.cache_enabled
        assert restored.cache_size_mb == original.cache_size_mb
        assert restored.max_workers == original.max_workers
        assert restored.gui_theme == original.gui_theme
        assert restored.recent_directories == original.recent_directories


class TestSettingsProfile:
    """Tests for SettingsProfile model."""

    def test_default_values(self):
        """Test that SettingsProfile has sensible defaults."""
        profile = SettingsProfile(name="Test")

        assert profile.name == "Test"
        assert profile.id is None
        assert profile.description == ""
        assert profile.hash_algorithm == "phash"
        assert profile.hash_size == 8
        assert profile.similarity_threshold == 0.95
        assert profile.min_resolution is None
        assert profile.max_resolution is None
        assert profile.color_mode is False
        assert profile.clustering_method == "dbscan"
        assert profile.quality_threshold is None
        assert profile.is_default is False
        assert profile.is_system is False
        assert profile.created_at is None
        assert profile.updated_at is None

    def test_custom_values(self):
        """Test creating SettingsProfile with custom values."""
        profile = SettingsProfile(
            name="Custom Profile",
            id=42,
            description="A custom profile for testing",
            hash_algorithm="whash",
            hash_size=16,
            similarity_threshold=0.85,
            min_resolution=100,
            max_resolution=10000,
            color_mode=True,
            clustering_method="agglomerative",
            quality_threshold=0.7,
            is_default=True,
            is_system=False,
        )

        assert profile.name == "Custom Profile"
        assert profile.id == 42
        assert profile.description == "A custom profile for testing"
        assert profile.hash_algorithm == "whash"
        assert profile.hash_size == 16
        assert profile.similarity_threshold == 0.85
        assert profile.min_resolution == 100
        assert profile.max_resolution == 10000
        assert profile.color_mode is True
        assert profile.clustering_method == "agglomerative"
        assert profile.quality_threshold == 0.7
        assert profile.is_default is True
        assert profile.is_system is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        profile = SettingsProfile(
            name="Test Profile",
            id=1,
            hash_algorithm="whash",
            similarity_threshold=0.90,
            is_system=True,
        )
        data = profile.to_dict()

        assert data['name'] == "Test Profile"
        assert data['id'] == 1
        assert data['hash_algorithm'] == "whash"
        assert data['similarity_threshold'] == 0.90
        assert data['is_system'] is True

    def test_to_dict_with_timestamps(self):
        """Test to_dict converts timestamps to ISO strings."""
        now = datetime.now()
        profile = SettingsProfile(
            name="Test",
            created_at=now,
            updated_at=now,
        )
        data = profile.to_dict()

        assert 'created_at' in data
        assert 'updated_at' in data
        assert isinstance(data['created_at'], str)
        assert isinstance(data['updated_at'], str)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            'name': 'Test Profile',
            'id': 5,
            'hash_algorithm': 'whash',
            'similarity_threshold': 0.85,
            'description': 'Test description',
            'is_default': True,
        }
        profile = SettingsProfile.from_dict(data)

        assert profile.name == 'Test Profile'
        assert profile.id == 5
        assert profile.hash_algorithm == 'whash'
        assert profile.similarity_threshold == 0.85
        assert profile.description == 'Test description'
        assert profile.is_default is True

    def test_from_dict_with_timestamps(self):
        """Test from_dict parses ISO timestamp strings."""
        now = datetime.now()
        data = {
            'name': 'Test',
            'created_at': now.isoformat(),
            'updated_at': now.isoformat(),
        }
        profile = SettingsProfile.from_dict(data)

        assert profile.created_at is not None
        assert profile.updated_at is not None
        assert isinstance(profile.created_at, datetime)
        assert isinstance(profile.updated_at, datetime)

    def test_clone(self):
        """Test profile cloning."""
        original = SettingsProfile(
            name="Original",
            id=10,
            hash_algorithm="whash",
            similarity_threshold=0.90,
            min_resolution=500,
            is_default=True,
        )

        cloned = original.clone("Cloned")

        # Cloned profile has new name and no ID
        assert cloned.name == "Cloned"
        assert cloned.id is None
        assert cloned.description == "Copy of Original"

        # Settings are copied
        assert cloned.hash_algorithm == "whash"
        assert cloned.similarity_threshold == 0.90
        assert cloned.min_resolution == 500

        # Flags are reset
        assert cloned.is_default is False
        assert cloned.is_system is False

    def test_clone_preserves_all_settings(self):
        """Test that clone preserves all relevant settings."""
        original = SettingsProfile(
            name="Original",
            hash_algorithm="phash",
            hash_size=16,
            similarity_threshold=0.88,
            min_resolution=100,
            max_resolution=5000,
            color_mode=True,
            clustering_method="agglomerative",
            quality_threshold=0.65,
        )

        cloned = original.clone("Clone")

        assert cloned.hash_algorithm == original.hash_algorithm
        assert cloned.hash_size == original.hash_size
        assert cloned.similarity_threshold == original.similarity_threshold
        assert cloned.min_resolution == original.min_resolution
        assert cloned.max_resolution == original.max_resolution
        assert cloned.color_mode == original.color_mode
        assert cloned.clustering_method == original.clustering_method
        assert cloned.quality_threshold == original.quality_threshold

    def test_round_trip(self):
        """Test that to_dict/from_dict roundtrip works correctly."""
        original = SettingsProfile(
            name="Test Profile",
            id=99,
            description="Test description",
            hash_algorithm="whash",
            similarity_threshold=0.87,
            is_system=True,
        )

        data = original.to_dict()
        restored = SettingsProfile.from_dict(data)

        assert restored.name == original.name
        assert restored.id == original.id
        assert restored.description == original.description
        assert restored.hash_algorithm == original.hash_algorithm
        assert restored.similarity_threshold == original.similarity_threshold
        assert restored.is_system == original.is_system


class TestDefaultProfiles:
    """Tests for default system profiles."""

    def test_default_profiles_exist(self):
        """Test that default system profiles are defined."""
        assert len(DEFAULT_PROFILES) >= 3
        assert all(isinstance(p, SettingsProfile) for p in DEFAULT_PROFILES)

    def test_default_profiles_are_system(self):
        """Test that all default profiles are marked as system."""
        assert all(p.is_system for p in DEFAULT_PROFILES)

    def test_one_default_profile(self):
        """Test that exactly one profile is marked as default."""
        default_count = sum(1 for p in DEFAULT_PROFILES if p.is_default)
        assert default_count == 1

    def test_default_profile_names(self):
        """Test that default profiles have expected names."""
        names = {p.name for p in DEFAULT_PROFILES}
        assert "Default" in names

    def test_exact_duplicates_profile(self):
        """Test Exact Duplicates profile has correct settings."""
        exact = next(p for p in DEFAULT_PROFILES if p.name == "Exact Duplicates")
        assert exact.similarity_threshold == 1.0
        assert exact.is_default is True
        assert exact.is_system is True

    def test_profiles_have_descriptions(self):
        """Test that all default profiles have descriptions."""
        assert all(p.description for p in DEFAULT_PROFILES)

    def test_profiles_have_unique_names(self):
        """Test that all default profiles have unique names."""
        names = [p.name for p in DEFAULT_PROFILES]
        assert len(names) == len(set(names))


class TestMigrationUtilities:
    """Tests for migration utilities (stubs for Phase 2)."""

    def test_migration_class_exists(self):
        """Test that SettingsMigration class can be imported."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration
        assert SettingsMigration is not None

    def test_migration_init(self):
        """Test that SettingsMigration can be initialized."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        db_path = Path("test.db")
        migration = SettingsMigration(db_path)

        assert migration.db_path == db_path
        assert migration.backup_path is None

    def test_migration_methods_exist(self):
        """Test that SettingsMigration has expected methods."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        migration = SettingsMigration(Path("test.db"))

        # Check all expected methods exist
        assert hasattr(migration, 'needs_migration')
        assert hasattr(migration, 'create_backup')
        assert hasattr(migration, 'migrate_app_settings')
        assert hasattr(migration, 'migrate_profiles')
        assert hasattr(migration, 'validate_migration')
        assert hasattr(migration, 'rollback')
        assert hasattr(migration, 'get_migration_report')

    def test_needs_migration_returns_bool(self):
        """Test that needs_migration returns a boolean."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        migration = SettingsMigration(Path("test.db"))
        result = migration.needs_migration()

        assert isinstance(result, bool)

    def test_migration_report_structure(self):
        """Test that get_migration_report returns expected structure."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        migration = SettingsMigration(Path("test.db"))
        report = migration.get_migration_report()

        # Check expected keys exist
        assert 'success' in report
        assert 'profiles_migrated' in report
        assert 'settings_migrated' in report
        assert isinstance(report, dict)


class TestSettingsMigrationLogic:
    """Tests for settings migration implementation."""

    def test_needs_migration_with_no_database(self, tmp_path):
        """Test migration detection when database doesn't exist."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        db_path = tmp_path / "nonexistent.db"
        migration = SettingsMigration(db_path)

        # Should return False if database doesn't exist
        assert migration.needs_migration() is False

    def test_create_backup_success(self, tmp_path):
        """Test successful backup creation."""
        import sqlite3
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        # Create a test database
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.close()

        # Create backup
        migration = SettingsMigration(db_path)
        backup_path = migration.create_backup()

        # Verify backup exists
        assert backup_path.exists()
        assert backup_path.parent.name == "backups"

        # Verify backup is valid
        test_conn = sqlite3.connect(str(backup_path))
        cursor = test_conn.execute("SELECT * FROM test")
        assert cursor.fetchone()[0] == 1
        test_conn.close()

    def test_create_backup_nonexistent_database(self, tmp_path):
        """Test backup creation fails for nonexistent database."""
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        db_path = tmp_path / "nonexistent.db"
        migration = SettingsMigration(db_path)

        # Should raise IOError
        import pytest
        with pytest.raises(IOError):
            migration.create_backup()

    def test_migrate_app_settings_with_old_data(self, tmp_path):
        """Test app settings migration with old format data."""
        import sqlite3
        import json
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        # Create old-style database
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE app_settings (
                theme TEXT, max_threads INTEGER, cache_size_mb INTEGER,
                window_geometry TEXT
            )
        """)
        conn.execute("""
            INSERT INTO app_settings VALUES ('dark', 8, 1024, '{"x":100,"y":200}')
        """)
        conn.close()

        # Migrate
        migration = SettingsMigration(db_path)
        settings = migration.migrate_app_settings()

        # Verify migration
        assert settings['gui_theme'] == 'dark'
        assert settings['max_workers'] == 8
        assert settings['cache_size_mb'] == 1024

    def test_migrate_profiles_creates_defaults(self, tmp_path):
        """Test profile migration creates defaults when no profiles exist."""
        import sqlite3
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        # Create empty database
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        conn.close()

        # Migrate
        migration = SettingsMigration(db_path)
        profiles = migration.migrate_profiles()

        # Should create default profiles
        assert len(profiles) >= 1
        assert any(p['name'] == 'Default' for p in profiles)

    def test_rollback_restores_backup(self, tmp_path):
        """Test rollback restores from backup."""
        import sqlite3
        from pk_py_lib.core.migrations.settings_migration import SettingsMigration

        # Create test database
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (value TEXT)")
        conn.execute("INSERT INTO test VALUES ('original')")
        conn.close()

        # Create backup
        migration = SettingsMigration(db_path)
        backup_path = migration.create_backup()

        # Modify database
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE test SET value = 'modified'")
        conn.close()

        # Rollback
        success = migration.rollback()
        assert success is True

        # Verify restored
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT value FROM test")
        assert cursor.fetchone()[0] == 'original'
        conn.close()


class TestAppSettingsManager:
    """Tests for AppSettingsManager."""

    def test_init_creates_schema(self, tmp_path):
        """Test initialization creates database schema."""
        from pk_py_lib.core.settings.app_settings import AppSettingsManager

        db_path = tmp_path / "settings.db"
        manager = AppSettingsManager(db_path)

        # Verify table exists
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings_v2'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_load_creates_defaults(self, tmp_path):
        """Test load creates default settings if none exist."""
        from pk_py_lib.core.settings.app_settings import AppSettingsManager

        db_path = tmp_path / "settings.db"
        manager = AppSettingsManager(db_path)
        settings = manager.load()

        # Verify defaults
        assert settings.cache_enabled is True
        assert settings.cache_size_mb == 500
        assert settings.max_workers == 4
        assert settings.gui_theme == 'auto'

    def test_save_and_load(self, tmp_path):
        """Test saving and loading settings."""
        from pk_py_lib.core.settings.app_settings import AppSettingsManager
        from pk_py_lib.core.models.settings import AppSettings

        db_path = tmp_path / "settings.db"
        manager = AppSettingsManager(db_path)

        # Create custom settings
        settings = AppSettings(
            cache_enabled=False,
            cache_size_mb=2048,
            max_workers=16,
            gui_theme='dark',
            log_level='DEBUG',
        )

        # Save
        manager.save(settings)

        # Load in new manager instance
        manager2 = AppSettingsManager(db_path)
        loaded = manager2.load()

        # Verify
        assert loaded.cache_enabled is False
        assert loaded.cache_size_mb == 2048
        assert loaded.max_workers == 16
        assert loaded.gui_theme == 'dark'
        assert loaded.log_level == 'DEBUG'

    def test_cache_enabled_getset(self, tmp_path):
        """Test cache enabled getter/setter."""
        from pk_py_lib.core.settings.app_settings import AppSettingsManager

        db_path = tmp_path / "settings.db"
        manager = AppSettingsManager(db_path)

        # Set
        manager.set_cache_enabled(False)

        # Get
        assert manager.get_cache_enabled() is False

    def test_theme_validation(self, tmp_path):
        """Test theme validation."""
        from pk_py_lib.core.settings.app_settings import AppSettingsManager
        import pytest

        db_path = tmp_path / "settings.db"
        manager = AppSettingsManager(db_path)

        # Valid themes
        manager.set_gui_theme('light')
        assert manager.get_gui_theme() == 'light'

        manager.set_gui_theme('dark')
        assert manager.get_gui_theme() == 'dark'

        # Invalid theme
        with pytest.raises(ValueError):
            manager.set_gui_theme('invalid')


class TestProfilesManager:
    """Tests for ProfilesManager."""

    def test_init_creates_defaults(self, tmp_path):
        """Test initialization creates default profiles."""
        from pk_py_lib.core.settings.profiles import ProfilesManager

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Verify default profiles exist
        profiles = manager.get_all()
        assert len(profiles) >= 3

        # Verify default profile names
        names = {p.name for p in profiles}
        assert 'Default' in names

    def test_create_profile(self, tmp_path):
        """Test creating a new profile."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        from pk_py_lib.core.models.settings import SettingsProfile

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Create profile
        profile = SettingsProfile(
            name="Custom Profile",
            description="Test profile",
            hash_algorithm="whash",
            similarity_threshold=0.85,
        )

        created = manager.create(profile)

        # Verify
        assert created.id is not None
        assert created.name == "Custom Profile"
        assert created.hash_algorithm == "whash"
        assert created.similarity_threshold == 0.85

    def test_create_duplicate_name_fails(self, tmp_path):
        """Test creating profile with duplicate name fails."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        from pk_py_lib.core.models.settings import SettingsProfile
        import pytest

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Create first profile
        profile1 = SettingsProfile(name="Test", similarity_threshold=0.90)
        manager.create(profile1)

        # Try to create duplicate
        profile2 = SettingsProfile(name="Test", similarity_threshold=0.80)
        with pytest.raises(ValueError, match="already exists"):
            manager.create(profile2)

    def test_get_by_name_case_insensitive(self, tmp_path):
        """Test get_by_name is case-insensitive."""
        from pk_py_lib.core.settings.profiles import ProfilesManager

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Get with different case
        profile1 = manager.get_by_name("exact duplicates")
        profile2 = manager.get_by_name("DEFAULT")
        profile3 = manager.get_by_name("Default")

        # Should all return the same profile
        assert profile1 is not None
        assert profile2 is not None
        assert profile3 is not None
        assert profile1.id == profile2.id == profile3.id

    def test_update_profile(self, tmp_path):
        """Test updating a profile."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        from pk_py_lib.core.models.settings import SettingsProfile

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Create profile
        profile = SettingsProfile(name="Test", similarity_threshold=0.90)
        created = manager.create(profile)

        # Update
        created.similarity_threshold = 0.85
        created.description = "Updated description"
        manager.update(created)

        # Verify
        updated = manager.get_by_id(created.id)
        assert updated.similarity_threshold == 0.85
        assert updated.description == "Updated description"

    def test_cannot_modify_system_profile(self, tmp_path):
        """Test that system profiles cannot be modified."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        import pytest

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Get a system profile
        profile = manager.get_by_name("Default")
        assert profile.is_system is True

        # Try to update
        profile.similarity_threshold = 0.50
        with pytest.raises(ValueError, match="Cannot modify system profiles"):
            manager.update(profile)

    def test_delete_profile(self, tmp_path):
        """Test deleting a profile."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        from pk_py_lib.core.models.settings import SettingsProfile

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Create profile
        profile = SettingsProfile(name="Temp", similarity_threshold=0.80)
        created = manager.create(profile)

        # Delete
        success = manager.delete(created.id)
        assert success is True

        # Verify deleted
        assert manager.get_by_id(created.id) is None

    def test_cannot_delete_system_profile(self, tmp_path):
        """Test that system profiles cannot be deleted."""
        from pk_py_lib.core.settings.profiles import ProfilesManager
        import pytest

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Get a system profile
        profile = manager.get_by_name("Default")

        # Try to delete
        with pytest.raises(ValueError, match="Cannot delete system profiles"):
            manager.delete(profile.id)

    def test_get_default_profile(self, tmp_path):
        """Test getting the default profile."""
        from pk_py_lib.core.settings.profiles import ProfilesManager

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Get default
        default = manager.get_default()

        # Verify
        assert default is not None
        assert default.is_default is True

    def test_set_default_profile(self, tmp_path):
        """Test setting a profile as default."""
        from pk_py_lib.core.settings.profiles import ProfilesManager

        db_path = tmp_path / "settings.db"
        manager = ProfilesManager(db_path)

        # Get the default profile
        profile = manager.get_by_name("Default")
        assert profile.is_default is True

        # Set as default
        manager.set_default(profile.id)

        # Verify
        default = manager.get_default()
        assert default.id == profile.id

class TestSettingsManager:
    """Tests for the unified SettingsManager."""

    def test_init(self, tmp_path):
        """Test that SettingsManager initializes correctly."""
        from pk_py_lib.core.settings.manager import SettingsManager

        db_path = tmp_path / "settings.db"
        manager = SettingsManager(db_path)

        assert isinstance(manager.app_settings, AppSettingsManager)
        assert isinstance(manager.profiles, ProfilesManager)
