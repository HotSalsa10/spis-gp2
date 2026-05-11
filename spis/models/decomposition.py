"""Additive seasonal decomposition via statsmodels."""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose


def decompose(series: "pd.Series | np.ndarray", period: int = 365) -> dict:
    """Returns {trend, seasonal, residual, observed} as float arrays."""
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
