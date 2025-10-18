"""
Application configuration.
"""

from pathlib import Path


class AppConfig:
    """
    Application configuration settings.

    This configuration now uses JSON files for settings storage instead of SQLite database.
    """

    def __init__(self):
        self.data_dir = self._get_data_dir()
        # Settings files are now stored directly in data_dir (same level as flat_cache.db)
        self.settings_dir = self.data_dir  # For backward compatibility, but files are in data_dir
        self.app_settings_file = self.data_dir / "app-settings.json"
        self.search_profiles_file = self.data_dir / "search-profiles.json"

    def _get_data_dir(self) -> Path:
        """
        Get the application data directory.

        Returns
        -------
        Path
            Platform-specific data directory for the application.
        """
        # Use the unified data directory
        from .utils import get_data_dir
        return get_data_dir()
