"""
src/pk_py_lib/core/utils/thresholds.py
Conversion helpers for similarity thresholds between UI (0-100%) and internal (0.0-1.0).
"""

import math
from typing import Union

# UI percentage bounds
MIN_UI_PERCENT = 0.0
MAX_UI_PERCENT = 100.0

# Internal bounds (canonical)
MIN_INTERNAL = 0.0
MAX_INTERNAL = 1.0


def _clamp(value: float, lo: float, hi: float) -> float:
    """
    Clamp a floating-point value to the inclusive range [lo, hi].

    Parameters
    ----------
    value : float
        Value to clamp.
    lo : float
        Lower bound.
    hi : float
        Upper bound.

    Returns
    -------
    float
        The clamped value.
    """
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def ui_percent_to_internal(pct: Union[int, float]) -> float:
    """
    Convert a UI percentage (0-100) to the canonical internal representation (0.0-1.0).

    Behaviour
    - Accepts int or float.
    - Non-finite values (NaN, ±Inf) raise ValueError.
    - Values outside 0-100 are clamped to the valid range (to allow slight user rounding).
    - Returns a float in [0.0, 1.0].

    Parameters
    ----------
    pct : int | float
        Percentage value as presented to users (0-100).

    Returns
    -------
    float
        Internal representation in the range [0.0, 1.0].

    Raises
    ------
    TypeError
        If `pct` is not numeric.
    ValueError
        If `pct` is NaN or infinite.
    """
    if not isinstance(pct, (int, float)):
        raise TypeError("pct must be int or float")

    if math.isnan(pct) or math.isinf(pct):
        raise ValueError("pct must be a finite number")

    pct_clamped = _clamp(float(pct), MIN_UI_PERCENT, MAX_UI_PERCENT)
    return pct_clamped / 100.0


def internal_to_ui_percent(value: Union[int, float]) -> float:
    """
    Convert an internal similarity value (0.0-1.0) to a UI percentage (0-100).

    Behaviour
    - Accepts int or float.
    - Non-finite values (NaN, ±Inf) raise ValueError.
    - Values outside 0.0-1.0 are clamped to the valid range.
    - Returns a float percent in [0.0, 100.0].

    Parameters
    ----------
    value : int | float
        Internal similarity value.

    Returns
    -------
    float
        UI percentage (0-100).

    Raises
    ------
    TypeError
        If `value` is not numeric.
    ValueError
        If `value` is NaN or infinite.
    """
    if not isinstance(value, (int, float)):
        raise TypeError("value must be int or float")

    if math.isnan(value) or math.isinf(value):
        raise ValueError("value must be a finite number")

    internal = _clamp(float(value), MIN_INTERNAL, MAX_INTERNAL)
    return internal * 100.0

# End of file