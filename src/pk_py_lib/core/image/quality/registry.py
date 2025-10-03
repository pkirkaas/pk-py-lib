"""
src/pk_py_lib/core/image/quality/registry.py

Registry for managing pluggable ImageQualityEvaluator implementations.

This module provides a central registry to register, retrieve, and manage different image quality evaluators.
It uses a class-based singleton pattern with a class-level dictionary to store evaluator classes by key (e.g., 'brisque').
This allows runtime extensibility: new evaluators can be registered without modifying core code.

Key features:
- Automatic registration of the default 'brisque' evaluator on import.
- Thread-safe registration (using simple dict; for high concurrency, consider locks if needed).
- Logging of registration events for debugging.
- Raises ValueError for unknown keys in get_evaluator_class.

Usage
-----
# Register a new evaluator (e.g., in a plugin module)
from pk_py_lib.core.image.quality.registry import ImageQualityEvaluatorRegistry
from .my_evaluator import MyEvaluator

ImageQualityEvaluatorRegistry.register_evaluator("my_metric", MyEvaluator)

# Retrieve a class
try:
    cls = ImageQualityEvaluatorRegistry.get_evaluator_class("brisque")
    evaluator = cls()  # Instantiate
except ValueError as e:
    logger.error(f"Unknown evaluator: {e}")
"""

from typing import Type
import logging

from .base import ImageQualityEvaluator
from .brisque import BRISQUEImageQualityEvaluator
from pk_py_lib.core.logging import get_logger


class ImageQualityEvaluatorRegistry:
    """Singleton-like registry for ImageQualityEvaluator classes.
    
        This class manages a dictionary of registered evaluator classes, keyed by string identifiers.
        It acts as a central point for pluggable quality metrics, allowing the provider to select
        evaluators based on settings. The registry is class-level, so it's shared across instances
        (effectively singleton behavior without explicit instance management).
    
        All registered evaluators return normalized scores where higher values indicate higher image quality.
    
        Initialization:
        - On first access or import, automatically registers the default 'brisque' evaluator.
        - Additional evaluators can be registered via register_evaluator().
    
        Recent Improvements for 'brisque' Evaluator:
        - The BRISQUE evaluator now handles palette PNGs (e.g., with transparency) and narrow images (e.g., 1x400)
          gracefully via robust loading (PIL fallback for failed cv2.imread), pre-checks for extreme dimensions/aspect
          ratios (skips BRISQUE if width/height <2 or aspect >100, using Laplacian fallback), and padding for small
          images (<8px min dim). This prevents OpenCV resize assertion failures and ensures consistent normalized
          scores [0,1] higher-better, even for edge cases.
    
        Attributes
        ----------
        _evaluators : dict[str, Type[ImageQualityEvaluator]]
            Internal class-level dict mapping keys to evaluator classes. Populated on import.
    
        Raises
        ------
        ValueError
            If attempting to register a duplicate key or retrieve an unknown key.
    
        Examples
        --------
        # Basic retrieval (after auto-registration)
        cls = ImageQualityEvaluatorRegistry.get_evaluator_class("brisque")
        # cls == BRISQUEImageQualityEvaluator
    
        # Registering a custom evaluator
        class CustomEvaluator(ImageQualityEvaluator):
            # Implementation...
            pass
    
        ImageQualityEvaluatorRegistry.register_evaluator("custom", CustomEvaluator)
    
        # Error handling
        try:
            cls = ImageQualityEvaluatorRegistry.get_evaluator_class("unknown")
        except ValueError as e:
            # e.message: "Unknown image quality evaluator: unknown"
            pass
    
        Notes
        -----
        - Registration is permanent (no unregister); for dynamic unloading, extend if needed.
        - Logs INFO on successful registration, WARNING on duplicates.
        - Enum in settings schema should mirror registered keys for validation.
        - All evaluators normalize scores to higher-better convention for consistency.
        """

    # Class-level registry dict; shared across all instances (singleton pattern)
    _evaluators: dict[str, Type[ImageQualityEvaluator]] = {}

    # Logger for registry events
    _logger = get_logger(__name__)

    @classmethod
    def register_evaluator(cls, key: str, evaluator_class: Type[ImageQualityEvaluator]) -> None:
        """Register a new ImageQualityEvaluator class under the given key.

        This method adds the evaluator to the registry for later retrieval. It validates
        that the class is a subclass of ImageQualityEvaluator and that the key is unique.

        Parameters
        ----------
        key : str
            A unique string identifier for the evaluator (e.g., 'brisque', 'niqe').
            Should match enum values in settings schema for validation.
        evaluator_class : Type[ImageQualityEvaluator]
            The concrete evaluator class to register (must subclass ImageQualityEvaluator).

        Raises
        ------
        ValueError
            If the key is already registered or evaluator_class is not a valid subclass.
        TypeError
            If evaluator_class does not inherit from ImageQualityEvaluator.

        Examples
        --------
        # Registering the default (done automatically)
        cls.register_evaluator("brisque", BRISQUEImageQualityEvaluator)

        # Custom registration
        from .custom import CustomEvaluator
        cls.register_evaluator("custom", CustomEvaluator)  # Logs: "Registered evaluator 'custom'"

        # Duplicate key error
        try:
            cls.register_evaluator("brisque", AnotherEvaluator)
        except ValueError as e:
            # e.message: "Evaluator key 'brisque' already registered"
            pass
        """
        # Validate input: key must be non-empty string
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Evaluator key must be a non-empty string")
        key = key.strip().lower()  # Normalize to lowercase for consistency

        # Validate class inheritance
        if not issubclass(evaluator_class, ImageQualityEvaluator):
            raise TypeError(
                f"Evaluator class {evaluator_class.__name__} must subclass ImageQualityEvaluator"
            )

        # Check for duplicate
        if key in cls._evaluators:
            cls._logger.warning(f"Evaluator key '{key}' already registered; skipping")
            raise ValueError(f"Evaluator key '{key}' already registered")

        # Register the class
        cls._evaluators[key] = evaluator_class
        # Log successful registration
        cls._logger.info(f"Registered image quality evaluator '{key}': {evaluator_class.__name__}")

    @classmethod
    def get_evaluator_class(cls, key: str) -> Type[ImageQualityEvaluator]:
        """Retrieve the registered evaluator class by key.
        
        This method looks up the class in the registry and returns it for instantiation.
        Used by the provider to create active evaluators based on settings.
        The returned evaluator will provide normalized higher-better scores.
        
        Parameters
        ----------
        key : str
            The registered key (e.g., 'brisque').
        
        Returns
        -------
        Type[ImageQualityEvaluator]
            The evaluator class (e.g., BRISQUEImageQualityEvaluator).
        
        Raises
        ------
        ValueError
            If the key is not found in the registry.
        
        Examples
        --------
        # Get default
        cls = cls.get_evaluator_class("brisque")  # Returns BRISQUEImageQualityEvaluator
        
        # Instantiate
        evaluator = cls()  # No args for default
        
        # Unknown key
        try:
            cls.get_evaluator_class("unknown")
        except ValueError as e:
            # e.message: "Unknown image quality evaluator: unknown"
            # Fallback in provider: use 'brisque'
            pass
        """
        # Normalize key
        key = key.strip().lower()
        # Retrieve or raise
        if key not in cls._evaluators:
            cls._logger.warning(f"Unknown image quality evaluator key: '{key}'; available: {list(cls._evaluators.keys())}")
            raise ValueError(f"Unknown image quality evaluator: '{key}'")
        # Return the class
        return cls._evaluators[key]

    @classmethod
    def get_registered_keys(cls) -> list[str]:
        """Get a list of all currently registered evaluator keys.

        Useful for settings validation or UI enumeration.

        Returns
        -------
        list[str]
            Sorted list of keys (e.g., ['brisque']).

        Examples
        --------
        keys = ImageQualityEvaluatorRegistry.get_registered_keys()
        # keys == ['brisque']
        """
        return sorted(cls._evaluators.keys())


# Auto-register default evaluators on module import
# Inline comment: Ensures 'brisque' is always available.
ImageQualityEvaluatorRegistry.register_evaluator("brisque", BRISQUEImageQualityEvaluator)


__all__ = ["ImageQualityEvaluatorRegistry"]