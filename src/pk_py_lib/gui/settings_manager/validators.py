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


from ...api.settings_profiles import SettingsProfilesAPI
from ...api import ApiResponse


def validate_profile_name_via_api(api: SettingsProfilesAPI, name: str) -> Tuple[bool, Optional[str]]:
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
    resp: ApiResponse[bool] = api.validate_name(name)
    if resp.success:
        return True, None
    return False, resp.error or "Invalid profile name"


def validate_keys_via_api(api: SettingsProfilesAPI, keys: Iterable[str]) -> Tuple[bool, Optional[str]]:
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
    resp: ApiResponse[bool] = api.validate_keys(keys)
    if resp.success:
        return True, None
    return False, resp.error or "Invalid keys"


class ProfileNameValidator(QValidator):  # type: ignore[misc]
    """
    Qt validator for profile names using SettingsProfilesAPI.validate_name().

    This validator performs live validation suitable for use with QLineEdit. It focuses
    on syntactic validity (allowed characters/length). Uniqueness is enforced when the
    name is actually saved through the API; callers should still handle AlreadyExistsError.

    Examples
    --------
    >>> api = SettingsProfilesAPI()
    >>> v = ProfileNameValidator(api)
    >>> state, text, pos = v.validate("My Profile", 10)
    >>> state == QValidator.Acceptable
    True
    """

    def __init__(self, api: SettingsProfilesAPI, parent: Optional[QObject] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for ProfileNameValidator")
        super().__init__(parent)
        self._api = api
        self._last_error: Optional[str] = None

    def validate(self, input: str, pos: int):  # type: ignore[override]
        """
        Validate the current text. Returns a tuple (State, text, pos).
        """
        text = (input or "").strip()
        if not text:
            self._last_error = "Name is required"
            return QValidator.Intermediate, input, pos

        ok, err = validate_profile_name_via_api(self._api, text)
        self._last_error = err
        # Treat API validation failure as Intermediate so the user can continue typing.
        return (QValidator.Acceptable if ok else QValidator.Intermediate), input, pos

    def last_error(self) -> Optional[str]:
        """
        Return the last error message set during validation, if any.
        """
        return self._last_error


class SingleKeyValidator(QValidator):  # type: ignore[misc]
    """
    Qt validator for a single settings key using SettingsProfilesAPI.validate_keys().

    The validator expects a single key string (no commas). It checks syntax against the
    canonical key regex via the API. Uniqueness within a profile is enforced when applying
    changes, not by this validator.

    Examples
    --------
    >>> api = SettingsProfilesAPI()
    >>> v = SingleKeyValidator(api)
    >>> state, text, pos = v.validate("alg.threshold", 5)
    >>> state == QValidator.Acceptable
    True
    """

    def __init__(self, api: SettingsProfilesAPI, parent: Optional[QObject] = None):
        if not PYSIDE_AVAILABLE:  # pragma: no cover
            raise RuntimeError("PySide6 is required for SingleKeyValidator")
        super().__init__(parent)
        self._api = api
        self._last_error: Optional[str] = None

    def validate(self, input: str, pos: int):  # type: ignore[override]
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

    def last_error(self) -> Optional[str]:
        """
        Return the last error message set during validation, if any.
        """
        return self._last_error


__all__ = [
    "validate_profile_name_via_api",
    "validate_keys_via_api",
    "ProfileNameValidator",
    "SingleKeyValidator",
]