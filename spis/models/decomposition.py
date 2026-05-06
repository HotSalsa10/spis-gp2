"""
spis/models/decomposition.py
-----------------------------
Item 7: additive seasonal decomposition wrapper.

Public API:
    decompose(series, period=365) -> dict
        Keys: 'trend', 'seasonal', 'residual', 'observed'
              Each is a numpy float64 array of the same length as the input.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose


def decompose(series: "pd.Series | np.ndarray", period: int = 365) -> dict:
    """
    Run additive seasonal decomposition on a daily time series.

    Args:
        series: 1-D numeric time series (pandas Series or array).
                Must have at least 2 * period observations.
        period: Seasonal period in samples.  Defaults to 365 (daily data).

    Returns:
        Dict with keys 'trend', 'seasonal', 'residual', 'observed'.
        Each value is a numpy float64 array of the same length as series.
        Edge NaNs in trend are extrapolated; remaining NaNs are zeroed.

    Raises:
        ValueError: if period < 2 or series is too short.
    """
    if period < 2:
        raise ValueError(f"period must be >= 2, got {period}")

    arr = np.asarray(series, dtype=float)
    min_obs = 2 * period
    if len(arr) < min_obs:
        raise ValueError(
            f"series length {len(arr)} is shorter than 2 * period ({min_obs})"
        )

    s = pd.Series(arr)
    if s.isna().any():
        s = s.interpolate(method="linear").ffill().bfill()

    result = seasonal_decompose(
        s, model="additive", period=period, extrapolate_trend="freq"
    )

    return {
        "trend":    np.nan_to_num(np.asarray(result.trend,    dtype=float)),
        "seasonal": np.nan_to_num(np.asarray(result.seasonal, dtype=float)),
        "residual": np.nan_to_num(np.asarray(result.resid,    dtype=float)),
        "observed": np.asarray(s, dtype=float),
    }
