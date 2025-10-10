"""
Unified settings data models for the pk-py-lib project.

This module provides the canonical data models for all application settings
and configuration, consolidating the previously fragmented models from
configuration.py and settings_profiles.py.

The unified architecture separates concerns:
- AppSettings: Global application-level settings (single instance)
- SettingsProfile: Named workflow configurations (multiple instances)

Both legacy and modern (JSON schema) profile formats are supported
during the transition period.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path


@dataclass
class AppSettings:
    """
    Application-wide settings that apply globally.

    These settings control application behavior across all profiles
    and persist in the database for the lifetime of the application.

    Attributes
    ----------
    cache_enabled : bool
        Whether hash caching is enabled (default: True)
    cache_size_mb : int
        Maximum cache size in megabytes (default: 500)
    max_workers : int
        Maximum number of worker threads for parallel processing (default: 4)
    default_profile_id : Optional[int]
        ID of the default settings profile to use
    gui_theme : str
        GUI theme name: 'light', 'dark', or 'auto' (default: 'auto')
    log_level : str
        Logging level: 'DEBUG', 'INFO', 'WARNING', 'ERROR' (default: 'INFO')
    recent_directories : List[str]
        List of recently accessed directories (default: empty list)
    window_geometry : Optional[Dict[str, int]]
        Saved window position and size (default: None)
    last_updated : Optional[datetime]
        Timestamp of last settings update (default: None)

    Examples
    --------
    >>> settings = AppSettings(cache_size_mb=1024, gui_theme='dark')
    >>> settings.cache_enabled
    True
    >>> settings.to_dict()
    {'cache_enabled': True, 'cache_size_mb': 1024, ...}
    """

    cache_enabled: bool = True
    cache_size_mb: int = 500
    max_workers: int = 4
    default_profile_id: Optional[int] = None
    gui_theme: str = 'auto'
    log_level: str = 'INFO'
    recent_directories: List[str] = field(default_factory=list)
    window_geometry: Optional[Dict[str, int]] = None
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert settings to dictionary for storage.

        Returns
        -------
        Dict[str, Any]
            Dictionary representation with all fields, timestamps as ISO strings

        Examples
        --------
        >>> settings = AppSettings(cache_size_mb=1024)
        >>> data = settings.to_dict()
        >>> data['cache_size_mb']
        1024
        """
        data = {
            'cache_enabled': self.cache_enabled,
            'cache_size_mb': self.cache_size_mb,
            'max_workers': self.max_workers,
            'default_profile_id': self.default_profile_id,
            'gui_theme': self.gui_theme,
            'log_level': self.log_level,
            'recent_directories': self.recent_directories,
            'window_geometry': self.window_geometry,
        }
        if self.last_updated:
            data['last_updated'] = self.last_updated.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppSettings':
        """
        Create settings from dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            Dictionary with settings data, as produced by to_dict()

        Returns
        -------
        AppSettings
            New AppSettings instance with values from dict

        Examples
        --------
        >>> data = {'cache_size_mb': 2048, 'gui_theme': 'dark'}
        >>> settings = AppSettings.from_dict(data)
        >>> settings.cache_size_mb
        2048
        """
        settings_data = data.copy()
        if 'last_updated' in settings_data and isinstance(settings_data['last_updated'], str):
            settings_data['last_updated'] = datetime.fromisoformat(settings_data['last_updated'])
        return cls(**settings_data)


@dataclass
class SettingsProfile:
    """
    A named configuration profile for image similarity detection.

    Profiles allow users to save and reuse different configurations
    for different use cases (e.g., "strict duplicates", "similar photos").

    Supports both legacy key-value format and modern JSON schema format
    for backward compatibility during migration.

    Attributes
    ----------
    name : str
        Human-readable profile name (required)
    id : Optional[int]
        Unique profile identifier (None for unsaved profiles)
    description : str
        Optional description of profile purpose (default: empty string)
    hash_algorithm : str
        Hash algorithm to use: 'phash', 'whash', 'blake3', 'xxh3' (default: 'phash')
    hash_size : int
        Size of the hash in bits (default: 8)
    similarity_threshold : float
        Similarity threshold from 0.0 (exact match) to 1.0 (any match) (default: 0.95)
    min_resolution : Optional[int]
        Minimum image resolution to process in pixels (default: None)
    max_resolution : Optional[int]
        Maximum image resolution to process in pixels (default: None)
    color_mode : bool
        Whether to use color hashing (default: False)
    clustering_method : str
        Clustering algorithm: 'dbscan', 'agglomerative' (default: 'dbscan')
    quality_threshold : Optional[float]
        Minimum image quality score (default: None)
    is_default : bool
        Whether this is the default profile (default: False)
    is_system : bool
        Whether this is a system profile (non-deletable) (default: False)
    created_at : Optional[datetime]
        Profile creation timestamp (default: None)
    updated_at : Optional[datetime]
        Last update timestamp (default: None)

    Examples
    --------
    >>> profile = SettingsProfile(
    ...     name="High Quality Photos",
    ...     hash_algorithm="phash",
    ...     similarity_threshold=0.90
    ... )
    >>> profile.is_system
    False
    >>> profile.clone("Copy of High Quality")
    SettingsProfile(name='Copy of High Quality', ...)
    """

    name: str
    id: Optional[int] = None
    description: str = ""
    hash_algorithm: str = "phash"
    hash_size: int = 8
    similarity_threshold: float = 0.95
    min_resolution: Optional[int] = None
    max_resolution: Optional[int] = None
    color_mode: bool = False
    clustering_method: str = "dbscan"
    quality_threshold: Optional[float] = None
    is_default: bool = False
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert profile to dictionary for storage.

        Returns
        -------
        Dict[str, Any]
            Dictionary representation with all fields, timestamps as ISO strings

        Examples
        --------
        >>> profile = SettingsProfile(name="Test", similarity_threshold=0.90)
        >>> data = profile.to_dict()
        >>> data['name']
        'Test'
        >>> data['similarity_threshold']
        0.90
        """
        data = {
            'name': self.name,
            'description': self.description,
            'hash_algorithm': self.hash_algorithm,
            'hash_size': self.hash_size,
            'similarity_threshold': self.similarity_threshold,
            'min_resolution': self.min_resolution,
            'max_resolution': self.max_resolution,
            'color_mode': self.color_mode,
            'clustering_method': self.clustering_method,
            'quality_threshold': self.quality_threshold,
            'is_default': self.is_default,
            'is_system': self.is_system,
        }
        if self.id is not None:
            data['id'] = self.id
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SettingsProfile':
        """
        Create profile from dictionary.

        Parameters
        ----------
        data : Dict[str, Any]
            Dictionary with profile data, as produced by to_dict()

        Returns
        -------
        SettingsProfile
            New SettingsProfile instance with values from dict

        Examples
        --------
        >>> data = {
        ...     'name': 'Test Profile',
        ...     'hash_algorithm': 'whash',
        ...     'similarity_threshold': 0.85
        ... }
        >>> profile = SettingsProfile.from_dict(data)
        >>> profile.name
        'Test Profile'
        >>> profile.hash_algorithm
        'whash'
        """
        profile_data = data.copy()
        for dt_field in ('created_at', 'updated_at'):
            if dt_field in profile_data and isinstance(profile_data[dt_field], str):
                profile_data[dt_field] = datetime.fromisoformat(profile_data[dt_field])
        return cls(**profile_data)

    def clone(self, new_name: str) -> 'SettingsProfile':
        """
        Create a copy of this profile with a new name.

        The cloned profile will have the same settings but will be
        a new instance with no ID (unsaved) and updated metadata.

        Parameters
        ----------
        new_name : str
            Name for the cloned profile

        Returns
        -------
        SettingsProfile
            New profile instance with copied settings

        Examples
        --------
        >>> original = SettingsProfile(
        ...     name="Original",
        ...     hash_algorithm="whash",
        ...     similarity_threshold=0.90
        ... )
        >>> cloned = original.clone("Cloned")
        >>> cloned.name
        'Cloned'
        >>> cloned.hash_algorithm
        'whash'
        >>> cloned.id is None
        True
        """
        return SettingsProfile(
            name=new_name,
            description=f"Copy of {self.name}",
            hash_algorithm=self.hash_algorithm,
            hash_size=self.hash_size,
            similarity_threshold=self.similarity_threshold,
            min_resolution=self.min_resolution,
            max_resolution=self.max_resolution,
            color_mode=self.color_mode,
            clustering_method=self.clustering_method,
            quality_threshold=self.quality_threshold,
        )


# Default system profiles that are created on first initialization
DEFAULT_PROFILES = [
    SettingsProfile(
        name="Exact Duplicates",
        description="Find exact duplicate files using cryptographic hashing",
        hash_algorithm="blake3",
        similarity_threshold=1.0,
        is_system=True,
        is_default=True,
    ),
    SettingsProfile(
        name="Very Similar",
        description="Find very similar images with strict matching (95% similarity)",
        hash_algorithm="phash",
        similarity_threshold=0.95,
        is_system=True,
    ),
    SettingsProfile(
        name="Similar Images",
        description="Find similar images with moderate matching (90% similarity)",
        hash_algorithm="phash",
        similarity_threshold=0.90,
        is_system=True,
    ),
]


__all__ = [
    'AppSettings',
    'SettingsProfile',
    'DEFAULT_PROFILES',
]
