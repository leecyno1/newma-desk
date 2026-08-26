"""
Gaussian-window FFT filtering in the spirit of the Huatai report.

This module implements a simple frequency-domain Gaussian extractor for
targeted cycle lengths (e.g. 200 / 100 / 42 / 21 / 12 months).

The goal is *not* to exactly reproduce Huatai's proprietary code, but to
capture the same idea:

- Transform to frequency domain
- Apply a narrow Gaussian window around the target frequency
- Transform back to time domain and study the extracted component
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Dict, List

import numpy as np
import pandas as pd


@dataclass
class GaussianCycleConfig:
    """Configuration for Gaussian FFT-based cycle extraction."""

    target_period: float  # in same time units as dt (e.g. months or years)
    width_frac: float = 0.25  # relative width in frequency domain (sigma / f0)
    detrend: bool = True


def _gaussian_window(freqs: np.ndarray, f0: float, width_frac: float) -> np.ndarray:
    """
    Build a symmetric Gaussian window centered at f0 in the *positive* frequency domain.

    Parameters
    ----------
    freqs : np.ndarray
        Non-negative frequencies corresponding to rfft.
    f0 : float
        Target frequency (cycles per unit time).
    width_frac : float
        Relative width, sigma = width_frac * f0.
    """
    if f0 <= 0:
        raise ValueError("f0 must be positive")

    sigma = max(width_frac * f0, 1e-8)
    # rfft only has non-negative freqs, so one-sided Gaussian is enough here
    return np.exp(-0.5 * ((freqs - f0) / sigma) ** 2)


def gaussian_cycle_component(
    s: pd.Series,
    cfg: GaussianCycleConfig,
    dt: float = 1.0,
) -> pd.Series:
    """
    Extract a single cycle component from a time series using a Gaussian window in FFT domain.

    Parameters
    ----------
    s : pd.Series
        Input time series with a DatetimeIndex (assumed equally spaced).
    cfg : GaussianCycleConfig
        Target period and window settings.
    dt : float
        Sampling interval in time units (1.0 for monthly, 1.0 for yearly).
    """
    x = s.dropna().astype(float)
    if x.size < 16:
        # Too short to say anything meaningful
        return pd.Series(index=s.index, dtype="float64")

    # Detrend by removing mean (Huatai 的做法本质上也是在波动周围看周期，而非绝对水平)
    values = x.values
    if cfg.detrend:
        values = values - values.mean()

    n = len(values)
    # One-sided FFT
    from numpy.fft import rfft, irfft, rfftfreq

    freqs = rfftfreq(n, d=dt)  # cycles per unit time
    fft_vals = rfft(values)

    f0 = 1.0 / cfg.target_period
    win = _gaussian_window(freqs, f0=f0, width_frac=cfg.width_frac)

    filtered_fft = fft_vals * win
    filtered_values = irfft(filtered_fft, n=n)

    comp = pd.Series(filtered_values, index=x.index)
    # Reindex back to original index to keep alignment
    return comp.reindex(s.index)


def cycle_significance_metrics(
    s: pd.Series,
    cfg: GaussianCycleConfig,
    dt: float = 1.0,
) -> Dict[str, float]:
    """
    Compute simple significance metrics for a target cycle:
    - variance_share: Var(component) / Var(original)
    - snr_local: amplitude at f0 vs median amplitude in a neighbourhood
    """
    x = s.dropna().astype(float)
    if x.size < 16 or x.var() == 0:
        return {"variance_share": 0.0, "snr_local": 0.0}

    comp = gaussian_cycle_component(s, cfg, dt=dt).dropna()
    if comp.size < 16:
        return {"variance_share": 0.0, "snr_local": 0.0}

    var_share = float(comp.var() / x.var())

    # Local SNR in frequency domain
    from numpy.fft import rfft, rfftfreq

    values = x.values
    if cfg.detrend:
        values = values - values.mean()
    n = len(values)
    freqs = rfftfreq(n, d=dt)
    fft_vals = rfft(values)
    amp = np.abs(fft_vals)

    f0 = 1.0 / cfg.target_period
    idx0 = int(np.argmin(np.abs(freqs - f0)))
    amp0 = amp[idx0]

    # neighbourhood: +/- 20% around f0, excluding the centre bin
    band = (freqs >= 0.8 * f0) & (freqs <= 1.2 * f0)
    band[idx0] = False
    local_bg = np.median(amp[band]) if band.any() else np.median(amp[1:])
    snr_local = float(amp0 / local_bg) if local_bg > 0 else 0.0

    return {
        "variance_share": var_share,
        "snr_local": snr_local,
    }


def scan_cycles_for_series(
    s: pd.Series,
    target_periods: List[float],
    dt: float = 1.0,
    width_frac: float = 0.25,
) -> pd.DataFrame:
    """
    Convenience wrapper: scan a list of target periods for one series.
    Returns a DataFrame with index=periods, columns=[variance_share, snr_local].
    """
    records = []
    for P in target_periods:
        cfg = GaussianCycleConfig(target_period=P, width_frac=width_frac)
        metrics = cycle_significance_metrics(s, cfg, dt=dt)
        records.append({"period": P, **metrics})
    df = pd.DataFrame.from_records(records).set_index("period")
    return df

