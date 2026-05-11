
import numpy as np
import pandas as pd
import pytest

from spis.models.decomposition import decompose

# Minimum length: 2 full periods at daily frequency
_N = 730


def _sine_series(n: int = _N, period: int = 365) -> pd.Series:
    """Gentle upward trend + sinusoidal seasonality, no noise."""
    t = np.arange(n, dtype=float)
    trend = 0.01 * t
    seasonal = 5.0 * np.sin(2 * np.pi * t / period)
    return pd.Series(trend + seasonal)


def test_output_shape():
    """All output arrays must have the same length as the input series."""
    s = _sine_series()
    out = decompose(s, period=365)

    assert out["trend"].shape    == (len(s),)
    assert out["seasonal"].shape == (len(s),)
    assert out["residual"].shape == (len(s),)
    assert out["observed"].shape == (len(s),)


def test_decomposition_reconstructs_series():
    """trend + seasonal + residual must equal observed within floating-point tolerance."""
    s = _sine_series()
    out = decompose(s, period=365)

    reconstructed = out["trend"] + out["seasonal"] + out["residual"]
    np.testing.assert_allclose(reconstructed, out["observed"], atol=1e-6)


def test_period_too_small_raises():
    """period < 2 must raise ValueError."""
    s = _sine_series()
    with pytest.raises(ValueError, match="period"):
        decompose(s, period=1)


def test_series_too_short_raises():
    """Series shorter than 2 * period must raise ValueError."""
    short = pd.Series(np.ones(10))
    with pytest.raises(ValueError, match="shorter"):
        decompose(short, period=365)


def test_nan_handling_returns_finite_arrays():
    """Interior NaN values must not propagate -- all output arrays must be finite."""
    s = _sine_series().copy()
    s.iloc[10:15] = np.nan   # inject 5 NaN values mid-series

    out = decompose(s, period=365)

    assert np.isfinite(out["trend"]).all(),    "trend has non-finite values"
    assert np.isfinite(out["seasonal"]).all(), "seasonal has non-finite values"
    assert np.isfinite(out["residual"]).all(), "residual has non-finite values"
