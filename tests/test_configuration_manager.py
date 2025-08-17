"""
tests/test_configuration_manager.py

Unit tests for ConfigurationManager get/set operations and profile management.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from src.pk_py_lib.core.database import DatabaseManager
from src.pk_py_lib.core.configuration import ConfigurationManager


def test_app_and_profile_settings_roundtrip(tmp_path: Path):
    data_dir = Path(tmp_path) / "appdata"
    data_dir.mkdir(parents=True)
    db_mgr = DatabaseManager(data_dir=data_dir)
    db_mgr.initialize()

    cfg = ConfigurationManager(db_mgr)

    # App-level setting read/write
    orig_cache_mb = cfg.get_app_setting("cache_size_mb")
    assert isinstance(orig_cache_mb, int)
    new_val = 1234
    cfg.set_app_setting("cache_size_mb", new_val)
    assert cfg.get_app_setting("cache_size_mb") == new_val

    # Profile creation and setting
    profile = cfg.create_profile("test-profile")
    assert profile.name == "test-profile"
    cfg.switch_profile("test-profile")
    cfg.set_profile_setting("file_handling.auto_scan", False)
    assert cfg.get_profile_setting("file_handling.auto_scan") is False

    # Clean up: reset app setting
    cfg.set_app_setting("cache_size_mb", orig_cache_mb)