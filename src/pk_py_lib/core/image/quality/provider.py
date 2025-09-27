"""
src/pk_py_lib/core/image/quality/provider.py

Provider for accessing the active ImageQualityEvaluator based on settings profiles.

This module acts as the entry point for the image quality subsystem, retrieving and instantiating
the active evaluator configured in the settings. It integrates with the settings profiles system
to read the 'image_quality_evaluator' key (default: 'brisque') and uses the registry to resolve
the evaluator class. If the configured key is invalid, it logs a warning and falls back to the
default 'brisque' evaluator.

Key features:
- Lazy instantiation: Evaluators are created only when requested.
- Settings integration: Reads from active profile via get_active_profile_settings().
- Fallback mechanism: Ensures a valid evaluator is always available.
- Setter for dynamic switching: Updates settings and returns new instance.
- Error handling: Logs issues and raises if no fallback possible.

Usage
-----
from pk_py_lib.core.image.quality.provider import get_active_image_quality_evaluator

# Get the active evaluator (e.g., BRISQUE by default)
evaluator = get_active_image_quality_evaluator()

# Evaluate an image
score = evaluator.evaluate("/path/to/image.jpg")  # e.g., 74.7 (higher better, normalized)

# Switch evaluator (updates settings)
new_evaluator = set_active_evaluator("custom")  # If registered
"""

from typing import Optional

from pk_py_lib.core.image.quality.base import ImageQualityEvaluator
from pk_py_lib.core.image.quality.registry import ImageQualityEvaluatorRegistry
from pk_py_lib.core.logging import get_logger
from pk_py_lib.core.settings_profiles import get_active_profile_settings


class ImageQualityProviderError(Exception):
    """Raised for provider-specific errors, such as failed settings retrieval or instantiation."""
    pass


_logger = get_logger(__name__)


def get_active_image_quality_evaluator() -> ImageQualityEvaluator:
    """Retrieve and instantiate the active image quality evaluator based on current settings.
    
    This function:
    1. Fetches the active profile settings.
    2. Extracts the 'image_quality_evaluator' key (defaults to 'brisque' if missing).
    3. Resolves the evaluator class via the registry.
    4. Instantiates and returns the evaluator.
    5. Falls back to 'brisque' on invalid keys, logging a warning.
    
    All evaluators return normalized scores where higher values indicate higher image quality.
    
    If settings retrieval fails (e.g., no active profile), initializes a default profile
    and uses 'brisque'.
    
    Returns
    -------
    ImageQualityEvaluator
        Instantiated evaluator (e.g., BRISQUEImageQualityEvaluator).
    
    Raises
    ------
    ImageQualityProviderError
        If fallback instantiation fails (rare, as 'brisque' is always registered).
    RuntimeError
        If settings_profiles module fails critically.
    
    Examples
    --------
    # Default usage
    evaluator = get_active_image_quality_evaluator()  # BRISQUE instance
    
    # With custom settings (e.g., 'image_quality_evaluator': 'custom' in profile)
    score = evaluator.evaluate("/path/to/img.jpg")  # Normalized higher-better score
    
    # Fallback logging (if settings has invalid key)
    # Logs: "Invalid evaluator 'invalid_key'; falling back to 'brisque'"
    """
    try:
        # Step 1: Get active settings
        settings = get_active_profile_settings()
        if not isinstance(settings, dict):
            _logger.warning("Active profile settings is not a dict; using default 'brisque'")
            key = "brisque"
        else:
            # Step 2: Extract key with default
            key = settings.get("image_quality_evaluator", "brisque")
            if not isinstance(key, str):
                _logger.warning("Settings 'image_quality_evaluator' is not a string; using default 'brisque'")
                key = "brisque"

        # Step 3: Resolve and instantiate
        evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(key)
        evaluator = evaluator_class()  # Assumes no-args constructor; extend if params needed

        # Step 4: Log selection
        _logger.debug(f"Selected image quality evaluator: '{key}' ({evaluator_class.__name__})")

        return evaluator

    except ValueError as e:
        # Invalid key from registry
        _logger.warning(f"Invalid evaluator key '{key}' from settings; falling back to 'brisque': {e}")
        try:
            fallback_class = ImageQualityEvaluatorRegistry.get_evaluator_class("brisque")
            return fallback_class()
        except ValueError:
            # Should not happen as 'brisque' is auto-registered
            raise ImageQualityProviderError("Fallback to 'brisque' failed; registry corrupted") from e
    except Exception as e:
        # Catch settings or instantiation errors
        _logger.error(f"Failed to get active evaluator: {e}", exc_info=True)
        # Final fallback: Force 'brisque'
        try:
            fallback_class = ImageQualityEvaluatorRegistry.get_evaluator_class("brisque")
            _logger.info("Forced fallback to 'brisque' evaluator")
            return fallback_class()
        except Exception as fallback_e:
            raise ImageQualityProviderError(f"Critical failure in provider; cannot instantiate any evaluator: {fallback_e}") from fallback_e


def set_active_evaluator(key: str) -> ImageQualityEvaluator:
    """Set the active image quality evaluator by updating settings and return the new instance.

    This function:
    1. Validates the key against the registry.
    2. Updates the active profile settings with the new key.
    3. Instantiates and returns the evaluator.
    4. Logs the change.

    If the key is invalid, raises ValueError. If settings update fails, rolls back and raises.

    Parameters
    ----------
    key : str
        The evaluator key to set (e.g., 'brisque', 'custom'). Must be registered.

    Returns
    -------
    ImageQualityEvaluator
        The newly instantiated evaluator for the set key.

    Raises
    ------
    ValueError
        If the key is unknown (not registered).
    ImageQualityProviderError
        If settings update or instantiation fails.
    RuntimeError
        From underlying settings_profiles if profile management fails.

    Examples
    --------
    # Switch to a registered evaluator
    evaluator = set_active_evaluator("brisque")  # Updates settings, returns BRISQUE

    # Error on unknown key
    try:
        set_active_evaluator("unknown")
    except ValueError as e:
        # e.message: "Unknown image quality evaluator: 'unknown'"
        pass

    Notes
    -----
    - This persists the change in the active profile's json_data.
    - If no active profile exists, creates a default one first.
    - Subsequent calls to get_active_image_quality_evaluator() will use the new setting.
    """
    # Step 1: Validate key
    try:
        evaluator_class = ImageQualityEvaluatorRegistry.get_evaluator_class(key)
    except ValueError as e:
        _logger.error(f"Cannot set evaluator '{key}': {e}")
        raise ValueError(f"Invalid evaluator key '{key}'; must be registered") from e

    try:
        # Step 2: Update settings (this handles profile creation if needed)
        from pk_py_lib.core.settings_profiles import SettingsProfilesManager, DatabaseManager
        db = DatabaseManager()
        mgr = SettingsProfilesManager(db)
        active_profile = mgr.get_active_profile()
        if active_profile is None:
            # Ensure default profile exists
            active_profile = mgr.ensure_default_profile()

        # Update json_data with new key (assumes JSON format; migrates if legacy)
        if not active_profile.is_json_format():
            # Migrate legacy to JSON if needed
            active_profile = mgr.migrate_to_json_format(active_profile.id)

        settings = active_profile.json_data.copy()
        settings["image_quality_evaluator"] = key
        mgr.update_structured_profile(active_profile.id, settings)

        # Step 3: Instantiate and return
        evaluator = evaluator_class()
        _logger.info(f"Set active image quality evaluator to '{key}' ({evaluator_class.__name__}); updated profile {active_profile.id}")

        return evaluator

    except Exception as e:
        _logger.error(f"Failed to update settings for evaluator '{key}': {e}", exc_info=True)
        raise ImageQualityProviderError(f"Settings update failed for key '{key}': {e}") from e


__all__ = [
    "get_active_image_quality_evaluator",
    "set_active_evaluator",
    "ImageQualityProviderError"
]