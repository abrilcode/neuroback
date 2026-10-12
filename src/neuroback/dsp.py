"""Signal-processing helpers: spectra, individual alpha frequency, band power, offline phase."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

ALPHA_SEARCH_BAND = (7.0, 14.0)


@dataclass(frozen=True)
class AlphaPeak:
    """Individual alpha frequency (IAF) estimate."""

    freq: float  # Hz
    snr_db: float  # peak height above the 1/f fit, in dB
    found: bool  # False when no peak rises above the 1/f background


def welch_psd(x: np.ndarray, fs: float, seg_s: float = 4.0, resolution_hz: float = 0.05):
    """Welch PSD with long segments and zero-padding for a fine frequency grid.

    The 2023 version used 0.75 s segments, which gives 1.34 Hz bins: the IAF could
    only be 8.02, 9.36, 10.70 or 12.03 Hz. Four-second segments plus zero-padding
    resolve the peak to ~0.05 Hz.
    """
    x = np.asarray(x, dtype=float)
    nperseg = int(min(len(x), round(seg_s * fs)))
    nfft = max(nperseg, int(round(fs / resolution_hz)))
    return signal.welch(
        x, fs=fs, window="hann", nperseg=nperseg, noverlap=nperseg // 2, nfft=nfft, detrend="linear"
    )


def individual_alpha_frequency(x: np.ndarray, fs: float, band=ALPHA_SEARCH_BAND) -> AlphaPeak:
    """Peak of the alpha band after removing the aperiodic (1/f) component.

    Fits a line to log-power vs log-frequency over 2-35 Hz excluding the search band,
    then takes the largest residual inside the band.
    """
    f, p = welch_psd(x, fs)
    fit_mask = (f >= 2) & (f <= 35) & ((f < band[0]) | (f > band[1]))
    slope, intercept = np.polyfit(np.log10(f[fit_mask]), np.log10(p[fit_mask]), 1)
    in_band = (f >= band[0]) & (f <= band[1])
    resid = np.log10(p[in_band]) - (slope * np.log10(f[in_band]) + intercept)
    i = int(np.argmax(resid))
    snr_db = float(10 * resid[i])
    return AlphaPeak(freq=float(f[in_band][i]), snr_db=snr_db, found=snr_db > 1.0)


def band_power(x: np.ndarray, fs: float, band: tuple[float, float]) -> float:
    """Absolute power in ``band`` (integrated Welch PSD, 2 s segments)."""
    f, p = welch_psd(x, fs, seg_s=min(2.0, len(x) / fs), resolution_hz=0.25)
    m = (f >= band[0]) & (f <= band[1])
    return float(np.trapezoid(p[m], f[m])) if hasattr(np, "trapezoid") else float(np.trapz(p[m], f[m]))


def offline_phase(x: np.ndarray, fs: float, f0: float, half_bw: float = 2.0):
    """Non-causal ("ground truth") phase and amplitude of the oscillation near ``f0``.

    Zero-phase Butterworth band-pass + Hilbert transform over the whole recording.
    Cosine convention: phase 0 = peak, +-pi = trough, -pi/2 = rising zero-crossing.
    Only usable offline; it needs future samples.
    """
    sos = signal.butter(2, [f0 - half_bw, f0 + half_bw], btype="band", fs=fs, output="sos")
    y = signal.sosfiltfilt(sos, np.asarray(x, dtype=float))
    a = signal.hilbert(y)
    return np.angle(a), np.abs(a), y


def resample(x: np.ndarray, fs_in: float, fs_out: float) -> np.ndarray:
    """Polyphase resampling between integer-ratio rates (e.g. 160 Hz -> 250 Hz)."""
    from fractions import Fraction

    r = Fraction(fs_out / fs_in).limit_denominator(1000)
    return signal.resample_poly(np.asarray(x, dtype=float), r.numerator, r.denominator)
