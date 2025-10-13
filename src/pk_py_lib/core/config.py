"""
Application configuration.
"""

from pathlib import Path


class AppConfig:
    """
    Application configuration settings.
    """

    def __init__(self):
        self.data_dir = self._get_data_dir()
        self.db_path = self.data_dir / "settings.db"

    def _get_data_dir(self) -> Path:
        """
        Get the application data directory.
        """
        # This is a simplified implementation. A real application might use
        # platform-specific directories.
        return Path.home() / ".pk-py-lib"
