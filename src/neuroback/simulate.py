"""Realistic synthetic EEG with a waxing-and-waning alpha rhythm, for demos and tests."""

from __future__ import annotations

import numpy as np
from scipy import signal


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """1/f noise via spectral shaping, unit variance."""
    spec = rng.normal(size=n // 2 + 1) + 1j * rng.normal(size=n // 2 + 1)
    f = np.arange(n // 2 + 1)
    f[0] = 1
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return x / x.std()


def alpha_eeg(
    duration_s: float,
    fs: float = 250.0,
    iaf: float = 10.0,
    alpha_uv: float = 12.0,
    background_uv: float = 8.0,
    bandwidth_hz: float = 1.0,
    eyes_closed: bool = True,
    line_noise_uv: float = 0.0,
    seed: int | None = None,
) -> np.ndarray:
    """Occipital-like EEG in microvolts.

    Alpha is a 2nd-order resonator (AR(2)) driven by white noise, so its amplitude and
    instantaneous frequency drift naturally from cycle to cycle like real alpha does.
    Eyes open scales alpha down by ~3x (alpha blocking).
    """
    rng = np.random.default_rng(seed)
    n = int(round(duration_s * fs))
    r = np.exp(-np.pi * bandwidth_hz / fs)
    a = [1, -2 * r * np.cos(2 * np.pi * iaf / fs), r**2]
    burn = int(2 * fs)
    alpha = signal.lfilter([1], a, rng.normal(size=n + burn))[burn:]
    alpha = alpha / alpha.std() * alpha_uv * (1.0 if eyes_closed else 0.33)
    x = alpha + background_uv * pink_noise(n, rng)
    if line_noise_uv:
        x += line_noise_uv * np.sin(2 * np.pi * 50 * np.arange(n) / fs)
    return x
