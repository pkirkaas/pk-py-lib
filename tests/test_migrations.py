"""
tests/test_migrations.py

Test the migration path from schema 1.0.0 (profiles containing UI/perf fields)
to schema 1.1.0 (app_settings single-row).
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from src.pk_py_lib.core.database import DatabaseManager, SETTINGS_SCHEMA
import os


def create_legacy_settings_db(path: Path) -> None:
    """
    Create a legacy settings.db with UI/perf fields on profiles (simulating v1.0.0).
    """
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    # Legacy schema: profiles with ui/perf columns and no app_settings table
    cur.executescript(
        """
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            theme TEXT,
            language TEXT,
            ui_scale REAL,
            max_threads INTEGER,
            max_memory_mb INTEGER,
            cache_size_gb REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO profiles (name, is_default, theme, language, ui_scale, max_threads, max_memory_mb, cache_size_gb)
        VALUES ('Default', 1, 'dark', 'fr', 1.25, 8, 4096, 5.0);
        """
    )
    conn.commit()
    conn.close()


def test_migrate_1_0_to_1_1(tmp_path: Path):
    data_dir = Path(tmp_path) / "appdata"
    data_dir.mkdir(parents=True)
    db_path = data_dir / "settings.db"

    # Create legacy DB
    create_legacy_settings_db(db_path)

    # Initialize DatabaseManager pointing to this data_dir
    db_mgr = DatabaseManager(data_dir=data_dir)
    # This should detect version missing and run migration path to create app_settings
    db_mgr.initialize()

    # Validate app_settings exists and contains migrated values
    conn = sqlite3.connect(str(db_mgr.settings_db))
    cur = conn.cursor()
    cur.execute("SELECT theme, language, ui_scale, max_threads, max_memory_mb, cache_size_mb FROM app_settings LIMIT 1")
    row = cur.fetchone()
    assert row is not None, "app_settings row should exist after migration"
    theme, language, ui_scale, max_threads, max_memory_mb, cache_size_mb = row
    assert theme == "dark"
    assert language == "fr"
    assert abs(ui_scale - 1.25) < 0.001
    assert int(max_threads) == 8
    assert int(max_memory_mb) == 4096
    # Legacy 5.0 GB -> 5120 MB expected (rounded within migration logic)
    assert int(cache_size_mb) == 5120

    # Validate profiles table no longer contains legacy UI columns (pragmatically check PRAGMA)
    cur.execute("PRAGMA table_info(profiles)")
    cols = [r[1] for r in cur.fetchall()]
    assert "theme" not in cols
    assert "cache_size_gb" not in cols

    conn.close()