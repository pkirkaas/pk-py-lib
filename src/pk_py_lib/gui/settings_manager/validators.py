"""
src/pk_py_lib/gui/settings_manager/validators.py

Reusable validation helpers and Qt validators for the Settings Manager GUI.

- Profile name validation delegates to SettingsProfilesAPI.validate_name()
- Key validation delegates to SettingsProfilesAPI.validate_keys()

This module is designed for reuse in any PySide6-based application.

Note: Syntax validation was performed using Python's ast module per project rules.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

import inspect
import traceback

# Defensive import pattern for PySide6 to keep library importable headless
try:
    from PySide6.QtCore import QObject
    from PySide6.QtGui import QValidator
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover - headless/test environments
    PYSIDE_AVAILABLE = False

    class _Missing:  # minimal stub to raise clear message if used without PySide6
        def __getattr__(self, name):
            raise RuntimeError("PySide6 is required for GUI validators")

    QObject = QValidator = _Missing()  # type: ignore[assignment]


from ...api.settings import UnifiedSettingsAPI
from ...api import ApiResponse
from ...gui.utils.messages import gui_error_handler
from ...core.logging import logger
from ...core.logging.decorators import log_errors


@log_errors(include_args=True, include_traceback=True)
@gui_error_handler(component_name="validators")
def validate_profile_name_via_api(api: UnifiedSettingsAPI, name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a profile name by delegating to the API.

    Parameters
    ----------
    api : SettingsProfilesAPI
        API instance used for validation.
    name : str
        Proposed profile name.

    Returns
    -------
    Tuple[bool, Optional[str]]
        (True, None) if valid; (False, error_message) if invalid.
    """
    try:
        resp: ApiResponse[bool] = api.validate_name(name)
        if resp.success:
            return True, None
        return False, resp.error or "Invalid profile name"
    except Exception as e:
        logger.error(
            f"Error validating profile name via API: {type(e).__name__}: {e}",
            file_path=__file__,
            line_number=inspect.currentframe().f_lineno,
            func_name="validate_profile_name_via_api",
            parameters={"name": name},
            stack_trace=traceback.format_exc()
        )
        handle_gui_error(
            error=e,
            title="Validation API Error",
            component_name="validate_profile_name_via_api",
            name=name
        )
        return False, str(e)


@log_errors(include_args=True, include_traceback=True)
def validate_keys_via_api(api: UnifiedSettingsAPI, keys: Iterable[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate a collection of keys by delegating to the API.

    Parameters
    ----------
    api : SettingsProfilesAPI
        API instance used for validation.
    keys : Iterable[str]
        Keys to validate.

    Returns
    -------
    Tuple[bool, Optional[str]]
        (True, None) if valid; (False, error_message) if invalid.
    """
    try:
        resp: ApiResponse[bool] = api.validate_keys(keys)
        if resp.success:
            return True, None
        return False, resp.error or "Invalid keys"
    except Exception as e:
        logger.error(
            f"Error validating keys via API: {type(e).__name__}: {e}",
            file_path=__file__,
            line_number=inspect.currentframe().f_lineno,
            func_name="validate_keys_via_api",
            parameters={"keys": list(keys)},
            stack_trace=traceback.format_exc()
        )
        return False, str(e)


@log_errors(include_args=True, include_traceback=True)
class ProfileNameValidator(QValidator):  # type: ignore[misc]
    """
    Qt validator for profile names using UnifiedSettingsAPI.validate_profile_name().

    This validator performs live validation suitable for use with QLineEdit. It focuses
    on syntactic validity (allowed characters/length). Uniqueness is enforced when the
    name is actually saved through the API; callers should still handle AlreadyExistsError.

    Examples
    --------
    >>> api = UnifiedSettingsAPI()
    >>> v = ProfileNameValidator(api)
    >>> state, text, pos = v.validate("My Profile", 10)
    >>> state == QValidator.Acceptable
    True
    """

    def __init__(self, api: UnifiedSettingsAPI, parent: Optional[QObject] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for ProfileNameValidator")
        try:
            super().__init__(parent)
            self._api = api
            self._last_error: Optional[str] = None
        except Exception as e:
            logger.error(
                f"Error initializing ProfileNameValidator: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="ProfileNameValidator.__init__",
                parameters={"api": api},
                stack_trace=traceback.format_exc()
            )
            raise

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfileNameValidator")
    def validate(self, input: str, pos: int):  # type: ignore[override]
        """
        Validate the current text. Returns a tuple (State, text, pos).
        """
        try:
            text = (input or "").strip()
            if not text:
                self._last_error = "Name is required"
                return QValidator.Intermediate, input, pos

            ok, err = validate_profile_name_via_api(self._api, text)
            self._last_error = err
            # Treat API validation failure as Intermediate so the user can continue typing.
            return (QValidator.Acceptable if ok else QValidator.Intermediate), input, pos
        except Exception as e:
            logger.error(
                f"Error validating name: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="validate",
                parameters={"input": input, "pos": pos},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Name Validation Error",
                component_name="ProfileNameValidator.validate",
                input=input
            )
            self._last_error = str(e)
            return QValidator.Intermediate, input, pos  # Safe fallback

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="ProfileNameValidator")
    def last_error(self) -> Optional[str]:
        """
        Return the last error message set during validation, if any.
        """
        try:
            return self._last_error
        except Exception as e:
            logger.error(
                f"Error getting last error: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="last_error",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Last Error Access Error",
                component_name="ProfileNameValidator.last_error"
            )
            return None


@log_errors(include_args=True, include_traceback=True)
class SingleKeyValidator(QValidator):  # type: ignore[misc]
    """
    Qt validator for a single settings key using UnifiedSettingsAPI.validate_keys().

    The validator expects a single key string (no commas). It checks syntax against the
    canonical key regex via the API. Uniqueness within a profile is enforced when applying
    changes, not by this validator.

    Examples
    --------
    >>> api = UnifiedSettingsAPI()
    >>> v = SingleKeyValidator(api)
    >>> state, text, pos = v.validate("alg.threshold", 5)
    >>> state == QValidator.Acceptable
    True
    """

    def __init__(self, api: UnifiedSettingsAPI, parent: Optional[QObject] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for SingleKeyValidator")
        try:
            super().__init__(parent)
            self._api = api
            self._last_error: Optional[str] = None
        except Exception as e:
            logger.error(
                f"Error initializing SingleKeyValidator: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="SingleKeyValidator.__init__",
                parameters={"api": api},
                stack_trace=traceback.format_exc()
            )
            raise

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SingleKeyValidator")
    def validate(self, input: str, pos: int):  # type: ignore[override]
        try:
            text = (input or "").strip()
            if not text:
                self._last_error = "Key is required"
                return QValidator.Intermediate, input, pos
            # No commas or whitespace sets for a single key input
            if "," in text or " " in text:
                self._last_error = "Only one key allowed (no commas/spaces)"
                return QValidator.Invalid, input, pos

            ok, err = validate_keys_via_api(self._api, [text])
            self._last_error = err
            return (QValidator.Acceptable if ok else QValidator.Intermediate), input, pos
        except Exception as e:
            logger.error(
                f"Error validating key: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="validate",
                parameters={"input": input, "pos": pos},
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Key Validation Error",
                component_name="SingleKeyValidator.validate",
                input=input
            )
            self._last_error = str(e)
            return QValidator.Intermediate, input, pos  # Safe fallback

    @log_errors(include_args=True, include_traceback=True)
    @gui_error_handler(component_name="SingleKeyValidator")
    def last_error(self) -> Optional[str]:
        """
        Return the last error message set during validation, if any.
        """
        try:
            return self._last_error
        except Exception as e:
            logger.error(
                f"Error getting last error: {type(e).__name__}: {e}",
                file_path=__file__,
                line_number=inspect.currentframe().f_lineno,
                func_name="last_error",
                stack_trace=traceback.format_exc()
            )
            handle_gui_error(
                error=e,
                title="Last Error Access Error",
                component_name="SingleKeyValidator.last_error"
            )
            return None


__all__ = [
    "validate_profile_name_via_api",
    "validate_keys_via_api",
    "ProfileNameValidator",
    "SingleKeyValidator",
]
